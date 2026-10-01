import os
from datetime import date
from decimal import Decimal

import pandas as pd
import psycopg
import pyarrow.parquet as pq

from src.clasificar import clasificar_dia, comprobar_dia
from src.columnas import COLUMNAS
from src.leer_datos import preparar

TAMANO_BLOQUE = 100_000


def conectar() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        dbname=os.environ.get("POSTGRES_DB", "movimientos"),
        user=os.environ.get("POSTGRES_USER", "tyba"),
        password=os.environ.get("POSTGRES_PASSWORD", "tyba"),
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


def corte_ya_aplicado(cur: psycopg.Cursor, nombre_corte: str) -> date | None:
    """Devuelve la fecha si ese corte ya se cargó. Si no, devuelve None."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS corte_aplicado (
            nombre text PRIMARY KEY,
            fecha_corte date NOT NULL
        )
        """
    )
    cur.execute(
        "SELECT fecha_corte FROM corte_aplicado WHERE nombre = %s",
        (nombre_corte,),
    )
    fila = cur.fetchone()
    if fila is None:
        return None
    return fila[0]


def cargar_dia(ruta: str, nombre_corte: str, fecha_corte: date) -> None:
    """Carga un Parquet, revisa duplicados y clasifica el día.

    Si el corte ya se aplicó, no lo vuelve a cargar. Si algo falla, se deshace
    la transacción. El historial no se vacía.
    """
    with conectar() as conn:
        with conn.cursor() as cur:
            fecha_previa = corte_ya_aplicado(cur, nombre_corte)
            if fecha_previa is not None:
                print(
                    f"El corte {nombre_corte} ya fue aplicado el {fecha_previa}. "
                    "No se vuelve a cargar."
                )
                return

            try:
                archivo = pq.ParquetFile(ruta)
            except FileNotFoundError:
                print(f"Revisar ruta del archivo: {ruta}")
                raise

            filas_archivo = archivo.metadata.num_rows
            print(f"Leído: {ruta}")
            print(f"Filas: {filas_archivo}")

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
            if copiadas != filas_archivo or en_tabla != filas_archivo:
                raise RuntimeError(
                    f"corte_dia quedó con {en_tabla} filas y el archivo tiene {filas_archivo}"
                )

            revisar_duplicados(cur)
            clasificar_dia(cur, fecha_corte)
            comprobar_dia(cur, fecha_corte)
            cur.execute(
                """
                INSERT INTO corte_aplicado (nombre, fecha_corte)
                VALUES (%s, %s)
                """,
                (nombre_corte, fecha_corte),
            )

            cur.execute("SELECT count(*) FROM movimiento_vigente")
            vigente = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM movimiento_historial")
            historial = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM corte_dia")
            corte = cur.fetchone()[0]

    print(f"Copiadas: {copiadas} | fecha_corte: {fecha_corte}")
    print(f"vigente: {vigente} | historial: {historial} | corte_dia: {corte}")
