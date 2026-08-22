defmodule Mapo.TeamsFixtures do
  @moduledoc """
  This module defines test helpers for creating
  entities via the `Mapo.Teams` context.
  """

  @doc """
  Generate a team. `scope`'s user becomes its `:owner`.
  """
  def team_fixture(scope, attrs \\ %{}) do
    attrs =
      Enum.into(attrs, %{
        name: "some name"
      })

    {:ok, team} = Mapo.Teams.create_team(scope, attrs)
    team
  end

  @doc """
  Generate a membership. Builds its own team and user if not given, so it
  never collides with the owner membership `team_fixture/2` already
  creates for its own scope.
  """
  def membership_fixture(attrs \\ %{}) do
    attrs = Enum.into(attrs, %{})

    team_id = attrs[:team_id] || team_fixture(Mapo.AccountsFixtures.user_scope_fixture()).id
    user_id = attrs[:user_id] || Mapo.AccountsFixtures.user_fixture().id

    attrs =
      attrs
      |> Enum.into(%{role: :member})
      |> Map.put(:team_id, team_id)
      |> Map.put(:user_id, user_id)

    {:ok, membership} = Mapo.Teams.create_membership(attrs)
    membership
  end

  @doc """
  Generate a pending invitacion for `team`, invited by `scope`'s user.
  """
  def invitacion_fixture(scope, team, attrs \\ %{}) do
    attrs = Enum.into(attrs, %{})
    email = attrs[:email] || "invitado#{System.unique_integer()}@example.com"
    role = attrs[:role] || :member

    {:ok, invitacion} =
      Mapo.Teams.invitar_por_correo(scope, team, email, role, fn token -> "http://localhost/invitaciones/#{token}" end)

    invitacion
  end
end
