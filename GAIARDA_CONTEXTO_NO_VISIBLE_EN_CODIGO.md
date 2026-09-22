# Gaiarda: contexto que Claude Code no puede deducir del código

Este documento junta todo lo que se decidió, se descartó o se aprendió en las conversaciones de este proyecto y que no queda escrito en ningún archivo del repo. La idea es que lo subas como contexto inicial en Claude Code para que no se repitan errores ya resueltos ni se reabran decisiones ya tomadas.

## Qué es Gaiarda y cómo se relaciona con Mapo

- Gaiarda es un monorepo con backend en Python y frontend en React/TypeScript. Descarga, normaliza y sirve datos abiertos del gobierno mexicano con un dashboard de mapa interactivo.
- Gaiarda es explícitamente el precursor de un segundo proyecto llamado Mapo (repo aparte, chat aparte). La división conceptual es:
  - Gaiarda responde "qué existe" en México (datos, infraestructura, geografía).
  - Mapo va a responder "qué deberías hacer con eso" (ruteo logístico, recomendaciones, colaboración en tiempo real).
- El feature de rutas turísticas (tema Odysseus) le pertenece a Gaiarda. El ruteo logístico de carga y pasajeros le pertenece a Mapo, no se debe meter en Gaiarda.
- Para Mapo ya se evaluó y priorizó el stack: Elixir + Phoenix es el mejor fit por la anotación colaborativa en tiempo real, seguido de Rust y Julia. Haskell quedó como prioridad baja para Mapo por el traslape con Rust y el costo de cambiar de paradigma. Otras herramientas que Remi está evaluando o aprendiendo en este contexto: HeidiSQL, Gatling, Rsync, Whimsical, Vim, Erlang, Scala, MXNet, Pascal.

## Fuentes de datos integradas

INEGI Marco Geoestadístico, CRE (gasolineras), DENUE (negocios, requiere token en `.env`), SESNSP (crimen), Censo de Población por AGEB, ENIGH (microdatos de gasto de hogares), ENOE (empleo), y CAPUFE (casetas de peaje).

CAPUFE es la única fuente sin descargador automático: usa un parser manual de TSV más geocodificación con OpenStreetMap/Overpass y geometría con shapely para cruces de ruta.

## Decisiones de alcance (el porqué, no solo el qué)

- **Hospedaje quedó fuera de alcance a propósito.** La columna `vivienda` de ENIGH mide renta de residentes, no tarifas de hotel. Meterla sería engañoso para un caso de uso de viaje. Esto no es una tarea pendiente, es una exclusión deliberada por fidelidad de los datos.
- **ENIGH `resumen.py` soporta `por_dia=True`**, que convierte de trimestral a diario usando 91.25 días según la metodología de INEGI. Importante: el dato es por hogar, no por persona. Cualquier cálculo per cápita necesita un ajuste aparte que no está implementado.

## Bugs ya resueltos y por qué importan (para no repetirlos)

- **Delimitador de ENIGH:** el CSV se estaba leyendo con tab en vez de coma, corrompía todas las filas en silencio. Los tests que comparten la misma suposición equivocada que el código que prueban se quedan en verde para siempre. Solo correr contra datos reales descargados detectó el bug. Por eso hay que mantener tests de integración contra datos de producción, no solo unitarios con mocks.
- **Desincronización de checkpoint:** si se borra `geo.db` pero sobrevive `checkpoint.json`, las descargas terminan en "éxito" con cero filas, en silencio. El patrón de solución es la bandera `--forzar` en los comandos CLI de ENIGH/ENOE, que ya existe para saltarse ese bug.
- **Selectores CSS descendiente vs compuesto:** `.metro .app-shell` (descendiente, mal) contra `.metro.app-shell` (compuesto, mismo elemento, correcto). Este error rompió en silencio todas las reglas de altura y overflow desde que se creó el layout inicial. Vale la pena revisar si queda algún selector con este patrón mal escrito en otras partes del CSS.
- **OSRM auto-hospedado confirmado funcionando** en Docker/WSL2 con 16GB de RAM. El extract de México llega a picos cercanos a 14.8-15GB, así que cualquier entorno con menos RAM se va a quedar corto.

## Estado al momento de este resumen (versión 0.3.0)

- Completo: fuente completa de casetas CAPUFE (`fuentes/casetas/`) con parser TSV manual, geocodificación Overpass y geometría shapely para cruces de ruta.
- Completo: sidebar redimensionable en el Dashboard (220 a 520px), persistido en localStorage vía el hook `useAnchoRedimensionable`.
- Completo: bandera `--forzar` en comandos CLI de ENIGH/ENOE.
- Completo: bug de delimitador de ENIGH corregido.
- GitHub Pages confirmado activo.
- Suite de pruebas en 170 tests pasando. Playwright se usa específicamente para pruebas visuales del sidebar.
- `GAIARDA_ESTADO.md` es el documento canónico de handoff para el chat de Mapo, se mantenía actualizado con decisiones, bugs y aprendizajes. Vale la pena revisar si ese archivo sigue existiendo y sigue vigente en el repo que vas a pasar a Claude Code.

## Cómo se trabajaba aquí (acuerdos de forma de trabajo)

Esto es contexto de proceso, no de producto, pero puede ser útil si le vas a pedir a Claude Code que trabaje con la misma disciplina:

- Todo cambio de código se reflejaba de inmediato en los README de raíz, backend y frontend, en `docs/index.html`, y en `GAIARDA_ESTADO.md`, en el mismo turno, sin documentación diferida.
- Nomenclatura con prefijo de módulo cuando hay riesgo de colisión de nombres (`casetas_db.py`, no `db.py`).
- Se probaba antes de entregar, y los cambios visuales o de UI se renderizaban para revisión antes de mandarlos.
- Español mexicano en todo el contenido y documentación de cara al usuario, sin guión largo en ninguna parte.

## Stack técnico como contexto (no solo lo que dice el código)

- Backend: Python, FastAPI, SQLite, shapely, dbfread, con módulos compartidos `comandos.py`, `consola.py`, `rutas.py`.
- Frontend: React, Vite, TypeScript, react-leaflet, react-leaflet-cluster. Tipografías Space Mono/DM Sans para el tema Metro, IM Fell English para el tema Odysseus.
- Ruteo: OSRM auto-hospedado vía Docker/WSL2.
- Geocodificación: OpenStreetMap Overpass API.
