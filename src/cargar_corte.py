from datetime import date

import pyarrow.parquet as pq

import src.base_datos as bd
from src.clasificar import clasificar_dia, comprobar_dia
from src.leer_datos import preparar

TAMANO_BLOQUE = 100_000


def cargar_dia(ruta: str, nombre_corte: str, fecha_corte: date) -> None:
    """Carga un Parquet, revisa duplicados y clasifica el día.

    Si el corte ya se aplicó, no lo vuelve a cargar. Si algo falla, se deshace
    la transacción. El historial no se vacía.
    """
    with bd.conectar() as conn:
        with conn.cursor() as cur:
            fecha_previa = bd.corte_ya_aplicado(cur, nombre_corte)
            if fecha_previa is not None:
                print(
                    f"El corte {nombre_corte} ya fue aplicado el {fecha_previa}. "
                    "No se vuelve a cargar."
                )
                return

            try:
                archivo = pq.ParquetFile(ruta)
            except FileNotFoundError:
                print(f"Revisar ruta del archivo: {ruta}")
                raise

            filas_archivo = archivo.metadata.num_rows
            print(f"Leído: {ruta}")
            print(f"Filas: {filas_archivo}")

            bd.vaciar_corte(cur)

            copiadas = 0
            for bloque in archivo.iter_batches(batch_size=TAMANO_BLOQUE):
                df, control = preparar(bloque.to_pandas(), nombre_corte)
                bd.copiar_bloque(cur, df)
                copiadas += control["filas"]
                print(
                    f"Control {control['corte']}: "
                    f"filas={control['filas']} columnas={control['columnas']} "
                    f"fechas_invalidas={control['fechas_invalidas']} "
                    f"type_sin_mapa={control['type_sin_mapa']} "
                    f"montos_invalidos={control['montos_invalidos']} "
                    f"ids_nulos={control['ids_nulos']}"
                )

            en_tabla = bd.contar_corte(cur)
            if copiadas != filas_archivo or en_tabla != filas_archivo:
                raise RuntimeError(
                    f"corte_dia quedó con {en_tabla} filas y el archivo tiene {filas_archivo}"
                )

            bd.revisar_duplicados(cur)
            clasificar_dia(cur, fecha_corte)
            comprobar_dia(cur, fecha_corte)
            bd.registrar_corte(cur, nombre_corte, fecha_corte)
            vigente, historial, corte = bd.contar_tablas(cur)

    print(f"Copiadas: {copiadas} | fecha_corte: {fecha_corte}")
    print(f"vigente: {vigente} | historial: {historial} | corte_dia: {corte}")
