from datetime import date
from decimal import Decimal

import pandas as pd

from src.base_datos import valor_sql


def test_un_vacio_entra_como_nulo():
    assert valor_sql(None) is None
    assert valor_sql(float("nan")) is None


def test_una_fecha_de_pandas_queda_en_date():
    assert valor_sql(pd.Timestamp("2024-10-01")) == date(2024, 10, 1)


def test_un_monto_float_queda_en_decimal():
    assert valor_sql(1490831.17) == Decimal("1490831.17")


def test_un_texto_se_conserva():
    assert valor_sql("Compra de activo") == "Compra de activo"
