# Encuesta Nacional de Vivienda (ENVI) 2020

Encuesta de INEGI con INFONAVIT y SHF, levantada de octubre a diciembre de 2020
en 55,147 viviendas, representativa **por estado**. Es la única fuente abierta
con **cuánto se paga de renta** y **en cuánto se vendería la vivienda** según
quien la habita.

```bash
docker compose exec mapo_core python -m mapo_core.cli envi [--archivo conjunto_de_datos_envi_2020_csv.zip]
```

Baja `https://www.inegi.org.mx/contenidos/programas/envi/2020/datosabiertos/conjunto_de_datos_envi_2020_csv.zip`
(13 MB), lee la tabla de vivienda (`tvivienda`), calcula los indicadores por
estado y nacional, y reemplaza `fuente_envi2020_entidad` en una transacción.
Tarda unos 30 s. No se guardan los microdatos.

## Qué se calcula

| Indicador | Cómo | Error estándar |
|---|---|---|
| `viviendas` | Suma del factor de expansión | No |
| `pct_rentadas` | Viviendas con P5.1 = 1 ("es rentada") | Sí |
| `pct_rentadas_con_contrato` | De las rentadas, P5.4 = 1 ("contrato vigente") | Sí |
| `renta_mensual_media` | P5.2 de las rentadas, de 100 a 50,000 pesos | Sí |
| `renta_mensual_mediana` | Igual, mediana ponderada | No |
| `valor_estimado_mediana` | P5.9 ("si tuviera que venderse, ¿en cuánto se daría?") de las propias (P5.1 = 4 o 5), de 600 a 45 millones | No |

Los rangos son los del diccionario de datos; 999999888 y 999999999 ("no sabe",
"no responde") se excluyen. `n_muestra` dice cuántas viviendas de la muestra
entraron en cada cifra.

El error estándar es por conglomerado último, como lo calcula INEGI: estrato
`EST_DIS` (552, ninguno cruza estados) y UPM `UPM_DIS`, con la media linealizada
como razón. Las medianas no llevan error: no se estima, y se deja nulo.

## Validación (2026-11-19)

Contra el boletín de resultados de la ENVI 2020:

| | Mapo | INEGI |
|---|---|---|
| Viviendas particulares habitadas | 35,259,433 | 35.3 millones |
| Rentadas | 16.4 % (5,782,349) | 16.4 % (5.8 millones) |
| Rentadas con contrato vigente | 54.0 % | 54.0 % |

INEGI no publica un monto de renta para cotejar las cifras de pesos. Lo que hay:
mediana nacional de 2,000 pesos al mes (media 2,791, ee 56); Jalisco 2,000 (media
2,851, ee 162, 442 viviendas en muestra); Ciudad de México 3,500.

## Límites

- Por estado, nada más abajo. Un estado entero mezcla la capital con lo rural.
- Es de 2020, con pandemia. Para tenencia más reciente y por municipio, la
  Intercensal 2025; para cómo cambió el precio, el índice SHF.
- El valor estimado es la opinión de quien habita la vivienda, no un avalúo.
- En P5.2 la pregunta es lo que se paga al mes "por esta vivienda": para las
  rentadas es la renta; para las propias que se pagan, la mensualidad (no se usa).
