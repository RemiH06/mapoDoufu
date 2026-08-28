defmodule MapoWeb.CoropletaLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} full_width?={true}>
      <div class="shrink-0 flex flex-wrap items-end gap-3">
        <h1 class="font-mono text-sm font-bold pb-2 whitespace-nowrap">Coropletas del censo</h1>

        <.form for={@form} id="coropleta_form" phx-change="cambiar" phx-submit="generar" class="contents">
          <div class="w-44">
            <.input
              field={@form[:cve_ent]}
              type="select"
              label="Estado"
              options={@estados}
              prompt="Selecciona un estado"
            />
          </div>
          <div class="w-48">
            <.input
              field={@form[:cve_mun]}
              type="select"
              label="Municipio"
              options={@municipios}
              prompt="Todos"
            />
          </div>
          <div class="w-56">
            <.input field={@form[:indicador]} type="select" label="Indicador" options={@indicadores} />
          </div>
          <.button
            phx-disable-with="Generando..."
            class="btn btn-primary btn-sm"
            disabled={@form[:cve_ent].value in [nil, ""]}
          >
            Generar mapa
          </.button>
        </.form>
      </div>

      <p :if={@estados == []} class="shrink-0 text-sm text-warning">
        No se pudo cargar la lista de estados: mapo_core no está disponible ahorita mismo, o
        todavía no se han descargado estados.
      </p>

      <div
        id="coropleta-map"
        phx-hook="CoropletaMap"
        phx-update="ignore"
        class="flex-1 min-h-0 w-full rounded-box overflow-hidden"
      >
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

    indicadores = Enum.map(MapoCore.indicadores_censo(), fn {codigo, etiqueta} -> {etiqueta, codigo} end)

    {:ok,
     assign(socket,
       estados: estados,
       municipios: [],
       indicadores: indicadores,
       form: to_form(%{"cve_ent" => "", "cve_mun" => "", "indicador" => "pobtot"}, as: "coropleta")
     )}
  end

  @impl true
  def handle_event("cambiar", %{"coropleta" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "coropleta"))}
  end

  def handle_event("generar", %{"coropleta" => params}, socket) do
    cve_ent = params["cve_ent"]
    cve_mun = if params["cve_mun"] in [nil, ""], do: nil, else: params["cve_mun"]
    indicador = params["indicador"]

    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coropleta_censo_poblacion(indicador, cve_ent, cve_mun) do
        {:ok, %{"features" => []}} ->
          {:noreply,
           put_flash(
             socket,
             :error,
             "Gaiarda no tiene AGEBs o censo descargados para ese estado/municipio todavía."
           )}

        {:ok, geojson} ->
          etiqueta = etiqueta_indicador(indicador)

          {:noreply, push_event(socket, "coropleta", %{geojson: geojson, etiqueta: etiqueta})}

        {:error, _} ->
          {:noreply,
           put_flash(socket, :error, "mapo_core no está disponible ahorita mismo, intenta de nuevo.")}
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

  # El `cvegeo` de un estado (2 digitos) es igual a su `cve_ent`, así
  # que sirve tal cual como valor del selector.
  defp opciones_estados(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cvegeo"]} end)
    |> Enum.sort()
  end

  # El `cvegeo` de un municipio son 5 digitos (cve_ent + cve_mun); el
  # endpoint de coropletas pide `cve_mun` por separado (3 digitos), así
  # que hay que usar esa propiedad, no `cvegeo`.
  defp opciones_municipios(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cve_mun"]} end)
    |> Enum.sort()
  end

  defp etiqueta_indicador(codigo) do
    Enum.find_value(MapoCore.indicadores_censo(), codigo, fn {c, e} -> if c == codigo, do: e end)
  end
end
