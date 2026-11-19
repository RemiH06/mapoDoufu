# Áreas naturales protegidas federales (CONANP)

Las 182 áreas naturales protegidas federales de agosto de 2020, con su categoría y
decreto. Responde: **¿esta zona está dentro o cerca de un área protegida, y de qué
tipo?**

```bash
docker compose exec mapo_core python -m mapo_core.cli ambiental --crudos /app/data/crudos-ambiental --fuente anp
```

Unos 10 s. Reemplaza `fuente_anp`.

## De dónde sale

`anp2020gw.zip`, la copia del geoportal de CONABIO de "Áreas Naturales Protegidas
Federales de México, agosto 2020" (SEMARNAT-CONANP). En WGS84, UTF-8 sin `.cpg`.

**Licencia:** la copia de CONABIO es CC BY-NC 2.5 México (metadatos del zip: "no se
permite utilizar estos datos con fines lucrativos"). Para uso comercial hay que
cambiarla por la capa original de CONANP. Citar "CONANP, 2020" y "CONABIO".

## Qué se guarda

`id` (`ID_ANP`), `nombre`, `categoria` del decreto (PN parque nacional, RB reserva
de la biosfera, APFF, SANT santuario, PMN, MN, y categorías viejas sin recategorizar),
`estados`, superficies del decreto en hectáreas (total, terrestre y marina), fecha del
primer decreto y del último DOF.

## Validación (2026-11-19)

- 182 ANP y 90.84 millones de hectáreas decretadas, las cifras de CONANP para 2020
  (182 áreas, 90.8 millones de ha, terrestres y marinas).
- El área de los polígonos da 90.93 millones: 0.1 % de diferencia con la decretada.

## Límites

- Solo federales: las estatales y municipales no están (en Jalisco, el Bosque La
  Primavera sí, porque es federal). Revisar la lista estatal antes de decir que una
  zona no está protegida.
- Corte de agosto de 2020: las decretadas después no están.
- Una ANP de categoría vieja no recategorizada puede tener otra regulación real.
