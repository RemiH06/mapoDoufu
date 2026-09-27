defmodule MapoWeb.LogisticaLive.Index do
  use MapoWeb, :live_view

  alias Mapo.MapoCore

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} full_width?={true}>
      <div class="shrink-0 flex flex-wrap items-end gap-3">
        <h1 class="font-mono text-sm font-bold pb-2 whitespace-nowrap">Logística (VRP)</h1>
        <p class="text-xs text-base-content/70 pb-2">
          Haz clic en el mapa para agregar paradas. La primera parada es el depósito (inicio y fin
          de cada ruta).
        </p>
      </div>

      <div class="flex-1 min-h-0 lg:flex lg:gap-4 lg:items-stretch overflow-y-auto lg:overflow-visible">
        <aside class="lg:w-80 lg:shrink-0 lg:overflow-y-auto space-y-3">
          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">
              Paradas ({length(@paradas)})
            </h3>
            <p :if={@paradas == []} class="text-xs text-base-content/70">
              Sin paradas todavía. Haz clic en el mapa para agregar la primera (será el depósito).
            </p>
            <ul :if={@paradas != []} class="space-y-2">
              <li
                :for={{parada, indice} <- Enum.with_index(@paradas)}
                class="text-xs border border-base-300 rounded-box p-2"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="font-mono font-bold">
                    {if indice == 0, do: "Depósito", else: "Parada #{indice}"}
                  </span>
                  <button
                    type="button"
                    phx-click="quitar_parada"
                    phx-value-indice={indice}
                    class="btn btn-ghost btn-xs"
                  >
                    Quitar
                  </button>
                </div>
                <p class="text-base-content/60">
                  {Float.round(parada.lat, 4)}, {Float.round(parada.lon, 4)}
                </p>
                <label class="flex items-center gap-2 mt-1">
                  Demanda
                  <input
                    type="number"
                    min="0"
                    value={parada.demanda}
                    phx-change="actualizar_demanda"
                    phx-value-indice={indice}
                    class="input input-xs w-20"
                  />
                </label>
              </li>
            </ul>
          </div>

          <div class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Vehículos</h3>
            <.form for={@vehiculos_form} id="vehiculos_form" phx-change="cambiar_vehiculos">
              <.input
                field={@vehiculos_form[:num_vehiculos]}
                type="number"
                label="Número de vehículos"
                min="1"
              />
              <.input
                field={@vehiculos_form[:capacidad]}
                type="number"
                label="Capacidad por vehículo"
                min="1"
              />
            </.form>
          </div>

          <div class="flex gap-2">
            <.button
              phx-click="calcular"
              phx-disable-with="Calculando..."
              class="btn btn-primary btn-sm flex-1"
              disabled={length(@paradas) < 2}
            >
              Calcular rutas
            </.button>
            <.button type="button" phx-click="limpiar" class="btn btn-soft btn-sm">
              Limpiar
            </.button>
          </div>

          <div :if={@resultado} class="card bg-base-200 p-3">
            <h3 class="font-mono text-sm font-bold mb-2">Resultado</h3>
            <span class={[
              "badge badge-sm",
              if(@resultado["metodo"] == "carretera_real", do: "badge-success", else: "badge-warning")
            ]}>
              {if @resultado["metodo"] == "carretera_real",
                do: "Carretera real",
                else: "Línea recta aproximada"}
            </span>
            <p class="text-xs mt-2">
              Distancia total: {Float.round(@resultado["distancia_total_km"] / 1, 1)} km
            </p>
            <ul class="text-xs mt-2 space-y-1">
              <li :for={ruta <- @resultado["rutas"]}>
                Vehículo {ruta["vehiculo_id"]}: {Float.round(ruta["distancia_km"] / 1, 1)} km, {length(
                  ruta["orden_paradas"]
                ) - 1} paradas
              </li>
            </ul>
          </div>
        </aside>

        <div
          id="logistica-map"
          phx-hook="LogisticaMap"
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
    {:ok,
     socket
     |> assign(
       paradas: [],
       resultado: nil,
       vehiculos_form: to_form(%{"num_vehiculos" => "1", "capacidad" => "100"}, as: "vehiculos")
     )
     |> push_event("paradas", %{paradas: []})}
  end

  @impl true
  def handle_event("click_mapa", %{"lat" => lat, "lon" => lon}, socket) do
    nueva_parada = %{lat: lat, lon: lon, demanda: 0}
    paradas = socket.assigns.paradas ++ [nueva_parada]

    {:noreply,
     socket
     |> assign(paradas: paradas, resultado: nil)
     |> push_event("paradas", %{paradas: paradas})
     |> push_event("limpiar_rutas", %{})}
  end

  def handle_event("quitar_parada", %{"indice" => indice}, socket) do
    indice = String.to_integer(indice)
    paradas = List.delete_at(socket.assigns.paradas, indice)

    {:noreply,
     socket
     |> assign(paradas: paradas, resultado: nil)
     |> push_event("paradas", %{paradas: paradas})
     |> push_event("limpiar_rutas", %{})}
  end

  def handle_event("actualizar_demanda", %{"indice" => indice, "value" => valor}, socket) do
    indice = String.to_integer(indice)

    demanda =
      case Integer.parse(valor) do
        {n, _} -> max(n, 0)
        :error -> 0
      end

    paradas = List.update_at(socket.assigns.paradas, indice, &Map.put(&1, :demanda, demanda))

    {:noreply, assign(socket, paradas: paradas)}
  end

  def handle_event("cambiar_vehiculos", %{"vehiculos" => params}, socket) do
    {:noreply, assign(socket, vehiculos_form: to_form(params, as: "vehiculos"))}
  end

  def handle_event("limpiar", _params, socket) do
    {:noreply,
     socket
     |> assign(paradas: [], resultado: nil)
     |> push_event("paradas", %{paradas: []})
     |> push_event("limpiar_rutas", %{})}
  end

  def handle_event("calcular", _params, socket) do
    paradas = socket.assigns.paradas

    if length(paradas) < 2 do
      {:noreply,
       put_flash(socket, :error, "Agrega al menos 2 paradas (la primera es el depósito).")}
    else
      num_vehiculos = entero_positivo(socket.assigns.vehiculos_form[:num_vehiculos].value, 1)
      capacidad = entero_positivo(socket.assigns.vehiculos_form[:capacidad].value, 1)
      capacidades = List.duplicate(capacidad, num_vehiculos)

      paradas_payload = Enum.map(paradas, &Map.take(&1, [:lat, :lon, :demanda]))

      case MapoCore.vrp_calcular(paradas_payload, capacidades) do
        {:ok, resultado} ->
          {:noreply,
           socket
           |> assign(resultado: resultado)
           |> push_event("rutas_vrp", %{rutas: resultado["rutas"], paradas: paradas})}

        {:error, {:status, 422, body}} ->
          mensaje = if is_map(body), do: body["detail"], else: nil

          {:noreply,
           put_flash(
             socket,
             :error,
             mensaje || "No se encontró una solución factible con esas restricciones."
           )}

        {:error, _} ->
          {:noreply,
           put_flash(
             socket,
             :error,
             "mapo_core no está disponible ahorita mismo, intenta de nuevo."
           )}
      end
    end
  end

  defp entero_positivo(valor, default) do
    case valor |> to_string() |> Integer.parse() do
      {n, _} when n > 0 -> n
      _ -> default
    end
  end
end
