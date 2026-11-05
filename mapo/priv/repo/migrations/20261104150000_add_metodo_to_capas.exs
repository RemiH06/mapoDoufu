defmodule Mapo.Repo.Migrations.AddMetodoToCapas do
  use Ecto.Migration

  def change do
    # Solo lo traen las capas que salen de un cruce.
    alter table(:capas) do
      add :metodo, :text
    end
  end
end
