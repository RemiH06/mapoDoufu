defmodule Mapo.Repo.Migrations.CreateInvitaciones do
  use Ecto.Migration

  def change do
    create table(:invitaciones) do
      add :email, :string, null: false
      add :role, :string, null: false
      add :token, :string, null: false
      add :estado, :string, null: false, default: "pendiente"
      add :team_id, references(:teams, on_delete: :delete_all), null: false
      add :invitado_por_id, references(:users, on_delete: :nilify_all)

      timestamps(type: :utc_datetime)
    end

    create unique_index(:invitaciones, [:token])
    create index(:invitaciones, [:team_id, :email])
  end
end
