defmodule MapoWeb.PerfilLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  defp estado_feature(cvegeo, nomgeo) do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => cvegeo, "nomgeo" => nomgeo},
      "geometry" => %{}
    }
  end

  defp municipio_feature(cve_ent, cve_mun, nomgeo) do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => cve_ent <> cve_mun, "cve_mun" => cve_mun, "nomgeo" => nomgeo},
      "geometry" => %{}
    }
  end

  defp perfil_con_demografia do
    %{
      "cve_ent" => "14",
      "cve_mun" => "039",
      "demografia" => %{
        "pobtot" => 1_500_000,
        "pobfem" => 800_000,
        "pobmas" => 700_000,
        "graproes" => 10.5,
        "pea" => 700_000,
        "pocupada" => 650_000,
        "pdesocup" => 50000,
        "tothog" => 400_000,
        "vivtot" => 420_000
      },
      "comercio" => %{
        "total_negocios" => 3200,
        "top_clases_actividad" => [["Comercio al por menor de abarrotes", 450]]
      },
      "consumo" => %{
        "n_hogares_muestra" => 12,
        "periodo" => "diario",
        "promedio_ponderado" => 476.23,
        "mediana" => 410.0
      },
      "seguridad" => %{
        "anio" => 2024,
        "total_delitos" => 320,
        "por_tipo" => [["Robo", 200], ["Homicidio", 20]]
      },
      "laboral" => %{
        "anio" => 2025,
        "trimestre" => "trim3",
        "tasa_desocupacion" => 2.49
      }
    }
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/perfil")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "ver_perfil without a municipio shows a flash", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    html =
      lv
      |> form("#perfil_form", perfil: %{"cve_ent" => "", "cve_mun" => ""})
      |> render_submit()

    assert html =~ "Selecciona un estado y un municipio"
  end

  defp ageb_feature do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => "1403900010010"},
      "geometry" => %{
        "type" => "Polygon",
        "coordinates" => [
          [[-103.35, 20.67], [-103.34, 20.67], [-103.34, 20.68], [-103.35, 20.67]]
        ]
      }
    }
  end

  defp stub_catalogo(perfil) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [estado_feature("14", "Jalisco")]
          })

        "/geo/municipios" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "039", "Guadalajara")]
          })

        "/geo/agebs" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [ageb_feature()]})

        "/perfil_zona" ->
          assert conn.params["cve_ent"] == "14"
          assert conn.params["cve_mun"] == "039"
          Req.Test.json(conn, perfil)
      end
    end)
  end

  test "ver_perfil puts the query in the URL and renders the five documents", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => ""})
    |> render_change()

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => "039"})
    |> render_submit()

    assert_patch(lv, ~p"/perfil?cve_ent=14&cve_mun=039")
    html = render_async(lv)

    assert html =~ "Guadalajara, Jalisco"
    assert html =~ "1,500,000"
    assert html =~ "2.49%"
    assert html =~ "Las demás clases"
    assert has_element?(lv, "[data-piel=demografia]")
    assert has_element?(lv, "[data-piel=laboral]")
    assert has_element?(lv, ".plano path")
  end

  test "opening /perfil with a query in the URL loads it directly", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")

    assert render_async(lv) =~ "Gasto de los hogares"
    assert has_element?(lv, "#perfil_form option[value='039'][selected]")
  end

  test "an unknown municipio in the URL shows a flash and no query", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=777")

    assert html =~ "Ese municipio no está en el catálogo."
    refute has_element?(lv, ".documentos")
  end

  test "each document says so when its source does not cover the municipio", %{conn: conn} do
    stub_catalogo(%{
      "demografia" => nil,
      "comercio" => %{"total_negocios" => 0, "top_clases_actividad" => []},
      "consumo" => nil,
      "seguridad" => nil,
      "laboral" => nil
    })

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
    html = render_async(lv)

    assert html =~ "El censo no tiene datos de este municipio."
    assert html =~ "El DENUE no registra negocios en este municipio."
    assert html =~ "La muestra de la ENIGH no llegó a este municipio."
    assert html =~ "No hay incidencia del SESNSP cargada para este municipio."
    assert html =~ "No hay datos de la ENOE cargados para este estado."
  end
end
