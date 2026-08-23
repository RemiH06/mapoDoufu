defmodule MapoWeb.ColoreadoLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  defp estado_feature(cvegeo, nomgeo) do
    %{"type" => "Feature", "properties" => %{"cvegeo" => cvegeo, "nomgeo" => nomgeo}, "geometry" => %{}}
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/coloreado")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "lists estados from mapo_core", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/estados"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})
    end)

    {:ok, _lv, html} = live(conn, ~p"/coloreado")
    assert html =~ "Jalisco"
  end

  test "generar pushes a coloreado event with the geojson", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/coloreado/municipios" ->
          assert conn.params["cve_ent"] == "14"

          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [
              %{
                "type" => "Feature",
                "properties" => %{"cvegeo" => "14039", "nomgeo" => "Guadalajara", "color_indice" => 0},
                "geometry" => %{}
              }
            ],
            "num_colores" => 2
          })
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/coloreado")

    lv
    |> form("#coloreado_form", coloreado: %{"cve_ent" => "14"})
    |> render_submit()

    assert_push_event(lv, "coloreado", %{
      geojson: %{"features" => [%{"properties" => %{"nomgeo" => "Guadalajara"}}]}
    })
  end

  test "generar without an estado shows a flash instead of calling mapo_core", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/estados"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/coloreado")

    html =
      lv
      |> form("#coloreado_form", coloreado: %{"cve_ent" => ""})
      |> render_submit()

    assert html =~ "Selecciona un estado"
  end

  test "an empty featurecollection from mapo_core shows an honest message", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/coloreado/municipios" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [], "num_colores" => 0})
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/coloreado")

    html =
      lv
      |> form("#coloreado_form", coloreado: %{"cve_ent" => "14"})
      |> render_submit()

    assert html =~ "no tiene municipios descargados"
  end
end
