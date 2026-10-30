defmodule Mapo.NotasTest do
  use Mapo.DataCase

  alias Mapo.Notas

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  defp attrs(extra \\ %{}) do
    Map.merge(
      %{"cve_ent" => "14", "cve_mun" => "039", "documento" => "comercio", "texto" => "  ojo  "},
      extra
    )
  end

  test "create_nota/3 saves it trimmed, with its author, and broadcasts it" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    Notas.subscribe(team.id, "14", "039")

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

    assert {:error, cs} = Notas.create_nota(scope, team.id, attrs(%{"cve_mun" => "39"}))
    assert %{cve_mun: [_]} = errors_on(cs)
  end

  test "list_notas/4 returns only that team and municipio, oldest first" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    otro = team_fixture(scope, %{name: "otro"})

    {:ok, primera} = Notas.create_nota(scope, team.id, attrs(%{"texto" => "primera"}))
    {:ok, segunda} = Notas.create_nota(scope, team.id, attrs(%{"texto" => "segunda"}))
    {:ok, _} = Notas.create_nota(scope, team.id, attrs(%{"cve_mun" => "120"}))
    {:ok, _} = Notas.create_nota(scope, otro.id, attrs())

    assert Enum.map(Notas.list_notas(scope, team.id, "14", "039"), & &1.id) ==
             [primera.id, segunda.id]
  end

  test "only team members can list, create or delete" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    {:ok, nota} = Notas.create_nota(scope, team.id, attrs())
    outsider = user_scope_fixture()

    assert_raise MatchError, fn -> Notas.list_notas(outsider, team.id, "14", "039") end
    assert_raise MatchError, fn -> Notas.create_nota(outsider, team.id, attrs()) end
    assert_raise MatchError, fn -> Notas.delete_nota(outsider, team.id, nota.id) end
  end

  test "delete_nota/3 broadcasts the id and refuses a note from another team" do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    otro = team_fixture(scope, %{name: "otro"})
    {:ok, nota} = Notas.create_nota(scope, team.id, attrs())

    assert_raise Ecto.NoResultsError, fn -> Notas.delete_nota(scope, otro.id, nota.id) end

    Notas.subscribe(team.id, "14", "039")
    assert {:ok, _} = Notas.delete_nota(scope, team.id, nota.id)
    id = nota.id
    assert_received {:nota_borrada, ^id}
  end
end
