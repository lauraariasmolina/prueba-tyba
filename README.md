# Pipeline de movimientos financieros

Carga dos cortes diarios en PostgreSQL y deja las transacciones vigentes y el historial de lo que salió. Cada corrida procesa un solo Parquet. Docker corre primero el día T y después el día T+1.

Las inconsistencias de los archivos, las decisiones de diseño y el resultado de los dos días están en [docs/insights.md](docs/insights.md).

## Requisitos

- Docker con Compose
- Los archivos `data/raw/movimientos_dia_T.parquet` y `data/raw/movimientos_dia_T1.parquet`

## Correr el proyecto

Desde la raíz del repositorio:

```bash
docker compose up --build
```

Eso levanta PostgreSQL, espera a que acepte conexiones y ejecuta el pipeline. T usa la fecha del día en que corre el contenedor. T+1 usa el día siguiente. La contraseña y el nombre de la base están fijos en `docker-compose.yml`.

Al terminar, la salida incluye un cierre por cada día, por ejemplo:

```text
Cierre 2026-09-30: nuevo=50000 sin_cambios=0 eliminado=0
Cierre 2026-10-01: nuevo=13841 sin_cambios=35159 eliminado=14841
Llaves en vigente y en historial: 0
```

El servicio de PostgreSQL sigue en marcha. El contenedor del pipeline termina al cerrar los dos días.

Si se vuelve a correr el mismo comando, T y T+1 no se cargan otra vez. El historial no se duplica.

## Consultar la base

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Puerto | `5433` |
| Base | `movimientos` |
| Usuario | `tyba` |
| Contraseña | `tyba` |

En pgAdmin se pueden revisar `movimiento_vigente` y `movimiento_historial`. `corte_dia` queda vacía al cerrar el día.

## Correr un solo corte

Con el entorno de Python del proyecto y PostgreSQL ya levantado:

```bash
python -m src.main T 2026-09-30
python -m src.main T1 2026-10-01
```

El primer argumento es el corte (`T` o `T1`). El segundo es la fecha de corte, en formato `AAAA-MM-DD`. Si no se pasa fecha, se usa la del día.
