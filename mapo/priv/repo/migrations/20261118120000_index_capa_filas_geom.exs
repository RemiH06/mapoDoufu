defmodule Mapo.Repo.Migrations.IndexCapaFilasGeom do
  use Ecto.Migration

  # La distancia entre capas busca el renglón más cercano con el índice, y el
  # filtro por texto ignora acentos ("educacion" encuentra "educación").
  def change do
    execute "CREATE EXTENSION IF NOT EXISTS unaccent", ""
    create index(:capa_filas, [:geom], using: :gist)
  end
end
