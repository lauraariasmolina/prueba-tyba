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
COLUMNAS_CON_NULO = ("commercial_name", "amount", "description")


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


def misma_llave(izquierda: str, derecha: str) -> str:
    """Dos filas son la misma si las ocho columnas coinciden, nulos incluidos."""
    partes = []
    for columna in COLUMNAS:
        if columna in COLUMNAS_CON_NULO:
            partes.append(
                f"{izquierda}.{columna} IS NOT DISTINCT FROM {derecha}.{columna}"
            )
        else:
            partes.append(f"{izquierda}.{columna} = {derecha}.{columna}")
    return " AND ".join(partes)


def pasar_eliminados(cur: psycopg.Cursor, fecha_corte: date) -> int:
    """Lo que estaba vigente y no viene hoy pasa al historial y sale de vigente."""
    columnas = ", ".join(COLUMNAS)
    cur.execute(
        f"""
        INSERT INTO movimiento_historial ({columnas}, situacion, fecha_corte)
        SELECT {columnas}, 'eliminado', %s
        FROM (
            SELECT {columnas} FROM movimiento_vigente
            EXCEPT
            SELECT {columnas} FROM corte_dia
        ) AS salieron
        """,
        (fecha_corte,),
    )
    eliminados = cur.rowcount
    cur.execute(
        f"""
        DELETE FROM movimiento_vigente AS vigente
        USING (
            SELECT {columnas} FROM movimiento_vigente
            EXCEPT
            SELECT {columnas} FROM corte_dia
        ) AS salieron
        WHERE {misma_llave("vigente", "salieron")}
        """
    )
    return eliminados


def marcar_sin_cambios(cur: psycopg.Cursor, fecha_corte: date) -> int:
    """Lo que está en vigente y en el día de hoy se queda, con sin_cambios."""
    cur.execute(
        f"""
        UPDATE movimiento_vigente AS vigente
        SET situacion = 'sin_cambios',
            fecha_corte = %s
        FROM corte_dia AS hoy
        WHERE {misma_llave("vigente", "hoy")}
        """,
        (fecha_corte,),
    )
    return cur.rowcount


def insertar_nuevos(cur: psycopg.Cursor, fecha_corte: date) -> int:
    """Lo que solo viene hoy entra a vigente como nuevo."""
    columnas = ", ".join(COLUMNAS)
    cur.execute(
        f"""
        INSERT INTO movimiento_vigente ({columnas}, situacion, fecha_corte)
        SELECT {columnas}, 'nuevo', %s
        FROM (
            SELECT {columnas} FROM corte_dia
            EXCEPT
            SELECT {columnas} FROM movimiento_vigente
        ) AS entraron
        """,
        (fecha_corte,),
    )
    return cur.rowcount


def clasificar_dia(cur: psycopg.Cursor, fecha_corte: date) -> None:
    """Aplica las tres reglas y, si terminan bien, vacía corte_dia."""
    eliminados = pasar_eliminados(cur, fecha_corte)
    sin_cambios = marcar_sin_cambios(cur, fecha_corte)
    nuevos = insertar_nuevos(cur, fecha_corte)
    cur.execute("TRUNCATE corte_dia")
    print(
        f"eliminados: {eliminados} | sin_cambios: {sin_cambios} | nuevos: {nuevos}"
    )


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


def comprobar_dia(cur: psycopg.Cursor, fecha_corte: date) -> None:
    """Cuenta el cierre del día y corta si una llave está en vigente y en historial."""
    cur.execute(
        """
        SELECT
            count(*) FILTER (WHERE situacion = 'nuevo'),
            count(*) FILTER (WHERE situacion = 'sin_cambios')
        FROM movimiento_vigente
        WHERE fecha_corte = %s
        """,
        (fecha_corte,),
    )
    nuevos, sin_cambios = cur.fetchone()

    cur.execute(
        """
        SELECT count(*)
        FROM movimiento_historial
        WHERE situacion = 'eliminado'
          AND fecha_corte = %s
        """,
        (fecha_corte,),
    )
    eliminados = cur.fetchone()[0]

    columnas = ", ".join(COLUMNAS)
    cur.execute(
        f"""
        SELECT count(*)
        FROM (
            SELECT {columnas} FROM movimiento_vigente
            INTERSECT
            SELECT {columnas} FROM movimiento_historial
        ) AS repetidas
        """
    )
    repetidas = cur.fetchone()[0]

    print(
        f"Cierre {fecha_corte}: "
        f"nuevo={nuevos} sin_cambios={sin_cambios} eliminado={eliminados}"
    )
    print(f"Llaves en vigente y en historial: {repetidas}")
    if repetidas != 0:
        raise RuntimeError(
            f"Hay {repetidas} llaves en vigente y en historial. El día se deshace."
        )


def cargar_dia(ruta: str, nombre_corte: str, fecha_corte: date) -> None:
    """Carga un Parquet, revisa duplicados y clasifica el día.

    Si algo falla, se deshace la transacción. El historial no se vacía.
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
            if copiadas != filas_archivo or en_tabla != filas_archivo:
                raise RuntimeError(
                    f"corte_dia quedó con {en_tabla} filas y el archivo tiene {filas_archivo}"
                )

            revisar_duplicados(cur)
            clasificar_dia(cur, fecha_corte)
            comprobar_dia(cur, fecha_corte)

            cur.execute("SELECT count(*) FROM movimiento_vigente")
            vigente = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM movimiento_historial")
            historial = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM corte_dia")
            corte = cur.fetchone()[0]

    print(f"Copiadas: {copiadas} | fecha_corte: {fecha_corte}")
    print(f"vigente: {vigente} | historial: {historial} | corte_dia: {corte}")
