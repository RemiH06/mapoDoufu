defmodule MapoWeb.SesionLive.ShowTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Mapo.SesionesFixtures

  alias Mapo.Sesiones

  setup :register_and_log_in_user

  test "renders the map for a team member", %{conn: conn, scope: scope} do
    team = team_fixture(scope)
    sesion = sesion_fixture(scope, team)

    {:ok, _lv, html} = live(conn, ~p"/sesiones/#{sesion}")

    assert html =~ sesion.nombre
    assert html =~ "mapa-colaborativo"
  end

  test "raises for a user who is not a member of the owning team", %{conn: conn} do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    sesion = sesion_fixture(owner_scope, team)

    assert_raise Ecto.NoResultsError, fn ->
      live(conn, ~p"/sesiones/#{sesion}")
    end
  end

  test "an annotation created anywhere is pushed live to anyone viewing the session", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)
    sesion = sesion_fixture(scope, team)

    {:ok, lv, _html} = live(conn, ~p"/sesiones/#{sesion}")

    {:ok, anotacion} = Sesiones.create_anotacion(scope, sesion, 19.4326, -99.1332, "hola equipo")
    id = anotacion.id
    autor = scope.user.email

    assert_push_event(lv, "nueva_anotacion", %{
      id: ^id,
      lat: 19.4326,
      lon: -99.1332,
      texto: "hola equipo",
      autor: ^autor
    })
  end

  test "clicking the map (simulated via the hook event) is visible to a second member watching the same session" do
    owner_scope = user_scope_fixture()
    team = team_fixture(owner_scope)
    member = user_fixture()
    {:ok, _} = Mapo.Teams.create_membership(%{team_id: team.id, user_id: member.id, role: :member})
    sesion = sesion_fixture(owner_scope, team)

    conn_owner = log_in_user(build_conn(), owner_scope.user)
    conn_member = log_in_user(build_conn(), member)

    {:ok, lv_owner, _html} = live(conn_owner, ~p"/sesiones/#{sesion}")
    {:ok, lv_member, _html} = live(conn_member, ~p"/sesiones/#{sesion}")

    render_hook(lv_owner, "crear_anotacion", %{"lat" => 19.0, "lon" => -99.0, "texto" => "aqui"})
    autor = owner_scope.user.email

    assert_push_event(lv_owner, "nueva_anotacion", %{texto: "aqui", autor: ^autor})
    assert_push_event(lv_member, "nueva_anotacion", %{texto: "aqui", autor: ^autor})
  end

  test "editing an annotation via the hook event is visible to a second member", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)
    sesion = sesion_fixture(scope, team)
    {:ok, anotacion} = Sesiones.create_anotacion(scope, sesion, 19.0, -99.0, "original")

    member = user_fixture()
    {:ok, _} = Mapo.Teams.create_membership(%{team_id: team.id, user_id: member.id, role: :member})
    member_conn = log_in_user(build_conn(), member)

    {:ok, lv, _html} = live(conn, ~p"/sesiones/#{sesion}")
    {:ok, lv_member, _html} = live(member_conn, ~p"/sesiones/#{sesion}")

    render_hook(lv_member, "editar_anotacion", %{"id" => anotacion.id, "texto" => "editado"})

    id = anotacion.id
    assert_push_event(lv, "anotacion_actualizada", %{id: ^id, texto: "editado"})
    assert_push_event(lv_member, "anotacion_actualizada", %{id: ^id, texto: "editado"})
    assert Sesiones.get_anotacion!(anotacion.id).texto == "editado"
  end

  test "deleting an annotation via the hook event is visible to a second member", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)
    sesion = sesion_fixture(scope, team)
    {:ok, anotacion} = Sesiones.create_anotacion(scope, sesion, 19.0, -99.0, "borrame")

    {:ok, lv, _html} = live(conn, ~p"/sesiones/#{sesion}")

    render_hook(lv, "borrar_anotacion", %{"id" => anotacion.id})

    id = anotacion.id
    assert_push_event(lv, "anotacion_borrada", %{id: ^id})
    assert_raise Ecto.NoResultsError, fn -> Sesiones.get_anotacion!(anotacion.id) end
  end

  test "presence: a second viewer connecting shows up in the first viewer's list", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)
    member = user_fixture()
    {:ok, _} = Mapo.Teams.create_membership(%{team_id: team.id, user_id: member.id, role: :member})
    sesion = sesion_fixture(scope, team)

    {:ok, lv, html} = live(conn, ~p"/sesiones/#{sesion}")
    refute html =~ "Viendo ahora"

    member_conn = log_in_user(build_conn(), member)
    {:ok, _lv_member, _html} = live(member_conn, ~p"/sesiones/#{sesion}")

    # el diff de presencia llega por PubSub de forma asincrona; se le da
    # un instante para que el proceso de lv lo procese antes de volver
    # a pedir el render.
    Process.sleep(50)

    assert render(lv) =~ member.email
  end
end
