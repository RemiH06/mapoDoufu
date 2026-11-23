defmodule Mapo.Repo.Migrations.AddZonaOperacionToUsers do
  use Ecto.Migration

  # Sesión 29b: la zona en la que opera cada quien (clave de la zona común,
  # docs/producto/zona.md). Las vistas la usan cuando el enlace no trae zona.
  def change do
    alter table(:users) do
      add :zona_operacion, :text
    end
  end
end
