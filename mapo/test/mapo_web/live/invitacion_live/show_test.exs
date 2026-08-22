defmodule MapoWeb.InvitacionLive.ShowTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  alias Mapo.Teams

  test "shows a not-found message for an unknown token", %{conn: conn} do
    {:ok, _lv, html} = live(conn, ~p"/invitaciones/no-existe")

    assert html =~ "no existe o ya no es válida"
  end

  test "shows an already-accepted message", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    invitado = user_fixture(%{email: "invitado@example.com"})
    invitado_scope = Mapo.Accounts.Scope.for_user(invitado)

    invitacion = invitacion_fixture(owner_scope, team, %{email: "invitado@example.com"})
    {:ok, _} = Teams.aceptar_invitacion(invitado_scope, invitacion)

    {:ok, _lv, html} = live(conn, ~p"/invitaciones/#{invitacion.token}")

    assert html =~ "ya fue aceptada"
  end

  test "shows login/register CTA for an anonymous visitor", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    invitacion = invitacion_fixture(owner_scope, team, %{email: "invitado@example.com"})

    {:ok, _lv, html} = live(conn, ~p"/invitaciones/#{invitacion.token}")

    assert html =~ team.name
    assert html =~ "invitado@example.com"
    assert html =~ "Iniciar sesión"
    assert html =~ "Crear cuenta"
  end

  test "shows a mismatch message for a logged-in user with a different email", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    invitacion = invitacion_fixture(owner_scope, team, %{email: "invitado@example.com"})

    otro = user_fixture(%{email: "otro@example.com"})
    conn = log_in_user(conn, otro)

    {:ok, _lv, html} = live(conn, ~p"/invitaciones/#{invitacion.token}")

    assert html =~ "invitado@example.com"
    assert html =~ "otro@example.com"
  end

  test "accepts the invitation for a logged-in user with the matching email", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    invitacion = invitacion_fixture(owner_scope, team, %{email: "invitado@example.com"})

    invitado = user_fixture(%{email: "invitado@example.com"})
    conn = log_in_user(conn, invitado)
    invitado_scope = Mapo.Accounts.Scope.for_user(invitado)

    {:ok, lv, html} = live(conn, ~p"/invitaciones/#{invitacion.token}")
    assert html =~ "Aceptar invitación"

    {:error, {:live_redirect, %{to: to}}} =
      lv
      |> element("button", "Aceptar invitación")
      |> render_click()

    assert to == ~p"/teams/#{team.id}"
    assert Teams.role_in_team(invitado_scope, team.id) == :member
  end
end
