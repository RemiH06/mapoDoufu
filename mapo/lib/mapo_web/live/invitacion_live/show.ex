defmodule MapoWeb.InvitacionLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Teams

  @role_labels %{admin: "Administrador", member: "Miembro"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <div class="mx-auto max-w-sm text-center">
        <.header>Invitación a un equipo</.header>

        <div :if={@invitacion == nil} class="mt-6">
          <p>Esta invitación no existe o ya no es válida.</p>
        </div>

        <div :if={@invitacion && @invitacion.estado == :aceptada} class="mt-6">
          <p>Esta invitación ya fue aceptada.</p>
          <.link navigate={~p"/teams"} class="font-semibold text-brand hover:underline">
            Ir a mis equipos
          </.link>
        </div>

        <div :if={@invitacion && @invitacion.estado == :pendiente && @current_scope == nil} class="mt-6">
          <p>
            Te invitaron a unirte al equipo <strong>{@invitacion.team.name}</strong>
            como {@role_labels[@invitacion.role]}.
          </p>
          <p class="mt-2 text-sm text-base-content/70">
            Inicia sesión o crea una cuenta con el correo {@invitacion.email} para aceptar.
          </p>
          <div class="mt-4 flex gap-2 justify-center">
            <.link navigate={~p"/users/log-in"} class="btn btn-primary">Iniciar sesión</.link>
            <.link navigate={~p"/users/register"} class="btn btn-soft">Crear cuenta</.link>
          </div>
        </div>

        <div
          :if={
            @invitacion && @invitacion.estado == :pendiente && @current_scope &&
              not correo_coincide?(@invitacion, @current_scope)
          }
          class="mt-6"
        >
          <p>
            Esta invitación es para {@invitacion.email}, pero iniciaste sesión como
            {@current_scope.user.email}.
          </p>
        </div>

        <div
          :if={
            @invitacion && @invitacion.estado == :pendiente && @current_scope &&
              correo_coincide?(@invitacion, @current_scope)
          }
          class="mt-6"
        >
          <p>
            Te invitaron a unirte al equipo <strong>{@invitacion.team.name}</strong>
            como {@role_labels[@invitacion.role]}.
          </p>
          <.button phx-click="aceptar" class="btn btn-primary mt-4">
            Aceptar invitación
          </.button>
        </div>
      </div>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"token" => token}, _session, socket) do
    {:ok, assign(socket, invitacion: Teams.get_invitacion_por_token(token), role_labels: @role_labels)}
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
