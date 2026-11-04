defmodule Mapo.Repo.Migrations.CreateCapaRasters do
  use Ecto.Migration

  def change do
    create table(:capa_rasters, primary_key: false) do
      add :capa_id, references(:capas, on_delete: :delete_all), primary_key: true
      add :png, :binary, null: false
      add :oeste, :float, null: false
      add :sur, :float, null: false
      add :este, :float, null: false
      add :norte, :float, null: false
      add :limites, {:array, :float}, null: false
    end
  end
end
