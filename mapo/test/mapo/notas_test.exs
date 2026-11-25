defmodule Mapo.NotasTest do
  use Mapo.DataCase

  alias Mapo.Notas

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  defp attrs(extra \\ %{}) do
    Map.merge(
      %{"zona" => "mun:14039", "documento" => "comercio", "texto" => "  ojo  "},
      extra
    )
  end

  test "create_nota/3 saves it trimmed, with its author, and broadcasts it" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    Notas.subscribe(team.id, "mun:14039")

    assert {:ok, nota} = Notas.create_nota(scope, team.id, attrs())
    assert nota.texto == "ojo"
    assert nota.user.id == scope.user.id
    assert_received {:nota_creada, ^nota}
  end

  test "create_nota/3 rejects an unknown document, an empty text and a bad clave" do
    scope = user_scope_fixture()
    team = team_fixture(scope)

    assert {:error, cs} =
             Notas.create_nota(scope, team.id, attrs(%{"documento" => "x", "texto" => " "}))

    assert %{documento: [_], texto: [_]} = errors_on(cs)

    for mala <- ["14039", "xx:1", "mun:", "mun:14039\n", "col:1 2", nil] do
      assert {:error, cs} = Notas.create_nota(scope, team.id, attrs(%{"zona" => mala}))
      assert %{zona: [_ | _]} = errors_on(cs)
    end
  end

  test "list_notas/3 returns only that team and zona, oldest first" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    otro = team_fixture(scope, %{name: "otro"})

    {:ok, primera} = Notas.create_nota(scope, team.id, attrs(%{"texto" => "primera"}))
    {:ok, segunda} = Notas.create_nota(scope, team.id, attrs(%{"texto" => "segunda"}))
    {:ok, _} = Notas.create_nota(scope, team.id, attrs(%{"zona" => "mun:14120"}))
    {:ok, _} = Notas.create_nota(scope, otro.id, attrs())

    assert Enum.map(Notas.list_notas(scope, team.id, "mun:14039"), & &1.id) ==
             [primera.id, segunda.id]
  end

  test "a note hangs from any zona, a drawing too" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    dibujo = "pol:" <> Enum.map_join(1..200, ";", &"-103.#{10_000 + &1},20.#{60_000 + &1}")

    for zona <- ["ent:14", "zm:14.1.01", "col:14098_0135", "cir:-103.35,20.67,2500", dibujo] do
      assert {:ok, nota} = Notas.create_nota(scope, team.id, attrs(%{"zona" => zona}))
      assert nota.cve_ent == nil
      assert [%{zona: ^zona}] = Notas.list_notas(scope, team.id, zona)
    end

    # De un solo municipio se guarda también como antes, para poder regresar de versión.
    assert {:ok, %{cve_ent: "14", cve_mun: "039"}} = Notas.create_nota(scope, team.id, attrs())
    varios = attrs(%{"zona" => "mun:14039,14120"})
    assert {:ok, %{cve_ent: nil}} = Notas.create_nota(scope, team.id, varios)
  end

  test "only team members can list, create or delete" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    {:ok, nota} = Notas.create_nota(scope, team.id, attrs())
    outsider = user_scope_fixture()

    assert_raise MatchError, fn -> Notas.list_notas(outsider, team.id, "mun:14039") end
    assert_raise MatchError, fn -> Notas.create_nota(outsider, team.id, attrs()) end
    assert_raise MatchError, fn -> Notas.delete_nota(outsider, team.id, nota.id) end
  end

  test "delete_nota/3 broadcasts the id and refuses a note from another team" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    otro = team_fixture(scope, %{name: "otro"})
    {:ok, nota} = Notas.create_nota(scope, team.id, attrs())

    assert_raise Ecto.NoResultsError, fn -> Notas.delete_nota(scope, otro.id, nota.id) end

    Notas.subscribe(team.id, "mun:14039")
    assert {:ok, _} = Notas.delete_nota(scope, team.id, nota.id)
    id = nota.id
    assert_received {:nota_borrada, ^id}
  end
end
