defmodule MapoWeb.Marcas do
  @moduledoc """
  Las marcas del equipo sobre el plano, compartidas por `/sesiones/:id` y la
  capa "Tus marcas" de `/mapa`: los dos hablan con el mismo hook de dibujo
  (`assets/js/marcas.js`) y escriben en la misma sesion, asi que una marca
  puesta en un lado llega en vivo al otro.

  La vista guarda la sesion en `socket.assigns.sesion` (en `/mapa` puede ser
  `nil` si no se eligio ninguna) y le pasa aqui sus eventos y mensajes.
  """

  use Phoenix.Component

  import Phoenix.LiveView, only: [push_event: 3, put_flash: 3]

  alias Mapo.Sesiones
  alias Mapo.Sesiones.Anotacion

  @herramientas ~w(punto circulo)
  @eventos ~w(crear_anotacion editar_anotacion borrar_anotacion elegir_herramienta)
  @mensajes [:anotacion_creada, :anotacion_actualizada, :anotacion_borrada]

  defguard evento_de_marca(evento) when evento in @eventos

  defguard mensaje_de_marca(mensaje)
           when is_tuple(mensaje) and tuple_size(mensaje) == 2 and elem(mensaje, 0) in @mensajes

  attr :herramienta, :string, required: true

  @doc "Con qué forma pone marca el siguiente clic en el plano."
  def selector(assigns) do
    ~H"""
    <div class="herramientas" role="group" aria-label="Forma de la marca">
      <button
        :for={{clave, nombre} <- [{"punto", "Punto"}, {"circulo", "Círculo"}]}
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

  def evento(_evento, _params, %{assigns: %{sesion: nil}} = socket), do: socket

  def evento("crear_anotacion", %{"lat" => lat, "lon" => lon} = params, socket) do
    %{current_scope: scope, sesion: sesion} = socket.assigns
    texto = Map.get(params, "texto", "")

    case Sesiones.create_anotacion(
           scope,
           sesion,
           lat,
           lon,
           texto,
           Map.take(params, ~w(forma radio_m))
         ) do
      {:ok, _anotacion} -> socket
      {:error, _changeset} -> put_flash(socket, :error, "No se pudo guardar la marca.")
    end
  end

  def evento("editar_anotacion", %{"id" => id, "texto" => texto}, socket) do
    %{current_scope: scope, sesion: sesion} = socket.assigns

    case Sesiones.update_anotacion(scope, sesion, Sesiones.get_anotacion!(id), texto) do
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
      when herramienta in @herramientas do
    socket
    |> assign(:herramienta, herramienta)
    |> push_event("herramienta", %{herramienta: herramienta})
  end

  def evento("elegir_herramienta", _params, socket), do: socket

  @doc "Reenvia al hook lo que llega por el PubSub de la sesion."
  def mensaje({:anotacion_creada, anotacion}, socket),
    do: push_event(socket, "nueva_anotacion", Anotacion.a_mapa(anotacion))

  def mensaje({:anotacion_actualizada, anotacion}, socket),
    do: push_event(socket, "anotacion_actualizada", Anotacion.a_mapa(anotacion))

  def mensaje({:anotacion_borrada, id}, socket),
    do: push_event(socket, "anotacion_borrada", %{id: id})
end
