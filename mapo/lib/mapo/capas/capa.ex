defmodule Mapo.Capas.Capa do
  use Ecto.Schema
  import Ecto.Changeset

  @tipos ~w(puntos municipio ageb)

  schema "capas" do
    field :nombre, :string
    field :archivo, :string
    field :tamano_bytes, :integer
    field :tipo, :string
    field :columnas, {:array, :string}
    field :numericas, {:array, :string}, default: []
    field :num_filas, :integer
    field :num_descartadas, :integer
    field :repetidas, :integer, default: 0
    belongs_to :team, Mapo.Teams.Team
    belongs_to :user, Mapo.Accounts.User
    has_many :filas, Mapo.Capas.CapaFila

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(capa, attrs) do
    capa
    |> cast(attrs, [
      :nombre,
      :archivo,
      :tamano_bytes,
      :tipo,
      :columnas,
      :numericas,
      :num_filas,
      :num_descartadas,
      :repetidas,
      :team_id,
      :user_id
    ])
    |> validate_required([:nombre, :archivo, :tamano_bytes, :tipo, :num_filas, :team_id])
    |> validate_length(:nombre, max: 120)
    |> validate_length(:archivo, max: 255)
    |> validate_inclusion(:tipo, @tipos)
    |> foreign_key_constraint(:team_id)
    |> foreign_key_constraint(:user_id)
  end
end
