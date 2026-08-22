defmodule MapoWeb.CoropletaLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  defp feature(cvegeo, nomgeo) do
    %{"type" => "Feature", "properties" => %{"cvegeo" => cvegeo, "nomgeo" => nomgeo}, "geometry" => %{}}
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/coropletas")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "lists estados from mapo_core and lets you pick a municipio", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [feature("14", "Jalisco")]})

        "/gaiarda/municipios" ->
          assert conn.params["cve_ent"] == "14"
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [feature("14039", "Guadalajara")]})
      end
    end)

    {:ok, lv, html} = live(conn, ~p"/coropletas")
    assert html =~ "Jalisco"

    html =
      lv
      |> form("#coropleta_form", coropleta: %{"cve_ent" => "14", "cve_mun" => "", "indicador" => "pobtot"})
      |> render_change()

    assert html =~ "Guadalajara"
  end

  test "generar pushes a coropleta event with the geojson", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [feature("14", "Jalisco")]})

        "/gaiarda/choropleth/censo_poblacion" ->
          assert conn.params["indicador"] == "pobtot"
          assert conn.params["cve_ent"] == "14"

          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [
              %{
                "type" => "Feature",
                "properties" => %{"valor_choropleth" => 120, "indicador" => "pobtot"},
                "geometry" => %{}
              }
            ]
          })
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/coropletas")

    lv
    |> form("#coropleta_form", coropleta: %{"cve_ent" => "14", "cve_mun" => "", "indicador" => "pobtot"})
    |> render_submit()

    assert_push_event(lv, "coropleta", %{etiqueta: "Población total"})
  end

  test "generar without an estado shows a flash instead of calling mapo_core", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/estados"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/coropletas")

    html =
      lv
      |> form("#coropleta_form", coropleta: %{"cve_ent" => "", "cve_mun" => "", "indicador" => "pobtot"})
      |> render_submit()

    assert html =~ "Selecciona un estado"
  end

  test "an empty featurecollection from mapo_core shows an honest message", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [feature("14", "Jalisco")]})

        "/gaiarda/choropleth/censo_poblacion" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/coropletas")

    html =
      lv
      |> form("#coropleta_form", coropleta: %{"cve_ent" => "14", "cve_mun" => "", "indicador" => "pobtot"})
      |> render_submit()

    assert html =~ "no tiene AGEBs o censo descargados"
  end
end
