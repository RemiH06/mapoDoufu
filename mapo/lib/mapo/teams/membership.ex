defmodule Mapo.Teams.Membership do
  use Ecto.Schema
  import Ecto.Changeset

  schema "team_memberships" do
    field :role, Ecto.Enum, values: [:owner, :admin, :member]
    field :team_id, :id
    field :user_id, :id

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(membership, attrs) do
    membership
    |> cast(attrs, [:role, :team_id, :user_id])
    |> validate_required([:role, :team_id, :user_id])
    |> foreign_key_constraint(:team_id)
    |> foreign_key_constraint(:user_id)
    |> unique_constraint([:team_id, :user_id])
  end
end
