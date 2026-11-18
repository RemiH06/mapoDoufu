defmodule Mapo.RasterFixtures do
  @moduledoc """
  Teselas en el formato WKB de PostGIS raster, como las que arma mapo_core:
  16 bits con signo, nodata -32768, esquina noroeste en (lon, lat).
  """

  def tesela(filas, lon, lat, paso) do
    alto = length(filas)
    ancho = length(hd(filas))

    cabeza =
      <<1, 0::little-16, 1::little-16, paso::little-float-64, -paso::little-float-64,
        lon::little-float-64, lat::little-float-64, 0.0::little-float-64, 0.0::little-float-64,
        4326::little-32, ancho::little-16, alto::little-16, 0x45, -32768::little-signed-16>>

    for v <- List.flatten(filas), into: cabeza, do: <<v::little-signed-16>>
  end

  @doc "Una capa ráster con valores, lista para muestrear."
  def capa_raster(scope, team_id, nombre, teselas, metros_pixel \\ 1_000.0) do
    {:ok, capa} =
      Mapo.Capas.crear_capa(
        scope,
        team_id,
        %{
          nombre: nombre,
          archivo: "#{nombre}.tif",
          tamano_bytes: 1,
          tipo: "raster",
          columnas: [],
          numericas: [],
          num_filas: 0,
          num_descartadas: 0
        },
        [],
        %{
          png: "imagen",
          oeste: -104.0,
          sur: 19.0,
          este: -103.0,
          norte: 20.0,
          limites: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
          metros_pixel: metros_pixel,
          teselas: teselas
        }
      )

    capa
  end
end
