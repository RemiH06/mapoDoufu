defmodule Mapo.Repo.Migrations.CreateCapaRasterTeselas do
  use Ecto.Migration

  # Los valores de un ráster, para consultar su píxel y resumirlo alrededor de
  # cada renglón de otra capa. Teselas de 256 x 256 en EPSG:4326 que arma
  # mapo_core: Postgres nunca abre con GDAL el archivo que subió alguien.
  def change do
    execute "CREATE EXTENSION IF NOT EXISTS postgis_raster", ""

    create table(:capa_raster_teselas) do
      add :capa_id, references(:capas, on_delete: :delete_all), null: false
      add :rast, :raster, null: false
    end

    create index(:capa_raster_teselas, [:capa_id])

    execute "CREATE INDEX capa_raster_teselas_rast_index ON capa_raster_teselas USING gist (ST_ConvexHull(rast))",
            "DROP INDEX capa_raster_teselas_rast_index"

    alter table(:capa_rasters) do
      add :banda, :string
      add :metros_pixel, :float
      add :reducido, :float
    end
  end
end
