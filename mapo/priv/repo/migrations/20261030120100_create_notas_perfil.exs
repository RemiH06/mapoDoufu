defmodule Mapo.Repo.Migrations.CreateNotasPerfil do
  use Ecto.Migration

  def change do
    create table(:notas_perfil) do
      add :cve_ent, :string, size: 2, null: false
      add :cve_mun, :string, size: 3, null: false
      add :documento, :string, null: false
      add :texto, :string, size: 500, null: false
      add :team_id, references(:teams, on_delete: :delete_all), null: false
      add :user_id, references(:users, on_delete: :delete_all), null: false

      timestamps(type: :utc_datetime)
    end

    create index(:notas_perfil, [:team_id, :cve_ent, :cve_mun])
  end
end
