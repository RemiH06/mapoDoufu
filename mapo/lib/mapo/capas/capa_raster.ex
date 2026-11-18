defmodule Mapo.Capas.CapaRaster do
  use Ecto.Schema

  # La imagen ya reproyectada y pintada por quintiles, para dibujar. Los valores
  # van aparte, en teselas de `capa_raster_teselas` (raster de PostGIS, que Ecto
  # no conoce: se leen y escriben con SQL). El original no se guarda.
  @primary_key false
  schema "capa_rasters" do
    belongs_to :capa, Mapo.Capas.Capa, primary_key: true
    field :png, :binary
    field :oeste, :float
    field :sur, :float
    field :este, :float
    field :norte, :float
    field :limites, {:array, :float}
    # Descripción de la banda en el GeoTIFF, lado del píxel guardado y cuánto se
    # redujo para caber (nil si no). Vacíos en capas de antes de los valores.
    field :banda, :string
    field :metros_pixel, :float
    field :reducido, :float
  end
end
