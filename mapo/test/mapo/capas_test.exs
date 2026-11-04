defmodule Mapo.CapasTest do
  use Mapo.DataCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  alias Mapo.Capas
  alias Mapo.Teams.Membership

  defp attrs(extra \\ %{}) do
    Map.merge(
      %{
        nombre: "Ventas",
        archivo: "ventas.csv",
        tamano_bytes: 1_000,
        tipo: "puntos",
        columnas: ["lat", "lon", "ventas"],
        numericas: ["lat", "lon", "ventas"],
        num_filas: 1,
        num_descartadas: 0,
        repetidas: 0
      },
      extra
    )
  end

  defp punto(ventas \\ 5) do
    %{"lat" => 20.6, "lon" => -103.3, "clave" => nil, "datos" => %{"ventas" => ventas}}
  end

  defp zona(clave, ventas) do
    %{"lat" => nil, "lon" => nil, "clave" => clave, "datos" => %{"ventas" => ventas}}
  end

  defp miembro(team, role) do
    scope = user_scope_fixture()
    Repo.insert!(%Membership{team_id: team.id, user_id: scope.user.id, role: role})
    scope
  end

  setup do
    scope = user_scope_fixture()
    %{scope: scope, team: team_fixture(scope)}
  end

  test "guarda puntos con su geometría", %{scope: scope, team: team} do
    {:ok, capa} = Capas.crear_capa(scope, team.id, attrs(), [punto()])

    assert [%{lat: 20.6, lon: -103.3, id: id}] = Capas.puntos(capa)
    assert {%{"ventas" => 5}, 1} = Capas.ficha(scope, capa.id, {:id, id})
  end

  test "guarda más filas que un lote", %{scope: scope, team: team} do
    {:ok, capa} = Capas.crear_capa(scope, team.id, attrs(), List.duplicate(punto(), 2_500))
    assert length(Capas.puntos(capa)) == 2_500
  end

  test "la ficha por clave dice cuántos renglones tiene la zona", %{scope: scope, team: team} do
    {:ok, capa} =
      Capas.crear_capa(scope, team.id, attrs(%{tipo: "municipio"}), [
        zona("14120", 1),
        zona("14120", 2),
        zona("14039", 3)
      ])

    assert {%{"ventas" => 1}, 2} = Capas.ficha(scope, capa.id, {:clave, "14120"})
    assert Enum.sort(Capas.claves(capa)) == ["14039", "14120"]
  end

  test "pintable? pide numérica, zonas y un renglón por zona", %{scope: scope, team: team} do
    {:ok, zonas} = Capas.crear_capa(scope, team.id, attrs(%{tipo: "ageb"}), [zona("x", 1)])
    assert Capas.pintable?(zonas, "ventas")
    refute Capas.pintable?(zonas, "nombre")
    refute Capas.pintable?(%{zonas | repetidas: 1}, "ventas")
    refute Capas.pintable?(%{zonas | tipo: "puntos"}, "ventas")
    assert Capas.valores(zonas, "ventas") == %{"x" => 1}
  end

  describe "aislamiento entre equipos" do
    setup %{scope: scope, team: team} do
      {:ok, capa} = Capas.crear_capa(scope, team.id, attrs(), [punto()])
      %{capa: capa, ajeno: user_scope_fixture()}
    end

    test "quien no es del equipo no ve ni su existencia", %{ajeno: ajeno, capa: capa, team: team} do
      assert Capas.get_capa(ajeno, capa.id) == nil
      assert Capas.list_capas(ajeno, team.id) == []
      assert Capas.list_capas_del_usuario(ajeno) == []
    end

    test "la ficha tampoco, ni con ids buenos", %{ajeno: ajeno, capa: capa} do
      [%{id: id}] = Capas.puntos(capa)
      assert Capas.ficha(ajeno, capa.id, {:id, id}) == nil
    end

    test "una fila de otra capa no se lee con el id de la propia", %{scope: scope, capa: capa} do
      otro = team_fixture(scope, %{name: "otro"})
      {:ok, otra} = Capas.crear_capa(scope, otro.id, attrs(), [punto()])
      [%{id: id}] = Capas.puntos(otra)
      assert Capas.ficha(scope, capa.id, {:id, id}) == nil
    end

    test "al salir del equipo se pierde el acceso", %{team: team, capa: capa} do
      scope = miembro(team, :member)
      assert Capas.get_capa(scope, capa.id)
      Repo.delete_all(from m in Membership, where: m.user_id == ^scope.user.id)
      assert Capas.get_capa(scope, capa.id) == nil
    end

    test "no se puede subir a un equipo ajeno", %{ajeno: ajeno, team: team} do
      assert_raise MatchError, fn -> Capas.crear_capa(ajeno, team.id, attrs(), [punto()]) end
    end
  end

  describe "borrar" do
    test "quien la subió y los admins sí; otro miembro no", %{scope: scope, team: team} do
      autor = miembro(team, :member)
      otro = miembro(team, :member)
      admin = miembro(team, :admin)
      {:ok, capa} = Capas.crear_capa(autor, team.id, attrs(), [punto()])

      assert Capas.puede_borrar?(autor, capa)
      assert Capas.puede_borrar?(admin, capa)
      assert Capas.puede_borrar?(scope, capa)
      refute Capas.puede_borrar?(otro, capa)
      assert_raise MatchError, fn -> Capas.delete_capa(otro, capa) end
    end

    test "se llevan sus filas y liberan cuota", %{scope: scope, team: team} do
      {:ok, capa} = Capas.crear_capa(scope, team.id, attrs(), [punto()])
      assert Capas.uso_equipo(team.id) == 1_000

      {:ok, _} = Capas.delete_capa(scope, capa)

      assert Capas.uso_equipo(team.id) == 0
      assert Repo.aggregate(Mapo.Capas.CapaFila, :count) == 0
    end
  end

  test "la cuota es por equipo y no deja pasar", %{scope: scope, team: team} do
    tope = Capas.max_bytes_equipo()
    {:ok, _} = Capas.crear_capa(scope, team.id, attrs(%{tamano_bytes: tope - 10}), [punto()])

    assert Capas.cabe?(team.id, 10)
    refute Capas.cabe?(team.id, 11)

    assert {:error, :cuota} =
             Capas.crear_capa(scope, team.id, attrs(%{tamano_bytes: 11}), [punto()])

    otro = team_fixture(scope, %{name: "otro"})
    assert {:ok, _} = Capas.crear_capa(scope, otro.id, attrs(%{tamano_bytes: 11}), [punto()])
  end

  test "una capa inválida no deja rastro", %{scope: scope, team: team} do
    assert {:error, %Ecto.Changeset{}} =
             Capas.crear_capa(scope, team.id, attrs(%{tipo: "otro"}), [punto()])

    assert Capas.uso_equipo(team.id) == 0
  end
end
