defmodule MapoWeb.TeamLive.Index do
  use MapoWeb, :live_view

  alias Mapo.Teams

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <div class="flex items-center justify-between mb-6">
        <.header>Mis equipos</.header>
        <.link navigate={~p"/teams/new"} class="btn btn-primary">Crear equipo</.link>
      </div>

      <div :if={@teams == []} class="alert alert-info">
        Todavía no perteneces a ningún equipo.
      </div>

      <ul class="space-y-2">
        <li :for={team <- @teams} class="card bg-base-200 p-4">
          <.link navigate={~p"/teams/#{team}"} class="font-semibold hover:underline">
            {team.name}
          </.link>
        </li>
      </ul>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    {:ok, assign(socket, teams: Teams.list_teams(socket.assigns.current_scope))}
  end
end
