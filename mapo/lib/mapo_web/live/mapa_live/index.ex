defmodule MapoWeb.MapaLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} full_width?={true}>
      <div class="shrink-0 flex flex-wrap items-end gap-3">
        <h1 class="font-mono text-sm font-bold pb-2 whitespace-nowrap">Mapa técnico</h1>

        <.form for={@form} id="ubicacion_form" phx-change="cambiar_ubicacion" class="contents">
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
              prompt="Todos los municipios del estado"
            />
          </div>
        </.form>
      </div>

      <p :if={@estados == []} class="shrink-0 text-sm text-warning">
        No se pudo cargar la lista de estados: mapo_core no está disponible ahorita mismo, o
        todavía no se han descargado estados.
      </p>

      <div class="flex-1 min-h-0 lg:flex lg:gap-4 lg:items-stretch overflow-y-auto lg:overflow-visible">
        <aside class="lg:w-72 lg:shrink-0 lg:overflow-y-auto space-y-3">
          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Coropleta del censo</h3>
            <.form for={@coropleta_form} id="coropleta_capa_form" phx-submit="mostrar_coropleta">
              <.input
                field={@coropleta_form[:indicador]}
                type="select"
                label="Indicador"
                options={@indicadores}
              />
              <div class="flex gap-2 mt-2">
                <.button phx-disable-with="Mostrando..." class="btn btn-primary btn-sm">Mostrar</.button>
                <.button
                  :if={@coropleta_activa?}
                  type="button"
                  phx-click="quitar_coropleta"
                  class="btn btn-soft btn-sm"
                >
                  Quitar
                </.button>
              </div>
            </.form>
          </div>

          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Voronoi de negocios (DENUE)</h3>
            <.form for={@voronoi_form} id="voronoi_capa_form" phx-submit="mostrar_voronoi">
              <.input
                field={@voronoi_form[:clase_actividad]}
                type="text"
                label="Giro (opcional)"
                placeholder="ej. papelería"
              />
              <p class="text-xs text-base-content/70 mt-1">Necesita un municipio elegido arriba.</p>
              <div class="flex gap-2 mt-2">
                <.button phx-disable-with="Mostrando..." class="btn btn-primary btn-sm">Mostrar</.button>
                <.button
                  :if={@voronoi_activa?}
                  type="button"
                  phx-click="quitar_voronoi"
                  class="btn btn-soft btn-sm"
                >
                  Quitar
                </.button>
              </div>
            </.form>
          </div>

          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Coloreado de municipios</h3>
            <p class="text-xs text-base-content/70">Colorea todos los municipios del estado elegido.</p>
            <div class="flex gap-2 mt-2">
              <.button phx-click="mostrar_coloreado" class="btn btn-primary btn-sm">Mostrar</.button>
              <.button
                :if={@coloreado_activa?}
                type="button"
                phx-click="quitar_coloreado"
                class="btn btn-soft btn-sm"
              >
                Quitar
              </.button>
            </div>
          </div>

          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Isócrona</h3>
            <.form for={@isocrona_form} id="isocrona_capa_form" phx-submit="activar_isocrona">
              <.input field={@isocrona_form[:minutos]} type="number" label="Minutos" min="1" />
              <p :if={@isocrona_activa?} class="text-xs text-base-content/70 mt-1">
                Haz clic en el mapa para elegir el punto de origen.
              </p>
              <div class="flex gap-2 mt-2">
                <.button phx-disable-with="Activando..." class="btn btn-primary btn-sm">Activar</.button>
                <.button
                  :if={@isocrona_activa?}
                  type="button"
                  phx-click="quitar_isocrona"
                  class="btn btn-soft btn-sm"
                >
                  Quitar
                </.button>
              </div>
            </.form>
          </div>
        </aside>

        <div
          id="mapa-tecnico"
          phx-hook="MapaTecnico"
          phx-update="ignore"
          class="h-[60vh] lg:h-auto lg:flex-1 min-h-0 w-full mt-4 lg:mt-0 rounded-box overflow-hidden"
        >
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
       indicadores: Enum.map(MapoCore.indicadores_censo(), fn {c, e} -> {e, c} end),
       form: to_form(%{"cve_ent" => "", "cve_mun" => ""}, as: "mapa"),
       coropleta_form: to_form(%{"indicador" => "pobtot"}, as: "coropleta_capa"),
       voronoi_form: to_form(%{"clase_actividad" => ""}, as: "voronoi_capa"),
       isocrona_form: to_form(%{"minutos" => "10"}, as: "isocrona_capa"),
       coropleta_activa?: false,
       voronoi_activa?: false,
       coloreado_activa?: false,
       isocrona_activa?: false
     )}
  end

  @impl true
  def handle_event("cambiar_ubicacion", %{"mapa" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "mapa"))}
  end

  def handle_event("mostrar_coropleta", %{"coropleta_capa" => %{"indicador" => indicador}}, socket) do
    cve_ent = socket.assigns.form[:cve_ent].value
    cve_mun = vacio_para_nil(socket.assigns.form[:cve_mun].value)

    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coropleta_censo_poblacion(indicador, cve_ent, cve_mun) do
        {:ok, geojson} ->
          etiqueta = etiqueta_indicador(indicador)

          {:noreply,
           socket
           |> assign(coropleta_activa?: true, coropleta_form: to_form(%{"indicador" => indicador}, as: "coropleta_capa"))
           |> push_event("capa_coropleta", %{activa: true, geojson: geojson, etiqueta: etiqueta})}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    end
  end

  def handle_event("quitar_coropleta", _params, socket) do
    {:noreply,
     socket
     |> assign(coropleta_activa?: false)
     |> push_event("capa_coropleta", %{activa: false})}
  end

  def handle_event("mostrar_voronoi", %{"voronoi_capa" => %{"clase_actividad" => clase_actividad}}, socket) do
    cve_ent = socket.assigns.form[:cve_ent].value
    cve_mun = vacio_para_nil(socket.assigns.form[:cve_mun].value)
    clase_actividad = vacio_para_nil(clase_actividad)

    cond do
      cve_ent in [nil, ""] or is_nil(cve_mun) ->
        {:noreply, put_flash(socket, :error, "Selecciona un estado y un municipio primero.")}

      true ->
        case MapoCore.voronoi_denue(cve_ent, cve_mun, clase_actividad) do
          {:ok, %{"celdas" => geojson}} ->
            {:noreply,
             socket
             |> assign(voronoi_activa?: true)
             |> push_event("capa_voronoi", %{activa: true, geojson: geojson})}

          {:error, {:status, 422, body}} ->
            mensaje = if is_map(body), do: body["detail"], else: nil
            {:noreply, put_flash(socket, :error, mensaje || "No hay suficientes negocios con ese filtro.")}

          {:error, {:status, 404, _}} ->
            {:noreply, put_flash(socket, :error, "Ese municipio no está descargado en Gaiarda todavía.")}

          {:error, _} ->
            {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
        end
    end
  end

  def handle_event("quitar_voronoi", _params, socket) do
    {:noreply,
     socket
     |> assign(voronoi_activa?: false)
     |> push_event("capa_voronoi", %{activa: false})}
  end

  def handle_event("mostrar_coloreado", _params, socket) do
    cve_ent = socket.assigns.form[:cve_ent].value

    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coloreado_municipios(cve_ent) do
        {:ok, geojson} ->
          {:noreply,
           socket
           |> assign(coloreado_activa?: true)
           |> push_event("capa_coloreado", %{activa: true, geojson: geojson})}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    end
  end

  def handle_event("quitar_coloreado", _params, socket) do
    {:noreply,
     socket
     |> assign(coloreado_activa?: false)
     |> push_event("capa_coloreado", %{activa: false})}
  end

  def handle_event("activar_isocrona", %{"isocrona_capa" => %{"minutos" => minutos}}, socket) do
    {:noreply,
     socket
     |> assign(isocrona_activa?: true, isocrona_form: to_form(%{"minutos" => minutos}, as: "isocrona_capa"))
     |> push_event("modo_isocrona", %{activo: true})}
  end

  def handle_event("quitar_isocrona", _params, socket) do
    {:noreply,
     socket
     |> assign(isocrona_activa?: false)
     |> push_event("modo_isocrona", %{activo: false})
     |> push_event("capa_isocrona", %{activa: false})}
  end

  def handle_event("click_mapa", %{"lat" => lat, "lon" => lon}, socket) do
    if socket.assigns.isocrona_activa? do
      minutos =
        case socket.assigns.isocrona_form[:minutos].value |> to_string() |> Float.parse() do
          {valor, _} -> valor
          :error -> 10.0
        end

      case MapoCore.isocrona_calcular(lat, lon, minutos) do
        {:ok, %{"poligono" => poligono, "metodo" => metodo}} ->
          {:noreply, push_event(socket, "capa_isocrona", %{activa: true, poligono: poligono, metodo: metodo})}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    else
      {:noreply, socket}
    end
  end

  defp vacio_para_nil(nil), do: nil
  defp vacio_para_nil(""), do: nil
  defp vacio_para_nil(valor), do: valor

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

  defp etiqueta_indicador(codigo) do
    Enum.find_value(MapoCore.indicadores_censo(), codigo, fn {c, e} -> if c == codigo, do: e end)
  end
end
