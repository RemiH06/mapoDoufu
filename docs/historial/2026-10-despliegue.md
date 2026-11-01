# Primer despliegue, octubre 2026

Sesión del 2026-10-31. Mapo corriendo en la máquina de casa con GPU,
dentro del Docker de su WSL (Debian), publicado solo a la tailnet. El
compose y los secretos venían de [la sesión anterior](2026-10-hosteo.md);
cómo se opera está en [despliegue.md](../despliegue.md).

## Qué quedó

- Código en `~/srv/mapo` (clon de git), `.env` nuevo con secretos
  generados en la misma máquina y `chmod 600`.
- OSRM en `~/srv/mapo-osrm`, en el disco de WSL y no en `C:`. Los 26
  archivos se verificaron con `sha256sum` contra el origen.
- Base con las fuentes copiadas de dev (ver abajo) y las tablas de
  cuentas vacías.
- `tailscale serve --https=1865`: se entra por
  `https://<máquina>.<tailnet>.ts.net:1865`.
- Respaldo con `scripts/respaldo.sh` y una restauración probada.

## Bug: la URL de mapo_core quedaba fija al construir

`/mapa` y `/perfil` se quedaban en `phx-loading` y el log decía
`connection refused` contra `mapo_core`. `config/config.exs` leía
`MAPO_CORE_URL` con `System.get_env`, pero en un release ese archivo se
evalúa al construir la imagen: la URL quedó en el valor por defecto,
`http://localhost:8010`, que dentro del contenedor no es nada. El
`MAPO_CORE_URL` correcto del compose llegaba al contenedor y nadie lo
leía. En dev no se nota porque Mix vuelve a evaluar `config.exs` en
cada arranque.

Se movió a `config/runtime.exs` (fuera de test, que usa su URL falsa).
El ensayo en la laptop de la sesión anterior no lo detectó porque solo
se revisó que la portada respondiera; `/mapa` pide sesión. Ahora la
prueba en navegador entra con una cuenta y abre `/mapa`, `/perfil` y
`/logistica`.

## El 443 ya estaba ocupado

La máquina ya publicaba otro proyecto en el 443 de la tailnet. El plan
decía `tailscale serve --bg 1865`, que lo habría reemplazado sin
avisar. Mapo va en su propio puerto HTTPS (`--https=1865`) y se agregó
`PHX_PORT` para que la URL de Phoenix lo lleve: sin él, los enlaces de
acceso de los correos salían sin puerto y apuntaban al otro proyecto.
El origen del WebSocket no cambia (Phoenix compara solo el host).

`force_ssl` no redirige en bucle: `tailscale serve` manda
`X-Forwarded-Proto`, y `curl -sI` da `200` con
`strict-transport-security`.

## Datos: copiar en vez de descargar

Solo las tablas de fuentes, con `pg_dump -t` (255 MB comprimido para 30
millones de filas de SESNSP y 400 mil de DENUE), restauradas en 6.5
minutos antes de levantar `mapo_core`. Las cuentas de dev eran de
prueba y no se copiaron. Los conteos de las nueve tablas coinciden con
el origen.

## Medido

- OSRM responde a los 13 segundos de arrancar (3.5 minutos en el
  ensayo, con los datos en una carpeta de Windows montada).
- Isócrona de 10 minutos en Guadalajara: `metodo: osrm_real`.
- Con todo arriba quedan unos 7 GB libres de los 16 de WSL.
- Prueba en navegador por la tailnet: registro, enlace del log con
  `:1865`, sesión, y `/mapa`, `/perfil` y `/logistica` conectadas sin
  errores de consola. Las cuentas de prueba se borraron.

## Tropiezos de operar por SSH

- La copia de OSRM se cortó a los 2 minutos: la máquina salió de la
  tailnet un momento (no se reinició). Iba por relay; al volver iba
  directo. Se reanudó archivo por archivo comparando tamaños.
- Un `docker compose exec -T` dentro de un script mandado por stdin se
  traga el resto del script. Lleva `< /dev/null`.
- `setsid nohup ... &` dentro de `wsl -- bash -s` no sobrevive al
  cierre de la sesión: la construcción se corrió en primer plano.
