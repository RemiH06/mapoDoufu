defmodule Mapo.Notas do
  @moduledoc """
  Notas del equipo sobre los documentos de `/perfil`: cada una cuelga de un
  equipo, un municipio y uno de los cinco documentos. No son geometricas
  (por eso no van en `anotaciones`, que son marcas sobre el plano).

  Igual que las anotaciones, son un pizarron del equipo: cualquier miembro
  las ve, las escribe y las borra, y llegan en vivo a quien tenga abierto el
  mismo perfil con el mismo equipo.
  """

  import Ecto.Query, warn: false
  alias Mapo.Repo
  alias Mapo.Accounts.Scope
  alias Mapo.Teams
  alias Mapo.Notas.NotaPerfil

  @doc "Notas de un equipo sobre un municipio, mas antigua primero, con autor precargado."
  def list_notas(%Scope{} = scope, team_id, cve_ent, cve_mun) do
    true = Teams.role_in_team(scope, team_id) != nil

    Repo.all(
      from n in NotaPerfil,
        where: n.team_id == ^team_id and n.cve_ent == ^cve_ent and n.cve_mun == ^cve_mun,
        order_by: [n.inserted_at, n.id],
        preload: :user
    )
  end

  def topico(team_id, cve_ent, cve_mun), do: "notas:#{team_id}:#{cve_ent}#{cve_mun}"

  def subscribe(team_id, cve_ent, cve_mun) do
    Phoenix.PubSub.subscribe(Mapo.PubSub, topico(team_id, cve_ent, cve_mun))
  end

  def unsubscribe(team_id, cve_ent, cve_mun) do
    Phoenix.PubSub.unsubscribe(Mapo.PubSub, topico(team_id, cve_ent, cve_mun))
  end

  defp broadcast(%NotaPerfil{} = nota, mensaje) do
    Phoenix.PubSub.broadcast(
      Mapo.PubSub,
      topico(nota.team_id, nota.cve_ent, nota.cve_mun),
      mensaje
    )
  end

  @doc """
  Crea una nota y la transmite. `attrs` lleva `"cve_ent"`, `"cve_mun"`,
  `"documento"` y `"texto"`. Requiere ser miembro del equipo.
  """
  def create_nota(%Scope{} = scope, team_id, attrs) do
    true = Teams.role_in_team(scope, team_id) != nil

    attrs = Map.merge(attrs, %{"team_id" => team_id, "user_id" => scope.user.id})

    with {:ok, nota} <- %NotaPerfil{} |> NotaPerfil.changeset(attrs) |> Repo.insert() do
      nota = Repo.preload(nota, :user)
      broadcast(nota, {:nota_creada, nota})
      {:ok, nota}
    end
  end

  @doc """
  Borra una nota del equipo `team_id`. Igual que en las anotaciones, se
  valida que la nota de verdad sea de ese equipo y no de otro cuyo id
  alguien haya adivinado. `Ecto.NoResultsError` si no.
  """
  def delete_nota(%Scope{} = scope, team_id, id) do
    true = Teams.role_in_team(scope, team_id) != nil
    nota = Repo.get_by!(NotaPerfil, id: id, team_id: team_id)

    with {:ok, nota} <- Repo.delete(nota) do
      broadcast(nota, {:nota_borrada, nota.id})
      {:ok, nota}
    end
  end
end
