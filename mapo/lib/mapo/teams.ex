defmodule Mapo.Teams do
  @moduledoc """
  The Teams context.
  """

  import Ecto.Query, warn: false
  alias Mapo.Repo

  alias Mapo.Teams.Team
  alias Mapo.Teams.Membership
  alias Mapo.Accounts.Scope

  @doc """
  Subscribes to scoped notifications about any team changes.

  The broadcasted messages match the pattern:

    * {:created, %Team{}}
    * {:updated, %Team{}}
    * {:deleted, %Team{}}

  """
  def subscribe_teams(%Scope{} = scope) do
    key = scope.user.id

    Phoenix.PubSub.subscribe(Mapo.PubSub, "user:#{key}:teams")
  end

  defp broadcast_team(%Scope{} = scope, message) do
    key = scope.user.id

    Phoenix.PubSub.broadcast(Mapo.PubSub, "user:#{key}:teams", message)
  end

  @doc """
  Returns the role (`:owner`, `:admin`, `:member`) the scoped user has in
  the given team, or `nil` if they are not a member.
  """
  def role_in_team(%Scope{} = scope, team_id) do
    Repo.one(
      from m in Membership,
        where: m.team_id == ^team_id and m.user_id == ^scope.user.id,
        select: m.role
    )
  end

  @doc """
  Returns the list of teams the scoped user belongs to.

  ## Examples

      iex> list_teams(scope)
      [%Team{}, ...]

  """
  def list_teams(%Scope{} = scope) do
    Repo.all(
      from t in Team,
        join: m in Membership,
        on: m.team_id == t.id,
        where: m.user_id == ^scope.user.id,
        select: t
    )
  end

  @doc """
  Gets a single team the scoped user belongs to.

  Raises `Ecto.NoResultsError` if the Team does not exist, or the user is
  not a member of it.

  ## Examples

      iex> get_team!(scope, 123)
      %Team{}

      iex> get_team!(scope, 456)
      ** (Ecto.NoResultsError)

  """
  def get_team!(%Scope{} = scope, id) do
    Repo.one!(
      from t in Team,
        join: m in Membership,
        on: m.team_id == t.id,
        where: t.id == ^id and m.user_id == ^scope.user.id,
        select: t
    )
  end

  @doc """
  Creates a team, with the scoped user as its `:owner`.

  ## Examples

      iex> create_team(scope, %{field: value})
      {:ok, %Team{}}

      iex> create_team(scope, %{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def create_team(%Scope{} = scope, attrs) do
    Repo.transaction(fn ->
      with {:ok, team} <- %Team{} |> Team.changeset(attrs) |> Repo.insert(),
           {:ok, _membership} <-
             %Membership{}
             |> Membership.changeset(%{team_id: team.id, user_id: scope.user.id, role: :owner})
             |> Repo.insert() do
        broadcast_team(scope, {:created, team})
        team
      else
        {:error, changeset} -> Repo.rollback(changeset)
      end
    end)
  end

  @doc """
  Updates a team. Requires the scoped user to be `:owner` or `:admin`.

  ## Examples

      iex> update_team(scope, team, %{field: new_value})
      {:ok, %Team{}}

      iex> update_team(scope, team, %{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def update_team(%Scope{} = scope, %Team{} = team, attrs) do
    true = role_in_team(scope, team.id) in [:owner, :admin]

    with {:ok, team = %Team{}} <-
           team
           |> Team.changeset(attrs)
           |> Repo.update() do
      broadcast_team(scope, {:updated, team})
      {:ok, team}
    end
  end

  @doc """
  Deletes a team. Requires the scoped user to be `:owner`.

  ## Examples

      iex> delete_team(scope, team)
      {:ok, %Team{}}

      iex> delete_team(scope, team)
      {:error, %Ecto.Changeset{}}

  """
  def delete_team(%Scope{} = scope, %Team{} = team) do
    true = role_in_team(scope, team.id) == :owner

    with {:ok, team = %Team{}} <-
           Repo.delete(team) do
      broadcast_team(scope, {:deleted, team})
      {:ok, team}
    end
  end

  @doc """
  Returns an `%Ecto.Changeset{}` for tracking team changes.

  ## Examples

      iex> change_team(scope, team)
      %Ecto.Changeset{data: %Team{}}

  """
  def change_team(%Scope{} = scope, %Team{} = team, attrs \\ %{}) do
    if team.id, do: true = role_in_team(scope, team.id) != nil

    Team.changeset(team, attrs)
  end

  @doc """
  Returns the list of team_memberships.

  ## Examples

      iex> list_team_memberships()
      [%Membership{}, ...]

  """
  def list_team_memberships do
    Repo.all(Membership)
  end

  @doc """
  Returns the list of memberships for a given team.
  """
  def list_team_memberships(team_id) do
    Repo.all(from m in Membership, where: m.team_id == ^team_id, order_by: m.inserted_at)
    |> Repo.preload(:user)
  end

  @doc """
  Agrega a un usuario existente (por correo) como miembro de un equipo.
  Requiere que el scope sea `:owner` o `:admin` del equipo. No permite
  agregar con rol `:owner` desde aqui (evita mintear dueños de paso).

  Devuelve `{:error, :not_found}` si no existe una cuenta con ese correo.
  """
  def add_member_by_email(%Scope{} = scope, %Team{} = team, email, role)
      when role in [:member, :admin] do
    true = role_in_team(scope, team.id) in [:owner, :admin]

    case Mapo.Accounts.get_user_by_email(email) do
      nil -> {:error, :not_found}
      user -> create_membership(%{team_id: team.id, user_id: user.id, role: role})
    end
  end

  @doc """
  Quita a un miembro de un equipo. Requiere que el scope sea `:owner`
  o `:admin`. No permite dejar el equipo sin ningun `:owner`.
  """
  def remove_member(%Scope{} = scope, %Team{} = team, %Membership{} = membership) do
    true = role_in_team(scope, team.id) in [:owner, :admin]
    true = membership.team_id == team.id

    if membership.role == :owner and count_owners(team.id) <= 1 do
      {:error, :last_owner}
    else
      delete_membership(membership)
    end
  end

  defp count_owners(team_id) do
    Repo.aggregate(
      from(m in Membership, where: m.team_id == ^team_id and m.role == :owner),
      :count
    )
  end

  @doc """
  Gets a single membership.

  Raises `Ecto.NoResultsError` if the Membership does not exist.

  ## Examples

      iex> get_membership!(123)
      %Membership{}

      iex> get_membership!(456)
      ** (Ecto.NoResultsError)

  """
  def get_membership!(id), do: Repo.get!(Membership, id)

  @doc """
  Creates a membership.

  ## Examples

      iex> create_membership(%{field: value})
      {:ok, %Membership{}}

      iex> create_membership(%{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def create_membership(attrs) do
    %Membership{}
    |> Membership.changeset(attrs)
    |> Repo.insert()
  end

  @doc """
  Updates a membership.

  ## Examples

      iex> update_membership(membership, %{field: new_value})
      {:ok, %Membership{}}

      iex> update_membership(membership, %{field: bad_value})
      {:error, %Ecto.Changeset{}}

  """
  def update_membership(%Membership{} = membership, attrs) do
    membership
    |> Membership.changeset(attrs)
    |> Repo.update()
  end

  @doc """
  Deletes a membership.

  ## Examples

      iex> delete_membership(membership)
      {:ok, %Membership{}}

      iex> delete_membership(membership)
      {:error, %Ecto.Changeset{}}

  """
  def delete_membership(%Membership{} = membership) do
    Repo.delete(membership)
  end

  @doc """
  Returns an `%Ecto.Changeset{}` for tracking membership changes.

  ## Examples

      iex> change_membership(membership)
      %Ecto.Changeset{data: %Membership{}}

  """
  def change_membership(%Membership{} = membership, attrs \\ %{}) do
    Membership.changeset(membership, attrs)
  end
end
