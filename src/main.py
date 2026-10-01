import sys
from datetime import date
from pathlib import Path

from src.cargar_corte import cargar_dia

CARPETA_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
ARCHIVOS = {
    "T": str(CARPETA_RAW / "movimientos_dia_T.parquet"),
    "T1": str(CARPETA_RAW / "movimientos_dia_T1.parquet"),
}


def leer_fecha_corte(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise SystemExit(f"Fecha de corte inválida: {texto}. Usa AAAA-MM-DD.")


def main() -> None:
    nombre = sys.argv[1] if len(sys.argv) > 1 else "T"
    if nombre not in ARCHIVOS:
        raise SystemExit(f"Corte desconocido: {nombre}. Usa T o T1.")

    if len(sys.argv) > 2:
        fecha_corte = leer_fecha_corte(sys.argv[2])
    else:
        fecha_corte = date.today()

    cargar_dia(ARCHIVOS[nombre], nombre, fecha_corte)


if __name__ == "__main__":
    main()
