defmodule Mapo.MapoCore do
  @moduledoc """
  Cliente HTTP hacia mapo_core, el motor de datos/decision en Python.
  mapo_core tiene sus propios datos geograficos/censo (vendorizados de
  Gaiarda, descargados por mapo_core mismo, sin depender de un
  Gaiarda corriendo en ningun lado). Nunca lanza: cualquier falla de
  red o de mapo_core regresa `{:error, _}`, para que quien llama
  decida como mostrarla.
  """

  @doc """
  Los indicadores validos para `coropleta_censo_poblacion/3`, con
  etiqueta en espanol para mostrar en un selector. Debe mantenerse
  igual al `INDICADORES_CHOROPLETH` de `mapo_core/src/mapo_core/server.py`.
  """
  def indicadores_censo do
    [
      {"pobtot", "Población total"},
      {"pobfem", "Población femenina"},
      {"pobmas", "Población masculina"},
      {"p_0a2", "Población de 0 a 2 años"},
      {"p_3a5", "Población de 3 a 5 años"},
      {"p_6a11", "Población de 6 a 11 años"},
      {"p_12a14", "Población de 12 a 14 años"},
      {"p_15a17", "Población de 15 a 17 años"},
      {"p_18a24", "Población de 18 a 24 años"},
      {"p_60ymas", "Población de 60 años o más"},
      {"graproes", "Grado promedio de escolaridad"},
      {"pea", "Población económicamente activa"},
      {"pea_f", "Población económicamente activa, mujeres"},
      {"pea_m", "Población económicamente activa, hombres"},
      {"pe_inac", "Población económicamente inactiva"},
      {"pocupada", "Población ocupada"},
      {"pdesocup", "Población desocupada"},
      {"pder_ss", "Población con acceso a servicios de salud"},
      {"tothog", "Total de hogares"},
      {"vivtot", "Total de viviendas"},
      {"tvivhab", "Viviendas habitadas"},
      {"prom_ocup", "Promedio de ocupantes por vivienda"},
      {"vph_inter", "Viviendas con internet"},
      {"vph_pc", "Viviendas con computadora"},
      {"vph_autom", "Viviendas con automóvil"},
      {"vph_cel", "Viviendas con celular"},
      {"vph_snbien", "Viviendas sin ningún bien"}
    ]
  end

  @doc """
  FeatureCollection de los estados, sin polígono (`geometry` en `nil`):
  solo se usa para llenar selects, y con polígono pesa 3 MB.
  """
  def estados, do: get("/geo/estados", geometria: false)

  @doc "FeatureCollection de los municipios de un estado, sin polígono (igual que `estados/0`)."
  def municipios(cve_ent), do: get("/geo/municipios", cve_ent: cve_ent, geometria: false)

  @doc "FeatureCollection de los AGEB urbanos de un municipio, con polígono simplificado."
  def agebs(cve_ent, cve_mun), do: get("/geo/agebs", cve_ent: cve_ent, cve_mun: cve_mun)

  @doc """
  FeatureCollection de AGEBs del censo, con el valor de `indicador` ya
  cruzado en `properties.valor_choropleth` (puede venir `null`, si el
  AGEB no tiene ese dato: nunca se inventa un cero). Cada AGEB trae su
  `area_km2` y un punto de dentro (`centro`); con `extras`, esas columnas
  del censo en `properties.valores` (docs/producto/escalas.md).
  """
  def coropleta_censo_poblacion(indicador, zona, extras \\ []) do
    # Una clave `extra` por columna: así las lee FastAPI como lista.
    get(
      "/censo/choropleth",
      [indicador: indicador, zona: zona] ++ Enum.map(extras, &{:extra, &1})
    )
  end

  @doc """
  Diagrama de Voronoi de los negocios de DENUE de una zona (clave de la zona
  común, docs/producto/zona.md), opcionalmente filtrados por `clase_actividad`,
  recortado a la zona. Los negocios cercanos de fuera también compiten: sus
  celdas traen `"fuera" => true`.
  """
  def voronoi_denue(zona, clase_actividad \\ nil) do
    params = [zona: zona] |> maybe_put(:clase_actividad, clase_actividad)
    get("/voronoi/denue", params, receive_timeout: 60_000)
  end

  @doc """
  Sugerencias del selector de zona: `%{"resultados" => [%{"clave", "tipo",
  "nombre", "detalle"}], "aviso" => texto o nil}`.
  """
  def zona_buscar(texto), do: get("/zona/buscar", q: texto)

  @doc """
  Una clave de zona (`mun:14039`, `zm:14.1.01`, `col:14098_0135`...) a su
  nombre, polígono, área y municipios. 422 si la clave no sirve, 404 si no
  hay nada cargado con ella.
  """
  def zona_resolver(clave), do: get("/zona/resolver", clave: clave)

  @doc """
  Los municipios de los estados que toca la zona, cada uno con
  `properties.color_indice` ya calculado (teorema de las 4 colores: dos
  municipios vecinos nunca traen el mismo índice), listos para pintar en un
  mapa categórico.
  """
  def coloreado_municipios(zona), do: get("/coloreado/municipios", zona: zona)

  @doc """
  Indicadores de la vista de vivienda (fuente, etiqueta, unidad), segmentos
  del SNIIV y sus años con cuántos meses trae cada uno.
  """
  def vivienda_catalogo, do: get("/vivienda/catalogo", [])

  @doc """
  Municipios de los estados que toca la zona con el valor de un indicador
  de vivienda de una sola fuente en `valor_choropleth` (`null` si no hay
  dato), más su `metodo` y su nivel; el precio por AGEB, solo dentro de la
  zona. `anio` y `segmento` solo cuentan para el SNIIV.
  """
  def vivienda_municipios(zona, indicador, anio \\ nil, segmento \\ nil) do
    params =
      [zona: zona, indicador: indicador]
      |> maybe_put(:anio, anio)
      |> maybe_put(:segmento, segmento)

    get("/vivienda/municipios", params)
  end

  @doc """
  Vista de riesgos: cada peligro de una zona por separado, con la gente que
  vive dentro y cerca. `zona` es la clave de la zona común (un círculo es
  `cir:lon,lat,radio`). Un municipio grande tarda varios segundos.
  """
  def riesgos_zona(zona, cerca_m) do
    get("/riesgos/zona", [zona: zona, cerca_m: cerca_m], receive_timeout: 120_000)
  end

  @doc """
  Solo lo que se dibuja de cada peligro pedido (lista de claves), sin contar
  gente: el acetato "Riesgos" de `/mapa`.
  """
  def riesgos_capas(zona, cerca_m, peligros) do
    get("/riesgos/capas", [zona: zona, cerca_m: cerca_m, peligros: Enum.join(peligros, ",")],
      receive_timeout: 60_000
    )
  end

  @doc """
  Rutas y paradas de transporte público que pasan por una zona (clave de la
  zona común; docs/fuentes/gtfs.md): las del GTFS con su frecuencia en hora
  pico o, si ningún GTFS la toca, las de OSM sin horarios (`"origen"` dice
  cuál). 422 si la zona pasa de 5,000 km².
  """
  def transporte_zona(zona) do
    get("/transporte/zona", [zona: zona], receive_timeout: 60_000)
  end

  @doc """
  Accesibilidad a servicios de una zona (clave de la zona común), a pie o en
  auto: por servicio, cuánta gente de su grupo vive a cada minuto o menos, y
  los minutos de cada lugar para el plano (docs/producto/accesibilidad.md).
  """
  def accesibilidad_zona(zona, modo) do
    get("/accesibilidad/zona", [zona: zona, modo: modo], receive_timeout: 60_000)
  end

  @doc """
  Fecha (`"AAAA-MM-DD"`) de la última carga de una tabla citable, del estado
  si la tabla es por estado; `nil` si no hay o mapo_core no responde. Es la
  versión que lleva la cita de las tablas que no traen una propia.
  """
  def carga(tabla, cve_ent \\ nil) do
    case get("/fuentes/carga", maybe_put([tabla: tabla], :cve_ent, cve_ent)) do
      {:ok, %{"cargada" => fecha}} when is_binary(fecha) -> fecha
      _ -> nil
    end
  end

  @doc "SHF, SNIIV, Intercensal 2025 y ENVI de un municipio, cada una con su nivel."
  def vivienda_ficha(cve_ent, cve_mun),
    do: get("/vivienda/ficha", cve_ent: cve_ent, cve_mun: cve_mun)

  @doc """
  Polígono del área alcanzable desde `(lat, lon)` en `minutos`, por
  carretera real (OSRM) si está disponible, o un círculo aproximado si
  no. `metodo` en el resultado siempre dice cuál de los dos se usó.
  """
  def isocrona_calcular(lat, lon, minutos, num_direcciones \\ 16) do
    post("/isocronas/calcular", %{
      lat: lat,
      lon: lon,
      minutos: minutos,
      num_direcciones: num_direcciones
    })
  end

  @doc """
  Cuánta gente vive dentro de cada isócrona (`poligonos`, GeoJSON de
  `isocrona_calcular/4`), en todas y en alguna, con la intersección para
  dibujarla (docs/producto/isocronas.md).
  """
  def isocronas_poblacion(poligonos), do: post("/isocronas/poblacion", %{poligonos: poligonos})

  @doc """
  Perfil de un municipio, una sección por enfoque: demografía (censo),
  comercio (DENUE), consumo (ENIGH), seguridad (SESNSP) y laboral (ENOE).
  Una sección viene `nil` si su fuente no cubre el municipio. Laboral es
  del estado entero: la ENOE no es representativa por municipio.
  """
  def perfil_zona(cve_ent, cve_mun), do: get("/perfil_zona", cve_ent: cve_ent, cve_mun: cve_mun)

  @doc """
  Resuelve el ruteo de vehículos (VRP) con capacidad y ventanas de
  tiempo opcionales, vía OR-Tools. `paradas` es una lista de mapas con
  `lat`/`lon`/`demanda` (y opcionalmente `ventana_inicio_min`/
  `ventana_fin_min`); `capacidades_vehiculos` es una lista con la
  capacidad de cada vehículo disponible. Intenta distancia real por
  carretera (OSRM) primero; el resultado siempre dice en `metodo` si
  se usó eso o una aproximación en línea recta, y cada ruta trae
  `geometria` (GeoJSON real) cuando sí hubo carretera real.
  """
  def vrp_calcular(paradas, capacidades_vehiculos, deposito \\ 0, velocidad_kmh \\ 40.0) do
    post("/vrp/calcular", %{
      paradas: paradas,
      capacidades_vehiculos: capacidades_vehiculos,
      deposito: deposito,
      velocidad_kmh: velocidad_kmh
    })
  end

  @doc """
  Lo que llena las plantillas del modo buscador: intenciones, sectores con
  sus rubros y grupos de edad del censo (docs/producto/buscador.md).
  """
  def buscador_catalogo, do: get("/buscador/catalogo", [])

  @doc """
  Pregunta en español común -> `%{"plantilla", "faltan", "avisos",
  "reconocidos"}`. Determinista: lo que no reconoce lo dice en `avisos`.
  """
  def buscador_interpretar(texto, cve_ent),
    do: post("/buscador/interpretar", %{texto: texto, cve_ent: cve_ent})

  @doc """
  Autocompletado de la pregunta -> `%{"sugerencias" => [%{"texto", "completa",
  "nombre", "tipo"}]}`: cada una es la pregunta entera con la última palabra
  completada, con el vocabulario del analizador.
  """
  def buscador_sugerir(texto, cve_ent),
    do:
      post("/buscador/sugerir", %{texto: texto, cve_ent: cve_ent},
        receive_timeout: 3_000,
        retry: false
      )

  @doc """
  Plantilla completa -> `%{"capas", "cifras", "avisos"}` con las mismas
  consultas del modo técnico, o `%{"perfil" => %{...}}` para ir a /perfil.
  Si le falta un hueco, `{:error, {:status, 422, %{"detail" => %{"faltan" => ...}}}}`.
  """
  def buscador_resolver(cve_ent, plantilla),
    do: post("/buscador/resolver", %{cve_ent: cve_ent, plantilla: plantilla})

  @doc """
  Zonas candidatas de un `donde_poner`: `%{"filas", "cvegeos", "criterios",
  "descartes", "avisos", ...}`. La primera vez calcula los minutos con OSRM y
  puede tardar más que el `receive_timeout` por defecto (15 s de Req).
  """
  def buscador_zonas(cve_ent, plantilla, criterios) do
    post(
      "/buscador/zonas",
      Map.merge(criterios, %{"cve_ent" => cve_ent, "plantilla" => plantilla}),
      receive_timeout: 60_000
    )
  end

  @doc """
  Patrón del rubro de un `donde_poner` o `cuantos`: `%{"agrupacion",
  "plazas", "junto_a", "focos", ...}`. Son 199 sorteos sobre todos los negocios
  de los municipios: con la zona metropolitana tarda unos segundos.
  """
  def buscador_patron(cve_ent, plantilla) do
    post("/buscador/patron", %{cve_ent: cve_ent, plantilla: plantilla}, receive_timeout: 60_000)
  end

  @doc """
  Lee un archivo del usuario sin guardarlo: `%{"columnas", "muestra",
  "num_filas", "avisos", "sugerencia"}`. Si el archivo no sirve, regresa
  `{:error, {:status, 422, %{"detail" => mensaje}}}` con el motivo.
  """
  def datos_leer(contenido, formato), do: post_archivo("/datos/leer", contenido, formato: formato)

  @doc """
  Ubica los renglones del archivo: `%{"filas", "descartes", "numericas",
  "repetidas", "columnas", "num_filas", "avisos"}`. `ubicacion` es `tipo` más
  `lat` y `lon`, o `clave`.
  """
  def datos_ubicar(contenido, formato, ubicacion) do
    post_archivo("/datos/ubicar", contenido, [{:formato, formato} | ubicacion])
  end

  @doc """
  Los valores de la primera banda de un GeoTIFF en teselas WKB de PostGIS:
  `{:ok, info, teselas}`. Ver `/datos/raster_valores` en mapo_core.
  """
  def raster_valores(contenido) do
    with {:ok, cuerpo} <- post_archivo("/datos/raster_valores", contenido, []),
         <<largo::32, info::binary-size(largo), resto::binary>> <- cuerpo do
      {:ok, Jason.decode!(info), teselas(resto, [])}
    else
      {:error, _} = error -> error
      _ -> {:error, :respuesta_rara}
    end
  end

  defp teselas(<<>>, acc), do: Enum.reverse(acc)

  defp teselas(<<largo::32, tesela::binary-size(largo), resto::binary>>, acc),
    do: teselas(resto, [tesela | acc])

  @doc "FeatureCollection de las zonas de `claves` que existan en el marco cargado."
  def geo_por_clave(nivel, claves), do: post("/geo/por_clave", %{nivel: nivel, claves: claves})

  @doc """
  Distancia de renglones (`%{filas: [%{id, geometria}], radio, ambito}`) a las
  localidades del censo 2020. Ver `/localidades/distancia` en mapo_core.
  """
  def localidades_distancia(solicitud),
    do: post("/localidades/distancia", solicitud, receive_timeout: 120_000)

  @doc """
  Cruza renglones de una capa con fuentes públicas, por zona. Con los minutos
  por calle y 50 mil renglones puede tardar: en Aerilate, unos 30 s.
  """
  def cruce_calcular(solicitud),
    do: post("/cruce/calcular", solicitud, receive_timeout: 120_000)

  defp post_archivo(path, contenido, params) do
    opts =
      [
        base_url: Application.fetch_env!(:mapo, :mapo_core_url),
        url: path,
        params: params,
        body: contenido,
        headers: [content_type: "application/octet-stream"],
        receive_timeout: 120_000
      ] ++ Application.get_env(:mapo, :mapo_core_req_options, [])

    request(Req.post(opts))
  end

  defp maybe_put(params, _key, nil), do: params
  defp maybe_put(params, key, value), do: params ++ [{key, value}]

  defp get(path, params, extra \\ []) do
    opts =
      [base_url: Application.fetch_env!(:mapo, :mapo_core_url), url: path, params: params] ++
        extra ++ Application.get_env(:mapo, :mapo_core_req_options, [])

    request(Req.get(opts))
  end

  defp post(path, json, extra \\ []) do
    opts =
      [base_url: Application.fetch_env!(:mapo, :mapo_core_url), url: path, json: json] ++
        extra ++ Application.get_env(:mapo, :mapo_core_req_options, [])

    request(Req.post(opts))
  end

  defp request({:ok, %Req.Response{status: 200, body: body}}), do: {:ok, body}

  defp request({:ok, %Req.Response{status: status, body: body}}),
    do: {:error, {:status, status, body}}

  defp request({:error, exception}), do: {:error, exception}
end
