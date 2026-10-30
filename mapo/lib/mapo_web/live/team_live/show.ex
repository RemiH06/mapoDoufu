defmodule MapoWeb.TeamLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Teams
  alias Mapo.Sesiones

  @role_labels %{owner: "Titular", admin: "Admin", member: "Miembro"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" amplio?={true}>
      <div class="equipo">
        <section class="doc pegado" aria-labelledby="t-equipo">
          <header class="doc-cab">
            <h1 id="t-equipo">{@team.name}</h1>
             <span class="doc-tipo">Tu rol: {@role_labels[@current_role]}</span>
          </header>
          
          <div class="doc-seccion">
            <h2>Miembros</h2>
            
            <ul class="lista-doc">
              <li :for={m <- @memberships} class="lista-fila">
                <span>{m.user.email}</span>
                <span class="lista-fin">
                  <span class={["sello-rol", m.role == :owner && "dueno"]}>{@role_labels[m.role]}</span>
                  <.button
                    :if={@can_manage? and not (m.role == :owner and @owner_count <= 1)}
                    phx-click="remove_member"
                    phx-value-id={m.id}
                    data-confirm="¿Quitar a esta persona del equipo?"
                    class="boton chico-doc borrar"
                  >
                    Quitar
                  </.button>
                </span>
              </li>
            </ul>
          </div>
          
          <div :if={@can_manage?} class="doc-seccion">
            <h2>Agregar a alguien</h2>
            
            <.form for={@add_form} id="add_member_form" phx-submit="add_member" class="agregar">
              <.input field={@add_form[:email]} type="email" label="Correo" required />
              <.input
                field={@add_form[:role]}
                type="select"
                label="Rol"
                options={[{"Miembro", "member"}, {"Admin", "admin"}]}
              /> <.button phx-disable-with="Agregando...">Agregar</.button>
            </.form>
            
            <p class="secundario">Si todavía no tiene cuenta, le llega una invitación al correo.</p>
          </div>
          
          <div :if={@can_manage? and @invitaciones_pendientes != []} class="doc-seccion">
            <h2>Invitaciones pendientes</h2>
            
            <ul class="lista-doc">
              <li :for={i <- @invitaciones_pendientes} class="lista-fila">
                <span>{i.email}</span>
                <span class="lista-fin">
                  <span class="sello-rol">{@role_labels[i.role]}</span>
                  <.button
                    phx-click="cancelar_invitacion"
                    phx-value-id={i.id}
                    data-confirm="¿Cancelar esta invitación?"
                    class="boton chico-doc borrar"
                  >
                    Cancelar
                  </.button>
                </span>
              </li>
            </ul>
          </div>
        </section>
        
        <section class="doc pegado" aria-labelledby="t-sesiones">
          <header class="doc-cab">
            <h2 id="t-sesiones">Sesiones</h2>
             <span class="doc-tipo">Mapas compartidos</span>
          </header>
          
          <div class="doc-seccion">
            <p :if={@sesiones == []} class="nota">
              Todavía no hay sesiones. En una sesión, lo que alguien marca en el mapa lo ven los demás al instante.
            </p>
            
            <ul :if={@sesiones != []} class="lista-doc">
              <li :for={s <- @sesiones} class="lista-fila">
                <.link navigate={~p"/sesiones/#{s}"} class="lista-enlace">{s.nombre}</.link>
              </li>
            </ul>
            
            <.form for={@sesion_form} id="sesion_form" phx-submit="crear_sesion" class="agregar">
              <.input field={@sesion_form[:nombre]} type="text" label="Sesión nueva" required />
              <.button variant="primary" phx-disable-with="Creando...">Crear sesión</.button>
            </.form>
          </div>
        </section>
      </div>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    scope = socket.assigns.current_scope
    team = Teams.get_team!(scope, id)
    role = Teams.role_in_team(scope, team.id)
    memberships = Teams.list_team_memberships(team.id)

    {:ok,
     assign(socket,
       team: team,
       current_role: role,
       can_manage?: role in [:owner, :admin],
       memberships: memberships,
       owner_count: Enum.count(memberships, &(&1.role == :owner)),
       add_form: to_form(%{"email" => "", "role" => "member"}, as: "member"),
       role_labels: @role_labels,
       invitaciones_pendientes: Teams.list_invitaciones_pendientes(scope, team),
       sesiones: Sesiones.list_sesiones(scope, team.id),
       sesion_form: to_form(%{"nombre" => ""}, as: "sesion")
     )}
  end

  @impl true
  def handle_event("add_member", %{"member" => %{"email" => email, "role" => role}}, socket) do
    scope = socket.assigns.current_scope
    team = socket.assigns.team

    case Teams.add_member_by_email(scope, team, email, String.to_existing_atom(role)) do
      {:ok, _membership} ->
        memberships = Teams.list_team_memberships(team.id)

        {:noreply,
         socket
         |> put_flash(:info, "Miembro agregado con éxito.")
         |> assign(
           memberships: memberships,
           owner_count: Enum.count(memberships, &(&1.role == :owner)),
           add_form: to_form(%{"email" => "", "role" => "member"}, as: "member")
         )}

      {:error, :not_found} ->
        role_atom = String.to_existing_atom(role)

        case Teams.invitar_por_correo(
               scope,
               team,
               email,
               role_atom,
               &url(~p"/invitaciones/#{&1}")
             ) do
          {:ok, _invitacion} ->
            {:noreply,
             socket
             |> put_flash(:info, "Se envió una invitación a #{email}.")
             |> assign(
               invitaciones_pendientes: Teams.list_invitaciones_pendientes(scope, team),
               add_form: to_form(%{"email" => "", "role" => "member"}, as: "member")
             )}

          {:error, %Ecto.Changeset{}} ->
            {:noreply, put_flash(socket, :error, "No se pudo enviar la invitación.")}
        end

      {:error, %Ecto.Changeset{}} ->
        {:noreply, put_flash(socket, :error, "Esa persona ya es miembro de este equipo.")}
    end
  end

  def handle_event("cancelar_invitacion", %{"id" => id}, socket) do
    scope = socket.assigns.current_scope
    team = socket.assigns.team
    invitacion = Teams.get_invitacion!(id)

    {:ok, _invitacion} = Teams.cancelar_invitacion(scope, invitacion)

    {:noreply,
     socket
     |> put_flash(:info, "Invitación cancelada.")
     |> assign(invitaciones_pendientes: Teams.list_invitaciones_pendientes(scope, team))}
  end

  def handle_event("remove_member", %{"id" => id}, socket) do
    scope = socket.assigns.current_scope
    team = socket.assigns.team
    membership = Teams.get_membership!(id)

    case Teams.remove_member(scope, team, membership) do
      {:ok, _membership} ->
        memberships = Teams.list_team_memberships(team.id)

        {:noreply,
         socket
         |> put_flash(:info, "Miembro quitado del equipo.")
         |> assign(
           memberships: memberships,
           owner_count: Enum.count(memberships, &(&1.role == :owner))
         )}

      {:error, :last_owner} ->
        {:noreply, put_flash(socket, :error, "El equipo necesita al menos una persona titular.")}
    end
  end

  def handle_event("crear_sesion", %{"sesion" => %{"nombre" => nombre}}, socket) do
    scope = socket.assigns.current_scope
    team = socket.assigns.team

    case Sesiones.create_sesion(scope, team.id, %{"nombre" => nombre}) do
      {:ok, sesion} ->
        {:noreply, push_navigate(socket, to: ~p"/sesiones/#{sesion}")}

      {:error, changeset} ->
        {:noreply, assign(socket, sesion_form: to_form(changeset, action: :insert, as: "sesion"))}
    end
  end
end
