# Gaiarda: cómo calcula rutas

## Referencia técnica: el módulo de rutas de Gaiarda

Gaiarda ya tiene un TSP heurístico funcional
(`gaiarda/src/gaiarda/rutas.py`): vecino más cercano + 2-opt, con
soporte de inicio/fin forzoso por parada y rutas circulares. Es para
turismo (un viajero, sin restricciones de carga), pero es un buen
punto de partida técnico para la logística de Mapo.

Actualización importante desde que se escribió la primera versión de
este documento: Gaiarda **ya no depende solo de línea recta**. Hay un
cliente de motor de ruteo real por carretera
(`gaiarda/src/gaiarda/ruteo_osrm.py`, protocolo OSRM estándar), que
Mapo puede reutilizar directo en vez de escribir uno desde cero: usa
el servidor demo público de OSRM por default (configurable a un OSRM
propio vía `GAIARDA_OSRM_URL`, con guía de despliegue en
`gaiarda/docs/osrm_propio.md`), y cae de vuelta a línea recta si el
servicio no responde, sin tronar. La distancia real de carretera para
logística comercial que se preveía como trabajo pendiente aquí, ya
está resuelta a nivel de cliente HTTP; lo que Mapo sí tiene que
construir encima es lo específico de logística que Gaiarda no
necesita: múltiples vehículos, capacidad de carga, ventanas de tiempo
de entrega, y paradas comerciales con restricciones propias (no un
viajero libre visitando lo que quiera).

## Detalle técnico: cómo se calculan las rutas (a fondo)

Como Mapo va a construir su propia logística encima de esta base, vale
la pena el detalle completo de principio a fin, no solo el resumen.

### 1. Entrada

El frontend manda `POST /rutas/calcular` con:
- `municipios`: lista de `cvegeo` (5 dígitos, `cve_ent`+`cve_mun`)
- `inicio_forzado` / `fin_forzado`: opcionales, un `cvegeo` de la
  lista. Si ambos son el mismo municipio, la ruta sale circular.

### 2. De municipio a coordenada

`server.py` busca cada municipio en la tabla `municipios`, y para cada
uno llama a `gaiarda_rutas.centroide_desde_geojson(ruta_geojson)`:
lee el `.geojson` de ese municipio y calcula el centroide como
**promedio simple de los vértices del anillo exterior** del polígono
(no `shapely.centroid`, que se comporta raro con anillos con hoyos y
no hace falta esa precisión para ubicar "más o menos dónde está" un
municipio). Si el municipio es un `MultiPolygon` (islas, enclaves), se
usa el polígono con más vértices como cuerpo principal. Si falta el
`.geojson` de algún municipio pedido, el endpoint regresa 500 con la
lista exacta de cuáles faltan, no truena a medias.

### 3. La matriz de distancias: real o de respaldo

Con los centroides en mano (`lat, lon` por municipio, en el MISMO
orden que llegó `municipios`), `server.py` intenta:

```python
matriz_real = ruteo_osrm.matriz_carretera(coords_para_osrm)
```

Esto pega una sola vez al servicio `table` de OSRM (no N² llamadas
sueltas), pidiendo distancias Y duraciones para TODOS los pares a la
vez. Si el servicio no responde, tronó, o algún par de puntos no es
alcanzable por carretera (OSRM regresa `null` en esa celda, ej. una
isla), `matriz_carretera` regresa `None` completo (una matriz a
medias no sirve para el TSP, se descarta entera en vez de intentar
repararla). En ese caso, `resolver_orden_visita` (en `rutas.py`)
construye la matriz con `distancia_haversine_km` (línea recta sobre la
esfera terrestre, fórmula de haversine) en su lugar.

El resultado siempre trae `metodo`: `"carretera_real"` o
`"linea_recta_aproximada"`. Nunca se le hace pasar una aproximación
por un dato confirmado.

### 4. El TSP en sí: heurística, no óptimo exacto

Sobre la matriz (real o de respaldo), en `rutas.resolver_orden_visita`:

1. **Vecino más cercano** (`_vecino_mas_cercano`): parte del primer
   punto (o del `inicio_forzado`, si se pidió, que se intercambia a la
   posición 0 antes de este paso), y en cada paso salta al punto no
   visitado más cercano al actual. Rápido, da una solución inicial
   razonable pero no óptima.
2. **Mejora 2-opt** (`_mejorar_2opt` para ruta abierta,
   `_mejorar_2opt_circular` para ruta cerrada): si invertir un tramo
   de en medio de la ruta la acorta, se invierte. Se repite hasta que
   ya no hay mejora posible. Para ruta abierta, las posiciones 0
   (inicio) y última (fin) nunca se tocan, así que un `inicio_forzado`
   / `fin_forzado` ya colocado ahí se queda garantizado en su lugar.
   Para ruta circular, solo se protege la posición 0 (el resto del
   circuito, incluyendo el tramo de regreso, sí se puede reacomodar).

No es óptimo garantizado (el TSP exacto es impráctico para más de
unas cuantas decenas de puntos), pero para las paradas que alguien
selecciona a mano en un viaje, la diferencia contra el óptimo real es
mínima y el cómputo es instantáneo.

### 5. Qué trae el resultado

```jsonc
{
  "orden": ["29018", "29033", ...],          // cvegeo en orden de visita
  "orden_nombres": ["Tlaxcala", "Apizaco"],   // solo para mostrar
  "tramos": [
    {
      "desde": "29018", "hasta": "29033",
      "desde_nombre": "Tlaxcala", "hasta_nombre": "Apizaco",
      "distancia_km": 15.2,
      "duracion_horas": 0.3                    // solo si metodo=carretera_real
    }
  ],
  "distancia_total_km": 15.2,                  // suma de tramos
  "duracion_total_horas": 0.3,                 // solo si metodo=carretera_real
  "es_circular": false,
  "metodo": "carretera_real",                   // u "linea_recta_aproximada"
  "geometria": { "type": "LineString", "coordinates": [[lon,lat], ...] }  // o null
}
```

`geometria` es una llamada APARTE (`ruteo_osrm.geometria_ruta`, al
servicio `route` de OSRM, no `table`) que se hace DESPUÉS de resolver
el orden de visita, pidiendo el trazado real siguiendo ese orden ya
decidido. Solo se intenta si `matriz_real` sí respondió (si ya se cayó
a línea recta, no tiene caso pedir un trazado real). También puede
regresar `None` si esa llamada específica falla aunque la de la
matriz haya funcionado.

### 6. Rutas guardadas

`rutas_guardadas` (SQLite) no normaliza cada tramo como su propia
fila: guarda `municipios_json` y `resultado_json` (el dict completo de
arriba, serializado) como texto, más `nombre`, `fecha_creacion`,
`presupuesto_estimado`, `notas`. Una ruta guardada se lee/escribe
siempre completa; no hay ninguna ventaja real en normalizarla más allá
de eso, solo complejidad de más.

### 7. Seguridad y presupuesto (no son parte del cálculo de ruta, se anexan aparte)

- **Seguridad** (`GET /rutas/seguridad`): por cada municipio, cuenta
  delitos de SESNSP del año más reciente disponible, agrupados por
  tipo. A propósito NO se combina en un solo "puntaje de seguridad":
  eso implicaría decisiones de metodología (¿un homicidio pesa igual
  que un robo sin violencia?) que no se deben esconder detrás de un
  número.
- **Presupuesto de gasolina**: `distancia_total_km ÷ rendimiento_km_por_litro
  × precio_promedio_regular` (precio de `GET
  /rutas/precio_gasolina_promedio`, promedio de las estaciones CRE ya
  descargadas). El rendimiento lo ajusta quien usa el dashboard.
- **Presupuesto de casetas** (`gaiarda.casetas_en_ruta`, parte de la
  respuesta de `POST /rutas/calcular`, no un endpoint aparte): compara
  la `geometria` real de la ruta (una `LineString`) contra cada caseta
  ya geocodificada, usando `shapely` (`punto.distance(linea)`,
  convertido de grados a metros con el factor `111,320`, aproximación
  suficiente para una tolerancia de ~300m, no una proyección
  cartográfica real). Suma la tarifa de `automovil` de las que caen
  dentro de la tolerancia. Las tarifas de CAPUFE se cargan a mano
  (`gaiarda casetas --archivo`, no hay downloader automático posible:
  `datos.gob.mx` bloquea acceso automatizado); la ubicación de cada
  caseta se geocodifica aparte cruzando nombres contra nodos
  `barrier=toll_booth` de OpenStreetMap vía Overpass
  (`gaiarda casetas_geocodificar`), con desambiguación honesta (si dos
  candidatos son casi igual de parecidos, no adivina, deja la plaza
  sin geocodificar). Ver `gaiarda/docs/casetas.md` para el detalle
  completo del flujo manual.
- **Gasto diario estimado** (`GET /fuentes/enigh/resumen?por_dia=true`,
  columna `alimentos`, mostrado por parada en el dashboard): trimestral
  de ENIGH dividido entre 91.25 días. **Por hogar, no por persona**
  (sin ajuste per cápita). Siempre trae
  `n_hogares_muestra`, porque ENIGH es representativo a nivel estado y
  dominio rural/urbano, NO a nivel municipio (confirmado contra la
  ficha metodológica oficial de INEGI). No se usa para hospedaje: el
  gasto de vivienda de ENIGH es renta de residentes, no tarifa de
  hotel para alguien de fuera, son categorías de gasto que no se
  corresponden.

### Lo que Mapo va a necesitar encima de esto

El cliente OSRM (`ruteo_osrm.py`), la construcción de matriz, y el
patrón de geocodificación por nombre contra OSM (`casetas/geocodificar.py`,
con desambiguación honesta) son reutilizables tal cual. Lo que Gaiarda
NO resuelve, y Mapo sí va a necesitar: múltiples vehículos
simultáneos, capacidad de carga por vehículo, ventanas de tiempo de
entrega por parada, y paradas comerciales con restricciones propias
(esto ya no es TSP de un viajero libre, es VRP con restricciones, un
problema de optimización distinto).
