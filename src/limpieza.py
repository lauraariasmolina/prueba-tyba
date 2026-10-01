import re
from datetime import date, datetime

import pandas as pd

MAPA_TYPE = {
    "entrada": "IN",
    "salida": "OUT",
    "in": "IN",
    "out": "OUT",
}

MAPA_FUND = {
    "balanceado": "Balanceado",
    "conservador": "Conservador",
    "crecimiento": "Crecimiento",
    "internacional": "Internacional",
    "mercado monetario": "Mercado Monetario",
    "renta fija": "Renta Fija",
    "renta variable": "Renta Variable",
}


def convertir_fecha(valor: object) -> date | None:
    """Pasa un date de texto a fecha.

    Prueba un formato y, si no entra, prueba el siguiente.
    2024-10-23 se lee como año-mes-día.
    01/10/2024 se lee como día/mes/año (1 de octubre), porque el negocio es Colombia.
    """
    if valor is None:
        return None

    texto = str(valor).strip()
    if texto == "" or texto.lower() in {"nat", "none", "nan", "<na>"}:
        return None

    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def convertir_fechas(serie: pd.Series) -> pd.Series:
    """Aplica convertir_fecha a cada valor de la columna."""
    return serie.map(convertir_fecha)


def traducir_type(valor: object) -> str | None:
    """Convierte un type a IN/OUT.

    'salida' -> OUT
    'entrada' -> IN
    'salida-entrada' o 'salida / entrada' -> OUT-IN
    Si aparece una palabra que no está en MAPA_TYPE, devuelve nulo.
    """
    if valor is None:
        return None

    texto = str(valor).strip()
    if texto == "" or texto.lower() in {"nat", "none", "nan", "<na>"}:
        return None

    texto = texto.lower()
    texto = texto.replace("/", "-")
    texto = texto.replace(" ", "")

    partes = [parte for parte in texto.split("-") if parte != ""]
    if not partes:
        return None

    traducidas = []
    for parte in partes:
        if parte not in MAPA_TYPE:
            return None
        traducidas.append(MAPA_TYPE[parte])

    return "-".join(traducidas)


def normalizar_fund(valor: object) -> str | None:
    """Pasa un fund al nombre del catálogo.

    Quita espacios de más y no distingue mayúsculas.
    'RENTA VARIABLE' y '  Renta Variable  ' quedan en 'Renta Variable'.
    Si el texto no está en el catálogo, devuelve nulo.
    """
    if valor is None:
        return None

    texto = str(valor).strip()
    if texto == "" or texto.lower() in {"nat", "none", "nan", "<na>"}:
        return None

    texto = re.sub(r"\s+", " ", texto).lower()
    return MAPA_FUND.get(texto)


def preparar(df: pd.DataFrame, nombre_corte: str) -> tuple[pd.DataFrame, dict[str, str | int]]:
    """Transforma date, type y fund. El df conserva las mismas columnas del Parquet."""
    df = df.copy()

    fecha_texto = df["date"]
    df["date"] = convertir_fechas(fecha_texto)
    fechas_invalidas = int((fecha_texto.notna() & df["date"].isna()).sum())

    type_texto = df["type"]
    df["type"] = type_texto.map(traducir_type)
    type_sin_mapa = int((type_texto.notna() & df["type"].isna()).sum())

    fund_texto = df["fund"]
    df["fund"] = fund_texto.map(normalizar_fund)
    fondos_sin_mapa = int((fund_texto.notna() & df["fund"].isna()).sum())

    monto_texto = df["amount"]
    df["amount"] = pd.to_numeric(monto_texto, errors="coerce")
    montos_invalidos = int((monto_texto.notna() & df["amount"].isna()).sum())

    controles = {
        "corte": nombre_corte,
        "filas": len(df),
        "columnas": len(df.columns),
        "fechas_invalidas": fechas_invalidas,
        "type_sin_mapa": type_sin_mapa,
        "fondos_sin_mapa": fondos_sin_mapa,
        "montos_invalidos": montos_invalidos,
        "ids_nulos": int(df["id_cliente"].isna().sum()),
    }
    return df, controles
