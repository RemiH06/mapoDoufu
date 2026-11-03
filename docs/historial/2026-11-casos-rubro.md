# Fase 7: casos por rubro (noviembre 2026)

Prueba de los cinco casos de `../producto/rubros.md` en los dos modos,
con varias formas reales de preguntar contra los datos de Jalisco. Es la
revisión de la tabla de rubros que la Fase 6a dejó pendiente, ya con
preguntas de verdad.

## Qué se encontró y cómo quedó

| Hallazgo | Causa | Arreglo |
|---|---|---|
| En `/mapa`, "florería", "call center" y "policía" daban 0 negocios | El filtro buscaba texto en el nombre oficial de la clase | El filtro entiende los términos de la tabla y dice qué reconoció |
| "papeleria" sin acento daba 0 | `ILIKE` distingue acentos | Comparación contra las clases, normalizada |
| "súper" daba 760 en Zapopan | Coincidía con "minisúper" | Ahora es el rubro: 53 |
| "cuántos oxxos" daba 478 sin aviso | DENUE clasifica por giro, no por marca | Columna `marcas`: se reconoce y se avisa |
| "centros de salud" daba 852 | Caía en todo el sector salud, con farmacias y veterinarias | Término de consultorio, solo sector público |
| "estaciones de policía" incluye fiscalía y protección civil | DENUE las junta en una clase | Columna `nota`, que sale con la cifra |
| "bomberos" daba 2 en Zapopan | Casi todos están en la clase de seguridad | Nota en el rubro `emergencias` |
| "autoservicio" llevaba a comida rápida | Sinónimo mal puesto | Movido a supermercado |
| "comisaría", "fiscalía" y "contact center" no se reconocían | Faltaban | Agregados |
| El rubro de "gente para un call center" se ignoraba sin decirlo | `donde_contratar` no usa rubro | Se quita y se avisa; igual en `perfil` |
| La tabla decía "Negocios" para policías y hospitales públicos | Texto fijo | `unidad` en las cifras: "unidades" en gobierno y `solo_publicos` |

## Cifras reales después de los arreglos

| Caso | Zona | Modo técnico | Buscador |
|---|---|---|---|
| Florería | Zapopan | 305 | 305 |
| Call center | Zapopan | 15 | 15 |
| Supermercado | Zapopan | 53 | 53 |
| Consultorio médico | Zapopan | 555 | 555 |
| Seguridad pública | Zapopan | 28 | 28 |

Los dos modos dan lo mismo porque resuelven igual: un test lo revisa
caso por caso (`tests/test_casos_rubro.py`).

## Decisiones

- **La marca se reconoce, pero no filtra.** Filtrar por nombre daría una
  cifra incompleta y frágil: el mismo Oxxo aparece en tres clases y el
  nombre en DENUE lo captura cada quien. El buscador da el giro y lo
  dice.
- **"Centro de salud" implica sector público**, porque así se usa en
  México y así está en DENUE: 306 de los negocios con ese nombre son
  públicos.
- **Consultorio y hospital siguen separados** y sin niveles de atención,
  como dice `rubros.md`.
- **Lo que no tiene palabra de intención sigue sin adivinarse.** "Vivero
  en Tlajomulco" llena el rubro y el municipio y pide el tipo de pregunta.

## Lo que se aprendió

- **Los tests verdes no veían esto.** Cada función hacía lo que decía;
  los errores estaban entre una pregunta real y un dato real.
- **Una cifra correcta puede responder otra pregunta.** Los 478 "oxxos"
  y las 72 "estaciones de policía" salían de datos bien clasificados. Lo
  que faltaba era decir qué se estaba contando.
- **`render_async` espera 100 ms por defecto**: un test de `/logistica`
  falló 1 de 5 veces con la máquina cargada. Se subió a 1 s en
  `test_helper.exs`.
