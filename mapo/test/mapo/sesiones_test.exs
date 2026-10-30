defmodule Mapo.SesionesTest do
  use Mapo.DataCase

  alias Mapo.Sesiones

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Mapo.SesionesFixtures

  describe "sesiones" do
    test "list_sesiones/2 lists only sessions of a team the scope belongs to" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert Sesiones.list_sesiones(scope, team.id) == [sesion]
    end

    test "list_sesiones/2 raises for a scope that is not a team member" do
      team = team_fixture(user_scope_fixture())
      outsider = user_scope_fixture()

      assert_raise MatchError, fn -> Sesiones.list_sesiones(outsider, team.id) end
    end

    test "create_sesion/3 requires the scope to be a team member" do
      team = team_fixture(user_scope_fixture())
      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.create_sesion(outsider, team.id, %{"nombre" => "x"})
      end
    end

    test "create_sesion/3 with invalid data returns an error changeset" do
      scope = user_scope_fixture()
      team = team_fixture(scope)

      assert {:error, %Ecto.Changeset{}} =
               Sesiones.create_sesion(scope, team.id, %{"nombre" => ""})
    end

    test "list_sesiones_del_usuario/1 lists sessions of every team of the scope, and only those" do
      scope = user_scope_fixture()
      b = team_fixture(scope, %{name: "B"})
      a = team_fixture(scope, %{name: "A"})
      de_b = sesion_fixture(scope, b, %{"nombre" => "uno"})
      de_a = sesion_fixture(scope, a, %{"nombre" => "dos"})
      ajeno = user_scope_fixture()
      sesion_fixture(ajeno, team_fixture(ajeno))

      assert [primera, segunda] = Sesiones.list_sesiones_del_usuario(scope)
      assert {primera.id, segunda.id} == {de_a.id, de_b.id}
      assert primera.team.name == "A"
    end

    test "get_sesion!/2 raises for a scope that is not a team member" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)
      outsider = user_scope_fixture()

      assert_raise Ecto.NoResultsError, fn -> Sesiones.get_sesion!(outsider, sesion.id) end
    end
  end

  describe "anotaciones" do
    test "create_anotacion/5 saves a real PostGIS point and broadcasts it" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      Sesiones.subscribe_sesion(sesion.id)

      assert {:ok, anotacion} =
               Sesiones.create_anotacion(scope, sesion, 19.4326, -99.1332, "una nota")

      assert %Geo.Point{coordinates: {-99.1332, 19.4326}, srid: 4326} = anotacion.geom
      assert anotacion.user.id == scope.user.id

      assert_received {:anotacion_creada, ^anotacion}
    end

    test "create_anotacion/5 accepts a mark without text and rejects one too long" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, %{texto: ""}} = Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "")

      assert {:error, changeset} =
               Sesiones.create_anotacion(
                 scope,
                 sesion,
                 20.67,
                 -103.35,
                 String.duplicate("a", 256)
               )

      assert %{texto: [_]} = errors_on(changeset)
    end

    test "create_anotacion/6 saves a circle as its center plus a radius" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, circulo} =
               Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "zona", %{
                 "forma" => "circulo",
                 "radio_m" => 450
               })

      assert circulo.forma == "circulo"
      assert circulo.radio_m == 450.0
      assert %Geo.Point{coordinates: {-103.35, 20.67}} = circulo.geom

      assert %{forma: "circulo", radio_m: 450.0, lat: 20.67, lon: -103.35} =
               Mapo.Sesiones.Anotacion.a_mapa(circulo)
    end

    test "create_anotacion/6 rejects a circle without radius and an unknown shape" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:error, cs} =
               Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "", %{
                 "forma" => "circulo"
               })

      assert %{radio_m: [_]} = errors_on(cs)

      assert {:error, cs} =
               Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "", %{"forma" => "flecha"})

      assert %{forma: [_]} = errors_on(cs)
    end

    test "a point drops any radius it was sent" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, %{forma: "punto", radio_m: nil}} =
               Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "", %{"radio_m" => 10})
    end

    test "create_anotacion/5 requires the scope to be a team member" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)
      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.create_anotacion(outsider, sesion, 0.0, 0.0, "")
      end
    end

    test "list_anotaciones/1 returns them oldest first with the author preloaded" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      {:ok, primera} = Sesiones.create_anotacion(scope, sesion, 19.0, -99.0, "primera")
      {:ok, segunda} = Sesiones.create_anotacion(scope, sesion, 20.0, -100.0, "segunda")

      [a, b] = Sesiones.list_anotaciones(sesion.id)
      assert a.id == primera.id
      assert b.id == segunda.id
      assert a.user.email == scope.user.email
    end

    test "update_anotacion/4 changes the text and broadcasts it, any team member can do it" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)
      {:ok, anotacion} = Sesiones.create_anotacion(owner_scope, sesion, 19.0, -99.0, "original")

      otro_miembro = user_fixture()

      {:ok, _} =
        Mapo.Teams.create_membership(%{team_id: team.id, user_id: otro_miembro.id, role: :member})

      otro_scope = Mapo.Accounts.Scope.for_user(otro_miembro)

      Sesiones.subscribe_sesion(sesion.id)

      assert {:ok, actualizada} =
               Sesiones.update_anotacion(otro_scope, sesion, anotacion, "editado")

      assert actualizada.texto == "editado"
      assert_received {:anotacion_actualizada, ^actualizada}
    end

    test "update_anotacion/4 requires the scope to be a team member" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)
      {:ok, anotacion} = Sesiones.create_anotacion(owner_scope, sesion, 19.0, -99.0, "original")
      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.update_anotacion(outsider, sesion, anotacion, "hackeo")
      end
    end

    test "update_anotacion/4 rejects an annotation that belongs to a different session" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion_a = sesion_fixture(owner_scope, team)
      sesion_b = sesion_fixture(owner_scope, team)

      {:ok, anotacion_de_a} =
        Sesiones.create_anotacion(owner_scope, sesion_a, 19.0, -99.0, "de a")

      assert_raise MatchError, fn ->
        Sesiones.update_anotacion(owner_scope, sesion_b, anotacion_de_a, "hackeo")
      end
    end

    test "delete_anotacion/3 removes it and broadcasts the id" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)
      {:ok, anotacion} = Sesiones.create_anotacion(scope, sesion, 19.0, -99.0, "borrame")

      Sesiones.subscribe_sesion(sesion.id)

      assert {:ok, _} = Sesiones.delete_anotacion(scope, sesion, anotacion)
      assert_raise Ecto.NoResultsError, fn -> Sesiones.get_anotacion!(anotacion.id) end
      id = anotacion.id
      assert_received {:anotacion_borrada, ^id}
    end

    test "delete_anotacion/3 requires the scope to be a team member" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)
      {:ok, anotacion} = Sesiones.create_anotacion(owner_scope, sesion, 19.0, -99.0, "original")
      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.delete_anotacion(outsider, sesion, anotacion)
      end
    end
  end
end
