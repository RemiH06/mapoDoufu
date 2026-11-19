# Descargas de aguas residuales (Conagua, REPDA)

Los puntos donde un título del Registro Público de Derechos de Agua tiene permiso de
descargar agua residual, con su volumen, de dónde viene y a dónde va. Responde:
**¿quién tiene permiso de descargar cerca de aquí, cuánto y a qué cuerpo de agua?**
Es lo permitido, no lo medido.

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente repda
```

Unos 45 s. Reemplaza `fuente_repda_descargas`.

## De dónde sale

`Otorgamiento_de_Concesiones.zip` de los datos abiertos de Conagua
(`datos.conagua.gob.mx/docs/DatosAbiertos/`), CSV en UTF-8:
`ANEXOS_RESIDUALES.csv` (un renglón por punto de descarga) unido por título con
`CONCESIONES.csv` para el uso y la fecha de registro. Licencia: datos abiertos del
gobierno federal; citar "Conagua, REPDA".

## Qué se guarda

| Columna | Qué es |
|---|---|
| `titulo`, `anexo` | Título de concesión y número de anexo (un título puede tener varias descargas) |
| `uso` | Uso que ampara el título: público urbano, industrial, servicios, acuacultura... |
| `cve_ent`, `cve_mun`, `municipio`, `cuenca` | Como los declara el título |
| `volumen_anual` | m³ al año permitidos |
| `procedencia`, `cuerpo_receptor`, `tipo_descarga`, `afluente`, `forma` | Texto libre del registro; `SIN DATO` es frecuente |
| `fecha_registro` | Del título |
| `geom` | De grados, minutos y segundos; la longitud viene sin signo y se vuelve negativa |

`TITULAR` no se lee: puede ser una persona. Para estudiar una zona basta el uso.

## Validación (2026-11-19)

- 33,807 descargas, los renglones del CSV; 33,701 con coordenada dentro de México.
  Todas encuentran su título en `CONCESIONES.csv`.
- En Jalisco (los municipios cargados en Mapo), 1,471 descargas con municipio y
  coordenada: el 90.6 % cae dentro del municipio que declara. El resto es error de
  captura de un lado o del otro.
- El volumen suma 33.7 km³ al año, y casi la mitad es industrial: las procedencias
  más grandes son agua de enfriamiento (la nucleoeléctrica sola, 1.9 km³). **No es
  "agua residual" en el sentido municipal**; comparar por `uso` y `procedencia`.

## Límites

- Es el permiso vigente a la fecha de descarga (2026-11-13), no lo que de verdad se
  descarga ni su calidad.
- Las descargas sin título (las irregulares) no están, y suelen ser las que más
  importan en un caso de contaminación.
- Hay coordenadas que caen en el municipio vecino o en el mar: revisar antes de
  afirmar "a 500 m".
