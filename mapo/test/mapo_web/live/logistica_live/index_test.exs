defmodule MapoWeb.LogisticaLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  @cdmx %{"lat" => 19.4326, "lon" => -99.1332}
  @puebla %{"lat" => 19.0414, "lon" => -98.2063}
  @toluca %{"lat" => 19.2826, "lon" => -99.6557}

  defp con_paradas(conn, puntos) do
    {:ok, lv, _html} = live(conn, ~p"/logistica")
    Enum.each(puntos, &render_hook(lv, "poner", &1))
    lv
  end

  defp stub_vrp(rutas, metodo \\ "linea_recta_aproximada") do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/vrp/calcular"

      Req.Test.json(conn, %{
        "rutas" => rutas,
        "distancia_total_km" => rutas |> Enum.map(& &1["distancia_km"]) |> Enum.sum(),
        "metodo" => metodo
      })
    end)
  end

  defp ruta(vehiculo, orden, km),
    do: %{
      "vehiculo_id" => vehiculo,
      "orden_paradas" => orden,
      "distancia_km" => km,
      "geometria" => nil
    }

  test "mounts with an empty hoja de ruta", %{conn: conn} do
    {:ok, _lv, html} = live(conn, ~p"/logistica")

    assert html =~ "Sin paradas. La primera que pongas será el depósito."
    assert html =~ "0 paradas"
  end

  test "the first point is the depósito and the next ones are numbered", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])

    assert has_element?(lv, "[data-fila='0'] .pin.deposito", "D")
    assert has_element?(lv, "[data-fila='1'] .pin.pendiente", "1")
    assert render(lv) =~ "1 paradas"

    assert_push_event(lv, "paradas", %{
      paradas: [%{id: 0, deposito: true}, %{id: 1, deposito: false, ruta: nil, demanda: 1}]
    })
  end

  test "points that are not numbers are ignored", %{conn: conn} do
    lv = con_paradas(conn, [%{"lat" => "x", "lon" => nil}])

    assert render(lv) =~ "Sin paradas"
  end

  test "a parada keeps its number when an earlier one is removed", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla, @toluca])

    lv |> element("[data-fila='1'] .quitar") |> render_click()

    refute has_element?(lv, "[data-fila='1']")
    assert has_element?(lv, "[data-fila='2'] .pin", "2")
  end

  test "demanda goes up and down from the hoja, never below zero", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])

    lv |> element("[data-fila='1'] button[aria-label^='Más']") |> render_click()
    assert has_element?(lv, "[data-fila='1'] output", "2")

    render_click(lv, "demanda", %{"campo" => "1", "d" => "-1"})
    render_click(lv, "demanda", %{"campo" => "1", "d" => "-1"})
    render_click(lv, "demanda", %{"campo" => "1", "d" => "-1"})
    assert has_element?(lv, "[data-fila='1'] output", "0")
  end

  test "dragging a marker moves the parada", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])

    render_hook(lv, "mover", %{"id" => 1, "lat" => 20.0, "lon" => -98.5})

    assert render(lv) =~ "20.0000, -98.5000"
  end

  test "volver_deposito swaps the depósito; the old one gets a new number", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla, @toluca])

    render_hook(lv, "volver_deposito", %{"id" => 2})

    assert render(lv) =~ "19.2826, -99.6557"
    assert has_element?(lv, "[data-fila='0'] .pin.deposito")
    assert has_element?(lv, "[data-fila='3']", "19.4326, -99.1332")
  end

  test "the fleet sentence changes vehículos and capacidad", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/logistica")

    render_click(lv, "flota", %{"campo" => "n", "d" => "1"})
    render_click(lv, "flota", %{"campo" => "cap", "d" => "-1"})

    html = render(lv)
    assert html =~ "vehículos de"
    assert has_element?(lv, "output[aria-label='vehículos']", "2")
    assert has_element?(lv, "output[aria-label='capacidad por vehículo']", "95")
  end

  test "calcular groups the paradas by vehículo and pushes the rutas", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla, @toluca])
    stub_vrp([ruta(0, [0, 2, 1, 0], 250.5), ruta(1, [0, 0], 0.0)])

    lv |> element("button", "Calcular rutas") |> render_click()
    html = render_async(lv)

    assert html =~ "Vehículo A"
    refute html =~ "Vehículo B"
    assert html =~ "Línea recta aproximada"
    assert html =~ "250.5"
    assert has_element?(lv, "[data-fila='2'] .pin:not(.pendiente)")

    assert_push_event(lv, "rutas", %{rutas: [%{geometria: nil, puntos: [_, _, _, _]}]})
    assert_push_event(lv, "paradas", %{vigente: true})
  end

  test "editing after calcular keeps the rutas but asks to recalculate", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])
    stub_vrp([ruta(0, [0, 1, 0], 12.5)], "carretera_real")

    lv |> element("button", "Calcular rutas") |> render_click()
    assert render_async(lv) =~ "Carretera real · OSRM"
    assert has_element?(lv, "button[disabled]", "Recalcular rutas")

    render_hook(lv, "poner", @toluca)

    assert render(lv) =~ "Cambiaste paradas"
    assert has_element?(lv, ".sin-ruta [data-fila='2']")
    refute has_element?(lv, "button[disabled]", "Recalcular rutas")
    assert_push_event(lv, "paradas", %{vigente: false})
  end

  test "calcular with fewer than 2 paradas shows a flash", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx])

    assert render_click(lv, "calcular", %{}) =~ "Agrega al menos 2 paradas"
  end

  test "calcular with an infeasible VRP (422) shows the detail message", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      conn
      |> Plug.Conn.put_resp_content_type("application/json")
      |> Plug.Conn.send_resp(
        422,
        Jason.encode!(%{"detail" => "No se encontró una solución factible con esa capacidad."})
      )
    end)

    lv |> element("button", "Calcular rutas") |> render_click()

    assert render_async(lv) =~ "No se encontró una solución factible con esa capacidad."
  end

  test "limpiar empties the hoja and the rutas", %{conn: conn} do
    lv = con_paradas(conn, [@cdmx, @puebla])

    lv |> element("button", "Limpiar") |> render_click()

    assert render(lv) =~ "Sin paradas"
    assert_push_event(lv, "rutas", %{rutas: []})
  end
end
