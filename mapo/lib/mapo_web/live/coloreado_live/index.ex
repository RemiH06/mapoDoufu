defmodule MapoWeb.ColoreadoLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope}>
      <.header>
        Coloreado de mapa
        <:subtitle>
          Los municipios de un estado, coloreados para que dos vecinos nunca se vean iguales.
        </:subtitle>
      </.header>

      <p :if={@estados == []} class="text-sm text-warning mt-2">
        No se pudo cargar la lista de estados: mapo_core (o Gaiarda detrás de él) no está
        disponible ahorita mismo, o todavía no se han descargado estados.
      </p>

      <.form for={@form} id="coloreado_form" phx-submit="generar" class="mt-4">
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
        </div>
        <.button
          phx-disable-with="Generando..."
          class="btn btn-primary mt-4"
          disabled={@form[:cve_ent].value in [nil, ""]}
        >
          Generar mapa
        </.button>
      </.form>

      <div
        id="coloreado-map"
        phx-hook="ColoreadoMap"
        phx-update="ignore"
        class="w-full h-[32rem] mt-6 rounded-box overflow-hidden border border-base-300"
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
