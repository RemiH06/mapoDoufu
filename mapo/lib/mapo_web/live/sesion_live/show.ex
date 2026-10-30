defmodule MapoWeb.SesionLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Sesiones
  alias Mapo.Teams

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" full_width?={true}>
      <:membrete>
        <.link navigate={~p"/teams/#{@team}"} class="mano">{@team.name}</.link>
      </:membrete>
      
      <div
        id="mapa-colaborativo"
        phx-hook="CollabMap"
        phx-update="ignore"
        data-sesion-id={@sesion.id}
        data-anotaciones={Jason.encode!(@anotaciones_json)}
        class="plano-leaflet flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano compartido de la sesión"
      >
      </div>
      
      <section id="hoja-sesion" class="hoja-sesion pegado" aria-labelledby="t-sesion">
        <header class="hoja-cab">
          <h1 id="t-sesion">{@sesion.nombre}</h1>
           <span class="tipo">Sesión del equipo</span>
        </header>
        
        <p class="pista">
          <span class="largo">
            Clic en el plano para poner una marca; tócala para cambiar su nota o borrarla. Todo el equipo la ve al instante.
          </span>
           <span class="corto">Toca el plano para poner una marca.</span>
        </p>
        
        <p class="presentes">
          <%= if @presentes == [] do %>
            <span class="secundario">Nadie más está viendo la sesión.</span>
          <% else %>
            <span class="secundario">Viendo ahora:</span>
            <span :for={correo <- @presentes} class="mano">{correo}</span>
          <% end %>
        </p>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    scope = socket.assigns.current_scope
    sesion = Sesiones.get_sesion!(scope, id)
    team = Teams.get_team!(scope, sesion.team_id)
    topico = Sesiones.topico_sesion(sesion.id)

    if connected?(socket) do
      Sesiones.subscribe_sesion(sesion.id)

      {:ok, _ref} =
        MapoWeb.Presence.track(self(), topico, to_string(scope.user.id), %{
          email: scope.user.email
        })
    end

    anotaciones = Sesiones.list_anotaciones(sesion.id)

    {:ok,
     assign(socket,
       sesion: sesion,
       team: team,
       topico: topico,
       presentes: presentes_en(topico, scope.user.id),
       anotaciones_json: Enum.map(anotaciones, &anotacion_a_mapa/1)
     )}
  end

  @impl true
  def handle_event("crear_anotacion", %{"lat" => lat, "lon" => lon, "texto" => texto}, socket) do
    case Sesiones.create_anotacion(
           socket.assigns.current_scope,
           socket.assigns.sesion,
           lat,
           lon,
           texto
         ) do
      {:ok, _anotacion} ->
        {:noreply, socket}

      {:error, _changeset} ->
        {:noreply, put_flash(socket, :error, "No se pudo guardar la anotación.")}
    end
  end

  def handle_event("editar_anotacion", %{"id" => id, "texto" => texto}, socket) do
    scope = socket.assigns.current_scope
    sesion = socket.assigns.sesion
    anotacion = Sesiones.get_anotacion!(id)

    case Sesiones.update_anotacion(scope, sesion, anotacion, texto) do
      {:ok, _anotacion} ->
        {:noreply, socket}

      {:error, _changeset} ->
        {:noreply, put_flash(socket, :error, "No se pudo actualizar la anotación.")}
    end
  end

  def handle_event("borrar_anotacion", %{"id" => id}, socket) do
    scope = socket.assigns.current_scope
    sesion = socket.assigns.sesion
    anotacion = Sesiones.get_anotacion!(id)

    case Sesiones.delete_anotacion(scope, sesion, anotacion) do
      {:ok, _anotacion} ->
        {:noreply, socket}

      {:error, _changeset} ->
        {:noreply, put_flash(socket, :error, "No se pudo borrar la anotación.")}
    end
  end

  @impl true
  def handle_info({:anotacion_creada, anotacion}, socket) do
    {:noreply, push_event(socket, "nueva_anotacion", anotacion_a_mapa(anotacion))}
  end

  def handle_info({:anotacion_actualizada, anotacion}, socket) do
    {:noreply, push_event(socket, "anotacion_actualizada", anotacion_a_mapa(anotacion))}
  end

  def handle_info({:anotacion_borrada, id}, socket) do
    {:noreply, push_event(socket, "anotacion_borrada", %{id: id})}
  end

  def handle_info(%Phoenix.Socket.Broadcast{event: "presence_diff"}, socket) do
    propio_id = socket.assigns.current_scope.user.id
    {:noreply, assign(socket, presentes: presentes_en(socket.assigns.topico, propio_id))}
  end

  # Excluye al propio usuario: a nadie le hace falta que le digan que el
  # mismo esta viendo la sesion, solo interesa quien mas esta ahi.
  defp presentes_en(topico, propio_user_id) do
    propio_key = to_string(propio_user_id)

    topico
    |> MapoWeb.Presence.list()
    |> Enum.reject(fn {key, _} -> key == propio_key end)
    |> Enum.map(fn {_user_id, %{metas: [meta | _]}} -> meta.email end)
    |> Enum.uniq()
    |> Enum.sort()
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
