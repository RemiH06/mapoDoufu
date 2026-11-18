defmodule Mapo.Repo.Migrations.AddFechasToCapas do
  use Ecto.Migration

  # Columnas de fecha de cada capa, para filtrar por rango (docs/producto/datos-propios.md).
  def change do
    alter table(:capas) do
      add :fechas, {:array, :text}, null: false, default: []
    end
  end
end
