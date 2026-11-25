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
    test "create_anotacion/3 saves a real PostGIS point and broadcasts it" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      Sesiones.subscribe_sesion(sesion.id)

      assert {:ok, anotacion} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 19.4326,
                 "lon" => -99.1332,
                 "texto" => "una nota"
               })

      assert %Geo.Point{coordinates: {-99.1332, 19.4326}, srid: 4326} = anotacion.geom
      assert anotacion.user.id == scope.user.id

      assert_received {:anotacion_creada, ^anotacion}
    end

    test "create_anotacion/3 accepts a mark without text and rejects one too long" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, %{texto: ""}} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 20.67,
                 "lon" => -103.35,
                 "texto" => ""
               })

      assert {:error, changeset} =
               Sesiones.create_anotacion(
                 scope,
                 sesion,
                 %{"lat" => 20.67, "lon" => -103.35, "texto" => String.duplicate("a", 256)}
               )

      assert %{texto: [_]} = errors_on(changeset)
    end

    test "create_anotacion/3 saves a circle as its center plus a radius" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, circulo} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 20.67,
                 "lon" => -103.35,
                 "texto" => "zona",
                 "forma" => "circulo",
                 "radio_m" => 450
               })

      assert circulo.forma == "circulo"
      assert circulo.radio_m == 450.0
      assert %Geo.Point{coordinates: {-103.35, 20.67}} = circulo.geom

      assert %{forma: "circulo", radio_m: 450.0, lat: 20.67, lon: -103.35} =
               Mapo.Sesiones.Anotacion.a_mapa(circulo)
    end

    test "create_anotacion/3 rejects a circle without radius and an unknown shape" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:error, cs} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 20.67,
                 "lon" => -103.35,
                 "texto" => "",
                 "forma" => "circulo"
               })

      assert %{radio_m: [_]} = errors_on(cs)

      assert {:error, cs} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 20.67,
                 "lon" => -103.35,
                 "texto" => "",
                 "forma" => "estrella"
               })

      assert %{forma: [_]} = errors_on(cs)
    end

    test "create_anotacion/3 saves arrows, strokes and polygons with their own geometry" do
      scope = user_scope_fixture()
      sesion = sesion_fixture(scope, team_fixture(scope))
      [a, b, c] = coords = [[-103.35, 20.67], [-103.34, 20.67], [-103.34, 20.68]]

      casos = [
        {"flecha", [a, b], [a, b]},
        # dos puntos iguales seguidos son uno
        {"trazo", [a, a, b, c], coords},
        # el anillo puede venir cerrado o abierto: se guarda cerrado y se manda abierto
        {"poligono", coords, coords},
        {"poligono", coords ++ [a], coords}
      ]

      for {forma, manda, esperado} <- casos do
        assert {:ok, marca} =
                 Sesiones.create_anotacion(scope, sesion, %{"forma" => forma, "coords" => manda})

        mapa = Mapo.Sesiones.Anotacion.a_mapa(Mapo.Repo.reload(marca) |> Mapo.Repo.preload(:user))
        assert mapa.forma == forma
        assert mapa.coords == esperado
        refute Map.has_key?(mapa, :lat)
      end
    end

    test "create_anotacion/3 rejects what cannot be drawn" do
      scope = user_scope_fixture()
      sesion = sesion_fixture(scope, team_fixture(scope))
      [a, b] = [[-103.35, 20.67], [-103.34, 20.67]]

      malas = [
        %{"lat" => "20", "lon" => -103.35},
        %{"lat" => 200, "lon" => -103.35},
        %{"forma" => "circulo", "radio_m" => 10},
        %{"forma" => "flecha", "coords" => [a]},
        %{"forma" => "flecha", "coords" => [a, a]},
        %{"forma" => "flecha", "coords" => [a, b, a]},
        %{"forma" => "flecha", "coords" => [a, [-103.35]]},
        %{"forma" => "trazo", "coords" => List.duplicate(a, 10) ++ [nil]},
        %{"forma" => "trazo", "coords" => for(i <- 1..501, do: [-103 - i / 1000, 20])},
        %{"forma" => "trazo"},
        %{"forma" => "trazo", "coords" => "x"},
        %{"forma" => "poligono", "coords" => []},
        %{"forma" => "poligono", "coords" => [a, b, a]},
        %{"forma" => "poligono", "coords" => for(i <- 1..202, do: [-103 - i / 1000, i / 10])}
      ]

      for mala <- malas do
        assert {:error, cs} = Sesiones.create_anotacion(scope, sesion, mala)
        assert %{geom: [_]} = errors_on(cs), inspect(mala)
      end

      assert Sesiones.list_anotaciones(sesion.id) == []
    end

    test "a mark keeps a long note apart from its label" do
      scope = user_scope_fixture()
      sesion = sesion_fixture(scope, team_fixture(scope))
      params = %{"lat" => 20.67, "lon" => -103.35, "texto" => "obra", "detalle" => "uno\n\ndos"}

      assert {:ok, %{texto: "obra", detalle: "uno\n\ndos"} = marca} =
               Sesiones.create_anotacion(scope, sesion, params)

      # La forma y el lugar no se editan; borrar la nota larga es mandarla vacía.
      assert {:ok, %{texto: "obra", detalle: "", forma: "punto"}} =
               Sesiones.update_anotacion(scope, sesion, marca, %{
                 "detalle" => "",
                 "forma" => "circulo"
               })

      assert {:error, cs} =
               Sesiones.update_anotacion(scope, sesion, marca, %{
                 "detalle" => String.duplicate("a", 5001)
               })

      assert %{detalle: [_]} = errors_on(cs)
    end

    test "each mark carries its author's pencil, graphite once they leave the team" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)
      membresia = membership_fixture(%{team_id: team.id})
      otro = Mapo.Accounts.Scope.for_user(Mapo.Accounts.get_user!(membresia.user_id))
      lugar = %{"lat" => 20.67, "lon" => -103.35}

      assert {:ok, %{lapiz: 1}} = Sesiones.create_anotacion(scope, sesion, lugar)
      assert {:ok, %{lapiz: 2} = suya} = Sesiones.create_anotacion(otro, sesion, lugar)
      # editarla no la cambia de lápiz
      assert {:ok, %{lapiz: 2}} =
               Sesiones.update_anotacion(scope, sesion, suya, %{"texto" => "corregida"})

      Mapo.Teams.delete_membership(membresia)
      assert [%{lapiz: 1}, %{lapiz: 0}] = Sesiones.list_anotaciones(sesion.id)
    end

    test "firma/1 gives two letters of the author" do
      alias Mapo.Sesiones.Anotacion

      assert Anotacion.firma("ana.perez@x.mx") == "AP"
      assert Anotacion.firma("remi@x.mx") == "RE"
      assert Anotacion.firma("ñu@x.mx") == "ÑU"
      assert Anotacion.firma("__@x.mx") == "?"
    end

    test "a point drops any radius it was sent" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      assert {:ok, %{forma: "punto", radio_m: nil}} =
               Sesiones.create_anotacion(scope, sesion, %{
                 "lat" => 20.67,
                 "lon" => -103.35,
                 "texto" => "",
                 "radio_m" => 10
               })
    end

    test "create_anotacion/3 requires the scope to be a team member" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)
      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.create_anotacion(outsider, sesion, %{"lat" => 0.0, "lon" => 0.0, "texto" => ""})
      end
    end

    test "list_anotaciones/1 returns them oldest first with the author preloaded" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      {:ok, primera} =
        Sesiones.create_anotacion(scope, sesion, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "primera"
        })

      {:ok, segunda} =
        Sesiones.create_anotacion(scope, sesion, %{
          "lat" => 20.0,
          "lon" => -100.0,
          "texto" => "segunda"
        })

      [a, b] = Sesiones.list_anotaciones(sesion.id)
      assert a.id == primera.id
      assert b.id == segunda.id
      assert a.user.email == scope.user.email
    end

    test "update_anotacion/4 changes the text and broadcasts it, any team member can do it" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)

      {:ok, anotacion} =
        Sesiones.create_anotacion(owner_scope, sesion, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "original"
        })

      otro_miembro = user_fixture()

      {:ok, _} =
        Mapo.Teams.create_membership(%{team_id: team.id, user_id: otro_miembro.id, role: :member})

      otro_scope = Mapo.Accounts.Scope.for_user(otro_miembro)

      Sesiones.subscribe_sesion(sesion.id)

      assert {:ok, actualizada} =
               Sesiones.update_anotacion(otro_scope, sesion, anotacion, %{"texto" => "editado"})

      assert actualizada.texto == "editado"
      assert_received {:anotacion_actualizada, ^actualizada}
    end

    test "update_anotacion/4 requires the scope to be a team member" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion = sesion_fixture(owner_scope, team)

      {:ok, anotacion} =
        Sesiones.create_anotacion(owner_scope, sesion, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "original"
        })

      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.update_anotacion(outsider, sesion, anotacion, %{"texto" => "hackeo"})
      end
    end

    test "update_anotacion/4 rejects an annotation that belongs to a different session" do
      owner_scope = user_scope_fixture()
      team = team_fixture(owner_scope)
      sesion_a = sesion_fixture(owner_scope, team)
      sesion_b = sesion_fixture(owner_scope, team)

      {:ok, anotacion_de_a} =
        Sesiones.create_anotacion(owner_scope, sesion_a, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "de a"
        })

      assert_raise MatchError, fn ->
        Sesiones.update_anotacion(owner_scope, sesion_b, anotacion_de_a, %{"texto" => "hackeo"})
      end
    end

    test "delete_anotacion/3 removes it and broadcasts the id" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      sesion = sesion_fixture(scope, team)

      {:ok, anotacion} =
        Sesiones.create_anotacion(scope, sesion, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "borrame"
        })

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

      {:ok, anotacion} =
        Sesiones.create_anotacion(owner_scope, sesion, %{
          "lat" => 19.0,
          "lon" => -99.0,
          "texto" => "original"
        })

      outsider = user_scope_fixture()

      assert_raise MatchError, fn ->
        Sesiones.delete_anotacion(outsider, sesion, anotacion)
      end
    end
  end
end
