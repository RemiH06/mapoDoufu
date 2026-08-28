defmodule MapoWeb.PerfilLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <.header>
        Perfil de zona
        <:subtitle>
          Comercio, demografía, consumo y seguridad de un municipio, juntos.
        </:subtitle>
      </.header>

      <p :if={@estados == []} class="text-sm text-warning mt-2">
        No se pudo cargar la lista de estados: mapo_core (o Gaiarda detrás de él) no está
        disponible ahorita mismo, o todavía no se han descargado estados.
      </p>

      <.form for={@form} id="perfil_form" phx-change="cambiar_ubicacion" phx-submit="ver_perfil" class="mt-4">
        <div class="flex gap-2 items-start flex-wrap">
          <div class="w-52">
            <.input
              field={@form[:cve_ent]}
              type="select"
              label="Estado"
              options={@estados}
              prompt="Selecciona un estado"
            />
          </div>
          <div class="w-56">
            <.input
              field={@form[:cve_mun]}
              type="select"
              label="Municipio"
              options={@municipios}
              prompt="Selecciona un municipio"
            />
          </div>
        </div>
        <.button phx-disable-with="Consultando..." class="btn btn-primary mt-4">
          Ver perfil
        </.button>
      </.form>

      <div :if={@perfil} class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-8">
        <div class="card bg-base-200 p-4">
          <h3 class="font-mono text-sm font-bold mb-2">Demografía (censo)</h3>
          <div :if={@perfil["demografia"]} class="text-sm space-y-1">
            <p>Población total: {@perfil["demografia"]["pobtot"]}</p>
            <p>Mujeres / hombres: {@perfil["demografia"]["pobfem"]} / {@perfil["demografia"]["pobmas"]}</p>
            <p>Grado promedio de escolaridad: {@perfil["demografia"]["graproes"]}</p>
            <p>Población económicamente activa: {@perfil["demografia"]["pea"]}</p>
            <p>Ocupada / desocupada: {@perfil["demografia"]["pocupada"]} / {@perfil["demografia"]["pdesocup"]}</p>
            <p>Hogares / viviendas: {@perfil["demografia"]["tothog"]} / {@perfil["demografia"]["vivtot"]}</p>
          </div>
          <p :if={!@perfil["demografia"]} class="text-sm text-base-content/70">
            Sin datos de censo para este municipio.
          </p>
        </div>

        <div class="card bg-base-200 p-4">
          <h3 class="font-mono text-sm font-bold mb-2">Comercio (DENUE)</h3>
          <p class="text-sm text-base-content/70">
            No disponible todavía: esta fuente no está vendorizada a mapo_core.
          </p>
        </div>

        <div class="card bg-base-200 p-4">
          <h3 class="font-mono text-sm font-bold mb-2">Consumo (ENIGH)</h3>
          <p class="text-sm text-base-content/70">
            No disponible todavía: esta fuente no está vendorizada a mapo_core.
          </p>
        </div>

        <div class="card bg-base-200 p-4">
          <h3 class="font-mono text-sm font-bold mb-2">Seguridad (SESNSP)</h3>
          <p class="text-sm text-base-content/70">
            No disponible todavía: esta fuente no está vendorizada a mapo_core.
          </p>
        </div>

        <div class="card bg-base-200 p-4">
          <h3 class="font-mono text-sm font-bold mb-2">Laboral (ENOE)</h3>
          <p class="text-sm text-base-content/70">
            No disponible todavía: esta fuente ni siquiera tenía endpoint de consulta del lado
            de Gaiarda (solo de descarga).
          </p>
        </div>
      </div>
    </Layouts.app>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    estados =
      case MapoCore.estados() do
        {:ok, %{"features" => features}} -> opciones_estados(features)
        {:error, _} -> []
      end

    {:ok,
     assign(socket,
       estados: estados,
       municipios: [],
       form: to_form(%{"cve_ent" => "", "cve_mun" => ""}, as: "perfil"),
       perfil: nil
     )}
  end

  @impl true
  def handle_event("cambiar_ubicacion", %{"perfil" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "perfil"))}
  end

  def handle_event("ver_perfil", %{"perfil" => %{"cve_ent" => cve_ent, "cve_mun" => cve_mun}}, socket) do
    if cve_ent in [nil, ""] or cve_mun in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado y un municipio primero.")}
    else
      case MapoCore.perfil_zona(cve_ent, cve_mun) do
        {:ok, perfil} ->
          {:noreply, assign(socket, perfil: perfil)}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo, intenta de nuevo.")}
      end
    end
  end

  defp municipios_de(cve_ent) when cve_ent in [nil, ""], do: []

  defp municipios_de(cve_ent) do
    case MapoCore.municipios(cve_ent) do
      {:ok, %{"features" => features}} -> opciones_municipios(features)
      {:error, _} -> []
    end
  end

  defp opciones_estados(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cvegeo"]} end)
    |> Enum.sort()
  end

  defp opciones_municipios(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cve_mun"]} end)
    |> Enum.sort()
  end
end
