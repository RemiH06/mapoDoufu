defmodule MapoWeb.VoronoiLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} full_width?={true}>
      <.header>
        Áreas de influencia (Voronoi)
        <:subtitle>
          De los negocios de DENUE en un municipio, a cuál le queda más cerca cada lugar.
        </:subtitle>
      </.header>

      <p :if={@estados == []} class="text-sm text-warning mt-2">
        No se pudo cargar la lista de estados: mapo_core (o Gaiarda detrás de él) no está
        disponible ahorita mismo, o todavía no se han descargado estados.
      </p>

      <.form for={@form} id="voronoi_form" phx-change="cambiar" phx-submit="generar" class="mt-4">
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
          <div class="w-56">
            <.input
              field={@form[:clase_actividad]}
              type="text"
              label="Giro (opcional)"
              placeholder="ej. papelería, farmacia"
            />
          </div>
        </div>
        <.button
          phx-disable-with="Generando..."
          class="btn btn-primary mt-4"
          disabled={@form[:cve_mun].value in [nil, ""]}
        >
          Generar mapa
        </.button>
      </.form>

      <div
        id="voronoi-map"
        phx-hook="VoronoiMap"
        phx-update="ignore"
        class="w-full h-[70vh] mt-6 rounded-box overflow-hidden border border-base-300"
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

    {:ok,
     assign(socket,
       estados: estados,
       municipios: [],
       form: to_form(%{"cve_ent" => "", "cve_mun" => "", "clase_actividad" => ""}, as: "voronoi")
     )}
  end

  @impl true
  def handle_event("cambiar", %{"voronoi" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "voronoi"))}
  end

  def handle_event("generar", %{"voronoi" => params}, socket) do
    cve_ent = params["cve_ent"]
    cve_mun = params["cve_mun"]
    clase_actividad = if params["clase_actividad"] in [nil, ""], do: nil, else: params["clase_actividad"]

    if cve_ent in [nil, ""] or cve_mun in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado y un municipio primero.")}
    else
      case MapoCore.voronoi_denue(cve_ent, cve_mun, clase_actividad) do
        {:ok, %{"celdas" => geojson}} ->
          {:noreply, push_event(socket, "voronoi", %{geojson: geojson})}

        {:error, {:status, 404, _}} ->
          {:noreply,
           put_flash(socket, :error, "Ese municipio no está descargado en Gaiarda todavía.")}

        {:error, {:status, 422, body}} ->
          mensaje = if is_map(body), do: body["detail"], else: nil
          {:noreply, put_flash(socket, :error, mensaje || "No hay suficientes negocios con ese filtro.")}

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

  # El `cvegeo` de un municipio son 5 digitos (cve_ent + cve_mun); los
  # endpoints de Gaiarda piden `cve_mun` por separado (3 digitos), así
  # que hay que usar esa propiedad, no `cvegeo`.
  defp opciones_municipios(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cve_mun"]} end)
    |> Enum.sort()
  end
end
