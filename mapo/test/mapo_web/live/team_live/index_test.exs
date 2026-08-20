defmodule MapoWeb.TeamLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  setup :register_and_log_in_user

  test "lists only the teams the user belongs to", %{conn: conn, scope: scope} do
    team = team_fixture(scope, %{name: "Mi equipo"})
    other_team = team_fixture(user_scope_fixture(), %{name: "Equipo ajeno"})

    {:ok, _lv, html} = live(conn, ~p"/teams")

    assert html =~ team.name
    refute html =~ other_team.name
  end

  test "shows an empty state with no teams", %{conn: conn} do
    {:ok, _lv, html} = live(conn, ~p"/teams")

    assert html =~ "Todavía no perteneces a ningún equipo."
  end

  test "links to the new team page", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/teams")

    {:ok, _new_live, new_html} =
      lv
      |> element("a", "Crear equipo")
      |> render_click()
      |> follow_redirect(conn, ~p"/teams/new")

    assert new_html =~ "Crear equipo"
  end

  test "redirects if user is not logged in" do
    conn = build_conn()
    assert {:error, redirect} = live(conn, ~p"/teams")
    assert {:redirect, %{to: path}} = redirect
    assert path == ~p"/users/log-in"
  end
end
