defmodule Mapo.ZonaFixtures do
  @moduledoc """
  Zonas de ejemplo para las pruebas de las vistas con el selector de zona común
  (MapoWeb.ZonaSelector): lo que respondería `/zona/resolver` y `/zona/buscar`
  de mapo_core, y cómo elegir una zona en una vista.
  """

  import Phoenix.LiveViewTest

  @municipios %{
    "14015" => "Autlán de Navarro",
    "14039" => "Guadalajara",
    "14061" => "Mezquitic",
    "14098" => "San Pedro Tlaquepaque",
    "14120" => "Zapopan"
  }

  @geojson %{
    "type" => "Polygon",
    "coordinates" => [[[-104, 19], [-104, 20], [-103, 20], [-104, 19]]]
  }

  def municipio(cvegeo) do
    %{
      "cvegeo" => cvegeo,
      "cve_ent" => String.slice(cvegeo, 0, 2),
      "cve_mun" => String.slice(cvegeo, 2, 3),
      "nombre" => Map.get(@municipios, cvegeo, "Municipio #{cvegeo}"),
      "estado" => "Jalisco"
    }
  end

  @doc "La zona resuelta de una clave, como la da mapo_core."
  def zona("ent:14" = clave) do
    base(clave, "estado", "Jalisco", "2 municipios cargados", [
      municipio("14039"),
      municipio("14120")
    ])
  end

  def zona("mun:" <> claves = clave) do
    cvegeos = String.split(claves, ",")

    if Enum.all?(cvegeos, &Map.has_key?(@municipios, &1)) do
      ms = Enum.map(cvegeos, &municipio/1)
      base(clave, "municipios", Enum.map_join(ms, " y ", & &1["nombre"]), "Jalisco", ms)
    end
  end

  def zona("zm:14.1.01" = clave) do
    base(clave, "metropoli", "Zona metropolitana de Guadalajara", "2 municipios", [
      municipio("14039"),
      municipio("14120")
    ])
  end

  def zona("col:14098_0135" = clave) do
    base(clave, "colonia", "Lopez Cotilla", "Pueblo · San Pedro Tlaquepaque, Jalisco", [
      municipio("14098")
    ])
  end

  def zona("pol:" <> _ = clave),
    do: base(clave, "poligono", "Polígono dibujado", "Guadalajara, Jalisco", [municipio("14039")])

  # Lo que mapo_core no tendría cargado.
  def zona(_clave), do: nil

  defp base(clave, tipo, nombre, detalle, municipios) do
    %{
      "clave" => clave,
      "tipo" => tipo,
      "nombre" => nombre,
      "detalle" => detalle,
      "geojson" => @geojson,
      "km2" => 151.4,
      "bbox" => [-104, 19, -103, 20],
      "municipios" => municipios,
      "estados" => municipios |> Enum.map(& &1["cve_ent"]) |> Enum.uniq(),
      "faltan" => [],
      "fuente" => "INEGI, Marco Geoestadístico",
      "metodo" => nil,
      "aviso" => nil
    }
  end

  @doc """
  Atiende `/zona/buscar` y `/zona/resolver` dentro de un `Req.Test.stub`;
  regresa `nil` con cualquier otra ruta, para que el stub de la prueba siga.
  Las claves que no conoce dan 404, como mapo_core con algo no cargado.
  """
  def responder_zona(conn) do
    case conn.request_path do
      "/zona/buscar" ->
        conn = Plug.Conn.fetch_query_params(conn)
        Req.Test.json(conn, %{"resultados" => buscar(conn.query_params["q"]), "aviso" => nil})

      "/zona/resolver" ->
        conn = Plug.Conn.fetch_query_params(conn)

        case zona(conn.query_params["clave"]) do
          nil -> conn |> Plug.Conn.put_status(404) |> Req.Test.json(%{"detail" => "no"})
          z -> Req.Test.json(conn, z)
        end

      _ ->
        nil
    end
  end

  # Lo que se escribe en las pruebas es la clave misma, o un nombre conocido.
  defp buscar(q) do
    clave =
      case q do
        "Jalisco" -> "ent:14"
        "Guadalajara" -> "mun:14039"
        "Zapopan" -> "mun:14120"
        "Autlán" -> "mun:14015"
        otro -> otro
      end

    case zona(clave) do
      nil ->
        []

      z ->
        tipo = if z["tipo"] == "municipios", do: "municipio", else: z["tipo"]
        [%{"clave" => clave, "tipo" => tipo, "nombre" => z["nombre"], "detalle" => z["detalle"]}]
    end
  end

  @doc "Escribe `texto` en el selector de la vista y elige la primera sugerencia (Enter)."
  def elegir_zona(lv, texto, id \\ "zona") do
    if has_element?(lv, "##{id}-cambiar"), do: lv |> element("##{id}-cambiar") |> render_click()
    lv |> form("##{id}-form", zona_q: %{q: texto}) |> render_change()
    lv |> form("##{id}-form", zona_q: %{q: texto}) |> render_submit()
    lv
  end
end
