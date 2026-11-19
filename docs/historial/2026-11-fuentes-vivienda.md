# Fuentes de vivienda (noviembre 2026, sesión 20)

Base para la vista de precios (sesión 21): cuatro fuentes con su cargador en
`mapo_core`, su ficha en `../fuentes/` y su validación contra lo publicado. Sin
pantalla todavía.

## Qué se hizo

| Fuente | Comando | Nivel | Responde |
|---|---|---|---|
| Índice SHF de precios (`../fuentes/shf.md`) | `cli shf` | 32 estados, 8 zonas metropolitanas, 74 municipios; trimestral desde 2005 | Cómo cambió el precio |
| Financiamientos del SNIIV (`../fuentes/sniiv.md`) | `cli sniiv` | Municipio, anual desde 2013 | Cuánto se presta, quién y para qué segmento |
| Intercensal 2025 (`../fuentes/eic2025.md`) | `cli eic2025` | Municipio y localidades de 50 mil o más | Cuánto se renta, escrituras, servicios |
| ENVI 2020 (`../fuentes/envi.md`) | `cli envi` | Estado | Cuánto se paga de renta, en cuánto se vendería |

Las cuatro cuadran con lo publicado: variación anual del SHF igual al IIEG (GDL
9.64 %, Zapopan 9.15 %), tenencia nacional de la EIC igual a INEGI (19.26 %
rentadas), viviendas rentadas y con contrato de la ENVI iguales a su boletín (16.4
y 54.0 %), y la banca del SNIIV igual a lo citado en prensa (170 mil créditos en
2023, 2.3 millones de promedio en 2024).

## Por qué así

- **Lo que de verdad existe, no lo que se suponía.** El plan decía SHF, SNIIV,
  ENVI e INV "de memoria". Al revisar: el SNIIV se mudó de dominio y el índice SHF
  sale de su API; la Intercensal 2025, que no estaba en el plan, da tenencia por
  municipio con cinco años menos de antigüedad que la ENVI; y el INV se quedó
  fuera porque la vivienda deshabitada por AGEB ya está en el censo cargado.
- **Ninguna da precio por zona.** El SHF es índice (cambio, no nivel), el SNIIV es
  lo prestado, la EIC no pregunta montos y la ENVI solo llega a estado. Cada
  tabla guarda lo suyo por separado; juntarlas en un "precio" sería un puntaje.
- **La precisión viaja con el valor.** La EIC guarda sus cinco estimadores en la
  misma fila; la ENVI calcula el error estándar por conglomerado último, como
  INEGI, y lo deja nulo en las medianas en vez de inventarlo. `MI` es nulo con
  nota, nunca cero.
- **Un año a medias no es una caída.** El SNIIV publica 2026 hasta agosto; cada
  fila guarda cuántos meses tiene su año.
- **Índice nacional por categoría.** La API del SHF no tiene serie nacional
  general; se guardan las seis categorías y nada inventado.
- **Solo agregados, ningún microdato.** La ENVI se reduce a 198 indicadores al
  cargar, igual que la ENOE.

## Bugs y sorpresas

- **Acentos "rotos" que no lo estaban:** los nombres del SNIIV se veían como
  `Jes�s Mar�a` en la consola de Windows. Los bytes eran UTF-8 correcto; lo roto
  era la consola (cp1252). Se revisó con `od -c` antes de escribir un reparador
  que no hacía falta.
- **INEGI responde 200 con HTML** a rutas que no existen, y `HEAD` responde lo
  mismo aunque el archivo exista. La ruta buena salió del JSON-LD de la página del
  programa (`../producto/pipeline-datos.md`).
- **Codificación por producto:** la EIC viene en latin-1 y la ENVI en UTF-8.
