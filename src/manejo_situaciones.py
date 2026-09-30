import pandas as pd

# La llave identifica el movimiento. commercial_name no cambia.
# amount y description quedan fuera: son los valores que pueden corregirse.
CLAVE = ["id_cliente", "date", "product", "type", "fund", "commercial_name"]
VALORES = ["amount", "description"]


def claves_repetidas(df: pd.DataFrame) -> pd.DataFrame:
    """Esta funcion cuenta la cantidad de datos repetidos que se tienen
    tomando en cuenta solo las claves definidas en CLAVE"""
    conteo = df.groupby(CLAVE, dropna=False).size()
    return conteo[conteo > 1].reset_index()[CLAVE]


def separar_ambiguas(df: pd.DataFrame, repetidas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Esta funcion encuentra las transacciones que estan repetidas en el mismo corte
    pero cambia en amount y la descripcion"""
    if repetidas.empty:
        return df.iloc[0:0].copy(), df.copy()

    marcado = df.merge(repetidas.assign(_ambigua=1), on=CLAVE, how="left")
    ambiguas = marcado[marcado["_ambigua"].eq(1)].drop(columns="_ambigua")
    limpias = marcado[marcado["_ambigua"].isna()].drop(columns="_ambigua")
    return ambiguas, limpias


def cruzar(df_t: pd.DataFrame, df_t1: pd.DataFrame) -> pd.DataFrame:
    """Junta T y T+1. _merge dice si la llave está en uno de los dos o en ambos."""
    return df_t.merge(df_t1, on=CLAVE, how="outer", suffixes=("_t", "_t1"), indicator=True)


def valores_cambiaron(cruce: pd.DataFrame) -> pd.Series:
    """True si amount o description no coinciden. Dos nulos cuentan como iguales."""
    cambio = pd.Series(False, index=cruce.index)
    for columna in VALORES:
        anterior = cruce[f"{columna}_t"]
        nuevo = cruce[f"{columna}_t1"]
        ambos_nulos = anterior.isna() & nuevo.isna()
        cambio = cambio | (anterior.ne(nuevo) & ~ambos_nulos)
    return cambio


def situacion_sin_cambios(cruce: pd.DataFrame) -> pd.DataFrame:
    """La transacción está en T y en T+1, y amount y description son iguales."""
    en_ambos = cruce["_merge"].eq("both")
    filas = cruce[en_ambos & ~valores_cambiaron(cruce)].copy()
    filas["situacion"] = "sin_cambios"
    return filas


def situacion_corregido(cruce: pd.DataFrame) -> pd.DataFrame:
    """La misma transacción está en T y en T+1, pero amount o description cambió."""
    en_ambos = cruce["_merge"].eq("both")
    filas = cruce[en_ambos & valores_cambiaron(cruce)].copy()
    filas["situacion"] = "corregido"
    return filas


def situacion_eliminado(cruce: pd.DataFrame) -> pd.DataFrame:
    """La transacción está en T y no aparece en T+1."""
    filas = cruce[cruce["_merge"].eq("left_only")].copy()
    filas["situacion"] = "eliminado"
    return filas


def situacion_nuevo(cruce: pd.DataFrame) -> pd.DataFrame:
    """La transacción está en T+1 y no estaba en T."""
    filas = cruce[cruce["_merge"].eq("right_only")].copy()
    filas["situacion"] = "nuevo"
    return filas


def tomar_valores(cruce: pd.DataFrame, lado: str, situaciones: list[str]) -> pd.DataFrame:
    """lado 't1' es el corte nuevo. lado 't' es el valor que se conserva aparte."""
    filas = cruce[cruce["situacion"].isin(situaciones)].copy()
    salida = filas[CLAVE].copy()
    for columna in VALORES:
        salida[columna] = filas[f"{columna}_{lado}"].values
    salida["situacion"] = filas["situacion"].values
    return salida
