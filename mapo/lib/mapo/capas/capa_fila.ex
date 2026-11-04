defmodule Mapo.Capas.CapaFila do
  use Ecto.Schema

  # Un renglón ya ubicado: con `geom` (punto) o con `clave` (CVEGEO de un
  # municipio o AGEB). Se guarda aparte y con geometría, no como JSON dentro de
  # `capas`, para que el cruce con fuentes públicas sea una consulta de PostGIS.
  schema "capa_filas" do
    field :geom, Geo.PostGIS.Geometry
    field :clave, :string
    field :datos, :map
    belongs_to :capa, Mapo.Capas.Capa
  end
end
