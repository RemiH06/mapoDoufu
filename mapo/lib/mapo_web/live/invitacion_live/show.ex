defmodule MapoWeb.InvitacionLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Teams

  @role_labels %{admin: "Admin", member: "Miembro"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <section class="doc pegado mx-auto max-w-md" aria-labelledby="t-invitacion">
        <header class="doc-cab">
          <h1 id="t-invitacion">{if @invitacion, do: @invitacion.team.name, else: "Invitación"}</h1>
           <span class="doc-tipo">Invitación a un equipo</span>
        </header>
        
        <div class="doc-seccion">
          <%= cond do %>
            <% @invitacion == nil -> %>
              <p>Esta invitación no existe o ya no es válida.</p>
              
              <p class="secundario">Pide a quien te invitó que te mande otra.</p>
            <% @invitacion.estado == :aceptada -> %>
              <p>Esta invitación ya se aceptó.</p>
              
              <div class="doc-botones">
                <.button variant="primary" navigate={~p"/teams"}>Ir a mis equipos</.button>
              </div>
            <% @current_scope == nil -> %>
              <p>
                Te invitaron a <strong>{@invitacion.team.name}</strong>
                con el rol de {String.downcase(@role_labels[@invitacion.role])}.
              </p>
              
              <p class="secundario">
                Para aceptarla, entra o crea una cuenta con <span class="mano">{@invitacion.email}</span>.
              </p>
              
              <div class="doc-botones">
                <.button variant="primary" navigate={~p"/users/log-in"}>Entrar</.button>
                <.button navigate={~p"/users/register"}>Crear cuenta</.button>
              </div>
            <% not correo_coincide?(@invitacion, @current_scope) -> %>
              <p>
                Esta invitación es para <span class="mano">{@invitacion.email}</span>
                y entraste como <span class="mano">{@current_scope.user.email}</span>.
              </p>
              
              <p class="secundario">Sal y vuelve a entrar con el correo de la invitación.</p>
            <% true -> %>
              <p>
                Te invitaron a <strong>{@invitacion.team.name}</strong>
                con el rol de {String.downcase(@role_labels[@invitacion.role])}.
              </p>
              
              <div class="doc-botones">
                <.button variant="primary" phx-click="aceptar">Aceptar invitación</.button>
              </div>
          <% end %>
        </div>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"token" => token}, _session, socket) do
    {:ok,
     assign(socket, invitacion: Teams.get_invitacion_por_token(token), role_labels: @role_labels)}
  end

  @impl true
  def handle_event("aceptar", _params, socket) do
    scope = socket.assigns.current_scope
    invitacion = socket.assigns.invitacion

    if scope && correo_coincide?(invitacion, scope) do
      case Teams.aceptar_invitacion(scope, invitacion) do
        {:ok, invitacion_aceptada} ->
          {:noreply,
           socket
           |> put_flash(:info, "Te uniste al equipo #{invitacion.team.name}.")
           |> push_navigate(to: ~p"/teams/#{invitacion_aceptada.team_id}")}

        {:error, _reason} ->
          {:noreply, put_flash(socket, :error, "No se pudo aceptar la invitación.")}
      end
    else
      {:noreply, socket}
    end
  end

  defp correo_coincide?(invitacion, scope) do
    String.downcase(invitacion.email) == String.downcase(scope.user.email)
  end
end
