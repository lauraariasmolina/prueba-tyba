from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from src.base_datos import conectar
from src.clasificar import clasificar_dia, comprobar_dia

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = "prueba_clasificar"
AYER = date(2026, 9, 30)
HOY = date(2026, 10, 1)
MANANA = date(2026, 10, 2)

# La misma fila en ayer y en hoy.
SIN_CAMBIOS = (
    "CLI000001",
    date(2024, 10, 2),
    "Divisas",
    "IN",
    "Internacional",
    "Scotiabank",
    Decimal("41924954.04"),
    "Reinversión automática",
)
# Ayer trae la compra. Hoy no. Sale de vigente.
COMPRA = (
    "CLI000863",
    date(2024, 9, 23),
    "Acciones",
    "IN",
    "Renta Variable",
    "Valores Bancolombia",
    Decimal("42773985.27"),
    "Compra de activo",
)
# Hoy trae la venta, con otro monto y otra descripción. Entra como movimiento nuevo.
VENTA = (
    "CLI000863",
    date(2024, 9, 23),
    "Acciones",
    "IN",
    "Renta Variable",
    "Valores Bancolombia",
    Decimal("12448886.11"),
    "Venta de activo",
)
# Los nulos también forman parte de la fila. Si coinciden, el movimiento sigue.
CON_NULOS = (
    "CLI000003",
    date(2024, 10, 2),
    "Bonos",
    "OUT",
    "Renta Fija",
    None,
    None,
    None,
)


def sentencias_del_esquema() -> list[str]:
    texto = (RAIZ / "sql" / "01_esquema.sql").read_text(encoding="utf-8")
    return [parte.strip() for parte in texto.split(";") if parte.strip()]


def insertar_vigente(
    cur: psycopg.Cursor,
    fila: tuple,
    fecha_corte: date,
    primera_vista: date | None = None,
) -> None:
    if primera_vista is None:
        primera_vista = fecha_corte
    cur.execute(
        """
        INSERT INTO movimiento_vigente (
            id_cliente, date, product, type, fund,
            commercial_name, amount, description,
            situacion, fecha_corte, primera_vista
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'nuevo', %s, %s)
        """,
        (*fila, fecha_corte, primera_vista),
    )


def insertar_corte(cur: psycopg.Cursor, fila: tuple) -> None:
    cur.execute(
        """
        INSERT INTO corte_dia (
            id_cliente, date, product, type, fund,
            commercial_name, amount, description
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        fila,
    )


def insertar_historial(
    cur: psycopg.Cursor,
    fila: tuple,
    fecha_corte: date,
    primera_vista: date | None = None,
) -> None:
    if primera_vista is None:
        primera_vista = fecha_corte
    cur.execute(
        """
        INSERT INTO movimiento_historial (
            id_cliente, date, product, type, fund,
            commercial_name, amount, description,
            situacion, fecha_corte, primera_vista
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'eliminado', %s, %s)
        """,
        (*fila, fecha_corte, primera_vista),
    )


def situacion_de(cur: psycopg.Cursor, tabla: str, fila: tuple) -> tuple | None:
    cur.execute(
        f"""
        SELECT situacion, fecha_corte, primera_vista
        FROM {tabla}
        WHERE id_cliente = %s
          AND date = %s
          AND product = %s
          AND type = %s
          AND fund = %s
          AND commercial_name IS NOT DISTINCT FROM %s
          AND amount IS NOT DISTINCT FROM %s
          AND description IS NOT DISTINCT FROM %s
        """,
        fila,
    )
    return cur.fetchone()


def preparar_dia(cur: psycopg.Cursor) -> None:
    """Ayer quedan tres movimientos. Hoy repite dos y trae la venta en lugar de la compra."""
    for fila in (SIN_CAMBIOS, COMPRA, CON_NULOS):
        insertar_vigente(cur, fila, AYER)
    for fila in (SIN_CAMBIOS, VENTA, CON_NULOS):
        insertar_corte(cur, fila)


@pytest.fixture
def cur():
    try:
        conn = conectar()
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL no está disponible: {error}")

    conn.autocommit = True
    conn.execute(f"DROP SCHEMA IF EXISTS {ESQUEMA} CASCADE")
    conn.autocommit = False
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE SCHEMA {ESQUEMA}")
        cursor.execute(f"SET LOCAL search_path TO {ESQUEMA}")
        for sentencia in sentencias_del_esquema():
            cursor.execute(sentencia)
        preparar_dia(cursor)
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def test_sin_cambios_se_queda_en_vigente_con_la_fecha_de_hoy(cur, capsys):
    clasificar_dia(cur, HOY)

    assert situacion_de(cur, "movimiento_vigente", SIN_CAMBIOS) == ("sin_cambios", HOY, AYER)
    assert situacion_de(cur, "movimiento_historial", SIN_CAMBIOS) is None
    assert situacion_de(cur, "movimiento_vigente", CON_NULOS) == ("sin_cambios", HOY, AYER)
    assert situacion_de(cur, "movimiento_historial", CON_NULOS) is None
    assert "sin_cambios: 2" in capsys.readouterr().out


def test_eliminados_salen_de_vigente_y_quedan_en_el_historial(cur, capsys):
    clasificar_dia(cur, HOY)

    assert situacion_de(cur, "movimiento_vigente", COMPRA) is None
    assert situacion_de(cur, "movimiento_historial", COMPRA) == ("eliminado", HOY, AYER)
    assert "eliminados: 1" in capsys.readouterr().out


def test_nuevos_entran_a_vigente(cur, capsys):
    clasificar_dia(cur, HOY)

    assert situacion_de(cur, "movimiento_vigente", VENTA) == ("nuevo", HOY, HOY)
    assert situacion_de(cur, "movimiento_historial", VENTA) is None
    assert "nuevos: 1" in capsys.readouterr().out


def test_un_cambio_de_monto_no_pisa_la_fila_anterior(cur):
    clasificar_dia(cur, HOY)

    assert situacion_de(cur, "movimiento_historial", COMPRA) == ("eliminado", HOY, AYER)
    assert situacion_de(cur, "movimiento_vigente", VENTA) == ("nuevo", HOY, HOY)
    cur.execute("SELECT count(*) FROM corte_dia")
    assert cur.fetchone()[0] == 0


def test_el_cierre_corta_si_la_misma_fila_esta_en_vigente_y_en_historial(cur):
    insertar_historial(cur, SIN_CAMBIOS, HOY)

    with pytest.raises(RuntimeError, match="Hay 1 llaves"):
        comprobar_dia(cur, HOY)


def test_una_fila_eliminada_puede_volver_identica_al_dia_siguiente(cur):
    clasificar_dia(cur, HOY)
    insertar_corte(cur, COMPRA)

    clasificar_dia(cur, MANANA)
    comprobar_dia(cur, MANANA)

    assert situacion_de(cur, "movimiento_vigente", COMPRA) == ("nuevo", MANANA, MANANA)
    assert situacion_de(cur, "movimiento_historial", COMPRA) == ("eliminado", HOY, AYER)
