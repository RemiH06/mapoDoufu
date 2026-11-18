defmodule Mapo.Teams do
  @moduledoc """
  The Teams context.
  """

  import Ecto.Query, warn: false
  alias Mapo.Repo

  alias Mapo.Teams.Team
  alias Mapo.Teams.Membership
  alias Mapo.Teams.Invitacion
  alias Mapo.Teams.TeamNotifier
  alias Mapo.Accounts.Scope

  # Lo que vive un enlace de invitacion sin aceptarse, desde el ultimo envio.
  @dias_invitacion 7

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
  Quita a un miembro de un equipo. Requiere que el scope sea `:owner`
  o `:admin`. Un `:admin` solo quita miembros (o se sale él); a otro admin
  o a un titular solo los quita un titular. No permite dejar el equipo sin
  ningun `:owner`.
  """
  def remove_member(%Scope{} = scope, %Team{} = team, %Membership{} = membership) do
    rol = role_in_team(scope, team.id)
    true = rol in [:owner, :admin]
    true = membership.team_id == team.id

    cond do
      not puede_quitar?(rol, membership, scope) -> {:error, :sin_permiso}
      membership.role == :owner and count_owners(team.id) <= 1 -> {:error, :last_owner}
      true -> delete_membership(membership)
    end
  end

  @doc "¿Puede alguien con `rol` quitar esa membresía? Lo usa también la pantalla."
  def puede_quitar?(:owner, _membership, _scope), do: true

  def puede_quitar?(:admin, %Membership{} = membership, %Scope{} = scope),
    do: membership.role == :member or membership.user_id == scope.user.id

  def puede_quitar?(_rol, _membership, _scope), do: false

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

  @doc """
  Invita por correo a alguien a un equipo, tenga o no cuenta en Mapo
  todavia. Requiere que el scope sea `:owner` o `:admin` del equipo.

  Si ya existe una invitacion pendiente para ese correo en ese equipo,
  la reutiliza (no duplica) con un enlace nuevo: el anterior deja de
  servir y el plazo de `@dias_invitacion` vuelve a correr. Regresa la
  invitacion con `token_claro`, que no se guarda.
  """
  def invitar_por_correo(%Scope{} = scope, %Team{} = team, email, role, url_fn)
      when role in [:member, :admin] and is_function(url_fn, 1) do
    true = role_in_team(scope, team.id) in [:owner, :admin]

    invitacion =
      Repo.get_by(Invitacion, team_id: team.id, email: email, estado: :pendiente) ||
        %Invitacion{}

    token = :crypto.strong_rand_bytes(32) |> Base.url_encode64(padding: false)

    attrs = %{
      email: email,
      role: role,
      token: hash_token(token),
      estado: :pendiente,
      team_id: team.id,
      invitado_por_id: scope.user.id
    }

    with {:ok, invitacion} <-
           invitacion
           |> Invitacion.changeset(attrs)
           |> Ecto.Changeset.force_change(:updated_at, DateTime.utc_now(:second))
           |> Repo.insert_or_update() do
      TeamNotifier.deliver_invitacion(invitacion, team, url_fn.(token))
      {:ok, %{invitacion | token_claro: token}}
    end
  end

  # Igual que en la migracion `20261117120000_hash_invitaciones_token`.
  defp hash_token(token), do: :crypto.hash(:sha256, token) |> Base.encode16(case: :lower)

  @doc """
  Busca una invitacion por su token: aceptada, o pendiente de los ultimos
  `@dias_invitacion` dias. Devuelve `nil` si no existe o ya caduco.
  Precarga `:team`.
  """
  def get_invitacion_por_token(token) when is_binary(token) do
    vigente_desde = DateTime.add(DateTime.utc_now(), -@dias_invitacion, :day)

    Repo.one(
      from i in Invitacion,
        where: i.token == ^hash_token(token),
        where: i.estado == :aceptada or i.updated_at > ^vigente_desde,
        preload: :team
    )
  end

  @doc """
  Gets a single invitacion.

  Raises `Ecto.NoResultsError` if the Invitacion does not exist.
  """
  def get_invitacion!(id), do: Repo.get!(Invitacion, id)

  @doc """
  Returns the list of pending invitaciones for a team. Requires the scoped
  user to belong to the team.
  """
  def list_invitaciones_pendientes(%Scope{} = scope, %Team{} = team) do
    true = role_in_team(scope, team.id) != nil

    Repo.all(
      from i in Invitacion,
        where: i.team_id == ^team.id and i.estado == :pendiente,
        order_by: i.inserted_at
    )
  end

  @doc """
  Acepta una invitacion pendiente para el usuario del scope. Requiere que
  el correo de la invitacion coincida (sin distinguir mayusculas) con el
  correo del usuario. Crea la membresia y marca la invitacion como
  aceptada, todo en una transaccion.
  """
  def aceptar_invitacion(%Scope{} = scope, %Invitacion{estado: :pendiente} = invitacion) do
    true = String.downcase(invitacion.email) == String.downcase(scope.user.email)

    Repo.transaction(fn ->
      with {:ok, _membership} <-
             create_membership(%{
               team_id: invitacion.team_id,
               user_id: scope.user.id,
               role: invitacion.role
             }),
           {:ok, invitacion} <-
             invitacion |> Invitacion.changeset(%{estado: :aceptada}) |> Repo.update() do
        invitacion
      else
        {:error, changeset} -> Repo.rollback(changeset)
      end
    end)
  end

  @doc """
  Cancela (borra) una invitacion pendiente. Requiere que el scope sea
  `:owner` o `:admin` del equipo de la invitacion.
  """
  def cancelar_invitacion(%Scope{} = scope, %Invitacion{} = invitacion) do
    true = role_in_team(scope, invitacion.team_id) in [:owner, :admin]

    Repo.delete(invitacion)
  end
end
