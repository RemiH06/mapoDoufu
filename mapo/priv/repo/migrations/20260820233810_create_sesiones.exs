defmodule Mapo.Repo.Migrations.CreateSesiones do
  use Ecto.Migration

  def change do
    create table(:sesiones) do
      add :nombre, :string, null: false
      add :team_id, references(:teams, on_delete: :delete_all), null: false

      timestamps(type: :utc_datetime)
    end

    create index(:sesiones, [:team_id])
  end
end
