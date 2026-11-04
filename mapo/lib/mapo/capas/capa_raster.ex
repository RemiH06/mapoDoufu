defmodule Mapo.Capas.CapaRaster do
  use Ecto.Schema

  # La imagen ya reproyectada y pintada por quintiles, no los valores: se ve,
  # pero no se puede consultar el valor de un píxel. El original no se guarda.
  @primary_key false
  schema "capa_rasters" do
    belongs_to :capa, Mapo.Capas.Capa, primary_key: true
    field :png, :binary
    field :oeste, :float
    field :sur, :float
    field :este, :float
    field :norte, :float
    field :limites, {:array, :float}
  end
end
