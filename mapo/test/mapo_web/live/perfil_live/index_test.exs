defmodule MapoWeb.PerfilLive.IndexTest do
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

  defp perfil_con_demografia do
    %{
      "cve_ent" => "14",
      "cve_mun" => "039",
      "demografia" => %{
        "pobtot" => 1500000,
        "pobfem" => 800000,
        "pobmas" => 700000,
        "graproes" => 10.5,
        "pea" => 700000,
        "pocupada" => 650000,
        "pdesocup" => 50000,
        "tothog" => 400000,
        "vivtot" => 420000
      },
      "comercio" => %{
        "total_negocios" => 3200,
        "top_clases_actividad" => [["Comercio al por menor de abarrotes", 450]]
      },
      "consumo_disponible" => false,
      "seguridad_disponible" => false,
      "laboral_disponible" => false
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

  test "ver_perfil renders demografia and the honest not-yet-ported gaps", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/geo/municipios" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "039", "Guadalajara")]
          })

        "/perfil_zona" ->
          assert conn.params["cve_ent"] == "14"
          assert conn.params["cve_mun"] == "039"
          Req.Test.json(conn, perfil_con_demografia())
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => ""})
    |> render_change()

    html =
      lv
      |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => "039"})
      |> render_submit()

    assert html =~ "Población total: 1500000"
    assert html =~ "No disponible todavía"
  end

  test "ver_perfil with missing demografia shows an honest empty message", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [estado_feature("14", "Jalisco")]})

        "/geo/municipios" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "999", "Sin Datos")]
          })

        "/perfil_zona" ->
          Req.Test.json(conn, %{
            "demografia" => nil,
            "comercio" => %{"total_negocios" => 0, "top_clases_actividad" => []},
            "consumo_disponible" => false,
            "seguridad_disponible" => false,
            "laboral_disponible" => false
          })
      end
    end)

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => ""})
    |> render_change()

    html =
      lv
      |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => "999"})
      |> render_submit()

    assert html =~ "Sin datos de censo para este municipio."
  end
end
