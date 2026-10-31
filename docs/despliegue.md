# Despliegue

Cómo se corre Mapo en producción. Lo de desarrollo está en
[desarrollo.md](desarrollo.md).

## Forma

`docker-compose.prod.yml` se monta encima de `docker-compose.yml`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

| Servicio | Imagen | Puerto en el host | Red |
|---|---|---|---|
| `mapo` | release de Phoenix (`mapo/Dockerfile.prod`) | `127.0.0.1:1865` | `interna` y `default` |
| `mapo_core` | la de dev, sin `--reload`, sin montajes y sin root | ninguno | `interna` y `default` |
| `db` | `postgis/postgis:16-3.4-alpine` | ninguno | `interna` |
| `osrm` | `ghcr.io/project-osrm/osrm-backend:v26.7.3-debian` | ninguno | `interna` |

- `name: mapo-prod` separa contenedores, redes y volúmenes de los de
  dev: la base de producción es el volumen `mapo-prod_mapo_db_data`.
- La red `interna` no tiene salida a internet. `mapo_core` también está
  en `default` para refrescar fuentes con el CLI; `mapo`, porque Docker
  no publica puertos desde una red interna.
- El único puerto en el host escucha en `127.0.0.1` y no es el 1864 de
  dev: si alguien levanta dev en el servidor por error, lo que se
  publique hacia fuera no incluye `/dev/mailbox` ni el dashboard.
- Todo lleva `restart: unless-stopped`, logs rotados (3 × 10 MB) y
  `healthcheck` (salvo OSRM, que no trae cliente HTTP en la imagen).

## Secretos

En `.env` junto al compose, con `chmod 600`. Plantilla: `.env.example`.

| Variable | Cómo se genera |
|---|---|
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` (solo hexadecimal: va dentro de `DATABASE_URL`) |
| `SECRET_KEY_BASE` | `openssl rand -base64 48` |
| `PHX_HOST` | el nombre con que se entra, sin `https://` |
| `MAPO_CONTACTO` | el correo que sale en `/privacidad` |
| `MAPO_OSRM_DATOS` | carpeta con `mexico-latest.osrm.*` |

El compose no arranca si falta alguna. `POSTGRES_PASSWORD` solo se
aplica la primera vez que se crea el volumen de la base; cambiarla
después es `ALTER USER mapo PASSWORD '...'` dentro de la base, además
del `.env`.

## Acceso

Sin dominio todavía: solo por Tailscale. En la máquina que hostea,
`tailscale serve --bg 1865` publica `https://<máquina>.<tailnet>.ts.net`
a la tailnet, con certificado. `PHX_HOST` es ese nombre: Phoenix
rechaza el WebSocket de LiveView si el origen no coincide.

Phoenix en prod redirige a HTTPS (`force_ssl`) y confía en
`X-Forwarded-Proto` para saber que la petición ya llegó cifrada. Al
publicar por primera vez, comprobar que no hay redirección en bucle:
`curl -sI https://<máquina>.<tailnet>.ts.net/` debe dar `200` con
`strict-transport-security`.

## Correo

No hay correo real hasta tener dominio. En prod el mailer es
`Swoosh.Adapters.Logger`: cada correo (enlace de acceso, invitación) se
escribe completo en el log, y quien administra lo reenvía a mano:

```bash
docker compose -p mapo-prod logs mapo | grep -A20 "Instrucciones"
```

Para crear una cuenta a mano y mandarle su enlace desde la terminal,
el proceso tiene que escribir en la salida del nodo y no en la de
`rpc` (si no, el correo aparece en la consola del `rpc` y no en el log):

```bash
docker compose -p mapo-prod exec mapo bin/mapo rpc '
  {:group_leader, gl} = Process.info(Process.whereis(Mapo.Repo), :group_leader)
  spawn(fn ->
    Process.group_leader(self(), gl)
    {:ok, u} = Mapo.Accounts.register_user(%{email: "alguien@correo.mx"})
    Mapo.Accounts.deliver_login_instructions(u, &"https://<PHX_HOST>/users/log-in/#{&1}")
  end)'
```

Los enlaces de acceso caducan en 15 minutos. El log los contiene
vigentes, así que solo lo lee quien opera el servidor.

## Migraciones

No corren solas al arrancar, para sacar un respaldo antes:

```bash
docker compose -p mapo-prod exec db pg_dump -U mapo -Fc mapo_prod > respaldo.dump
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm mapo bin/migrate
```

## OSRM

Sirve el mapa de México ya preprocesado (algoritmo MLD). Ocupa unos
8 GB en disco y 5.1 GB de RAM al cargar; tarda unos minutos en
responder después de arrancar (3.5 minutos medidos en Aerilate). Mientras tanto, `mapo_core` cae a línea
recta y lo dice en `metodo`. Detalle en [fuentes/osrm.md](fuentes/osrm.md).

## Operación

```bash
docker compose -p mapo-prod ps                       # estado y salud
docker compose -p mapo-prod logs -f --tail 100 mapo  # logs
docker compose -p mapo-prod stop mapo                # cortar el acceso
```

Antes de desplegar una versión nueva, `git tag deploy-AAAAMMDD` en la
que funciona; revertir es `git checkout <tag>` y el mismo `up -d --build`.

## Revisión de seguridad

Hecha el 2026-10-30 antes del primer despliegue
([historial/2026-10-hosteo.md](historial/2026-10-hosteo.md)): sin
hallazgos críticos ni altos. Lo que quedó abierto, con su riesgo, está
en ese mismo documento.
