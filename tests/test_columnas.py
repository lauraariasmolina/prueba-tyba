from src.columnas import misma_llave


def test_las_columnas_obligatorias_se_comparan_con_igual():
    condicion = misma_llave("vigente", "salieron")

    assert "vigente.id_cliente = salieron.id_cliente" in condicion
    assert "vigente.date = salieron.date" in condicion
    assert "vigente.product = salieron.product" in condicion
    assert "vigente.type = salieron.type" in condicion
    assert "vigente.fund = salieron.fund" in condicion


def test_los_nulos_cuentan_como_el_mismo_valor():
    condicion = misma_llave("vigente", "salieron")

    assert "vigente.commercial_name IS NOT DISTINCT FROM salieron.commercial_name" in condicion
    assert "vigente.amount IS NOT DISTINCT FROM salieron.amount" in condicion
    assert "vigente.description IS NOT DISTINCT FROM salieron.description" in condicion
