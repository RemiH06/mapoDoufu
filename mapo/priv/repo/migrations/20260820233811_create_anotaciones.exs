defmodule Mapo.Repo.Migrations.CreateAnotaciones do
  use Ecto.Migration

  def change do
    create table(:anotaciones) do
      add :texto, :string, null: false
      add :geom, :geometry, null: false
      add :sesion_id, references(:sesiones, on_delete: :delete_all), null: false
      add :user_id, references(:users, on_delete: :delete_all), null: false

      timestamps(type: :utc_datetime)
    end

    create index(:anotaciones, [:sesion_id])
    execute "CREATE INDEX anotaciones_geom_index ON anotaciones USING GIST (geom)",
            "DROP INDEX anotaciones_geom_index"
  end
end
