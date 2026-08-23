defmodule Mapo.MapoCore do
  @moduledoc """
  Cliente HTTP hacia mapo_core, el motor de datos/decision en Python
  (que a su vez consume Gaiarda). Nunca lanza: cualquier falla de red
  o de mapo_core regresa `{:error, _}`, para que quien llama decida
  como mostrarla, igual que mapo_core hace con Gaiarda.
  """

  @doc """
  Los indicadores validos para `coropleta_censo_poblacion/3`, con
  etiqueta en espanol para mostrar en un selector. Debe mantenerse
  igual al `INDICADORES_CHOROPLETH` de `gaiarda/src/gaiarda/server.py`.
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

  @doc "FeatureCollection de los estados (con polígono)."
  def estados, do: get("/gaiarda/estados")

  @doc "FeatureCollection de municipios, opcionalmente filtrada por estado."
  def municipios(cve_ent), do: get("/gaiarda/municipios", cve_ent: cve_ent)

  @doc """
  FeatureCollection de AGEBs del censo, con el valor de `indicador` ya
  cruzado en `properties.valor_choropleth` (puede venir `null`, si el
  AGEB no tiene ese dato: nunca se inventa un cero).
  """
  def coropleta_censo_poblacion(indicador, cve_ent, cve_mun \\ nil) do
    params = [indicador: indicador, cve_ent: cve_ent] |> maybe_put(:cve_mun, cve_mun)
    get("/gaiarda/choropleth/censo_poblacion", params)
  end

  @doc """
  Diagrama de Voronoi de los negocios de DENUE en un municipio
  (opcionalmente filtrados por texto en `clase_actividad`), recortado
  al polígono real del municipio: para cada negocio, el área que le
  queda más cerca a él que a cualquier otro de la lista.
  """
  def voronoi_denue(cve_ent, cve_mun, clase_actividad \\ nil) do
    params = [cve_ent: cve_ent, cve_mun: cve_mun] |> maybe_put(:clase_actividad, clase_actividad)
    get("/voronoi/denue", params)
  end

  defp maybe_put(params, _key, nil), do: params
  defp maybe_put(params, key, value), do: params ++ [{key, value}]

  defp get(path, params \\ []) do
    opts =
      [base_url: Application.fetch_env!(:mapo, :mapo_core_url), url: path, params: params] ++
        Application.get_env(:mapo, :mapo_core_req_options, [])

    case Req.get(opts) do
      {:ok, %Req.Response{status: 200, body: body}} -> {:ok, body}
      {:ok, %Req.Response{status: status, body: body}} -> {:error, {:status, status, body}}
      {:error, exception} -> {:error, exception}
    end
  end
end
