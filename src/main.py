from src.cargar_corte import cargar_dia
from src.leer_datos import ARCHIVO_T


def main() -> None:
    cargar_dia(ARCHIVO_T, "T")


if __name__ == "__main__":
    main()
