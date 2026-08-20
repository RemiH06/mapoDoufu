defmodule MapoWeb.TeamLive.Show do
  use MapoWeb, :live_view

  alias Mapo.Teams

  @role_labels %{owner: "Dueño", admin: "Administrador", member: "Miembro"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <.header>
        {@team.name}
        <:subtitle>Tu rol: {@role_labels[@current_role]}</:subtitle>
      </.header>

      <h3 class="font-mono text-sm font-bold mt-8 mb-2">Miembros</h3>
      <ul class="space-y-2">
        <li :for={m <- @memberships} class="card bg-base-200 p-3 flex flex-row items-center justify-between">
          <div>
            <span>{m.user.email}</span>
            <span class="badge ml-2">{@role_labels[m.role]}</span>
          </div>
          <.button
            :if={@can_manage? and not (m.role == :owner and @owner_count <= 1)}
            phx-click="remove_member"
            phx-value-id={m.id}
            data-confirm="¿Quitar a este miembro del equipo?"
            class="btn btn-sm btn-soft btn-error"
          >
            Quitar
          </.button>
        </li>
      </ul>

      <div :if={@can_manage?} class="mt-8">
        <h3 class="font-mono text-sm font-bold mb-2">Agregar miembro</h3>
        <.form for={@add_form} id="add_member_form" phx-submit="add_member">
          <div class="flex gap-2 items-start">
            <div class="flex-1">
              <.input field={@add_form[:email]} type="email" label="Correo" required />
            </div>
            <div class="w-40">
              <.input
                field={@add_form[:role]}
                type="select"
                label="Rol"
                options={[{"Miembro", "member"}, {"Administrador", "admin"}]}
              />
            </div>
          </div>
          <.button phx-disable-with="Agregando..." class="btn btn-primary">
            Agregar
          </.button>
        </.form>
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
       role_labels: @role_labels
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
        {:noreply, put_flash(socket, :error, "No existe ninguna cuenta con ese correo.")}

      {:error, %Ecto.Changeset{}} ->
        {:noreply,
         put_flash(socket, :error, "Esa persona ya es miembro de este equipo.")}
    end
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
        {:noreply,
         put_flash(socket, :error, "No puedes quitar al único dueño del equipo.")}
    end
  end
end
