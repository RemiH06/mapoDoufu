defmodule MapoWeb.ColoreadoLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} full_width?={true}>
      <div class="shrink-0 flex flex-wrap items-end gap-3">
        <h1 class="font-mono text-sm font-bold pb-2 whitespace-nowrap">Coloreado de mapa</h1>

        <.form for={@form} id="coloreado_form" phx-submit="generar" class="contents">
          <div class="w-44">
            <.input
              field={@form[:cve_ent]}
              type="select"
              label="Estado"
              options={@estados}
              prompt="Selecciona un estado"
            />
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
        id="coloreado-map"
        phx-hook="ColoreadoMap"
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
        {:ok, %{"features" => features}} ->
          features
          |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cvegeo"]} end)
          |> Enum.sort()

        {:error, _} ->
          []
      end

    {:ok, assign(socket, estados: estados, form: to_form(%{"cve_ent" => ""}, as: "coloreado"))}
  end

  @impl true
  def handle_event("generar", %{"coloreado" => %{"cve_ent" => cve_ent}}, socket) do
    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coloreado_municipios(cve_ent) do
        {:ok, %{"features" => []}} ->
          {:noreply,
           put_flash(socket, :error, "Gaiarda no tiene municipios descargados para ese estado todavía.")}

        {:ok, geojson} ->
          {:noreply, push_event(socket, "coloreado", %{geojson: geojson})}

        {:error, _} ->
          {:noreply,
           put_flash(socket, :error, "mapo_core no está disponible ahorita mismo, intenta de nuevo.")}
      end
    end
  end
end
