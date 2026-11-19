defmodule MapoWeb.RiesgosLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  @estados %{
    "type" => "FeatureCollection",
    "features" => [
      %{"properties" => %{"cvegeo" => "14", "nomgeo" => "Jalisco"}, "geometry" => nil},
      %{"properties" => %{"cvegeo" => "20", "nomgeo" => "Oaxaca"}, "geometry" => nil}
    ]
  }

  @municipios %{
    "type" => "FeatureCollection",
    "features" => [
      %{"properties" => %{"cve_mun" => "015", "nomgeo" => "Autlán de Navarro"}, "geometry" => nil}
    ]
  }

  defp grupos(pob) do
    %{
      "POBTOT" => %{"etiqueta" => "personas", "valor" => pob, "reservados" => 0},
      "P_0A2" => %{"etiqueta" => "de 0 a 2 años", "valor" => 30, "reservados" => 4},
      "P_60YMAS" => %{"etiqueta" => "de 60 años o más", "valor" => 90, "reservados" => 0}
    }
  end

  defp resultado(zona) do
    %{
      "zona" =>
        Map.merge(zona, %{
          "geojson" => %{
            "type" => "Polygon",
            "coordinates" => [[[-104, 19], [-104, 20], [-103, 20], [-104, 19]]]
          },
          "km2" => 705.1,
          "municipios" => [
            %{"cve_ent" => "14", "cve_mun" => "015", "nombre" => "Autlán de Navarro"}
          ]
        }),
      "cerca_m" => 1000,
      "poblacion" => %{
        "agebs" => 33,
        "localidades" => 139,
        "grupos" => grupos(64_931),
        "urbanas_por_punto" => 1,
        "pob_urbanas_por_punto" => 12_500
      },
      "metodo_poblacion" => "AGEB urbanos y localidades del ITER.",
      "bloques" => [
        %{
          "clave" => "agua_superficial",
          "titulo" => "Calidad del agua superficial",
          "fuente" => "Conagua, RENAMECA",
          "fecha_dato" => "2012 a 2025",
          "nivel" => "punto (sitio de monitoreo)",
          "metodo" => "Semáforo de Conagua tal cual.",
          "hechos" => ["1 sitio dentro de la zona: 1 en rojo."],
          "poblacion_cerca" =>
            Map.put(
              %{"agebs" => 2, "localidades" => 1, "grupos" => grupos(1_575)},
              "frase",
              "viven a menos de 1,000 m de un sitio en rojo"
            ),
          "capa" => %{
            "type" => "FeatureCollection",
            "features" => [
              %{
                "type" => "Feature",
                "geometry" => %{"type" => "Point", "coordinates" => [-104.3, 19.7]},
                "properties" => %{"semaforo" => "ROJO"}
              }
            ]
          },
          "ficha" => nil
        },
        %{
          "clave" => "sequia",
          "titulo" => "Sequía",
          "fuente" => "SMN, Monitor de Sequía",
          "fecha_dato" => "2003 a 2026-10-31",
          "nivel" => "municipio",
          "metodo" => "Categoría del Monitor.",
          "hechos" => ["Autlán de Navarro: anormalmente seco al 2026-10-31."],
          "poblacion_cerca" => nil,
          "capa" => nil,
          "ficha" => nil
        }
      ]
    }
  end

  defp stub(fun) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" -> Req.Test.json(conn, @estados)
        "/geo/municipios" -> municipios(conn)
        "/riesgos/zona" -> fun.(conn)
      end
    end)
  end

  defp municipios(conn) do
    conn = Plug.Conn.fetch_query_params(conn)

    if conn.query_params["cve_ent"] == "14",
      do: Req.Test.json(conn, @municipios),
      else: Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
  end

  defp sin_consulta, do: stub(fn _ -> raise "no debería consultar" end)

  test "mounts with the form and the states", %{conn: conn} do
    sin_consulta()
    {:ok, _lv, html} = live(conn, ~p"/riesgos")

    assert html =~ "Riesgos de la zona"
    assert html =~ "Jalisco"
    assert html =~ "aquí no hay índice"
  end

  test "a state without loaded municipios says to use a circle", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")

    html = lv |> form("#riesgos_form", riesgos: %{cve_ent: "20"}) |> render_change()
    assert html =~ "no tiene municipios cargados"

    html = lv |> form("#riesgos_form", riesgos: %{cve_ent: "14"}) |> render_change()
    assert html =~ "Autlán de Navarro"
  end

  test "a municipio shows each hazard on its own, with source, date and method", %{conn: conn} do
    stub(fn conn ->
      conn = Plug.Conn.fetch_query_params(conn)
      assert conn.query_params == %{"cve_ent" => "14", "cve_mun" => "015", "cerca_m" => "1000"}

      Req.Test.json(
        conn,
        resultado(%{"tipo" => "municipio", "cve_ent" => "14", "cve_mun" => "015"})
      )
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    lv |> form("#riesgos_form", riesgos: %{cve_ent: "14"}) |> render_change()
    lv |> form("#riesgos_form", riesgos: %{cve_ent: "14", cve_mun: "015"}) |> render_submit()
    html = render_async(lv)

    assert html =~ "Quién vive en Autlán de Navarro"
    assert html =~ "64,931"
    assert html =~ "en 4 de los 172"
    assert html =~ "12,500 personas son de 1 localidad urbana que cuenta entera por su punto"
    assert has_element?(lv, "#bloque-agua_superficial h2", "Calidad del agua superficial")
    assert has_element?(lv, "#bloque-agua_superficial .procedencia", "Conagua, RENAMECA")

    assert has_element?(
             lv,
             "#bloque-agua_superficial .cerca",
             "1,575 personas de la zona viven a menos de 1,000 m"
           )

    assert has_element?(lv, "#bloque-sequia .metodo", "Categoría del Monitor")
    refute html =~ "expuest"

    assert_push_event(lv, "zona", %{capas: [%{clave: "agua_superficial"}]})
  end

  test "a circle needs a point and sends lon, lat and radio in meters", %{conn: conn} do
    stub(fn conn ->
      conn = Plug.Conn.fetch_query_params(conn)

      assert %{"lon" => "-104.3", "lat" => "19.7", "radio_m" => "2500", "cerca_m" => "500"} =
               conn.query_params

      Req.Test.json(
        conn,
        resultado(%{"tipo" => "circulo", "lon" => -104.3, "lat" => 19.7, "radio_m" => 2500})
      )
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    lv |> form("#riesgos_form", riesgos: %{modo: "circulo"}) |> render_change()

    html =
      lv |> form("#riesgos_form", riesgos: %{modo: "circulo", radio_km: "2.5"}) |> render_submit()

    assert html =~ "Toca el plano para poner el centro"

    render_hook(lv, "punto", %{"lat" => 19.7, "lon" => -104.3})
    assert_push_event(lv, "previa", %{lat: 19.7, lon: -104.3})

    lv
    |> form("#riesgos_form", riesgos: %{modo: "circulo", radio_km: "2.5", cerca_m: "500"})
    |> render_submit()

    assert render_async(lv) =~ "Quién vive en el círculo de 2.5 km"
  end

  test "a radius out of range or an unknown distance is not sent", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")
    render_hook(lv, "punto", %{"lat" => 19.7, "lon" => -104.3})

    html =
      lv |> form("#riesgos_form", riesgos: %{modo: "circulo", radio_km: "80"}) |> render_submit()

    assert html =~ "El radio va de 0.1 a 25 km"

    html =
      render_submit(lv, "consultar", %{
        "riesgos" => %{"modo" => "circulo", "radio_km" => "2", "cerca_m" => "999"}
      })

    assert html =~ "Elige qué tan cerca contar"
  end

  test "points that are not numbers are ignored", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")

    render_hook(lv, "punto", %{"lat" => "x", "lon" => nil})
    refute render(lv) =~ "Centro en"
  end

  test "an error from mapo_core is said, not hidden", %{conn: conn} do
    stub(fn conn -> conn |> Plug.Conn.put_status(500) |> Req.Test.json(%{"detail" => "boom"}) end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    lv |> form("#riesgos_form", riesgos: %{cve_ent: "14"}) |> render_change()
    lv |> form("#riesgos_form", riesgos: %{cve_ent: "14", cve_mun: "015"}) |> render_submit()

    assert render_async(lv) =~ "No se pudo consultar la zona"
  end
end
