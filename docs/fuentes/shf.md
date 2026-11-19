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

## Zonas metropolitanas: pregunta a la SHF

La SHF no publica qué municipios forman cada una de sus 8 zonas ni con qué
delimitación las arma (`../producto/vista-vivienda.md`, Pendiente). Por eso se le
pregunta por la Plataforma Nacional de Transparencia (sujeto obligado: Sociedad
Hipotecaria Federal, S.N.C.):

1. Municipios de cada zona, con su clave de INEGI.
2. Delimitación oficial que usa (SEDATU, CONAPO e INEGI 2015, Sistema Urbano
   Nacional 2018, Metrópolis de México 2020 u otra) y su versión.
3. Si la composición de las zonas cambió desde 2005, y cuándo. Lo mismo para los
   municipios con índice propio, que pasaron de 69 a 74 en 2022-I según los
   reportes del IIEG.
4. Si la serie de una zona usa los avalúos de todos sus municipios o solo los de
   los que tienen índice propio.
5. Número de avalúos por zona, municipio y trimestre, o al nivel que exista.

Mientras no haya respuesta, la ficha de vivienda no muestra serie de zona: un
municipio sin serie propia ve la de su estado.
