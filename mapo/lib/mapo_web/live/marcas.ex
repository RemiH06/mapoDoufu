defmodule MapoWeb.Marcas do
  @moduledoc """
  Las marcas del equipo sobre el plano, compartidas por `/sesiones/:id` y la
  capa "Tus marcas" de `/mapa`: los dos hablan con el mismo hook de dibujo
  (`assets/js/marcas.js`) y escriben en la misma sesion, asi que una marca
  puesta en un lado llega en vivo al otro.

  La vista guarda la sesion en `socket.assigns.sesion` (en `/mapa` puede ser
  `nil` si no se eligio ninguna), llama a `poner/2` al abrirla y le pasa aqui
  sus eventos y mensajes. De cada marca solo se guarda de quien es
  (`@marcas`), para la lista de lapices; la geometria vive en el hook.
  """

  use Phoenix.Component

  import Phoenix.LiveView, only: [push_event: 3, put_flash: 3]

  alias Mapo.Sesiones
  alias Mapo.Sesiones.Anotacion

  @herramientas [
    {"punto", "Punto", "Clic en el plano para poner una marca.", "Toca el plano."},
    {"circulo", "Círculo", "Un clic en el centro y otro en la orilla para encerrar una zona.",
     "Toca el centro y luego la orilla."},
    {"flecha", "Flecha", "Un clic donde empieza y otro en lo que señala.",
     "Toca donde empieza y luego lo que señala."},
    {"trazo", "Trazo", "Arrastra para dibujar a mano alzada; con la rueda se acerca el plano.",
     "Dibuja con un dedo; con dos se mueve el plano."},
    {"poligono", "Polígono", "Un clic por vértice; para cerrar, clic en el primero o doble clic.",
     "Toca cada vértice; el primero cierra."}
  ]
  @claves Enum.map(@herramientas, &elem(&1, 0))
  @eventos ~w(crear_anotacion editar_anotacion borrar_anotacion elegir_herramienta)
  @mensajes [:anotacion_creada, :anotacion_actualizada, :anotacion_borrada]

  defguard evento_de_marca(evento) when evento in @eventos

  defguard mensaje_de_marca(mensaje)
           when is_tuple(mensaje) and tuple_size(mensaje) == 2 and elem(mensaje, 0) in @mensajes

  attr :herramienta, :string, required: true

  @doc "Con qué forma pone marca el siguiente clic en el plano."
  def selector(assigns) do
    assigns = assign(assigns, :herramientas, @herramientas)

    ~H"""
    <div class="herramientas" role="group" aria-label="Forma de la marca">
      <button
        :for={{clave, nombre, _, _} <- @herramientas}
        type="button"
        phx-click="elegir_herramienta"
        phx-value-herramienta={clave}
        aria-pressed={to_string(@herramienta == clave)}
      >
        {nombre}
      </button>
    </div>
    """
  end

  attr :herramienta, :string, required: true

  @doc "Cómo se dibuja la forma elegida: completa con ratón, corta con el dedo."
  def pista(assigns) do
    {_, _, largo, corto} = List.keyfind!(@herramientas, assigns.herramienta, 0)
    assigns = assign(assigns, largo: largo, corto: corto)

    ~H"""
    <span class="largo">{@largo}</span><span class="corto">{@corto}</span>
    """
  end

  attr :marcas, :map, required: true
  attr :yo, :string, required: true

  @doc "De quién es cada lápiz: la firma que sale en el plano, el correo y cuántas marcas lleva."
  def lapices(assigns) do
    assigns = assign(assigns, :autores, autores(assigns.marcas))

    ~H"""
    <ul :if={@autores != []} class="lapices" aria-label="Lápices">
      <li :for={a <- @autores} style={"--lapiz: var(--lapiz-#{a.lapiz})"}>
        <span class="lapiz-firma" aria-hidden="true">{a.firma}</span>
        <span class="lapiz-autor">{if a.autor == @yo, do: "tú", else: a.autor}</span>
        <span class="secundario">
          {a.cuantas}{if a.lapiz == 0, do: ", ya no está en el equipo"}
        </span>
      </li>
    </ul>
    """
  end

  defp autores(marcas) do
    marcas
    |> Map.values()
    |> Enum.frequencies()
    |> Enum.map(fn {marca, cuantas} -> Map.put(marca, :cuantas, cuantas) end)
    |> Enum.sort_by(&{-&1.cuantas, &1.autor})
  end

  @doc "Guarda de quién es cada marca de la sesión recién abierta."
  def poner(socket, anotaciones),
    do: assign(socket, :marcas, Map.new(anotaciones, &{&1.id, de_quien(&1)}))

  defp de_quien(%Anotacion{} = a),
    do: %{autor: a.user.email, firma: Anotacion.firma(a.user.email), lapiz: a.lapiz}

  def evento(_evento, _params, %{assigns: %{sesion: nil}} = socket), do: socket

  def evento("crear_anotacion", params, socket) do
    %{current_scope: scope, sesion: sesion} = socket.assigns

    case Sesiones.create_anotacion(scope, sesion, params) do
      {:ok, _anotacion} -> socket
      {:error, _changeset} -> put_flash(socket, :error, "No se pudo guardar la marca.")
    end
  end

  def evento("editar_anotacion", %{"id" => id} = params, socket) do
    %{current_scope: scope, sesion: sesion} = socket.assigns

    case Sesiones.update_anotacion(scope, sesion, Sesiones.get_anotacion!(id), params) do
      {:ok, _anotacion} -> socket
      {:error, _changeset} -> put_flash(socket, :error, "No se pudo actualizar la marca.")
    end
  end

  def evento("borrar_anotacion", %{"id" => id}, socket) do
    %{current_scope: scope, sesion: sesion} = socket.assigns

    case Sesiones.delete_anotacion(scope, sesion, Sesiones.get_anotacion!(id)) do
      {:ok, _anotacion} -> socket
      {:error, _changeset} -> put_flash(socket, :error, "No se pudo borrar la marca.")
    end
  end

  def evento("elegir_herramienta", %{"herramienta" => herramienta}, socket)
      when herramienta in @claves do
    socket
    |> assign(:herramienta, herramienta)
    |> push_event("herramienta", %{herramienta: herramienta})
  end

  def evento("elegir_herramienta", _params, socket), do: socket

  @doc "Reenvia al hook lo que llega por el PubSub de la sesion."
  def mensaje({:anotacion_creada, anotacion}, socket) do
    socket
    |> update(:marcas, &Map.put(&1, anotacion.id, de_quien(anotacion)))
    |> push_event("nueva_anotacion", Anotacion.a_mapa(anotacion))
  end

  def mensaje({:anotacion_actualizada, anotacion}, socket),
    do: push_event(socket, "anotacion_actualizada", Anotacion.a_mapa(anotacion))

  def mensaje({:anotacion_borrada, id}, socket) do
    socket
    |> update(:marcas, &Map.delete(&1, id))
    |> push_event("anotacion_borrada", %{id: id})
  end
end
