defmodule Mapo.Sesiones.Anotacion do
  use Ecto.Schema
  import Ecto.Changeset

  # Cómo se dibuja la marca. `geom` es geometría genérica: un punto para
  # "punto" y "circulo" (su centro, con `radio_m`), una línea para "flecha" (de
  # la cola a la punta) y "trazo", y un polígono. Una forma nueva se agrega
  # aquí, en `geom/1` y en `marcas.js`.
  @formas ~w(punto circulo flecha trazo poligono)
  # Un círculo más grande que una ciudad ya no es una marca a mano.
  @radio_maximo_m 50_000
  # Los mismos topes que respeta `marcas.js` al dibujar.
  @max_puntos 500
  @max_vertices 200
  @max_detalle 5_000

  schema "anotaciones" do
    field :texto, :string
    field :detalle, :string, default: ""
    field :geom, Geo.PostGIS.Geometry
    field :forma, :string, default: "punto"
    field :radio_m, :float
    # Lo llena `Mapo.Sesiones`: el lápiz de quien la puso en el equipo de la
    # sesión; 0 (grafito) si ya no está en él.
    field :lapiz, :integer, virtual: true, default: 0
    belongs_to :sesion, Mapo.Sesiones.Sesion
    belongs_to :user, Mapo.Accounts.User

    timestamps(type: :utc_datetime)
  end

  def formas, do: @formas

  @doc false
  def changeset(anotacion, attrs) do
    anotacion
    |> changeset_texto(attrs)
    |> cast(attrs, [:geom, :forma, :radio_m, :sesion_id, :user_id])
    |> validate_required([:geom, :forma, :sesion_id, :user_id])
    |> validate_inclusion(:forma, @formas)
    |> validar_radio()
    |> foreign_key_constraint(:sesion_id)
    |> foreign_key_constraint(:user_id)
  end

  @doc "Lo único que se edita de una marca ya puesta: su nota y su nota larga."
  def changeset_texto(anotacion, attrs) do
    anotacion
    # Una marca sin nota es válida: "" se guarda tal cual (las columnas son NOT
    # NULL y cast lo volvería nil). El tope es el del varchar de la columna.
    |> cast(attrs, [:texto, :detalle], empty_values: [])
    |> validate_length(:texto, max: 255)
    |> validate_length(:detalle, max: @max_detalle)
  end

  defp validar_radio(changeset) do
    case get_field(changeset, :forma) do
      "circulo" ->
        changeset
        |> validate_required([:radio_m])
        |> validate_number(:radio_m, greater_than: 0, less_than_or_equal_to: @radio_maximo_m)

      _ ->
        put_change(changeset, :radio_m, nil)
    end
  end

  @doc """
  La geometría de lo que manda el plano: `"lat"` y `"lon"` para el punto y el
  círculo, `"coords"` (pares `[lon, lat]`) para lo demás. `nil` si no se puede
  dibujar: coordenadas fuera del mundo, puntos de menos o de más.
  """
  def geom(%{"forma" => "flecha"} = params), do: linea(params["coords"], 2)
  def geom(%{"forma" => "trazo"} = params), do: linea(params["coords"], @max_puntos)

  def geom(%{"forma" => "poligono"} = params) do
    with [primero | _] = puntos <- puntos(params["coords"], @max_vertices + 1),
         vertices = quitar_cierre(puntos),
         true <- length(Enum.uniq(vertices)) >= 3 do
      %Geo.Polygon{coordinates: [vertices ++ [primero]], srid: 4326}
    else
      _ -> nil
    end
  end

  def geom(params) do
    case punto([params["lon"], params["lat"]]) do
      nil -> nil
      punto -> %Geo.Point{coordinates: punto, srid: 4326}
    end
  end

  defp linea(coords, maximo) do
    case puntos(coords, maximo) do
      [_, _ | _] = puntos -> %Geo.LineString{coordinates: puntos, srid: 4326}
      _ -> nil
    end
  end

  # Los puntos sin repetidos seguidos, o `nil` si alguno no sirve.
  defp puntos(coords, maximo) when is_list(coords) and length(coords) <= maximo do
    puntos = Enum.map(coords, &punto/1)
    if nil in puntos, do: nil, else: Enum.dedup(puntos)
  end

  defp puntos(_coords, _maximo), do: nil

  defp punto([lon, lat])
       when is_number(lon) and is_number(lat) and lon >= -180 and lon <= 180 and lat >= -90 and
              lat <= 90,
       do: {lon * 1.0, lat * 1.0}

  defp punto(_), do: nil

  defp quitar_cierre([primero | _] = puntos) do
    if length(puntos) > 1 and List.last(puntos) == primero,
      do: Enum.drop(puntos, -1),
      else: puntos
  end

  @doc "La anotación como la dibujan los hooks (`marcas.js`). Requiere `:user` precargado."
  def a_mapa(%__MODULE__{} = anotacion) do
    Map.merge(lugar(anotacion.geom), %{
      id: anotacion.id,
      forma: anotacion.forma,
      radio_m: anotacion.radio_m,
      texto: anotacion.texto,
      detalle: anotacion.detalle,
      autor: anotacion.user.email,
      firma: firma(anotacion.user.email),
      lapiz: anotacion.lapiz
    })
  end

  defp lugar(%Geo.Point{coordinates: {lon, lat}}), do: %{lat: lat, lon: lon}

  defp lugar(%Geo.LineString{coordinates: puntos}),
    do: %{coords: Enum.map(puntos, &Tuple.to_list/1)}

  defp lugar(%Geo.Polygon{coordinates: [anillo | _]}),
    do: %{coords: anillo |> Enum.drop(-1) |> Enum.map(&Tuple.to_list/1)}

  @doc """
  Dos letras de quien firma, para reconocerle sin depender del color: las
  iniciales si el correo trae nombre y apellido (`ana.perez@` es "AP"), o las
  dos primeras letras.
  """
  def firma(correo) do
    partes = correo |> String.split("@") |> hd() |> String.split(~r/[^\p{L}\p{N}]+/u, trim: true)

    case partes do
      [a, b | _] -> String.first(a) <> String.first(b)
      [a] -> String.slice(a, 0, 2)
      [] -> "?"
    end
    |> String.upcase()
  end
end
