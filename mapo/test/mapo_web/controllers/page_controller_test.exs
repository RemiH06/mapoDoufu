defmodule MapoWeb.PageControllerTest do
  use MapoWeb.ConnCase

  import Mapo.AccountsFixtures

  test "GET / shows the register/log-in CTA when logged out", %{conn: conn} do
    conn = get(conn, ~p"/")
    html = html_response(conn, 200)

    assert html =~ "qué deberías hacer con eso"
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

  test "the old single-layer screens redirect to /mapa", %{conn: conn} do
    for ruta <- ["/coropletas", "/voronoi", "/coloreado"] do
      assert redirected_to(get(conn, ruta)) == ~p"/mapa"
    end
  end
end
