from datetime import date

import psycopg

from src.columnas import COLUMNAS, misma_llave


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
