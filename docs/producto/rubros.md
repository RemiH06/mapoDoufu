# Enfoques y rubros

## Enfoques temáticos (rubros de análisis)

| Enfoque | Fuente(s) que lo respaldan | Estado |
|---|---|---|
| Comercio | DENUE | Listo |
| Demografía | Censo de Población por AGEB | Listo |
| Consumo | ENIGH | Listo (advertencia: representativo a nivel estado/dominio, no municipal) |
| Seguridad | SESNSP | Listo (sin puntaje único, por decisión ya tomada en Gaiarda) |
| Laboral/empleo | ENOE | Listo (tasa de desocupación ponderada, a nivel estado: la ENOE no es representativa por municipio). Separado de demografía a propósito: demografía dice quién vive ahí, laboral dice si esa gente está disponible/empleada |
| Movilidad/accesibilidad (isócronas, tiempos de traslado) | Motor OSRM (ya propio, confirmado funcionando) | No es un enfoque con fuente propia, es una **capacidad transversal**: mide tiempo/distancia hasta lo que sea que se esté analizando, y cruza con todos los demás enfoques |
| Ambiental | Ninguna fuente actual | Real pero a futuro. Ninguna de las 7-8 fuentes de Gaiarda cubre calidad del aire, riesgo natural, uso de suelo o agua. Candidatas si se decide perseguir: SINAICA/RAMA (aire), CENAPRED (riesgo natural), CONAGUA/SEMARNAT (agua, uso de suelo). No prometer esto hasta integrar una fuente nueva |

**Principio de arquitectura, no solo de producto**: Mapo debe ser
escalable en sus herramientas Y en su estructura de datos (extracción,
consumo, despliegue), para que agregar un enfoque nuevo (ej. ambiental
el día que haya fuente) sea agregar un módulo, no reestructurar. Mismo
patrón que Gaiarda ya usa en `fuentes/`: cada fuente es un subpaquete
independiente que se autorregistra en un catálogo central.

## Casos de ejemplo iniciales (rubros de negocio para probar Mapo)

Para no diseñar en abstracto, los primeros rubros contra los que se
prueba Mapo (modo técnico y buscador):

- Floristería
- Call center
- Supermercado
- Consultorio médico / hospital (simplificado a **consultorio vs.
  hospital**, sin intentar mapear los niveles oficiales de atención
  médica: DENUE clasifica por código SCIAN, no por nivel de atención,
  y no vale la pena inventar una clasificación que la fuente no trae)
- Estación de policía: confirmado que DENUE la cubre, vía la clase
  `Mantenimiento de la seguridad y el orden público` (ver
  `../fuentes/denue.md`)
