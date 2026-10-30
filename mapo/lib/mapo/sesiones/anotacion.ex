defmodule Mapo.Sesiones.Anotacion do
  use Ecto.Schema
  import Ecto.Changeset

  # Cómo se dibuja la marca. `geom` es geometría genérica: un punto para
  # "punto" y para "circulo" (su centro, con `radio_m`). Una forma nueva se
  # agrega aquí, en su validación y en `marcas.js`; un trazo libre guardaría
  # un LineString en la misma columna.
  @formas ~w(punto circulo)
  # Un círculo más grande que una ciudad ya no es una marca a mano.
  @radio_maximo_m 50_000

  schema "anotaciones" do
    field :texto, :string
    field :geom, Geo.PostGIS.Geometry
    field :forma, :string, default: "punto"
    field :radio_m, :float
    belongs_to :sesion, Mapo.Sesiones.Sesion
    belongs_to :user, Mapo.Accounts.User

    timestamps(type: :utc_datetime)
  end

  @doc false
  def changeset(anotacion, attrs) do
    anotacion
    # Una marca sin nota es válida: "" se guarda tal cual (la columna es NOT
    # NULL y cast lo volvería nil). El tope es el del varchar de la columna.
    |> cast(attrs, [:texto, :geom, :forma, :radio_m, :sesion_id, :user_id], empty_values: [nil])
    |> validate_required([:geom, :forma, :sesion_id, :user_id])
    |> validate_length(:texto, max: 255)
    |> validate_inclusion(:forma, @formas)
    |> validar_radio()
    |> foreign_key_constraint(:sesion_id)
    |> foreign_key_constraint(:user_id)
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

  @doc "La anotación como la dibujan los hooks (`marcas.js`). Requiere `:user` precargado."
  def a_mapa(%__MODULE__{geom: %Geo.Point{coordinates: {lon, lat}}} = anotacion) do
    %{
      id: anotacion.id,
      lat: lat,
      lon: lon,
      forma: anotacion.forma,
      radio_m: anotacion.radio_m,
      texto: anotacion.texto,
      autor: anotacion.user.email
    }
  end
end
