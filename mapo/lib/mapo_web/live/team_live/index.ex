defmodule MapoWeb.TeamLive.Index do
  use MapoWeb, :live_view

  alias Mapo.Teams

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos">
      <section class="doc pegado" aria-labelledby="t-equipos">
        <header class="doc-cab">
          <h1 id="t-equipos">Equipos</h1>
          <span class="doc-tipo">{length(@teams)} {if length(@teams) == 1,
            do: "equipo",
            else: "equipos"}</span>
        </header>

        <div class="doc-seccion">
          <p :if={@teams == []} class="nota">
            Todavía no estás en ningún equipo. Crea uno o pide que te inviten.
          </p>
          <ul :if={@teams != []} class="lista-doc">
            <li :for={team <- @teams} class="lista-fila">
              <.link navigate={~p"/teams/#{team}"} class="lista-enlace">{team.name}</.link>
            </li>
          </ul>
          <div class="doc-botones">
            <.button variant="primary" navigate={~p"/teams/new"}>Crear equipo</.button>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    {:ok, assign(socket, teams: Teams.list_teams(socket.assigns.current_scope))}
  end
end
