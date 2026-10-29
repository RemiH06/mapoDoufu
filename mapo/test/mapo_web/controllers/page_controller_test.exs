defmodule MapoWeb.PageControllerTest do
  use MapoWeb.ConnCase

  import Mapo.AccountsFixtures

  test "GET / shows the register/log-in CTA when logged out", %{conn: conn} do
    conn = get(conn, ~p"/")
    html = html_response(conn, 200)

    assert html =~ "Mapo, powered by Gaiarda"
    assert html =~ "Crear cuenta"
    assert html =~ "Iniciar sesión"
    refute html =~ "Ir a mis equipos"
  end

  test "GET / shows the teams CTA when logged in", %{conn: conn} do
    conn = conn |> log_in_user(user_fixture()) |> get(~p"/")
    html = html_response(conn, 200)

    assert html =~ "Ir a mis equipos"
    refute html =~ "Crear cuenta"
  end

  test "the old single-layer screens redirect to /mapa", %{conn: conn} do
    for ruta <- ["/coropletas", "/voronoi", "/coloreado"] do
      assert redirected_to(get(conn, ruta)) == ~p"/mapa"
    end
  end
end
