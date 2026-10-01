from datetime import date

import pytest

from src.main import leer_fecha_corte


def test_la_fecha_de_corte_usa_anio_mes_dia():
    assert leer_fecha_corte("2024-09-30") == date(2024, 9, 30)


def test_una_fecha_de_corte_invalida_detiene_el_proceso():
    with pytest.raises(SystemExit):
        leer_fecha_corte("30/09/2024")
