# Insights, inconsistencias y decisiones

Cada día llega un archivo con la lista completa de movimientos financieros de ese día. El del día siguiente no es una lista de cambios: es otra lista completa. El pipeline compara la lista de hoy con los movimientos que quedaron vigentes ayer y actualiza una base en PostgreSQL.

Los archivos de la prueba son dos: `movimientos_dia_T.parquet` (día T, 50.000 filas) y `movimientos_dia_T1.parquet` (día T+1, 49.000 filas).

## Qué pide la prueba y qué traen los archivos

La prueba define cuatro situaciones a partir de un `id` de transacción. El glosario dice que `id` es el identificador de la transacción:

| Situación en la prueba | Cómo la describe el documento |
|---|---|
| Registro nuevo | Un id que no estaba en T aparece en T+1. |
| Registro corregido | Un id que estaba en T aparece en T+1 con otro monto, otra descripción u otro campo. |
| Registro eliminado | Un id que estaba en T no aparece en T+1. |
| Sin cambios | Un id aparece igual en los dos cortes. |

Los Parquet no tienen una columna `id`. Tienen `id_cliente`, con valores como `CLI000339`. En cada archivo hay 3.000 clientes y muchas filas por cliente: 47.000 filas de más en T y 46.000 en T+1. `id_cliente` es el cliente, no la transacción.

Sin un identificador de transacción no se puede saber si dos filas son el mismo movimiento con un dato corregido. El caso "registro corregido" no se implementa.

## Las tablas que se consultan

Después de correr los dos días, la información queda en dos tablas. Una tercera tabla solo se usa durante la carga y al final queda vacía.

`movimiento_vigente` es la lista de movimientos del último día ya procesado. Si alguien pregunta qué movimientos están vigentes hoy, la respuesta está en esta tabla.

`movimiento_historial` guarda los movimientos que estuvieron vigentes y dejaron de venir en un día posterior. No se borran: se mueven aquí para no perder el rastro. Esta tabla solo crece.

`corte_dia` es una mesa de trabajo. Recibe el archivo de hoy, se compara con `movimiento_vigente` y, si el día termina bien, se vacía. No guarda historia y no sirve para consultar. Su función se explica más abajo, porque es lo que permite que el mismo proceso sirva con millones de filas.

El mismo día, una fila no queda en vigente y en historial. Si salió en un día anterior y un archivo posterior la trae otra vez idéntica, vuelve a vigente y el historial conserva el día en que había salido.

## Cómo se decide dónde queda cada fila

Dos filas son el mismo movimiento solo si coinciden en las ocho columnas: `id_cliente`, `date`, `product`, `type`, `fund`, `commercial_name`, `amount` y `description`.

Cada corrida recibe un solo archivo, el del día. Los movimientos del día anterior ya están en `movimiento_vigente`. El archivo de hoy se copia a `corte_dia` y PostgreSQL compara las dos tablas:

| Situación | Qué se compara | Dónde queda |
|---|---|---|
| Sin cambios | La misma fila está en vigente y en el archivo de hoy. | Sigue en `movimiento_vigente`. |
| Eliminado | La fila estaba en vigente y el archivo de hoy no la trae. | Sale de vigente y se copia a `movimiento_historial`. |
| Nuevo | La fila viene en el archivo de hoy y no estaba en vigente. | Entra a `movimiento_vigente`. |

El primer día la tabla vigente está vacía, así que todas las filas de T entran como nuevas. Al día siguiente, vigente ya tiene lo de T y el archivo de T+1 se compara contra eso.

Si el monto o la descripción cambian, no es una corrección del mismo movimiento. Son dos filas distintas. La de ayer sale de vigente y queda en historial, porque el archivo de hoy no la trae. La de hoy entra a vigente, porque ayer no estaba.

Si una fila ya está en el historial y el archivo de hoy la trae otra vez igual, entra a vigente como nueva. La fila del historial no se borra: sigue diciendo qué día había dejado de venir.

## Para qué sirve corte_dia

La prueba advierte que el volumen puede crecer a millones de filas. Comparar el día de ayer y el de hoy armando las dos listas completas en la memoria de Python puede quedarse sin RAM. `corte_dia` evita eso.

Python no arma vigente ni historial. Lee el Parquet por bloques de 100.000 filas, normaliza la fecha, el tipo y el fondo en ese bloque, y lo copia a `corte_dia` con `COPY`. En memoria solo está el bloque que se está copiando. El archivo de ayer no se vuelve a leer: sus movimientos ya están en `movimiento_vigente`, en disco.

La comparación la hace PostgreSQL entre dos tablas que ya están en la base: lo vigente y `corte_dia`. Así se decide qué sigue, qué sale al historial y qué entra como nuevo. Si algo falla, se deshace el día completo y las dos tablas de consulta quedan como estaban.

Al terminar bien, `corte_dia` se vacía. No acumula los días anteriores. El historial sí se queda con lo que salió, y vigente se queda con la lista del último día. La mesa de trabajo vuelve a quedar libre para el archivo de mañana, aunque ese archivo tenga millones de filas.

## Ejemplo: el monto y la descripción cambian

`CLI000863`, el 2024-09-23, tiene un movimiento de Acciones, entrada, fondo Renta Variable y nombre comercial Valores Bancolombia. En T y en T+1 coinciden esas seis columnas, pero cambian el monto y la descripción.

| Día | Monto | Descripción | Dónde queda |
|---|---|---|---|
| T | 42.773.985,27 | Compra de activo | Historial. T+1 no trae esta fila. |
| T+1 | 12.448.886,11 | Venta de activo | Vigente. Esta fila no estaba en T. |

Las dos se guardan. No se elige una y se descarta la otra. La compra deja de estar vigente porque el archivo de T+1 ya no la incluye. La venta entra a vigente porque es otra fila y T+1 sí la incluye.

## Ejemplo: dos movimientos que siguen los dos

`CLI000339`, el 2024-10-02, tiene dos movimientos de Divisas, entrada, fondo Internacional y nombre comercial Scotiabank. Uno es 41.924.954,04 con descripción "Reinversión automática". El otro es 19.583.875,04 con descripción "Ajuste por valoración".

Las dos filas están en T y también en T+1. Como el monto y la descripción son distintos, son dos movimientos. Como las dos vienen en el archivo de T+1, las dos siguen en `movimiento_vigente`.

## Inconsistencias de los archivos

`type` no llega en un solo formato. En T aparecen `entrada` (25.423), `salida` (20.631), `IN` (586), `Entrada` (547), `ENTRADA` (530), `in` (520), `Salida` (478), `out` (448), `SALIDA` (429) y `OUT` (408). T+1 trae las mismas diez formas. Antes de cargar, entrada se guarda como `IN` y salida como `OUT`. Ningún valor quedó sin mapa.

`date` llega en dos textos. En T, 46.518 fechas están en `AAAA-MM-DD` y 3.482 en `DD/MM/AAAA`. En T+1 son 45.567 y 3.433. `01/10/2024` se lee como 1 de octubre, porque el negocio es Colombia.

`fund` llega con 23 textos distintos en cada archivo y ninguno viene vacío. En T, 5.989 filas no usan el nombre del catálogo. En T+1 son 5.900. Cambian las mayúsculas o sobran espacios. Antes de cargar, el texto se pasa a minúsculas, se dejan los espacios en uno solo y se compara con siete nombres: Balanceado, Conservador, Crecimiento, Internacional, Mercado Monetario, Renta Fija y Renta Variable. En la última corrida ningún fondo quedó sin mapa. En vigente y en historial solo aparecen esos siete.

`amount`, `description` y `commercial_name` vienen vacíos. El monto ya es numérico: el vacío es un nulo, no un texto inválido. Esas filas se cargan. No se descartan.

| Columna | Nulos en T | Nulos en T+1 |
|---|---:|---:|
| `amount` | 1.543 | 1.440 |
| `description` | 4.563 | 4.485 |
| `commercial_name` | 8.307 | 8.167 |

`id_cliente`, `date`, `product`, `type` y `fund` no tienen nulos.

En cada archivo, ninguna fila está repetida completa. Si se compara todo menos la descripción, tampoco hay repeticiones. Las filas parecidas aparecen solo cuando se dejan por fuera el monto y la descripción: 7 pares en T y 6 en T+1. Esas filas coinciden en cliente, fecha, producto, tipo, fondo y nombre comercial, y se distinguen por el monto.

## Decisiones de carga

Dos vacíos en `commercial_name`, `amount` o `description` cuentan como el mismo valor. Si no fuera así, dos filas iguales con el monto vacío se guardarían las dos en vigente.

Si el archivo del día trae la misma fila dos veces, la carga se detiene y vigente e historial quedan como el día anterior. En T y en T+1 no pasa: el conteo de filas repetidas es cero. No se elige una de las dos copias.

`fecha_corte` es el día en que se corre el archivo, no la fecha del movimiento. No está escrita en el código. Se pasa al ejecutar y, si no se pasa, se usa la fecha del día. En Docker, T toma la fecha del contenedor y T+1 el día siguiente. En vigente, esa fecha dice qué corrida dejó la fila ahí. En historial, dice qué día dejó de venir.

El Parquet original no se modifica.

## Resultado después de los dos días

La última corrida fue con Docker. T usó la fecha del contenedor, `2026-10-01`. T+1 usó el día siguiente, `2026-10-02`. En los dos cortes el control de limpieza quedó en cero: fechas inválidas, tipos sin mapa, fondos sin mapa, montos inválidos e identificadores nulos. Tampoco hubo filas repetidas.

La primera corrida carga T con vigente vacía. Las 50.000 filas entran a `movimiento_vigente` como nuevas. El historial sigue vacío.

La segunda corrida carga T+1 y compara contra esas 50.000:

| Situación | Filas | Qué significa |
|---|---:|---|
| Sin cambios | 35.159 | Estaban en T y T+1 las vuelve a traer. Siguen en vigente. |
| Nuevo | 13.841 | No estaban en T y T+1 las trae. Entran a vigente. |
| Eliminado | 14.841 | Estaban en T y T+1 no las trae. Pasan a historial. |

35.159 + 13.841 = 49.000, que son las filas de T+1. Esas 49.000 quedan en `movimiento_vigente`. 35.159 + 14.841 = 50.000, que son las filas de T. Las 14.841 que T+1 ya no trae quedan en `movimiento_historial`.

Los movimientos vigentes pasan de 50.000 a 49.000. Ninguna fila queda al mismo tiempo en las dos tablas. `corte_dia` queda vacía.
