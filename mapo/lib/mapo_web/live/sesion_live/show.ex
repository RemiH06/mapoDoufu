defmodule MapoWeb.SesionLive.Show do
  use MapoWeb, :live_view

  require MapoWeb.Marcas

  alias Mapo.Sesiones
  alias Mapo.Sesiones.Anotacion
  alias Mapo.Teams
  alias MapoWeb.Marcas

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

        <Marcas.selector herramienta={@herramienta} />
        <p class="pista">
          <span class="largo">
            {if @herramienta == "circulo",
              do: "Un clic en el centro y otro en la orilla para encerrar una zona.",
              else: "Clic en el plano para poner una marca."} Tócala para cambiar su nota o borrarla. Todo el equipo la ve al instante.
          </span>
          <span class="corto">
            {if @herramienta == "circulo",
              do: "Toca el centro y luego la orilla.",
              else: "Toca el plano para poner una marca."}
          </span>
        </p>
        <.link navigate={~p"/mapa?#{[sesion: @sesion.id]}"} class="mano a-mapa">
          Ver las marcas con las capas de datos
        </.link>

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
       herramienta: "punto",
       presentes: presentes_en(topico, scope.user.id),
       anotaciones_json: Enum.map(anotaciones, &Anotacion.a_mapa/1)
     )}
  end

  @impl true
  def handle_event(evento, params, socket) when Marcas.evento_de_marca(evento) do
    {:noreply, Marcas.evento(evento, params, socket)}
  end

  @impl true
  def handle_info(mensaje, socket) when Marcas.mensaje_de_marca(mensaje) do
    {:noreply, Marcas.mensaje(mensaje, socket)}
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
end
