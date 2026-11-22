# Grado de Rezago Social por AGEB urbana 2020 (CONEVAL)

Un grado de CONEVAL (muy bajo, bajo, medio, alto, muy alto) para cada una de las 61,430
AGEB urbanas, hecho con 17 indicadores del Censo 2020 (analfabetismo, asistencia escolar,
derechohabiencia, hacinamiento, servicios y bienes de la vivienda). En `/perfil`, en la
cédula censal: AGEB y personas en cada grado.

- **Dónde:** https://www.coneval.org.mx/Medicion/Documents/GRS_AGEB_2020/GRS_AGEB_urbana_2020.zip
  (16 MB, un Excel), desde la página
  https://www.coneval.org.mx/Medicion/IRS/Paginas/Rezago_social_AGEB_2020.aspx, que sigue
  en CONEVAL (2026-11-22) aunque CONEVAL ya pasó a INEGI.
- **Carga:** `python -m mapo_core.cli rezago_social GRS_AGEB_urbana_2020.xlsx`
  (`mapo_core/rezago_social.py`), a `fuente_rezago_social_ageb` con el grado y los 17
  porcentajes en `indicadores`. Un grado fuera de los cinco detiene la carga.
- **Reserva:** las AGEB con menos de 3 viviendas traen solo el grado (2,658): sus
  indicadores quedan `null`, y su población a veces también; el perfil no la cuenta como
  cero.
- **No es un puntaje de Mapo** ni una medición de pobreza (no usa ingreso): es el grado de
  CONEVAL con su método, y el perfil lo dice. Junto a la marginación de CONAPO, cuando entre
  a Mapo, irá aparte.

## Validación

Contra el comunicado 07 de CONEVAL (2022-07-26): 61,430 AGEB urbanas; 3,947 con grado muy
alto y 10,264 alto; 14.3 % muy bajo (8,769). Benito Juárez (Ciudad de México): sus 102
AGEB en muy bajo, con 434,153 personas. Todo igual a lo cargado.

## Pendiente

- Como capa en `/mapa` (grado por AGEB): hoy el acetato del censo es solo de variables del
  censo, con su cita; el grado necesita su propia leyenda de cinco clases.
- La marginación de CONAPO por AGEB (ya usada en la comparación de ciudades) en Mapo.
