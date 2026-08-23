defmodule MapoWeb.VoronoiLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  defp estado_feature(cvegeo, nomgeo) do
    %{"type" => "Feature", "properties" => %{"cvegeo" => cvegeo, "nomgeo" => nomgeo}, "geometry" => %{}}
  end

  defp municipio_feature(cve_ent, cve_mun, nomgeo) do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => cve_ent <> cve_mun, "cve_mun" => cve_mun, "nomgeo" => nomgeo},
      "geometry" => %{}
    }
  end

  defp celdas_geojson do
    %{
      "type" => "FeatureCollection",
      "features" => [
        %{
          "type" => "Feature",
          "properties" => %{"id" => "1", "nombre" => "Papelería A", "lat" => 20.0, "lon" => -100.0},
          "geometry" => %{"type" => "Polygon", "coordinates" => [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        }
      ]
    }
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/voronoi")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "lists estados and lets you pick a municipio with its cve_mun (3 digits)", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/gaiarda/municipios" ->
          assert conn.params["cve_ent"] == "14"

          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "039", "Guadalajara")]
          })
      end
    end)

    {:ok, lv, html} = live(conn, ~p"/voronoi")
    assert html =~ "Jalisco"

    html =
      lv
      |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "", "clase_actividad" => ""})
      |> render_change()

    assert html =~ "Guadalajara"
    assert html =~ ~s(value="039")
  end

  defp montar_con_municipio(conn, stub_extra) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/gaiarda/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/gaiarda/municipios" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "039", "Guadalajara")]
          })

        _ ->
          stub_extra.(conn)
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/voronoi")

    lv
    |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "", "clase_actividad" => ""})
    |> render_change()

    lv
  end

  test "generar pushes a voronoi event with the geojson", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        assert conn.params["cve_ent"] == "14"
        assert conn.params["cve_mun"] == "039"
        Req.Test.json(conn, %{"celdas" => celdas_geojson(), "metodo" => "recortado_a_limite", "num_negocios" => 1})
      end)

    lv
    |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "039", "clase_actividad" => ""})
    |> render_submit()

    assert_push_event(lv, "voronoi", %{geojson: %{"features" => [%{"properties" => %{"nombre" => "Papelería A"}}]}})
  end

  test "generar includes clase_actividad when given", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        assert conn.params["clase_actividad"] == "papelería"
        Req.Test.json(conn, %{"celdas" => celdas_geojson(), "metodo" => "recortado_a_limite", "num_negocios" => 1})
      end)

    lv
    |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "039", "clase_actividad" => "papelería"})
    |> render_submit()
  end

  test "generar without a municipio shows a flash instead of calling mapo_core", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/estados"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/voronoi")

    html =
      lv
      |> form("#voronoi_form", voronoi: %{"cve_ent" => "", "cve_mun" => "", "clase_actividad" => ""})
      |> render_submit()

    assert html =~ "Selecciona un estado y un municipio"
  end

  test "a 422 from mapo_core (not enough businesses) shows its detail message", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        conn
        |> Plug.Conn.put_status(422)
        |> Req.Test.json(%{"detail" => "Solo hay 1 negocio(s) con esos filtros; se necesitan al menos 3."})
      end)

    html =
      lv
      |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "039", "clase_actividad" => ""})
      |> render_submit()

    assert html =~ "se necesitan al menos 3"
  end

  test "a 404 from mapo_core (municipio not found) shows an honest message", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        conn |> Plug.Conn.put_status(404) |> Req.Test.json(%{"detail" => "no encontrado"})
      end)

    html =
      lv
      |> form("#voronoi_form", voronoi: %{"cve_ent" => "14", "cve_mun" => "039", "clase_actividad" => ""})
      |> render_submit()

    assert html =~ "no está descargado"
  end
end
