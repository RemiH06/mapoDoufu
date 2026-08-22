defmodule MapoWeb.TeamLive.ShowTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  alias Mapo.Teams

  setup :register_and_log_in_user

  test "owner sees the team, its members, and the add-member form", %{conn: conn, scope: scope} do
    team = team_fixture(scope)

    {:ok, _lv, html} = live(conn, ~p"/teams/#{team}")

    assert html =~ team.name
    assert html =~ scope.user.email
    assert html =~ "Dueño"
    assert html =~ "Agregar miembro"
  end

  test "plain member does not see the add-member form", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    member = user_fixture()
    {:ok, _} = Teams.create_membership(%{team_id: team.id, user_id: member.id, role: :member})

    conn = log_in_user(conn, member)
    {:ok, _lv, html} = live(conn, ~p"/teams/#{team}")

    assert html =~ team.name
    refute html =~ "Agregar miembro"
  end

  test "raises for a user who is not a member of the team", %{conn: conn} do
    team = team_fixture(user_scope_fixture())

    assert_raise Ecto.NoResultsError, fn ->
      live(conn, ~p"/teams/#{team}")
    end
  end

  test "owner adds an existing user as a member", %{conn: conn, scope: scope} do
    team = team_fixture(scope)
    new_member = user_fixture()

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    html =
      lv
      |> form("#add_member_form", member: %{email: new_member.email, role: "member"})
      |> render_submit()

    assert html =~ "Miembro agregado con éxito."
    assert html =~ new_member.email
    assert Teams.role_in_team(scope, team.id) |> is_atom()
  end

  test "adding a member with an unknown email sends an invitation", %{conn: conn, scope: scope} do
    team = team_fixture(scope)

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    html =
      lv
      |> form("#add_member_form", member: %{email: "nadie@example.com", role: "member"})
      |> render_submit()

    assert html =~ "Se envió una invitación a nadie@example.com."
    assert html =~ "Invitaciones pendientes"
    assert html =~ "nadie@example.com"
    assert Teams.list_invitaciones_pendientes(scope, team) |> length() == 1
  end

  test "owner cancels a pending invitation", %{conn: conn, scope: scope} do
    team = team_fixture(scope)

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    lv
    |> form("#add_member_form", member: %{email: "nadie@example.com", role: "member"})
    |> render_submit()

    html =
      lv
      |> element("[phx-click='cancelar_invitacion']")
      |> render_click()

    assert html =~ "Invitación cancelada."
    refute html =~ "nadie@example.com"
    assert Teams.list_invitaciones_pendientes(scope, team) == []
  end

  test "owner removes a member", %{conn: conn, scope: scope} do
    team = team_fixture(scope)
    member = user_fixture()
    {:ok, membership} = Teams.create_membership(%{team_id: team.id, user_id: member.id, role: :member})

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    html =
      lv
      |> element("[phx-value-id='#{membership.id}']")
      |> render_click()

    assert html =~ "Miembro quitado del equipo."
    refute html =~ member.email
  end

  test "cannot remove the last owner", %{conn: conn, scope: scope} do
    team = team_fixture(scope)
    [owner_membership] = Teams.list_team_memberships(team.id)

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    refute has_element?(lv, "[phx-value-id='#{owner_membership.id}']")
  end

  test "redirects if user is not logged in" do
    team = team_fixture(user_scope_fixture())
    conn = build_conn()
    assert {:error, redirect} = live(conn, ~p"/teams/#{team}")
    assert {:redirect, %{to: path}} = redirect
    assert path == ~p"/users/log-in"
  end

  test "creates a sesion and redirects straight to its collaborative map", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)

    {:ok, lv, _html} = live(conn, ~p"/teams/#{team}")

    {:ok, sesion_live, html} =
      lv
      |> form("#sesion_form", sesion: %{nombre: "Mapa de arranque"})
      |> render_submit()
      |> follow_redirect(conn)

    assert html =~ "Mapa de arranque"
    assert sesion_live
  end

  test "lists existing sesiones", %{conn: conn, scope: scope} do
    team = team_fixture(scope)
    sesion = Mapo.SesionesFixtures.sesion_fixture(scope, team, %{"nombre" => "Ya existente"})

    {:ok, _lv, html} = live(conn, ~p"/teams/#{team}")

    assert html =~ sesion.nombre
  end
end
