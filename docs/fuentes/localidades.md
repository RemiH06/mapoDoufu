# Localidades del censo (ITER 2020)

El ITER ("Integración Territorial") de INEGI es el Censo 2020 por localidad: una
fila por cada una de las 189,432 localidades del país, de las ciudades a los
ranchos de una vivienda, con su punto y 286 indicadores. Es lo único que ubica a
la población rural: el censo por AGEB que usa Mapo solo cubre lo urbano. Es base
pública de Mapo, para todo el país.

```bash
docker compose exec mapo_core python -m mapo_core.cli localidades [--archivo iter_00_cpv2020_csv.zip]
```

Baja el archivo nacional (37 MB) de
`https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip`
y reemplaza la tabla `localidades` de `mapo_core` en una transacción. Ocupa unos
490 MB en la base, casi todo los 286 indicadores en `datos` (JSONB).

## Qué se guarda

| Columna | Qué es |
|---|---|
| `cvegeo` | Clave de 9: estado, municipio y localidad |
| `nombre`, `nom_mun` | Como los escribe INEGI. "Ninguno" es el nombre que INEGI da a una localidad sin nombre |
| `ambito` | `urbana` con 2,500 habitantes o más, `rural` con menos, como lo define INEGI |
| `tamloc` | Tamaño de localidad de INEGI (1 es de 1 a 249 habitantes; 14, un millón o más) |
| `altitud`, `pobtot` | Metros sobre el nivel del mar y población total |
| `datos` | El renglón completo del ITER |
| `geom` | El punto de la localidad, convertido de grados, minutos y segundos |

Los renglones de totales (estado y municipio) y los de resumen de localidades de
una y dos viviendas (`LOC` 9998 y 9999) no se guardan: esas localidades ya vienen
una por una con su clave.

## Validación (2026-11-18)

- La población de las localidades de cada estado es igual al total que publica el
  mismo archivo, en los 32 estados; si un estado no cuadra, no se guarda nada.
  Nacional: 126,014,024.
- Rurales: 185,243 localidades con 26,983,528 personas, el 21.4 % del país, que es
  la parte rural que reporta INEGI para 2020.
- La cabecera de Autlán de Navarro tiene 52,019 habitantes, igual que el ITER de
  Jalisco del paquete ambiental, y cae en su centro.

## En Mapo

En "Distancia", el destino "Localidades del censo 2020" mide de cada renglón de
una capa a la localidad más cercana (todas, solo rurales o solo urbanas) y, con
radio, cuántas hay y cuánta gente vive en ellas. Las localidades son de
`mapo_core`: Mapo manda las geometrías de los renglones en la petición
(`POST /localidades/distancia`), como en el cruce, y allá no se guardan. El método
es el de la distancia entre capas.

## Límites

- Una localidad es un punto, no un polígono. En una ciudad, el punto es su
  centro: la distancia a una ciudad es a su centro, no a su orilla. Para lo
  urbano están los AGEB.
- La población a cierto radio cuenta la localidad completa en cuanto su punto
  queda dentro.
- Es de 2020. Lo que se fundó o se despobló después no está.
