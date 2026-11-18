# Pasada de seguridad, noviembre 2026

Sesión 17, el 2026-11-17. Repo completo, con foco en lo construido después de
la revisión del 2026-10-30 ([2026-10-hosteo.md](2026-10-hosteo.md)): subida de
archivos, autorización por equipo, CSV, buscador y dependencias. También se
cerraron los hallazgos bajos que quedaron abiertos en octubre.

## Hallazgos y correcciones

| Hallazgo | Riesgo | Qué se hizo |
|---|---|---|
| Un `.prj` de shapefile o la definición de proyección de un GeoPackage con `http://...` hacía que `mapo_core` pidiera esa URL (GDAL la descarga dentro de `CRS.from_user_input`) | Medio: SSRF a ciegas desde la red de Pixilate, que tiene salida a internet y alcanza la tailnet | La proyección se lee solo como WKT o `EPSG:n` (`from_wkt`, `from_epsg`). Prueba con un socket local que verifica que nadie se conecta |
| Repintar una capa propia en `/mapa` reusaba la capa del momento en que se abrió | Bajo: a quien sacan de un equipo con el mapa abierto podía seguir trayendo datos | `pintar_capa` vuelve a pasar por `Capas.get_capa/2` con el scope |
| La CSP no restringía `script-src` | Bajo, defensa en profundidad: un XSS que se colara podía cargar scripts de cualquier lado | CSP completa con nonce por petición para el único script en línea (el del tema). Revisada en navegador real en 16 pantallas: cero violaciones |
| Un admin podía sacar a otro admin o a un titular | Bajo | Un admin solo quita miembros o se sale él; a admins y titulares los quita un titular. El botón solo aparece cuando se puede |
| Los enlaces de invitación no caducaban y el token se guardaba en claro | Bajo: un respaldo filtrado daba enlaces vigentes para siempre | Se guarda el SHA-256; el enlace caduca a los 7 días del último envío, y reenviar da un enlace nuevo y anula el anterior. La migración convierte los tokens existentes, así que los enlaces ya enviados siguen sirviendo |
| Agregar a alguien por correo lo metía sin aceptar si ya tenía cuenta, y el mensaje distinto revelaba si el correo estaba registrado | Bajo | Siempre por invitación, con el mismo mensaje tenga o no cuenta (decisión de Remi). Mientras no haya correo real, el enlace sale del log como el resto |
| `mapo_core` dejaba `/docs` y `/openapi.json` abiertos y su 503 devolvía el texto de psycopg (host, usuario, base) | Bajo: solo lo alcanza `mapo` | Sin documentación de la API; el detalle del 503 va al log |
| El GeoPackage se abría sin el modo defensivo de SQLite | Endurecimiento | `SQLITE_DBCONFIG_DEFENSIVE` además de `trusted_schema=OFF`, `query_only` y el límite de tiempo |
| La etiqueta del popup de la coropleta se insertaba sin escapar | Ninguno hoy (solo llega si `mapo_core` aceptó el indicador de la lista cerrada) | Se escapa igual, para no depender de eso |
| La tailnet como puerta trasera daba 403 en el WebSocket | Operación | `PHX_ORIGENES_EXTRA` en el `.env`: orígenes aceptados además de `PHX_HOST` ([despliegue.md](../despliegue.md), Acceso) |

## Lo que se revisó y estaba bien

- **Subida de archivos.** Nada toca disco: CSV y XLSX se leen en memoria, el
  shapefile se lee del ZIP con `zipfile` (los nombres con `../` no importan
  porque no se extrae nada), el GeoPackage con `sqlite3.deserialize` y el
  GeoTIFF con `MemoryFile` y el driver fijo. La bomba de descompresión la frena
  el tamaño declarado de las piezas (200 MB); `zipfile` no lee más allá. El XLSX
  va por `openpyxl` con `defusedxml` activo (verificado en el contenedor), así
  que no expande entidades. El formato se elige por extensión, pero cada uno
  tiene su lector y un archivo disfrazado solo falla. Tope de 50 MB en LiveView
  y otra vez en `mapo_core`, que en producción no publica puerto y corre como
  `nobody`.
- **Autorización por equipo.** `/capas/:id/raster.png`, `/capas/:id/cruce.csv`,
  `/mapa?capa=`, la pantalla de cruce y los eventos `agregar_capa`, `ver_fila` y
  `borrar` pasan por un join contra la membresía. `cancelar_invitacion` y
  `remove_member` revisan el rol en el equipo de la invitación o membresía.
- **CSV descargable.** Las celdas de texto que empiezan con `=`, `+`, `-`, `@`,
  tabulador o retorno llevan un apóstrofo delante; el nombre del archivo lo
  codifica `send_download`.
- **Buscador y SQL.** El texto libre se interpreta en Python y nunca se arma como
  SQL. Los identificadores interpolados (indicador del censo, columnas del cruce,
  columna de ENIGH, tabla por nivel) salen de listas cerradas. Las plantillas no
  usan `raw`, y el JS que arma HTML escapa lo que viene del usuario (ficha,
  nombres de negocios, marcas).
- **Dependencias.** Sin avisos conocidos: `pip-audit` en `mapo_core`, la base de
  avisos de GitHub para los 46 paquetes de `mix.lock` (la consulta se comprobó
  con versiones vulnerables conocidas; `mix hex.audit` no alcanzó hex.pm desde
  el contenedor), `npm audit` en `scripts/capturas`, y Leaflet 1.9.4 y anime.js
  4.5.0 vendorizados.
- **Secretos.** Ni `docs/` ni la historia de git tienen llaves, contraseñas ni
  datos de la tailnet.

## Pendiente

- Las fuentes vienen de `fonts.bunny.net` y `cdn.jsdelivr.net`: cada visita le
  avisa a dos terceros. Servirlas desde Mapo quitaría las dos excepciones de la
  CSP.
- `mapo_core` instala sus dependencias con `>=`, sin archivo de bloqueo: cada
  `--build` puede traer versiones nuevas sin revisar.
