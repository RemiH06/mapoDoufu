defmodule MapoWeb.TeamLive.NewTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  alias Mapo.Teams

  setup :register_and_log_in_user

  test "renders the new team form", %{conn: conn} do
    {:ok, _lv, html} = live(conn, ~p"/teams/new")
    assert html =~ "Crear equipo"
  end

  test "creates a team and makes the user its owner", %{conn: conn, scope: scope} do
    {:ok, lv, _html} = live(conn, ~p"/teams/new")

    {:ok, show_live, html} =
      lv
      |> form("#team_form", team: %{name: "Equipo de prueba"})
      |> render_submit()
      |> follow_redirect(conn)

    assert html =~ "Equipo creado con éxito."
    assert html =~ "Equipo de prueba"

    [team] = Teams.list_teams(scope)
    assert team.name == "Equipo de prueba"
    assert Teams.role_in_team(scope, team.id) == :owner
    assert show_live
  end

  test "renders errors for invalid data", %{conn: conn} do
    {:ok, lv, _html} = live(conn, ~p"/teams/new")

    result =
      lv
      |> form("#team_form", team: %{name: ""})
      |> render_change()

    assert result =~ "no puede estar en blanco"
  end

  test "redirects if user is not logged in" do
    conn = build_conn()
    assert {:error, redirect} = live(conn, ~p"/teams/new")
    assert {:redirect, %{to: path}} = redirect
    assert path == ~p"/users/log-in"
  end
end
