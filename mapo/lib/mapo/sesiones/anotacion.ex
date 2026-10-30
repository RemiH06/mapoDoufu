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
    # Una marca sin nota es válida: "" se guarda tal cual (la columna es NOT
    # NULL y cast lo volvería nil). El tope es el del varchar de la columna.
    |> cast(attrs, [:texto, :geom, :sesion_id, :user_id], empty_values: [nil])
    |> validate_required([:geom, :sesion_id, :user_id])
    |> validate_length(:texto, max: 255)
    |> foreign_key_constraint(:sesion_id)
    |> foreign_key_constraint(:user_id)
  end
end
