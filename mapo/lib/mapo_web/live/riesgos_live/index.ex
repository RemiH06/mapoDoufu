defmodule MapoWeb.RiesgosLive.Index do
  @moduledoc """
  Vista de riesgos: se elige una zona (con el selector común: estado,
  municipios, metrópoli, colonia, CP o un dibujo; o un círculo en el plano) y
  se ve cada peligro por separado, con su fuente, fecha, nivel y método, y
  cuánta gente vive dentro de la zona y cerca de cada uno. Nunca un índice ni
  "expuesta". El cálculo vive en `mapo_core/riesgos.py`; ver
  docs/producto/vista-riesgos.md y docs/producto/zona.md.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.Limite
  alias Mapo.MapoCore
  alias MapoWeb.Cita
  alias MapoWeb.ZonaSelector

  # Un municipio grande cruza millones de focos y miles de polígonos.
  @max_consultas 30
  @ventana 3600
  @cercas [
    {"250 m", "250"},
    {"500 m", "500"},
    {"1 km", "1000"},
    {"2 km", "2000"},
    {"5 km", "5000"}
  ]
  @cercas_validas Enum.map(@cercas, &elem(&1, 1))

  # Cada bloque de mapo_core/riesgos.py con su referencia (docs/producto/citar.md).
  @fuente_bloque %{
    "poblacion" => "censo",
    "descargas" => "repda",
    "retc" => "retc",
    "fuego" => "firms",
    "acuifero" => "acuiferos",
    "sequia" => "sequia",
    "anp" => "anp",
    "uso_suelo" => "uso_suelo",
    "agricultura" => "siap",
    "defunciones" => "defunciones"
  }

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="riesgos" full_width?={true}>
      <:membrete><span class="mano">Riesgos ambientales de una zona</span></:membrete>

      <div
        id="riesgos-map"
        phx-hook="RiesgosMapa"
        phx-update="ignore"
        class="plano-gl flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano de la zona"
      >
      </div>

      <section
        id="hoja"
        class={["hoja pegado riesgos", @plegada && "plegada"]}
        data-piel="laboral"
        aria-labelledby="t-hoja"
      >
        <div class="hoja-cab">
          <h1 id="t-hoja">Riesgos de la zona</h1>

          <button
            type="button"
            class="chico plegar"
            phx-click="plegar"
            aria-expanded={to_string(!@plegada)}
          >
            {if @plegada, do: "Ver la hoja", else: "Plegar"}
          </button>
          <span :if={@resultado} class="tipo">{cifra(@resultado["zona"]["km2"], 1)} km²</span>
        </div>

        <div class="riesgos-cuerpo">
          <p class="pista">
            Cada peligro va por separado, con su fuente y su fecha: aquí no hay índice. Cercanía no dice causa.
          </p>

          <div class="riesgos-modo" role="group" aria-label="Cómo elegir la zona">
            <button
              :for={
                {texto, modo} <- [{"Buscar una zona", "zona"}, {"Un círculo en el plano", "circulo"}]
              }
              type="button"
              id={"modo-#{modo}"}
              class="chico"
              phx-click="modo"
              phx-value-modo={modo}
              aria-pressed={to_string(@modo == modo)}
            >
              {texto}
            </button>
          </div>

          <.live_component
            :if={@modo == "zona"}
            module={ZonaSelector}
            id="zona"
            zona={@zona}
            scope={@current_scope}
          />

          <.form for={@form} id="riesgos_form" phx-change="cambiar" phx-submit="consultar">
            <%= if @modo == "circulo" do %>
              <.input
                field={@form[:radio_km]}
                type="number"
                min="0.1"
                max="25"
                step="0.1"
                label="Radio (km)"
              />
              <p class="secundario">
                {if @punto,
                  do:
                    "Centro en #{cifra(@punto.lat, 4)}, #{cifra(@punto.lon, 4)}. Toca otro lugar para moverlo.",
                  else: "Toca el plano para poner el centro."}
              </p>
            <% end %>

            <.input
              field={@form[:cerca_m]}
              type="select"
              label="Contar como cerca"
              options={@cercas}
            />
            <div class="botones">
              <.button variant="primary" phx-disable-with="Consultando..." disabled={@consultando}>
                {if @consultando, do: "Consultando...", else: "Consultar la zona"}
              </.button>
            </div>
          </.form>

          <p :if={@error} class="aviso" role="alert">{@error}</p>

          <div :if={@resultado} id="riesgos-resultado" class="riesgos-resultado">
            <.poblacion
              titulo={titulo_poblacion(@resultado)}
              poblacion={@resultado["poblacion"]}
              metodo={@resultado["metodo_poblacion"]}
            >
              <.citar clave="poblacion" citando={@citando} citas={@citas} enlace={@cita_enlace} />
            </.poblacion>
            <article :for={b <- @resultado["bloques"]} id={"bloque-#{b["clave"]}"} class="bloque">
              <h2>{b["titulo"]}</h2>

              <p class="procedencia">
                {b["fuente"]}<span :if={b["fecha_dato"] not in [nil, ""]}> · {b["fecha_dato"]}</span>
                · {b["nivel"]}
              </p>

              <ul>
                <li :for={h <- b["hechos"]}>{h}</li>
              </ul>

              <p :if={cerca = b["poblacion_cerca"]} class="cerca">
                {cifra_o_nada(cerca["grupos"]["POBTOT"]["valor"])} personas de la zona {cerca["frase"]}{detalle_grupos(
                  cerca["grupos"]
                )}.
              </p>

              <p class="metodo">Método: {b["metodo"]}</p>
              <.citar clave={b["clave"]} citando={@citando} citas={@citas} enlace={@cita_enlace} />
            </article>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  attr :titulo, :string, required: true
  attr :poblacion, :map, required: true
  attr :metodo, :string, required: true
  slot :inner_block

  defp poblacion(assigns) do
    ~H"""
    <article id="bloque-poblacion" class="bloque">
      <h2>{@titulo}</h2>

      <p class="procedencia">INEGI, censo 2020 · AGEB urbano y localidad</p>

      <ul>
        <li :for={{clave, g} <- grupos_ordenados(@poblacion["grupos"])}>
          <span class="num">{cifra_o_nada(g["valor"])}</span> {g["etiqueta"]}{donde(clave, @poblacion)}
        </li>
      </ul>

      <p :if={reservados(@poblacion) > 0} class="cerca">
        INEGI reserva los datos de lugares con pocas viviendas: en {cifra(reservados(@poblacion))} de los {cifra(
          @poblacion["agebs"] + @poblacion["localidades"]
        )} lugares falta algún grupo. No se cuentan como cero, así que los grupos pueden quedar cortos.
      </p>

      <p :if={(@poblacion["urbanas_por_punto"] || 0) > 0} class="cerca">
        {cifra(@poblacion["pob_urbanas_por_punto"])} personas son de {cifra(
          @poblacion["urbanas_por_punto"]
        )} {if @poblacion[
                 "urbanas_por_punto"
               ] == 1,
               do: "localidad urbana que cuenta",
               else: "localidades urbanas que cuentan"} entera por su punto: Mapo no tiene sus AGEB cargados, así que cuenta a toda la ciudad aunque la zona toque solo una parte.
      </p>

      <p class="metodo">Método: {@metodo}</p>
      {render_slot(@inner_block)}
    </article>
    """
  end

  attr :clave, :string, required: true
  attr :citando, :string, default: nil
  attr :citas, :list, default: []
  attr :enlace, :string, default: nil

  defp citar(assigns) do
    ~H"""
    <div class="cinta-citar">
      <button
        type="button"
        id={"citar-#{@clave}"}
        class="enlace"
        phx-click="citar"
        phx-value-clave={@clave}
        aria-expanded={to_string(@citando == @clave)}
      >
        {if @citando == @clave, do: "Cerrar la cita", else: "Cómo citar"}
      </button>
      <Cita.como_citar :if={@citando == @clave} id={"cita-#{@clave}"} citas={@citas} enlace={@enlace} />
    </div>
    """
  end

  @orden ~w(POBTOT P_0A2 P_3A5 P_60YMAS PCON_DISC PSINDER P3YM_HLI TVIVPARHAB VPH_AGUAFV VPH_NODREN)

  defp grupos_ordenados(grupos), do: for(c <- @orden, g = grupos[c], do: {c, g})

  defp donde("POBTOT", p),
    do: " en #{cifra(p["agebs"])} AGEB urbanos y #{cifra(p["localidades"])} localidades"

  defp donde(_clave, _p), do: ""

  defp reservados(%{"grupos" => grupos}) do
    grupos |> Map.values() |> Enum.map(&(&1["reservados"] || 0)) |> Enum.max(fn -> 0 end)
  end

  defp cifra_o_nada(nil), do: "sin dato"
  defp cifra_o_nada(v) when is_binary(v), do: v |> String.to_integer() |> cifra()
  defp cifra_o_nada(v), do: cifra(v)

  defp detalle_grupos(grupos) do
    partes =
      for c <- ~w(P_0A2 P_3A5 P_60YMAS PCON_DISC),
          g = grupos[c],
          g["valor"] not in [nil, 0, "0"] do
        "#{cifra_o_nada(g["valor"])} #{g["etiqueta"]}"
      end

    if partes == [], do: "", else: "; entre ellas, " <> Enum.join(partes, ", ")
  end

  defp titulo_poblacion(resultado), do: "Quién vive en #{lugar(resultado)}"

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     assign(socket,
       page_title: "Riesgos",
       cercas: @cercas,
       modo: "zona",
       zona: nil,
       punto: nil,
       resultado: nil,
       error: nil,
       consultando: false,
       plegada: false,
       form: formulario(%{}),
       consultada: nil,
       pedida: nil,
       nombre_pedido: nil,
       citando: nil,
       citas: [],
       cita_enlace: nil
     )}
  end

  # Enlace permanente: la zona y la cercanía de la última consulta. Al abrirlo
  # se consulta igual que con el botón (con el mismo límite por hora). Cada
  # valor pasa por la misma validación que el formulario; uno raro deja la
  # hoja vacía, sin error. Los enlaces de antes de la 29b (`modo=municipio`
  # con `ent` y `mun`, o `modo=circulo` con `lat`, `lon` y `radio`) se leen
  # como su clave de zona: ya hay citas con ellos.
  @impl true
  def handle_params(params, _uri, socket) do
    cond do
      not connected?(socket) or not is_nil(socket.assigns.consultada) -> {:noreply, socket}
      params != %{} -> {:noreply, consultar_de_url(socket, params)}
      # Sin zona en el enlace, la que guardó quien abre (sin consultar sola).
      true -> {:noreply, ZonaSelector.con_zona_inicial(socket)}
    end
  end

  defp consultar_de_url(socket, params) do
    cerca = params["cerca"] || "1000"

    case clave_de_url(params) do
      {:circulo, lon, lat, km} ->
        form = %{"radio_km" => km, "cerca_m" => cerca}

        socket
        |> assign(modo: "circulo", punto: %{lat: lat, lon: lon}, form: formulario(form))
        |> previa()
        |> consultar(form)

      {:zona, clave} ->
        with {:ok, _} <- cerca(cerca), {:ok, zona} <- ZonaSelector.resolver(clave) do
          socket
          |> assign(zona: zona, form: formulario(%{"cerca_m" => cerca}))
          |> push_event("zona_elegida", %{geojson: zona["geojson"]})
          |> consultar(%{"cerca_m" => cerca})
        else
          _ -> socket
        end

      nil ->
        socket
    end
  end

  defp clave_de_url(%{"zona" => "cir:" <> resto}) do
    with [lon, lat, radio] <- String.split(resto, ","),
         {lon, ""} <- Float.parse(lon),
         {lat, ""} <- Float.parse(lat),
         {radio, ""} <- Float.parse(radio) do
      {:circulo, lon, lat, to_string(radio / 1000)}
    else
      _ -> nil
    end
  end

  defp clave_de_url(%{"zona" => clave}) when is_binary(clave), do: {:zona, clave}

  defp clave_de_url(%{"modo" => "circulo"} = params) do
    with {lat, ""} <- Float.parse(params["lat"] || ""),
         {lon, ""} <- Float.parse(params["lon"] || "") do
      {:circulo, lon, lat, params["radio"] || ""}
    else
      _ -> nil
    end
  end

  defp clave_de_url(%{"ent" => ent, "mun" => mun}) when is_binary(ent) and is_binary(mun) do
    if String.match?(ent, ~r/^\d{2}$/) and String.match?(mun, ~r/^\d{3}$/),
      do: {:zona, "mun:#{ent}#{mun}"},
      else: nil
  end

  defp clave_de_url(_params), do: nil

  defp ruta_riesgos(params), do: ~p"/riesgos" <> "?" <> ZonaSelector.query(params)

  defp formulario(params) do
    base = %{"radio_km" => "2", "cerca_m" => "1000"}
    to_form(Map.merge(base, Map.take(params, Map.keys(base))), as: "riesgos")
  end

  @impl true
  def handle_info({:zona_elegida, zona}, socket) do
    socket = assign(socket, zona: zona, modo: "zona")
    {:noreply, consultar(socket, socket.assigns.form.params)}
  end

  @impl true
  def handle_event("cambiar", %{"riesgos" => params}, socket) do
    {:noreply, socket |> assign(form: formulario(params)) |> previa()}
  end

  def handle_event("modo", %{"modo" => modo}, socket) when modo in ~w(zona circulo) do
    {:noreply, socket |> assign(modo: modo, error: nil) |> previa()}
  end

  def handle_event("punto", %{"lat" => lat, "lon" => lon}, socket)
      when is_number(lat) and is_number(lon) do
    {:noreply, socket |> assign(punto: %{lat: lat, lon: lon}, modo: "circulo") |> previa()}
  end

  def handle_event("punto", _params, socket), do: {:noreply, socket}

  def handle_event("plegar", _params, socket),
    do: {:noreply, assign(socket, plegada: !socket.assigns.plegada)}

  def handle_event("consultar", _params, %{assigns: %{consultando: true}} = socket),
    do: {:noreply, socket}

  def handle_event("consultar", %{"riesgos" => params}, socket) do
    {:noreply, consultar(socket, params)}
  end

  def handle_event("citar", %{"clave" => clave}, socket) when is_binary(clave) do
    a = socket.assigns

    cond do
      a.citando == clave ->
        {:noreply, assign(socket, citando: nil)}

      is_nil(a.resultado) or is_nil(fuente_bloque(clave)) or
          (clave != "poblacion" and not Enum.any?(a.resultado["bloques"], &(&1["clave"] == clave))) ->
        {:noreply, socket}

      true ->
        enlace = Cita.enlace(ruta_riesgos(a.consultada))

        {:noreply,
         assign(socket,
           citando: clave,
           citas: citas(a.resultado, clave, enlace),
           cita_enlace: enlace
         )}
    end
  end

  defp consultar(socket, params) do
    socket = assign(socket, form: formulario(params))

    with {:ok, clave, nombre} <- zona(socket.assigns, params),
         {:ok, cerca} <- cerca(params["cerca_m"]),
         :ok <- limite(socket) do
      socket
      |> assign(
        consultando: true,
        error: nil,
        pedida: [zona: clave, cerca: cerca],
        nombre_pedido: nombre
      )
      |> start_async(:riesgos, fn -> MapoCore.riesgos_zona(clave, cerca) end)
    else
      {:error, mensaje} -> assign(socket, error: mensaje)
    end
  end

  defp citas(resultado, "poblacion", enlace) do
    [
      Cita.armar("censo",
        que: "#{titulo_poblacion(resultado)} (AGEB urbanos y localidades)",
        datos: "2020",
        enlace: enlace
      )
    ]
  end

  defp citas(resultado, clave, enlace) do
    b = Enum.find(resultado["bloques"], &(&1["clave"] == clave))

    [
      Cita.armar(fuente_bloque(clave),
        que: "#{b["titulo"]}, #{lugar(resultado)}, por #{b["nivel"]}",
        datos: b["fecha_dato"] not in [nil, ""] && b["fecha_dato"],
        enlace: enlace
      )
    ]
  end

  defp fuente_bloque("agua_" <> _tipo), do: "renameca"
  defp fuente_bloque(clave), do: @fuente_bloque[clave]

  defp lugar(%{"zona" => %{"tipo" => "circulo"} = z}),
    do: "el círculo de #{cifra(z["radio_m"] / 1000, 1)} km"

  defp lugar(%{"nombre_zona" => nombre}) when is_binary(nombre), do: nombre
  defp lugar(_resultado), do: "la zona"

  @impl true
  def handle_async(:riesgos, {:ok, {:ok, resultado}}, socket) do
    capas =
      for b <- resultado["bloques"], b["capa"] && b["capa"]["features"] != [] do
        %{clave: b["clave"], titulo: b["titulo"], datos: b["capa"]}
      end

    {:noreply,
     socket
     |> assign(
       consultando: false,
       resultado: Map.put(resultado, "nombre_zona", socket.assigns.nombre_pedido),
       consultada: socket.assigns.pedida,
       citando: nil
     )
     |> push_event("zona", %{zona: resultado["zona"]["geojson"], capas: capas})
     |> push_patch(to: ruta_riesgos(socket.assigns.pedida), replace: true)}
  end

  def handle_async(:riesgos, {:ok, {:error, {:status, 422, %{"detail" => d}}}}, socket)
      when is_binary(d),
      do: {:noreply, assign(socket, consultando: false, error: "La zona no sirve: #{d}.")}

  def handle_async(:riesgos, {:ok, {:error, {:status, 404, _}}}, socket),
    do:
      {:noreply,
       assign(socket, consultando: false, error: "Esa zona no toca nada cargado en Mapo.")}

  def handle_async(:riesgos, _resultado, socket) do
    {:noreply,
     assign(socket,
       consultando: false,
       error: "No se pudo consultar la zona. Inténtalo de nuevo en un momento."
     )}
  end

  defp zona(%{modo: "circulo", punto: punto}, params) do
    with %{lat: lat, lon: lon} <- punto,
         {km, ""} when km >= 0.1 and km <= 25 <- Float.parse(params["radio_km"] || "") do
      {:ok, "cir:#{Float.round(lon / 1, 5)},#{Float.round(lat / 1, 5)},#{round(km * 1000)}", nil}
    else
      nil -> {:error, "Toca el plano para poner el centro del círculo."}
      _ -> {:error, "El radio va de 0.1 a 25 km."}
    end
  end

  defp zona(%{zona: %{"clave" => clave, "nombre" => nombre}}, _params), do: {:ok, clave, nombre}
  defp zona(_assigns, _params), do: {:error, "Elige una zona."}

  defp cerca(valor) when valor in @cercas_validas, do: {:ok, String.to_integer(valor)}
  defp cerca(_), do: {:error, "Elige qué tan cerca contar."}

  defp limite(socket) do
    if Limite.permitir?(
         {:riesgos, socket.assigns.current_scope.user.id},
         @max_consultas,
         @ventana
       ),
       do: :ok,
       else: {:error, "Llevas #{@max_consultas} consultas en una hora. Espera un poco."}
  end

  # El círculo se dibuja en cuanto hay centro y radio, antes de consultar.
  defp previa(%{assigns: %{modo: "circulo", punto: %{lat: lat, lon: lon}, form: form}} = socket) do
    with {km, ""} when km >= 0.1 and km <= 25 <- Float.parse(form.params["radio_km"] || "") do
      push_event(socket, "previa", %{lat: lat, lon: lon, radio_m: km * 1000})
    else
      _ -> socket
    end
  end

  defp previa(socket), do: socket
end
