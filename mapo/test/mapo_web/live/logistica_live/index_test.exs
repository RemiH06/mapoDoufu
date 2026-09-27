defmodule MapoWeb.LogisticaLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  test "mounts with no paradas", %{conn: conn} do
    {:ok, _lv, html} = live(conn, ~p"/logistica")

    assert html =~ "Sin paradas todavía"
    assert html =~ "Paradas (0)"
  end

  test "clicking the map adds a parada, the first one is the depósito", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})

    html = render(lv)
    assert html =~ "Depósito"
    assert html =~ "Paradas (1)"
    assert_push_event(lv, "paradas", %{paradas: [%{lat: 19.4326, lon: -99.1332, demanda: 0}]})
  end

  test "a second click adds a numbered parada, not another depósito", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})
    render_hook(lv, "click_mapa", %{"lat" => 19.0414, "lon" => -98.2063})

    html = render(lv)
    assert html =~ "Paradas (2)"
    assert html =~ "Parada 1"
  end

  test "quitar_parada removes a stop and resets any previous resultado", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})
    render_hook(lv, "click_mapa", %{"lat" => 19.0414, "lon" => -98.2063})

    lv |> element("[phx-value-indice='1'][phx-click='quitar_parada']") |> render_click()

    assert render(lv) =~ "Paradas (1)"
    assert_push_event(lv, "limpiar_rutas", %{})
  end

  test "calcular with fewer than 2 paradas shows a flash", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})
    html = render_click(lv, "calcular", %{})

    assert html =~ "Agrega al menos 2 paradas"
  end

  test "calcular with a real solution pushes rutas_vrp and renders the summary", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})
    render_hook(lv, "click_mapa", %{"lat" => 19.0414, "lon" => -98.2063})

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/vrp/calcular"

      Req.Test.json(conn, %{
        "rutas" => [
          %{
            "vehiculo_id" => 0,
            "orden_paradas" => [0, 1, 0],
            "distancia_km" => 12.5,
            "geometria" => nil
          }
        ],
        "distancia_total_km" => 12.5,
        "metodo" => "linea_recta_aproximada"
      })
    end)

    html = lv |> element("button", "Calcular rutas") |> render_click()

    assert html =~ "Línea recta aproximada"
    assert html =~ "12.5"

    assert_push_event(lv, "rutas_vrp", %{
      rutas: [
        %{
          "vehiculo_id" => 0,
          "orden_paradas" => [0, 1, 0],
          "distancia_km" => 12.5,
          "geometria" => nil
        }
      ]
    })
  end

  test "calcular with an infeasible VRP (422) shows the detail message", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_hook(lv, "click_mapa", %{"lat" => 19.4326, "lon" => -99.1332})
    render_hook(lv, "click_mapa", %{"lat" => 19.0414, "lon" => -98.2063})

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      conn
      |> Plug.Conn.put_resp_content_type("application/json")
      |> Plug.Conn.send_resp(
        422,
        Jason.encode!(%{"detail" => "No se encontró una solución factible con esa capacidad."})
      )
    end)

    html = lv |> element("button", "Calcular rutas") |> render_click()

    assert html =~ "No se encontró una solución factible con esa capacidad."
  end
end
