defmodule Mapo.Sesiones.Sesion do
  use Ecto.Schema
  import Ecto.Changeset

  schema "sesiones" do
    field :nombre, :string
    belongs_to :team, Mapo.Teams.Team
    has_many :anotaciones, Mapo.Sesiones.Anotacion

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(sesion, attrs) do
    sesion
    |> cast(attrs, [:nombre, :team_id])
    |> validate_required([:nombre, :team_id])
    |> foreign_key_constraint(:team_id)
  end
end
