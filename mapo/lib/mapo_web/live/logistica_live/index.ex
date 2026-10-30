defmodule MapoWeb.LogisticaLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.MapoCore

  # El plano ocupa la mesa y encima queda una sola hoja de ruta
  # (design/mesa_planeacion/logistica.html). Las paradas son marcas del
  # equipo: se ponen con un clic, se arrastran y se editan sobre el plano o
  # en la hoja. El estado vive aquí; el hook solo dibuja y avisa.
  #
  # Cada parada lleva un número que no cambia al quitar otras (es su nombre
  # en el plano). La primera de la lista es el depósito. Si algo cambia
  # después de calcular, las rutas se quedan pero dejan de estar vigentes:
  # nunca se muestra una ruta vieja como si correspondiera.

  # Una tinta por vehículo: los anillos del logo, empezando por movilidad.
  @tintas ~w(--f-movilidad --f-urbanismo --f-demografia --f-comercio --f-seguridad)
  @letras ~w(A B C D E F G H I J)
  @max_paradas 50
  @max_vehiculos length(@letras)

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="logistica" full_width?={true}>
      <:membrete><span class="mano">Rutas de reparto</span></:membrete>

      <div
        id="logistica-map"
        phx-hook="LogisticaMap"
        phx-update="ignore"
        class="plano-leaflet flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano para poner paradas"
      >
      </div>

      <section
        id="hoja"
        class={["hoja pegado", @plegada && "plegada"]}
        data-piel="movilidad"
        aria-labelledby="t-hoja"
      >
        <div class="hoja-cab">
          <h1 id="t-hoja">Hoja de ruta</h1>
          <button
            type="button"
            class="chico plegar"
            phx-click="plegar"
            aria-expanded={to_string(!@plegada)}
          >
            {if @plegada, do: "Ver paradas", else: "Plegar"}
          </button>
          <span class="tipo">{max(length(@paradas) - 1, 0)} paradas</span>
        </div>

        <p class="pista">
          <span class="largo">
            Clic en el plano para poner una parada; arrástrala para moverla o tócala para editarla.
          </span>
          <span class="corto">Toca el plano para poner una parada.</span>
        </p>

        <div class="flota">
          <p class="frase">
            <.paso valor={@flota.n} evento="flota" campo="n" etiqueta="vehículos" minimo={1} />
            {if @flota.n == 1, do: "vehículo", else: "vehículos"} de
            <.paso
              valor={@flota.cap}
              evento="flota"
              campo="cap"
              etiqueta="capacidad por vehículo"
              minimo={5}
            />
          </p>
          <p class={["balance", demanda_total(@paradas) > @flota.n * @flota.cap && "no-cabe"]}>
            Demanda <span class="num">{demanda_total(@paradas)}</span>
            de <span class="num">{@flota.n * @flota.cap}</span>
            de capacidad{if demanda_total(@paradas) > @flota.n * @flota.cap,
              do: ": no cabe, agrega vehículos o capacidad"}
          </p>
        </div>

        <ol id="paradas" class="lista" aria-label="Paradas">
          <li :if={@paradas == []} class="vacia">
            Sin paradas. La primera que pongas será el depósito.
          </li>
          <.fila :if={@paradas != []} parada={hd(@paradas)} deposito?={true} />
          <%= if @calculo do %>
            <li :for={{ruta, k} <- Enum.with_index(@calculo.rutas)} class="grupo" style={tinta(k)}>
              <% ps = paradas_de(ruta, @paradas) %>
              <div class="grupo-cab">
                <span class="tinta"></span>
                <b>Vehículo {letra(k)}</b>
                <span class="num">{cifra(ruta.km, 1)} km</span>
                <span class="num">
                  carga {suma_demanda(ps)} de {@flota.cap} · {length(ps)} paradas
                </span>
              </div>
              <ol>
                <.fila :for={p <- ps} parada={p} ruta={k} />
              </ol>
            </li>
            <li :if={sin_ruta(@paradas, @calculo) != []} class="grupo sin-ruta">
              <div class="grupo-cab">
                <span class="tinta"></span><b>Sin ruta todavía</b><span></span>
                <span>Se reparten al recalcular.</span>
              </div>
              <ol>
                <.fila :for={p <- sin_ruta(@paradas, @calculo)} parada={p} />
              </ol>
            </li>
          <% else %>
            <.fila :for={p <- Enum.drop(@paradas, 1)} parada={p} />
          <% end %>
        </ol>

        <div class="pie">
          <p :if={@error} class="aviso">{@error}</p>
          <div :if={@calculo && !@error} class="resumen">
            <span class={["sello", @calculo.metodo != "carretera_real" && "aprox"]}>
              {if @calculo.metodo == "carretera_real",
                do: "Carretera real · OSRM",
                else: "Línea recta aproximada"}
            </span>
            <span><span class="total">{cifra(@calculo.total, 1)}</span> km</span>
          </div>
          <p :if={@calculo && !@vigente && !@error} class="aviso">
            Cambiaste paradas: las rutas ya no corresponden. Recalcula.
          </p>
          <div class="botones">
            <button
              type="button"
              class="boton primario"
              phx-click="calcular"
              disabled={length(@paradas) < 2 or @calculando or (@calculo && @vigente)}
            >
              {cond do
                @calculando -> "Calculando..."
                @calculo -> "Recalcular rutas"
                true -> "Calcular rutas"
              end}
            </button>
            <button type="button" class="boton" phx-click="limpiar" disabled={@paradas == []}>
              Limpiar
            </button>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  attr :parada, :map, required: true
  attr :deposito?, :boolean, default: false
  attr :ruta, :integer, default: nil

  defp fila(assigns) do
    ~H"""
    <li class="fila" data-fila={@parada.id}>
      <span
        class={["pin", @deposito? && "deposito", !@deposito? && is_nil(@ruta) && "pendiente"]}
        style={!@deposito? && @ruta && tinta(@ruta)}
      >
        {if @deposito?, do: "D", else: @parada.id}
      </span>
      <span class="nombre">
        {nombre(@parada, @deposito?)}
        <small>{cifra(@parada.lat, 4)}, {cifra(@parada.lon, 4)}</small>
      </span>
      <span :if={@deposito?}></span>
      <.paso
        :if={!@deposito?}
        valor={@parada.demanda}
        evento="demanda"
        campo={@parada.id}
        etiqueta={"demanda de #{nombre(@parada, false)}"}
        minimo={0}
      />
      <button
        type="button"
        class="quitar"
        phx-click="quitar"
        phx-value-id={@parada.id}
        aria-label={"Quitar #{nombre(@parada, @deposito?)}"}
      >
        ×
      </button>
    </li>
    """
  end

  attr :valor, :integer, required: true
  attr :evento, :string, required: true
  attr :campo, :any, required: true
  attr :etiqueta, :string, required: true
  attr :minimo, :integer, required: true

  # Contador de − y +: demanda de una parada, vehículos o capacidad.
  defp paso(assigns) do
    ~H"""
    <span class="paso">
      <button
        type="button"
        phx-click={@evento}
        phx-value-campo={@campo}
        phx-value-d="-1"
        aria-label={"Menos: #{@etiqueta}"}
        disabled={@valor <= @minimo}
      >
        −
      </button>
      <output class="num" aria-label={@etiqueta}>{@valor}</output>
      <button
        type="button"
        phx-click={@evento}
        phx-value-campo={@campo}
        phx-value-d="1"
        aria-label={"Más: #{@etiqueta}"}
      >
        +
      </button>
    </span>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     assign(socket,
       page_title: "Logística",
       paradas: [],
       siguiente: 1,
       flota: %{n: 1, cap: 100},
       calculo: nil,
       vigente: true,
       error: nil,
       calculando: false,
       plegada: false
     )}
  end

  @impl true
  def handle_event("poner", %{"lat" => lat, "lon" => lon}, socket)
      when is_number(lat) and is_number(lon) do
    if length(socket.assigns.paradas) >= @max_paradas do
      {:noreply, put_flash(socket, :error, "Caben hasta #{@max_paradas} paradas por cálculo.")}
    else
      %{paradas: paradas, siguiente: n} = socket.assigns
      parada = %{id: if(paradas == [], do: 0, else: n), lat: lat, lon: lon, demanda: 1}
      siguiente = if paradas == [], do: n, else: n + 1

      {:noreply, socket |> assign(siguiente: siguiente) |> cambiar(paradas ++ [parada])}
    end
  end

  def handle_event("mover", %{"id" => id, "lat" => lat, "lon" => lon}, socket)
      when is_number(lat) and is_number(lon) do
    {:noreply, actualizar(socket, entero(id), &%{&1 | lat: lat, lon: lon})}
  end

  # Coordenadas que no son números (no salen del hook) se ignoran.
  def handle_event(evento, _params, socket) when evento in ["poner", "mover"],
    do: {:noreply, socket}

  def handle_event("demanda", %{"campo" => id, "d" => d}, socket) do
    {:noreply, actualizar(socket, entero(id), &%{&1 | demanda: max(&1.demanda + entero(d), 0)})}
  end

  def handle_event("quitar", %{"id" => id}, socket) do
    id = entero(id)
    {:noreply, cambiar(socket, Enum.reject(socket.assigns.paradas, &(&1.id == id)))}
  end

  # El orden de visita lo decide el solver; lo único que la persona ordena
  # es cuál parada es el depósito. La que deja de serlo toma un número nuevo.
  def handle_event("volver_deposito", %{"id" => id}, socket) do
    id = entero(id)
    %{paradas: [anterior | resto], siguiente: n} = socket.assigns

    case Enum.find(resto, &(&1.id == id)) do
      nil ->
        {:noreply, socket}

      nueva ->
        resto = Enum.reject(resto, &(&1.id == id)) ++ [%{anterior | id: n}]
        {:noreply, socket |> assign(siguiente: n + 1) |> cambiar([%{nueva | id: 0} | resto])}
    end
  end

  def handle_event("flota", %{"campo" => campo, "d" => d}, socket) do
    flota = socket.assigns.flota
    d = entero(d)

    flota =
      case campo do
        "n" -> %{flota | n: (flota.n + d) |> max(1) |> min(@max_vehiculos)}
        "cap" -> %{flota | cap: (flota.cap + d * 5) |> max(5) |> min(9995)}
        _ -> flota
      end

    {:noreply, socket |> assign(flota: flota) |> cambiar(socket.assigns.paradas)}
  end

  def handle_event("limpiar", _params, socket) do
    {:noreply,
     socket
     |> assign(calculo: nil, siguiente: 1)
     |> push_event("rutas", %{rutas: []})
     |> cambiar([])}
  end

  def handle_event("plegar", _params, socket) do
    {:noreply, assign(socket, plegada: !socket.assigns.plegada)}
  end

  def handle_event("calcular", _params, socket) do
    %{paradas: paradas, flota: flota} = socket.assigns

    if length(paradas) < 2 do
      {:noreply,
       put_flash(socket, :error, "Agrega al menos 2 paradas (la primera es el depósito).")}
    else
      solicitud = Enum.map(paradas, &Map.take(&1, [:lat, :lon, :demanda]))
      capacidades = List.duplicate(flota.cap, flota.n)

      {:noreply,
       socket
       |> assign(calculando: true, error: nil)
       |> start_async(:vrp, fn ->
         {paradas, flota, MapoCore.vrp_calcular(solicitud, capacidades)}
       end)}
    end
  end

  @impl true
  def handle_async(:vrp, {:ok, {foto, flota, {:ok, resultado}}}, socket) do
    rutas =
      for ruta <- resultado["rutas"], length(ruta["orden_paradas"]) > 2 do
        visitadas = Enum.map(ruta["orden_paradas"], &Enum.at(foto, &1))

        %{
          ids: Enum.map(visitadas, & &1.id),
          km: ruta["distancia_km"] / 1,
          geometria: ruta["geometria"],
          puntos: Enum.map(visitadas, &[&1.lat, &1.lon])
        }
      end

    calculo = %{
      metodo: resultado["metodo"],
      total: resultado["distancia_total_km"] / 1,
      rutas: rutas
    }

    # Si la persona siguió editando mientras se calculaba, el resultado ya
    # llega viejo.
    vigente = foto == socket.assigns.paradas and flota == socket.assigns.flota

    {:noreply,
     socket
     |> assign(calculo: calculo, vigente: vigente, calculando: false)
     |> push_event("rutas", %{rutas: Enum.map(rutas, &Map.take(&1, [:geometria, :puntos]))})
     |> pintar_plano()}
  end

  def handle_async(:vrp, {:ok, {_foto, _flota, {:error, {:status, 422, cuerpo}}}}, socket) do
    mensaje = if is_map(cuerpo), do: cuerpo["detail"]

    {:noreply,
     assign(socket,
       calculando: false,
       error: mensaje || "No se encontró un reparto con esas restricciones."
     )}
  end

  def handle_async(:vrp, _fallo, socket) do
    {:noreply,
     socket
     |> assign(calculando: false)
     |> put_flash(:error, "mapo_core no está disponible ahorita mismo, intenta de nuevo.")}
  end

  defp actualizar(socket, id, fun) do
    paradas = Enum.map(socket.assigns.paradas, &if(&1.id == id, do: fun.(&1), else: &1))
    cambiar(socket, paradas)
  end

  defp cambiar(socket, paradas) do
    socket
    |> assign(paradas: paradas, vigente: false, error: nil)
    |> pintar_plano()
  end

  # Le manda al hook las paradas ya clasificadas: depósito, vehículo o sin ruta.
  defp pintar_plano(socket) do
    %{paradas: paradas, calculo: calculo, vigente: vigente} = socket.assigns

    marcas =
      paradas
      |> Enum.with_index()
      |> Enum.map(fn {p, i} ->
        Map.merge(p, %{
          deposito: i == 0,
          nombre: nombre(p, i == 0),
          ruta: ruta_de(p.id, calculo)
        })
      end)

    push_event(socket, "paradas", %{paradas: marcas, vigente: vigente})
  end

  defp ruta_de(_id, nil), do: nil

  defp ruta_de(id, calculo) do
    Enum.find_index(calculo.rutas, fn r -> id in Enum.slice(r.ids, 1..-2//1) end)
  end

  defp paradas_de(ruta, paradas) do
    ruta.ids
    |> Enum.slice(1..-2//1)
    |> Enum.map(fn id -> Enum.find(paradas, &(&1.id == id)) end)
    |> Enum.reject(&is_nil/1)
  end

  defp sin_ruta(paradas, calculo) do
    paradas |> Enum.drop(1) |> Enum.filter(&is_nil(ruta_de(&1.id, calculo)))
  end

  # La demanda del depósito no cuenta: ahí se carga, no se entrega.
  defp demanda_total(paradas), do: paradas |> Enum.drop(1) |> suma_demanda()
  defp suma_demanda(paradas), do: paradas |> Enum.map(& &1.demanda) |> Enum.sum()

  defp nombre(_parada, true), do: "Depósito"
  defp nombre(parada, false), do: "Parada #{parada.id}"
  defp tinta(k), do: "--v: var(#{Enum.at(@tintas, rem(k, length(@tintas)))})"
  defp letra(k), do: Enum.at(@letras, k)

  defp entero(v) when is_integer(v), do: v

  defp entero(v) do
    case Integer.parse(to_string(v)) do
      {n, _} -> n
      :error -> 0
    end
  end
end
