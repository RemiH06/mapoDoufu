defmodule MapoWeb.UserLive.Login do
  use MapoWeb, :live_view

  alias Mapo.Accounts

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <section class="doc pegado mx-auto max-w-md" aria-labelledby="t-entrar">
        <header class="doc-cab">
          <h1 id="t-entrar">{if @current_scope, do: "Confirma que eres tú", else: "Entrar"}</h1>
           <span class="doc-tipo">Ficha de acceso</span>
        </header>
        
        <div :if={@current_scope} class="doc-seccion">
          <p>Para cambiar el correo o la contraseña hay que volver a entrar.</p>
        </div>
        
        <div class="doc-seccion">
          <h2>Con un enlace al correo</h2>
          
          <.form
            :let={f}
            for={@form}
            id="login_form_magic"
            action={~p"/users/log-in"}
            phx-submit="submit_magic"
            class="grid gap-3"
          >
            <.input
              readonly={!!@current_scope}
              field={f[:email]}
              type="email"
              label="Correo electrónico"
              autocomplete="username"
              spellcheck="false"
              required
              phx-mounted={JS.focus()}
            /> <.button variant="primary">Mandarme el enlace</.button>
          </.form>
          
          <p :if={local_mail_adapter?()} class="nota">
            En desarrollo los correos no salen: llegan a la <.link href="/dev/mailbox">bandeja de pruebas</.link>.
          </p>
        </div>
        
        <div class="doc-seccion">
          <h2>Con contraseña</h2>
          
          <.form
            :let={f}
            for={@form}
            id="login_form_password"
            action={~p"/users/log-in"}
            phx-submit="submit_password"
            phx-trigger-action={@trigger_submit}
            class="grid gap-3"
          >
            <.input
              readonly={!!@current_scope}
              field={f[:email]}
              type="email"
              label="Correo electrónico"
              autocomplete="username"
              spellcheck="false"
              required
            />
            <.input
              field={@form[:password]}
              type="password"
              label="Contraseña"
              autocomplete="current-password"
              spellcheck="false"
            />
            <div class="doc-botones">
              <.button name={@form[:remember_me].name} value="true">
                Entrar y recordarme
              </.button>
               <.button>Solo esta vez</.button>
            </div>
          </.form>
        </div>
        
        <p :if={!@current_scope} class="doc-seccion secundario">
          <span>¿Todavía no tienes cuenta? <.link navigate={~p"/users/register"}>Crea una</.link>.</span>
        </p>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    email =
      Phoenix.Flash.get(socket.assigns.flash, :email) ||
        get_in(socket.assigns, [:current_scope, Access.key(:user), Access.key(:email)])

    form = to_form(%{"email" => email}, as: "user")

    {:ok, assign(socket, form: form, trigger_submit: false)}
  end

  @impl true
  def handle_event("submit_password", _params, socket) do
    {:noreply, assign(socket, :trigger_submit, true)}
  end

  def handle_event("submit_magic", %{"user" => %{"email" => email}}, socket) do
    if user = Accounts.get_user_by_email(email) do
      Accounts.deliver_login_instructions(
        user,
        &url(~p"/users/log-in/#{&1}")
      )
    end

    info =
      "Si tu correo está registrado, recibirás instrucciones para iniciar sesión en breve."

    {:noreply,
     socket
     |> put_flash(:info, info)
     |> push_navigate(to: ~p"/users/log-in")}
  end

  defp local_mail_adapter? do
    Application.get_env(:mapo, Mapo.Mailer)[:adapter] == Swoosh.Adapters.Local
  end
end
