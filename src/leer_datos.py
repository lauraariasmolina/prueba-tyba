import os
from datetime import date, datetime

import pandas as pd

CARPETA_DATOS = r"C:/Users/micen/Documents/TYBA/data"
CARPETA_PREPARADOS = CARPETA_DATOS + "/preparados"
MARCADOR_PASO = CARPETA_PREPARADOS + "/paso_leer_datos_listo.txt"
ARCHIVO_T = CARPETA_DATOS + r"/raw/movimientos_dia_T.parquet"
ARCHIVO_T1 = CARPETA_DATOS + r"/raw/movimientos_dia_T1.parquet"

MAPA_TYPE = {
    "entrada": "IN",
    "salida": "OUT",
    "in": "IN",
    "out": "OUT",
}

def leer_parquet(ruta: str) -> pd.DataFrame:
    """Abre un Parquet. Si la ruta no existe, el try lo dice y corta."""
    try:
        df = pd.read_parquet(ruta)
    except FileNotFoundError:
        print(f"Revisar ruta del archivo: {ruta}")
        raise

    print(f"Leído: {ruta}")
    print(f"Filas: {len(df)} | Columnas: {list(df.columns)}")
    return df


def mostrar_perfil(df: pd.DataFrame, nombre: str) -> None:
    """Métricas del corte tal como llegó, antes de tocar nada."""
    print("\n" + "=" * 60)
    print(nombre)
    print("=" * 60)
    print("Dimensiones:", df.shape)
    print("\nTipos de dato:")
    print(df.dtypes)
    print("\nNulos por columna:")
    print(df.isna().sum())

    if "id_cliente" in df.columns:
        repetidos = df["id_cliente"].duplicated().sum()
        print("\nIds nulos:", df["id_cliente"].isna().sum())
        print("Ids duplicados:", repetidos)

    if "type" in df.columns:
        print("\nValores de type:")
        print(df["type"].value_counts(dropna=False).head(20))


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


def preparar(df: pd.DataFrame, nombre_corte: str) -> tuple[pd.DataFrame, dict[str, str | int]]:
    """Transforma date y type. El df conserva las mismas columnas del Parquet."""
    df = df.copy()

    fecha_texto = df["date"]
    df["date"] = convertir_fechas(fecha_texto)
    fechas_invalidas = int((fecha_texto.notna() & df["date"].isna()).sum())

    type_texto = df["type"]
    df["type"] = type_texto.map(traducir_type)
    type_sin_mapa = int((type_texto.notna() & df["type"].isna()).sum())

    monto_texto = df["amount"]
    df["amount"] = pd.to_numeric(monto_texto, errors="coerce")
    montos_invalidos = int((monto_texto.notna() & df["amount"].isna()).sum())

    controles = {
        "corte": nombre_corte,
        "filas": len(df),
        "columnas": len(df.columns),
        "fechas_invalidas": fechas_invalidas,
        "type_sin_mapa": type_sin_mapa,
        "montos_invalidos": montos_invalidos,
        "ids_nulos": int(df["id_cliente"].isna().sum()),
    }
    return df, controles


if __name__ == '__main__':
    os.makedirs(CARPETA_PREPARADOS, exist_ok=True)
    if os.path.exists(MARCADOR_PASO):
        os.remove(MARCADOR_PASO)

    try:
        df_t = leer_parquet(ARCHIVO_T)
        df_t1 = leer_parquet(ARCHIVO_T1)
    except FileNotFoundError:
        print("Revisar ruta de los archivos")
        raise

    df_t, control_t = preparar(df_t, "T")
    df_t1, control_t1 = preparar(df_t1, "T1")

    for control in (control_t, control_t1):
        print(
            f"Control {control['corte']}: "
            f"filas={control['filas']} columnas={control['columnas']} "
            f"fechas_invalidas={control['fechas_invalidas']} "
            f"type_sin_mapa={control['type_sin_mapa']} "
            f"montos_invalidos={control['montos_invalidos']} "
            f"ids_nulos={control['ids_nulos']}"
        )

    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    # print("\n20 filas de T después de fechas y type")
    # print(df_t.head(100))

    # print("\n20 filas de T+1 después de fechas y type")
    # print(df_t1.head(20))

    df_t.to_parquet(CARPETA_PREPARADOS + "/movimientos_dia_T.parquet", index=False)
    df_t1.to_parquet(CARPETA_PREPARADOS + "/movimientos_dia_T1.parquet", index=False)

    with open(MARCADOR_PASO, "w", encoding="utf-8") as marca:
        marca.write("ok")

    print("Siguiente paso habilitado:", MARCADOR_PASO)

    duplicados = df_t[df_t.duplicated(subset=['id_cliente'])]['id_cliente'].unique()
    print("Duplicados:")
    print(duplicados)
