defmodule MapoWeb.SesionLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Sesiones
  alias Mapo.Teams

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <.header>
        {@sesion.nombre}
        <:subtitle>Sesión de {@team.name}. Los demás miembros del equipo ven tus anotaciones al instante.</:subtitle>
      </.header>

      <div
        id="mapa-colaborativo"
        phx-hook="CollabMap"
        phx-update="ignore"
        data-anotaciones={Jason.encode!(@anotaciones_json)}
        class="w-full h-[70vh] rounded-box border border-base-300 mt-4"
      >
      </div>

      <p class="text-sm text-base-content/70 mt-2">
        Haz clic en el mapa para agregar una anotación.
      </p>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    scope = socket.assigns.current_scope
    sesion = Sesiones.get_sesion!(scope, id)
    team = Teams.get_team!(scope, sesion.team_id)

    if connected?(socket), do: Sesiones.subscribe_sesion(sesion.id)

    anotaciones = Sesiones.list_anotaciones(sesion.id)

    {:ok,
     assign(socket,
       sesion: sesion,
       team: team,
       anotaciones_json: Enum.map(anotaciones, &anotacion_a_mapa/1)
     )}
  end

  @impl true
  def handle_event("crear_anotacion", %{"lat" => lat, "lon" => lon, "texto" => texto}, socket) do
    case Sesiones.create_anotacion(socket.assigns.current_scope, socket.assigns.sesion, lat, lon, texto) do
      {:ok, _anotacion} ->
        {:noreply, socket}

      {:error, _changeset} ->
        {:noreply, put_flash(socket, :error, "No se pudo guardar la anotación.")}
    end
  end

  @impl true
  def handle_info({:anotacion_creada, anotacion}, socket) do
    {:noreply, push_event(socket, "nueva_anotacion", anotacion_a_mapa(anotacion))}
  end

  defp anotacion_a_mapa(anotacion) do
    %Geo.Point{coordinates: {lon, lat}} = anotacion.geom

    %{
      id: anotacion.id,
      lat: lat,
      lon: lon,
      texto: anotacion.texto,
      autor: anotacion.user.email
    }
  end
end
