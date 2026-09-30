from src.leer_datos import (preparar, leer_parquet, ARCHIVO_T,ARCHIVO_T1)

def main():
    # se leen los datos
    try:
        df_t = leer_parquet(ARCHIVO_T)
        df_t1 = leer_parquet(ARCHIVO_T1)
    except FileNotFoundError:
        print("Revisar ruta de los archivos")
        raise
    # Limpiar y normalizar los datos 
    df_t, control_t = preparar(df_t, "T")
    df_t1, control_t1 = preparar(df_t1, "T1")
    # Revision de casos
    
if __name__ == "__main__":
    main()  