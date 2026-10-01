import os
from datetime import date
from decimal import Decimal

import pandas as pd
import psycopg

from src.columnas import COLUMNAS


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


def vaciar_corte(cur: psycopg.Cursor) -> None:
    cur.execute("TRUNCATE corte_dia")


def contar_corte(cur: psycopg.Cursor) -> int:
    cur.execute("SELECT count(*) FROM corte_dia")
    return cur.fetchone()[0]


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


def registrar_corte(cur: psycopg.Cursor, nombre_corte: str, fecha_corte: date) -> None:
    cur.execute(
        """
        INSERT INTO corte_aplicado (nombre, fecha_corte)
        VALUES (%s, %s)
        """,
        (nombre_corte, fecha_corte),
    )


def contar_tablas(cur: psycopg.Cursor) -> tuple[int, int, int]:
    cur.execute("SELECT count(*) FROM movimiento_vigente")
    vigente = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM movimiento_historial")
    historial = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM corte_dia")
    corte = cur.fetchone()[0]
    return vigente, historial, corte
