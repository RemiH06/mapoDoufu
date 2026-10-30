defmodule Mapo.Notas.NotaPerfil do
  use Ecto.Schema
  import Ecto.Changeset

  # Los cinco documentos de /perfil, por su enfoque.
  @documentos ~w(demografia comercio consumo seguridad laboral)

  schema "notas_perfil" do
    field :cve_ent, :string
    field :cve_mun, :string
    field :documento, :string
    field :texto, :string
    belongs_to :team, Mapo.Teams.Team
    belongs_to :user, Mapo.Accounts.User

    timestamps(type: :utc_datetime)
  end

  def documentos, do: @documentos

  @doc false
  def changeset(nota, attrs) do
    nota
    |> cast(attrs, [:cve_ent, :cve_mun, :documento, :texto, :team_id, :user_id])
    |> update_change(:texto, &String.trim/1)
    |> validate_required([:cve_ent, :cve_mun, :documento, :texto, :team_id, :user_id])
    |> validate_format(:cve_ent, ~r/^\d{2}$/)
    |> validate_format(:cve_mun, ~r/^\d{3}$/)
    |> validate_inclusion(:documento, @documentos)
    |> validate_length(:texto, max: 500)
    |> foreign_key_constraint(:team_id)
    |> foreign_key_constraint(:user_id)
  end
end
