COLUMNAS = (
    "id_cliente",
    "date",
    "product",
    "type",
    "fund",
    "commercial_name",
    "amount",
    "description",
)
COLUMNAS_CON_NULO = ("commercial_name", "amount", "description")


def misma_llave(izquierda: str, derecha: str) -> str:
    """Dos filas son la misma si las ocho columnas coinciden, nulos incluidos."""
    partes = []
    for columna in COLUMNAS:
        if columna in COLUMNAS_CON_NULO:
            partes.append(
                f"{izquierda}.{columna} IS NOT DISTINCT FROM {derecha}.{columna}"
            )
        else:
            partes.append(f"{izquierda}.{columna} = {derecha}.{columna}")
    return " AND ".join(partes)
