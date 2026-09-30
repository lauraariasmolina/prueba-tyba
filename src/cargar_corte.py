from datetime import date
from decimal import Decimal

import pandas as pd
import psycopg
import pyarrow.parquet as pq

from src.leer_datos import preparar

TAMANO_BLOQUE = 100_000
COLUMNAS = (
    "id_cliente",
    "date",
    "product",
    "type",
    "fund",
    "commercial_name",
    "amount",
    "description",
)


def conectar() -> psycopg.Connection:
    return psycopg.connect(
        host="localhost",
        port=5433,
        dbname="movimientos",
        user="tyba",
        password="tyba",
    )


def valor_sql(valor: object) -> str | date | Decimal | None:
    """Deja el valor listo para COPY. Un vacío entra como NULL."""
    if valor is None or pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if isinstance(valor, float):
        return Decimal(str(valor))
    return valor


def copiar_bloque(cur: psycopg.Cursor, df: pd.DataFrame) -> None:
    columnas = ", ".join(COLUMNAS)
    with cur.copy(f"COPY corte_dia ({columnas}) FROM STDIN") as copia:
        for fila in df.loc[:, COLUMNAS].itertuples(index=False, name=None):
            copia.write_row(tuple(valor_sql(valor) for valor in fila))


def revisar_duplicados(cur: psycopg.Cursor) -> None:
    """Si una fila completa está repetida, imprime esas llaves y corta la carga."""
    columnas = ", ".join(COLUMNAS)
    cur.execute(
        f"""
        SELECT {columnas}, count(*) AS copias
        FROM corte_dia
        GROUP BY {columnas}
        HAVING count(*) > 1
        """
    )
    repetidas = cur.fetchall()
    if not repetidas:
        print("Duplicados en el día: 0")
        return

    print(f"Duplicados en el día: {len(repetidas)}")
    for fila in repetidas:
        print(fila)
    raise RuntimeError("El corte trae filas idénticas. La carga se deshace.")


def cargar_dia(ruta: str, nombre_corte: str) -> None:
    """Vacía corte_dia, lee un Parquet por bloques y copia cada bloque.

    Si el día trae una fila completa repetida, la transacción se deshace.
    Vigente e historial no se modifican.
    """
    try:
        archivo = pq.ParquetFile(ruta)
    except FileNotFoundError:
        print(f"Revisar ruta del archivo: {ruta}")
        raise

    filas_archivo = archivo.metadata.num_rows
    print(f"Leído: {ruta}")
    print(f"Filas: {filas_archivo}")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE corte_dia")

            copiadas = 0
            for bloque in archivo.iter_batches(batch_size=TAMANO_BLOQUE):
                df, control = preparar(bloque.to_pandas(), nombre_corte)
                copiar_bloque(cur, df)
                copiadas += control["filas"]
                print(
                    f"Control {control['corte']}: "
                    f"filas={control['filas']} columnas={control['columnas']} "
                    f"fechas_invalidas={control['fechas_invalidas']} "
                    f"type_sin_mapa={control['type_sin_mapa']} "
                    f"montos_invalidos={control['montos_invalidos']} "
                    f"ids_nulos={control['ids_nulos']}"
                )

            cur.execute("SELECT count(*) FROM corte_dia")
            en_tabla = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM movimiento_vigente")
            vigente = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM movimiento_historial")
            historial = cur.fetchone()[0]

            if copiadas != filas_archivo or en_tabla != filas_archivo:
                raise RuntimeError(
                    f"corte_dia quedó con {en_tabla} filas y el archivo tiene {filas_archivo}"
                )

            revisar_duplicados(cur)

    print(f"Copiadas: {copiadas} | corte_dia: {en_tabla}")
    print(f"vigente: {vigente} | historial: {historial}")
