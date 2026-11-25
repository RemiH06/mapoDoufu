defmodule Mapo.Notas.NotaPerfil do
  use Ecto.Schema
  import Ecto.Changeset

  # Los ocho documentos de /perfil, por su enfoque.
  @documentos ~w(demografia vivienda servicios comercio consumo seguridad laboral hacienda)

  schema "notas_perfil" do
    field :zona, :string
    # Solo si la zona es un municipio, para poder regresar a la versión sin zonas.
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
    |> cast(attrs, [:zona, :documento, :texto, :team_id, :user_id])
    |> update_change(:texto, &String.trim/1)
    |> validate_required([:zona, :documento, :texto, :team_id, :user_id])
    |> validate_format(:zona, ~r/\A(ent|mun|zm|cp|col|pol|cir):[\w.,;-]+\z/)
    |> validate_length(:zona, max: 6_000)
    |> poner_municipio()
    |> validate_inclusion(:documento, @documentos)
    |> validate_length(:texto, max: 500)
    |> foreign_key_constraint(:team_id)
    |> foreign_key_constraint(:user_id)
  end

  defp poner_municipio(changeset) do
    case get_field(changeset, :zona) do
      <<"mun:", ent::binary-size(2), mun::binary-size(3)>> ->
        change(changeset, cve_ent: ent, cve_mun: mun)

      _ ->
        changeset
    end
  end
end
