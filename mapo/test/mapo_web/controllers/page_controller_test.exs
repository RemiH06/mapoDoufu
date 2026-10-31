defmodule MapoWeb.PageControllerTest do
  use MapoWeb.ConnCase

  import Mapo.AccountsFixtures

  test "GET / shows the register/log-in CTA when logged out", %{conn: conn} do
    conn = get(conn, ~p"/")
    html = html_response(conn, 200)

    assert html =~ "tu equipo decida"
    assert html =~ ~p"/privacidad"
    assert html =~ "plano-portada"
    assert html =~ "Crear cuenta"
    assert html =~ ~p"/users/log-in"
    refute html =~ "Mis equipos"
  end

  test "GET / shows the teams CTA when logged in", %{conn: conn} do
    conn = conn |> log_in_user(user_fixture()) |> get(~p"/")
    html = html_response(conn, 200)

    assert html =~ "Mis equipos"
    assert html =~ "Abrir el mapa"
    refute html =~ "Crear cuenta"
  end

  describe "GET /privacidad" do
    setup do
      contacto = Application.get_env(:mapo, :contacto_privacidad)
      osrm = Application.get_env(:mapo, :osrm_propio)

      on_exit(fn ->
        Application.put_env(:mapo, :contacto_privacidad, contacto)
        Application.put_env(:mapo, :osrm_propio, osrm)
      end)
    end

    test "says the contact is missing when none is configured", %{conn: conn} do
      Application.put_env(:mapo, :contacto_privacidad, nil)
      html = conn |> get(~p"/privacidad") |> html_response(200)

      assert html =~ "Aviso de privacidad"
      assert html =~ "todavía no publica un contacto"
    end

    test "shows the configured contact", %{conn: conn} do
      Application.put_env(:mapo, :contacto_privacidad, "datos@mapo.test")
      html = conn |> get(~p"/privacidad") |> html_response(200)

      assert html =~ "datos@mapo.test"
      refute html =~ "todavía no publica un contacto"
    end

    test "names the public OSRM demo only when there is no own server", %{conn: conn} do
      Application.put_env(:mapo, :osrm_propio, false)
      assert conn |> get(~p"/privacidad") |> html_response(200) =~ "demostración de OSRM"

      Application.put_env(:mapo, :osrm_propio, true)
      html = build_conn() |> get(~p"/privacidad") |> html_response(200)
      assert html =~ "los puntos no salen de aquí"
      refute html =~ "demostración de OSRM"
    end
  end

  test "the old single-layer screens redirect to /mapa", %{conn: conn} do
    for ruta <- ["/coropletas", "/voronoi", "/coloreado"] do
      assert redirected_to(get(conn, ruta)) == ~p"/mapa"
    end
  end
end
