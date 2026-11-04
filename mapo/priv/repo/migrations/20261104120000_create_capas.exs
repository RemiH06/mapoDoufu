defmodule Mapo.Repo.Migrations.CreateCapas do
  use Ecto.Migration

  def change do
    create table(:capas) do
      add :nombre, :string, null: false
      add :archivo, :string, null: false
      add :tamano_bytes, :bigint, null: false
      add :tipo, :string, null: false
      add :columnas, {:array, :text}, null: false
      add :numericas, {:array, :text}, null: false, default: []
      add :num_filas, :integer, null: false
      add :num_descartadas, :integer, null: false
      add :repetidas, :integer, null: false, default: 0
      add :team_id, references(:teams, on_delete: :delete_all), null: false
      # Si la cuenta se borra, la capa sigue siendo del equipo.
      add :user_id, references(:users, on_delete: :nilify_all)

      timestamps(type: :utc_datetime)
    end

    create index(:capas, [:team_id])

    create table(:capa_filas) do
      add :capa_id, references(:capas, on_delete: :delete_all), null: false
      add :geom, :geometry
      add :clave, :text
      add :datos, :map, null: false
    end

    create index(:capa_filas, [:capa_id, :clave])
  end
end
