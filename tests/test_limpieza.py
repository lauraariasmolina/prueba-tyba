from datetime import date

import pandas as pd

from src.limpieza import convertir_fecha, normalizar_fund, preparar, traducir_type


def test_fecha_iso_se_lee_como_anio_mes_dia():
    assert convertir_fecha("2024-10-23") == date(2024, 10, 23)


def test_fecha_con_barras_se_lee_como_dia_mes_anio():
    assert convertir_fecha("01/10/2024") == date(2024, 10, 1)


def test_fecha_vacia_o_invalida_queda_en_nulo():
    assert convertir_fecha(None) is None
    assert convertir_fecha("   ") is None
    assert convertir_fecha("no-es-fecha") is None


def test_type_de_entrada_y_salida_queda_en_in_y_out():
    assert traducir_type("entrada") == "IN"
    assert traducir_type("ENTRADA") == "IN"
    assert traducir_type("in") == "IN"
    assert traducir_type("salida") == "OUT"
    assert traducir_type("Salida") == "OUT"
    assert traducir_type("OUT") == "OUT"


def test_type_desconocido_queda_en_nulo():
    assert traducir_type(None) is None
    assert traducir_type("otro") is None


def test_fund_ignora_mayusculas_y_espacios_de_mas():
    assert normalizar_fund("  Renta Variable  ") == "Renta Variable"
    assert normalizar_fund("RENTA VARIABLE") == "Renta Variable"
    assert normalizar_fund("Mercado  Monetario") == "Mercado Monetario"
    assert normalizar_fund("balanceado") == "Balanceado"


def test_fund_fuera_del_catalogo_queda_en_nulo():
    assert normalizar_fund(None) is None
    assert normalizar_fund("   ") is None
    assert normalizar_fund("fondo inventado") is None


def test_preparar_cuenta_lo_que_no_se_pudo_limpiar():
    df = pd.DataFrame(
        [
            {
                "id_cliente": "CLI000001",
                "date": "01/10/2024",
                "product": "Acciones",
                "type": "Entrada",
                "fund": "  crecimiento",
                "commercial_name": "BBVA",
                "amount": 10.5,
                "description": "Compra",
            },
            {
                "id_cliente": None,
                "date": "no-es-fecha",
                "product": "Acciones",
                "type": "otro",
                "fund": "fondo inventado",
                "commercial_name": None,
                "amount": "no-es-monto",
                "description": None,
            },
            {
                "id_cliente": "CLI000002",
                "date": None,
                "product": "Bonos",
                "type": None,
                "fund": None,
                "commercial_name": "Skandia",
                "amount": None,
                "description": "Retiro",
            },
        ]
    )

    limpio, control = preparar(df, "T")

    assert list(limpio.columns) == list(df.columns)
    assert limpio.loc[0, "date"] == date(2024, 10, 1)
    assert limpio.loc[0, "type"] == "IN"
    assert limpio.loc[0, "fund"] == "Crecimiento"
    assert control["corte"] == "T"
    assert control["filas"] == 3
    assert control["fechas_invalidas"] == 1
    assert control["type_sin_mapa"] == 1
    assert control["fondos_sin_mapa"] == 1
    assert control["montos_invalidos"] == 1
    assert control["ids_nulos"] == 1
