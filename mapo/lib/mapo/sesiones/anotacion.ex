defmodule Mapo.Sesiones.Anotacion do
  use Ecto.Schema
  import Ecto.Changeset

  schema "anotaciones" do
    field :texto, :string
    field :geom, Geo.PostGIS.Geometry
    belongs_to :sesion, Mapo.Sesiones.Sesion
    belongs_to :user, Mapo.Accounts.User

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(anotacion, attrs) do
    anotacion
    |> cast(attrs, [:texto, :geom, :sesion_id, :user_id])
    |> validate_required([:geom, :sesion_id, :user_id])
    |> foreign_key_constraint(:sesion_id)
    |> foreign_key_constraint(:user_id)
  end
end
