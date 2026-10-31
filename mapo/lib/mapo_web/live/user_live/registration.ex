defmodule MapoWeb.UserLive.Registration do
  use MapoWeb, :live_view

  alias Mapo.Accounts
  alias Mapo.Accounts.User

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <section class="doc pegado mx-auto max-w-md" aria-labelledby="t-alta">
        <header class="doc-cab">
          <h1 id="t-alta">Crear cuenta</h1>
          <span class="doc-tipo">Solicitud de alta</span>
        </header>

        <div class="doc-seccion">
          <p>
            Te mandamos un enlace para confirmar el correo. La contraseña es opcional y se pone después, en la cuenta.
          </p>

          <.form
            for={@form}
            id="registration_form"
            phx-submit="save"
            phx-change="validate"
            class="grid gap-3"
          >
            <.input
              field={@form[:email]}
              type="email"
              label="Correo electrónico"
              autocomplete="username"
              spellcheck="false"
              required
              phx-mounted={JS.focus()}
            /> <.button variant="primary" phx-disable-with="Creando cuenta...">Crear cuenta</.button>
          </.form>
        </div>

        <p class="doc-seccion secundario">
          <span>¿Ya tienes cuenta? <.link navigate={~p"/users/log-in"}>Entra</.link>.</span>
        </p>

        <p class="doc-seccion secundario">
          <span>
            Qué guarda Mapo y quién lo ve: <.link href={~p"/privacidad"}>aviso de privacidad</.link>.
          </span>
        </p>
      </section>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, %{assigns: %{current_scope: %{user: user}}} = socket)
      when not is_nil(user) do
    {:ok, redirect(socket, to: MapoWeb.UserAuth.signed_in_path(socket))}
  end

  def mount(_params, _session, socket) do
    changeset = Accounts.change_user_email(%User{}, %{}, validate_unique: false)

    {:ok, assign_form(socket, changeset), temporary_assigns: [form: nil]}
  end

  @impl true
  def handle_event("save", %{"user" => user_params}, socket) do
    case Accounts.register_user(user_params) do
      {:ok, user} ->
        {:ok, _} =
          Accounts.deliver_login_instructions(
            user,
            &url(~p"/users/log-in/#{&1}")
          )

        {:noreply,
         socket
         |> put_flash(
           :info,
           "Se envió un correo a #{user.email}, revísalo para confirmar tu cuenta."
         )
         |> push_navigate(to: ~p"/users/log-in")}

      {:error, %Ecto.Changeset{} = changeset} ->
        {:noreply, assign_form(socket, changeset)}
    end
  end

  def handle_event("validate", %{"user" => user_params}, socket) do
    changeset = Accounts.change_user_email(%User{}, user_params, validate_unique: false)
    {:noreply, assign_form(socket, Map.put(changeset, :action, :validate))}
  end

  defp assign_form(socket, %Ecto.Changeset{} = changeset) do
    form = to_form(changeset, as: "user")
    assign(socket, form: form)
  end
end
