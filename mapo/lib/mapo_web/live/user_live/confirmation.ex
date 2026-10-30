defmodule MapoWeb.UserLive.Confirmation do
  use MapoWeb, :live_view

  alias Mapo.Accounts

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <section class="doc pegado mx-auto max-w-md" aria-labelledby="t-confirmar">
        <header class="doc-cab">
          <h1 id="t-confirmar">{if @user.confirmed_at, do: "Entrar", else: "Confirmar cuenta"}</h1>
          <span class="doc-tipo">Ficha de acceso</span>
        </header>

        <div class="doc-seccion">
          <p>Entras como <span class="mano">{@user.email}</span></p>

          <.form
            :if={!@user.confirmed_at}
            for={@form}
            id="confirmation_form"
            phx-mounted={JS.focus_first()}
            phx-submit="submit"
            action={~p"/users/log-in?_action=confirmed"}
            phx-trigger-action={@trigger_submit}
            class="doc-botones"
          >
            <input type="hidden" name={@form[:token].name} value={@form[:token].value} />
            <.button
              variant="primary"
              name={@form[:remember_me].name}
              value="true"
              phx-disable-with="Confirmando..."
            >
              Confirmar y recordarme
            </.button>
            <.button phx-disable-with="Confirmando...">Solo esta vez</.button>
          </.form>

          <.form
            :if={@user.confirmed_at}
            for={@form}
            id="login_form"
            phx-submit="submit"
            phx-mounted={JS.focus_first()}
            action={~p"/users/log-in"}
            phx-trigger-action={@trigger_submit}
            class="doc-botones"
          >
            <input type="hidden" name={@form[:token].name} value={@form[:token].value} />
            <%= if @current_scope do %>
              <.button variant="primary" phx-disable-with="Entrando...">Entrar</.button>
            <% else %>
              <.button
                variant="primary"
                name={@form[:remember_me].name}
                value="true"
                phx-disable-with="Entrando..."
              >
                Entrar y recordarme
              </.button>
              <.button phx-disable-with="Entrando...">Solo esta vez</.button>
            <% end %>
          </.form>

          <p :if={!@user.confirmed_at} class="nota">
            Si prefieres contraseña, la puedes poner después en la cuenta.
          </p>
        </div>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(%{"token" => token}, _session, socket) do
    if user = Accounts.get_user_by_magic_link_token(token) do
      form = to_form(%{"token" => token}, as: "user")

      {:ok, assign(socket, user: user, form: form, trigger_submit: false),
       temporary_assigns: [form: nil]}
    else
      {:ok,
       socket
       |> put_flash(:error, "El enlace mágico no es válido o ya expiró.")
       |> push_navigate(to: ~p"/users/log-in")}
    end
  end

  @impl true
  def handle_event("submit", %{"user" => params}, socket) do
    {:noreply, assign(socket, form: to_form(params, as: "user"), trigger_submit: true)}
  end
end
