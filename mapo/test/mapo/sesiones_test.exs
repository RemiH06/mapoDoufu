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

      assert {:error, %Ecto.Changeset{}} = Sesiones.create_sesion(scope, team.id, %{"nombre" => ""})
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
  end
end
