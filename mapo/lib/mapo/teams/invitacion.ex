defmodule Mapo.Teams.Invitacion do
  use Ecto.Schema
  import Ecto.Changeset

  schema "invitaciones" do
    field :email, :string
    field :role, Ecto.Enum, values: [:member, :admin]
    # En la base va el SHA-256 del token: quien lea un respaldo no puede usar
    # los enlaces. El token en claro solo existe al mandar el correo.
    field :token, :string
    field :token_claro, :string, virtual: true
    field :estado, Ecto.Enum, values: [:pendiente, :aceptada], default: :pendiente
    belongs_to :team, Mapo.Teams.Team
    belongs_to :invitado_por, Mapo.Accounts.User

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(invitacion, attrs) do
    invitacion
    |> cast(attrs, [:email, :role, :token, :estado, :team_id, :invitado_por_id])
    |> validate_required([:email, :role, :token, :estado, :team_id])
    |> validate_format(:email, ~r/^[^@,;\s]+@[^@,;\s]+$/,
      message: "debe tener un signo @ y sin espacios"
    )
    |> unique_constraint(:token)
    |> foreign_key_constraint(:team_id)
  end
end
