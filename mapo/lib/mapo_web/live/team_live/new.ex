defmodule MapoWeb.TeamLive.New do
  use MapoWeb, :live_view

  alias Mapo.Teams
  alias Mapo.Teams.Team

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos">
      <section class="doc pegado mx-auto max-w-md" aria-labelledby="t-nuevo">
        <header class="doc-cab">
          <h1 id="t-nuevo">Equipo nuevo</h1>
           <span class="doc-tipo">Acta de formación</span>
        </header>
        
        <div class="doc-seccion">
          <p class="secundario">Quedas como titular. Después puedes agregar a más personas.</p>
          
          <.form for={@form} id="team_form" phx-submit="save" phx-change="validate" class="grid gap-3">
            <.input
              field={@form[:name]}
              type="text"
              label="Nombre del equipo"
              required
              phx-mounted={JS.focus()}
            />
            <div class="doc-botones">
              <.button variant="primary" phx-disable-with="Creando...">Crear equipo</.button>
              <.button navigate={~p"/teams"}>Cancelar</.button>
            </div>
          </.form>
        </div>
      </section>
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
