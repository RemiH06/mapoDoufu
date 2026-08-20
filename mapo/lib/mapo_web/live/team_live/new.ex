defmodule MapoWeb.TeamLive.New do
  use MapoWeb, :live_view

  alias Mapo.Teams
  alias Mapo.Teams.Team

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <div class="mx-auto max-w-sm">
        <div class="text-center">
          <.header>Crear equipo</.header>
        </div>

        <.form for={@form} id="team_form" phx-submit="save" phx-change="validate">
          <.input field={@form[:name]} type="text" label="Nombre" required phx-mounted={JS.focus()} />
          <.button phx-disable-with="Creando..." class="btn btn-primary w-full">
            Crear equipo
          </.button>
        </.form>
      </div>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    changeset = Teams.change_team(socket.assigns.current_scope, %Team{})
    {:ok, assign(socket, form: to_form(changeset))}
  end

  @impl true
  def handle_event("validate", %{"team" => team_params}, socket) do
    changeset =
      Teams.change_team(socket.assigns.current_scope, %Team{}, team_params)
      |> Map.put(:action, :validate)

    {:noreply, assign(socket, form: to_form(changeset))}
  end

  def handle_event("save", %{"team" => team_params}, socket) do
    case Teams.create_team(socket.assigns.current_scope, team_params) do
      {:ok, team} ->
        {:noreply,
         socket
         |> put_flash(:info, "Equipo creado con éxito.")
         |> push_navigate(to: ~p"/teams/#{team}")}

      {:error, changeset} ->
        {:noreply, assign(socket, form: to_form(changeset, action: :insert))}
    end
  end
end
