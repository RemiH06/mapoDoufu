# Índice SHF de Precios de la Vivienda

Índice trimestral de la Sociedad Hipotecaria Federal, base 2018 = 100, desde el
primer trimestre de 2005. Responde una sola pregunta: **cómo cambió el precio de
la vivienda aquí**. No da el precio en pesos (ese sale en el boletín de la SHF,
no en la API).

```bash
docker compose exec mapo_core python -m mapo_core.cli shf
```

Baja la serie completa de la API del SNIIV (SEDATU), sin llave, y reemplaza la
tabla `fuente_shf_ipv` en una transacción. Tarda unos 12 s.

## De dónde sale

`https://sniiv.sedatu.gob.mx/api/ShfPriceAPI/`, la misma que alimenta la página
"Precios de vivienda" del SNIIV. No está documentada: se encontró en el script de
esa página (`/js/housing-price-indicators/shf-housing-price-chart.js`).

| Ruta | Qué da |
|---|---|
| `GetConfiguration` | Trimestres disponibles y categorías de la serie nacional |
| `GetTerritorialVariation?baseYear=&baseQuarter=&finalYear=&finalQuarter=` | Valor inicial, final y variación entre dos trimestres, para 32 estados, 8 zonas metropolitanas y 74 municipios |
| `GetNationalPrices?startYear=&startQuarter=&endYear=&endQuarter=&categories=&metric=index` | Serie nacional por categoría; `categories` es obligatorio |

La API territorial no da la serie: da dos puntos. Con el mismo trimestre de los dos
lados, el valor final es el índice de ese trimestre; el cargador pide los 86
trimestres así, uno por uno.

## Qué se guarda

| Columna | Qué es |
|---|---|
| `nivel` | `nacional`, `estado`, `zm` o `municipio` |
| `clave` | `00`; clave de estado; nombre de la zona metropolitana (la API no les da clave); clave de estado y municipio juntas (`14120`) |
| `categoria` | `General` en lo territorial. En lo nacional: Nueva, Usada, Casa en condominio - depto., Casa sola, Económica - Social, Media - Residencial |
| `anio`, `trimestre`, `indice` | Índice del trimestre, base 2018 = 100 |

Cobertura al 2026-11-19: de 2005-I a 2026-II. Las 8 zonas son Guadalajara, León,
Monterrey, Puebla-Tlaxcala, Querétaro, Tijuana, Toluca y Valle de México. De
Jalisco hay cuatro municipios: Guadalajara, Zapopan, San Pedro Tlaquepaque y
Tlajomulco de Zúñiga. Los 74 municipios tienen serie desde 2005.

La serie nacional no trae un índice general, solo por categoría.

## Validación (2026-11-19)

Variación anual del segundo trimestre de 2026, calculada con lo guardado, contra el
reporte del IIEG de ese trimestre:

| Municipio | Mapo | IIEG |
|---|---|---|
| Guadalajara | 9.64 % | 9.64 % |
| San Pedro Tlaquepaque | 9.87 % | 9.87 % |
| Zapopan | 9.15 % | 9.15 % |

## Límites

- Sale de avalúos de crédito hipotecario. Deja fuera la compra de contado, la
  informal y la vivienda que no se financia; en zonas de autoconstrucción dice
  poco.
- Es un índice: compara un lugar consigo mismo en el tiempo. Un índice de 235 en
  Zapopan y otro de 210 en León no dicen que Zapopan sea más caro, sino que subió
  más desde 2018.
- Las cifras recientes son preliminares según el SNIIV.
- La SHF no publica licencia. El SNIIV dice "fuente: Sociedad Hipotecaria Federal".
  Citarla así.

## Zonas metropolitanas y avalúos

La API no dice qué municipios forman cada zona ni con cuántos avalúos se calcula
cada serie. Se preguntó por transparencia a la Sociedad Hipotecaria Federal
(enviada el 2026-11-19); respondió con oficio del 2026-11-20, recibido el 2026-11-24, y dos archivos. Son dos tablas
fijas dentro de `mapo_core`, que no pasan por la base:

| Archivo | Qué trae |
|---|---|
| `shf_zonas.csv` | Los 169 municipios de las 8 zonas, con su clave en el Sistema Urbano Nacional 2018 (SUN) |
| `shf_avaluos.csv` | Avalúos por año, 2005 a 2026, de los 74 municipios y las 8 zonas (1,804 filas) |

Salen del ZIP de la respuesta con `uv run scripts/shf/extraer.py <zip>`. El XLSX trae
las 417 filas de todo el SUN; se quedan las 8 zonas con serie. El nombre de la serie
(`ZM Valle México`, `ZM PueblaTlax`) se liga a mano con la clave del SUN.

| Zona | Clave SUN | Municipios | Con índice propio | Avalúos 2025 | De municipios con índice propio |
|---|---|---|---|---|---|
| Guadalajara | M14.01 | 10 | 4 | 41,514 | 77 % |
| León | M11.03 | 2 | 1 | 14,441 | 93 % |
| Monterrey | M19.01 | 18 | 4 | 51,959 | 52 % |
| Puebla-Tlaxcala | M21.01 | 39 | 2 | 12,110 | 55 % |
| Querétaro | M22.01 | 5 | 3 | 15,193 | 99.7 % |
| Tijuana | M02.03 | 3 | 1 | 9,480 | 92 % |
| Toluca | M15.02 | 16 | 2 | 6,267 | 40 % |
| Valle de México | M09.01 | 76 | 8 | 66,167 | 49 % |

### Qué contestó y qué no

1. **Municipios y delimitación:** contestado, SUN 2018.
2. **Municipios con índice propio:** de 69 a 74 en 2022-I; la serie de Miguel
   Hidalgo, Guadalajara, Metepec, Monterrey y Corregidora se reconstruyó
   hacia atrás hasta 2005.
3. **Si la composición de las zonas cambió desde 2005:** no lo dice. Con una sola
   delimitación, Mapo toma las zonas como fijas.
4. **Si la zona usa los avalúos de todos sus municipios:** no lo dice, pero los datos
   sí. Los avalúos de cada zona superan cada año a los de sus municipios con índice,
   y el índice de la zona se sale del rango de esos municipios en Puebla-Tlaxcala (50
   de 86 trimestres). No puede ser un promedio solo de ellos.
5. **Avalúos:** por año, no por trimestre. 2026 está a medias (el archivo no dice
   hasta qué mes) y Mapo no lo muestra.

### Validación (2026-11-24)

- Las 74 claves de municipio del archivo son exactamente las 74 de la API.
- Ninguna zona tiene, ningún año, menos avalúos que la suma de sus municipios
  (prueba en `test_shf_ipv.py`).
- Donde un solo municipio pesa más de 90 % de los avalúos, la zona es casi él: León y
  Tijuana difieren de su municipio menos de 0.25 % en los 86 trimestres.
- El índice de la zona queda entre los de sus municipios con índice en los 86
  trimestres en Guadalajara, Monterrey, Querétaro y Valle de México, y en 85 en
  Toluca. En León y Tijuana (un solo municipio) y Puebla-Tlaxcala (dos, 55 % de los
  avalúos) no tiene por qué.

### Límites

- **Series con pocos avalúos.** Huejotzingo tiene índice desde 2005, pero en 2008 se
  apoya en 36 avalúos; Tlacolula de Matamoros, en 6 en 2005. La SHF no dice
  un mínimo. La ficha muestra los avalúos del último año completo y los del año con
  menos.
- **Una zona puede decir poco del municipio que la ve.** Huimilpan y Apaseo el Alto
  juntos ponen 44 de los 15,193 avalúos de Querétaro. La ficha da esa cuenta.
- La delimitación de 2018 no es Metrópolis de México 2020 (`zonas.md`): la ZM de
  Guadalajara del índice tiene 10 municipios y la de 2020, 7.
