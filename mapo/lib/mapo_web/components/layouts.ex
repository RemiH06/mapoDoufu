defmodule MapoWeb.Layouts do
  @moduledoc """
  This module holds layouts and related functionality
  used by your application.
  """
  use MapoWeb, :html

  # Embed all files in layouts/* within this module.
  # The default root.html.heex file contains the HTML
  # skeleton of your application, namely HTML headers
  # and other static content.
  embed_templates "layouts/*"

  @doc """
  Renders your app layout.

  This function is typically invoked from every template,
  and it often contains your application menu, sidebar,
  or similar.

  ## Examples

      <Layouts.app flash={@flash}>
        <h1>Content</h1>
      </Layouts.app>

  """
  attr :flash, :map, required: true, doc: "the map of flash messages"

  attr :current_scope, :map,
    default: nil,
    doc: "the current [scope](https://phoenix.hexdocs.pm/scopes.html)"

  attr :full_width?, :boolean,
    default: false,
    doc: """
    Para las vistas de mapo con plano a pantalla completa (ej. /mapa): el
    contenido ocupa toda la ventana y el membrete flota encima, pegado al
    plano. El propio contenido trae su parte "de relleno" (el mapa) con
    `flex-1 min-h-0`.
    """

  attr :amplio?, :boolean,
    default: false,
    doc: "Para las vistas con varios documentos sobre la mesa (ej. /perfil): ancho de 80rem."

  attr :seccion, :string,
    default: nil,
    doc:
      "la sección del membrete que va marcada: \"mapa\", \"perfil\", \"logistica\" o \"equipos\""

  slot :inner_block, required: true

  slot :membrete,
    doc: """
    Segunda fila del membrete, propia de cada vista (ej. la ubicación en
    /mapa). Si no viene, va el correo de la cuenta, anotado a mano.
    """

  def app(assigns) do
    ~H"""
    <header class={["cabecera", @full_width? && "cabecera-flotante"]}>
      <div class="membrete pegado">
        <.link navigate={~p"/"} class="marca">
          <img src={~p"/images/mapo-logo.svg"} alt="" /> <span>MAPO</span>
        </.link>
        
        <div :if={@current_scope || @membrete != []} class="membrete-datos">
          <nav :if={@current_scope} class="secciones" aria-label="Secciones">
            <.link
              :for={{clave, texto, ruta} <- secciones()}
              navigate={ruta}
              aria-current={@seccion == clave && "page"}
            >
              {texto}
            </.link>
          </nav>
          
          <div class="membrete-fila">
            <%= if @membrete != [] do %>
              {render_slot(@membrete)}
            <% else %>
              <span :if={@current_scope} class="mano">{@current_scope.user.email}</span>
            <% end %>
          </div>
        </div>
      </div>
      
      <div class="esquina">
        <%!-- El texto lo pone el script de root.html.heex; ignore evita que un
             parche de LiveView lo regrese a "Modo". --%>
        <button
          id="modo"
          type="button"
          class="modo"
          data-modo
          phx-update="ignore"
          phx-click={JS.dispatch("mapo:modo")}
        >
          Modo
        </button>
        
        <%= if @current_scope do %>
          <.link navigate={~p"/users/settings"} class="esquina-enlace">Cuenta</.link>
          <.link href={~p"/users/log-out"} method="delete" class="esquina-enlace">Salir</.link>
        <% else %>
          <.link navigate={~p"/users/log-in"} class="esquina-enlace">Entrar</.link>
        <% end %>
      </div>
    </header>

    <main class={[
      if(@full_width?, do: "fixed inset-0 flex flex-col", else: "px-4 sm:px-6 lg:px-8 pt-4 pb-16")
    ]}>
      <div class={[
        cond do
          @full_width? -> "flex-1 flex flex-col min-h-0"
          @amplio? -> "mx-auto max-w-7xl"
          true -> "mx-auto max-w-2xl"
        end,
        "space-y-4"
      ]}>
        {render_slot(@inner_block)}
      </div>
    </main>
     <.flash_group flash={@flash} />
    """
  end

  defp secciones do
    [
      {"mapa", "Mapa", ~p"/mapa"},
      {"perfil", "Perfil", ~p"/perfil"},
      {"logistica", "Logística", ~p"/logistica"},
      {"equipos", "Equipos", ~p"/teams"}
    ]
  end

  @doc """
  Shows the flash group with standard titles and content.

  ## Examples

      <.flash_group flash={@flash} />
  """
  attr :flash, :map, required: true, doc: "the map of flash messages"
  attr :id, :string, default: "flash-group", doc: "the optional id of flash container"

  def flash_group(assigns) do
    ~H"""
    <div id={@id} aria-live="polite">
      <.flash kind={:info} flash={@flash} /> <.flash kind={:error} flash={@flash} />
      <.flash
        id="client-error"
        kind={:error}
        title={gettext("We can't find the internet")}
        phx-disconnected={
          show(".phx-client-error #client-error")
          |> JS.remove_attribute("hidden", to: ".phx-client-error #client-error")
        }
        phx-connected={hide("#client-error") |> JS.set_attribute({"hidden", ""})}
        hidden
      >
        {gettext("Attempting to reconnect")}
        <.icon name="hero-arrow-path" class="ml-1 size-3 motion-safe:animate-spin" />
      </.flash>
      
      <.flash
        id="server-error"
        kind={:error}
        title={gettext("Something went wrong!")}
        phx-disconnected={
          show(".phx-server-error #server-error")
          |> JS.remove_attribute("hidden", to: ".phx-server-error #server-error")
        }
        phx-connected={hide("#server-error") |> JS.set_attribute({"hidden", ""})}
        hidden
      >
        {gettext("Attempting to reconnect")}
        <.icon name="hero-arrow-path" class="ml-1 size-3 motion-safe:animate-spin" />
      </.flash>
    </div>
    """
  end
end
