defmodule MapoWeb.DatosLive.Derivada do
  @moduledoc """
  Piezas que comparten las pantallas que sacan una capa de otra (distancia y
  valor de un ráster): las condiciones de filtro y la lectura de lo que llega
  del navegador, que solo vale si es una columna de la capa.
  """

  use Phoenix.Component

  import MapoWeb.CoreComponents, only: [input: 1]

  attr :form, :any, required: true
  attr :lado, :string, required: true
  attr :columnas, :list, required: true
  attr :ejemplo, :string, required: true

  @doc """
  Dos condiciones que se cumplen las dos; una barra separa alternativas dentro
  de una ("039|120"). Los campos van en `<form>[filtro_<lado>][i]`.
  """
  def condiciones(assigns) do
    ~H"""
    <p class="secundario">
      Solo los renglones que cumplan, sin importar mayúsculas ni acentos. Para aceptar varios textos, sepáralos con una barra: 039|120.
    </p>

    <div :for={i <- 0..1} class="distancia-condicion">
      <.input
        type="select"
        id={"#{@lado}_columna_#{i}"}
        name={"#{@form.name}[filtro_#{@lado}][#{i}][columna]"}
        label={if i == 0, do: "Donde la columna", else: "y donde la columna"}
        value={condicion(@form, @lado, i, "columna")}
        options={[{"(cualquiera)", ""} | @columnas]}
      />
      <.input
        type="text"
        id={"#{@lado}_texto_#{i}"}
        name={"#{@form.name}[filtro_#{@lado}][#{i}][texto]"}
        label="contiene"
        value={condicion(@form, @lado, i, "texto")}
        placeholder={if i == 0, do: @ejemplo}
      />
    </div>
    """
  end

  defp condicion(form, lado, i, campo),
    do: get_in(form.params, ["filtro_#{lado}", to_string(i), campo]) || ""

  @doc "La columna si es de la capa; si no, `nil`."
  def columna(nombre, capa), do: if(nombre in capa.columnas, do: nombre)

  @doc "Las condiciones del formulario que traen columna de la capa y texto."
  def filtros(condiciones, capa) when is_map(condiciones) do
    for i <- ["0", "1"],
        %{"columna" => col, "texto" => texto} <- [condiciones[i]],
        columna(col, capa) && String.trim(texto) != "",
        do: {col, String.trim(texto)}
  end

  def filtros(_, _), do: []

  @doc "Radio en metros enteros, de 1 a 100,000, o `nil` si viene vacío."
  def radio(texto) do
    case Integer.parse(String.trim(texto || "")) do
      :error -> {:ok, nil}
      {n, ""} when n >= 1 and n <= 100_000 -> {:ok, n}
      _ -> {:error, "El radio va de 1 a 100,000 metros, en número entero."}
    end
  end

  @doc "Una columna que parezca nombre; si no, la primera."
  def etiqueta(capa) do
    Enum.find(capa.columnas, List.first(capa.columnas), fn c ->
      String.downcase(c) =~ ~r/nombre|^nom_|^name|descrip|titulo/
    end)
  end

  @doc "Por qué no se guardó."
  def mensaje(:cuota), do: "El resultado ya no cabe en los 500 MB del equipo. Borra alguna capa."
  def mensaje(%Ecto.Changeset{}), do: "Revisa el nombre de la capa (máximo 120 caracteres)."
  def mensaje(_), do: "No se pudo guardar."
end
