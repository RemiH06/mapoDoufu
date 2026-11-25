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
  import MapoWeb.Iconos, only: [icono: 1]

  alias Mapo.Limite
  alias Mapo.MapoCore
  alias MapoWeb.Cita
  alias MapoWeb.Cotejo
  alias MapoWeb.ZonaSelector

  # Un municipio grande cruza millones de focos y miles de polígonos.
  @max_consultas 60
  @ventana 3600
  @cercas [
    {"250 m", "250"},
    {"500 m", "500"},
    {"1 km", "1000"},
    {"2 km", "2000"},
    {"5 km", "5000"}
  ]
  @cercas_validas Enum.map(@cercas, &elem(&1, 1))
  @vistas ~w(lista matriz mapas)
  # Zonas que se dejan fijas en la matriz para comparar con la siguiente.
  @max_fijas 4

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="riesgos" full_width?={true}>
      <:membrete><span class="mano">Riesgos ambientales de una zona</span></:membrete>

      <div
        id="riesgos-map"
        phx-hook="RiesgosMapa"
        phx-update="ignore"
        data-peligros={Cotejo.plano_json()}
        class="plano-gl flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano de la zona"
      >
      </div>

      <section
        id="hoja"
        class={[
          "hoja pegado riesgos cotejo-peligros",
          @plegada && "plegada",
          @resultado && @vista != "lista" && "ancha"
        ]}
        data-piel="laboral"
        aria-labelledby="t-hoja"
      >
        <div class="hoja-cab">
          <h1 id="t-hoja">
            {if @resultado, do: "Riesgos de #{lugar(@resultado)}", else: "Riesgos de la zona"}
          </h1>

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
          <p :if={is_nil(@resultado)} class="pista">
            Cada peligro por separado, sin índice. Cercanía no dice causa.
          </p>

          <div :if={@resultado} class="cotejo-barra">
            <Cotejo.vistas vista={@vista} />
            <div class="cotejo-acciones">
              <button
                type="button"
                id="ajustar"
                class="enlace"
                phx-click="ajustar"
                aria-expanded={to_string(@ajustes?)}
                aria-controls="ajustes"
              >
                {if @ajustes?, do: "Cerrar", else: "Cambiar la zona"}
              </button>
              <.link id="abrir-mapa" class="enlace" navigate={ruta_mapa(@consultada, @peligro)}>
                Abrir en el mapa
              </.link>
              <.link
                id="abrir-perfil"
                class="enlace"
                navigate={"/perfil?" <> ZonaSelector.query(zona: @consultada[:zona])}
              >
                Su perfil
              </.link>
            </div>
          </div>

          <div id="ajustes" hidden={@resultado && !@ajustes?}>
            <div class="riesgos-modo" role="group" aria-label="Cómo elegir la zona">
              <button
                :for={
                  {texto, modo} <- [
                    {"Buscar una zona", "zona"},
                    {"Un círculo en el plano", "circulo"}
                  ]
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
          </div>

          <.form
            for={@form}
            id="riesgos_form"
            class={@resultado && !@ajustes? && "en-linea"}
            phx-change="cambiar"
            phx-submit="consultar"
          >
            <%= if @modo == "circulo" do %>
              <div hidden={@resultado && !@ajustes?}>
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
              </div>
            <% end %>

            <.input
              field={@form[:cerca_m]}
              type="select"
              label="Contar como cerca"
              options={@cercas}
            />
            <div class="botones" hidden={@resultado && !@ajustes?}>
              <.button variant="primary" phx-disable-with="Consultando..." disabled={@consultando}>
                {if @consultando, do: "Consultando...", else: "Consultar la zona"}
              </.button>
            </div>
          </.form>

          <p :if={@consultando} class="secundario" role="status">Consultando la zona...</p>

          <p :if={@error} class="aviso" role="alert">{@error}</p>

          <div :if={@resultado} id="riesgos-resultado" class="riesgos-resultado">
            <%= if @vista == "matriz" do %>
              <Cotejo.matriz
                id="matriz"
                titulo="Peligros por zona"
                columnas={columnas(@resultado)}
                filas={filas(@resultado, @fijas)}
                activa={@peligro}
              />
              <.fijar fijas={@fijas} resultado={@resultado} max={@max_fijas} />
            <% end %>

            <Cotejo.mapas
              tipo="peligros"
              columnas={columnas_mapas(@resultado)}
              celdas={celdas(@resultado, "zona")}
              activa={@peligro}
              oculta={@vista != "mapas"}
            />
            <Cotejo.leyenda
              :if={@vista != "lista"}
              que={"Gente a #{cerca_texto(@resultado["cerca_m"])} o menos; en Acuífero, área sin agua disponible"}
              sin="sin medición o sin gente"
              sequia={true}
            />
            <div :if={@vista == "lista"} class="cotejo-lista">
              <.renglon
                clave="poblacion"
                titulo={titulo_poblacion(@resultado)}
                abierto={@peligro == "poblacion"}
                cifra={cifra_o_nada(@resultado["poblacion"]["grupos"]["POBTOT"]["valor"])}
              >
                <.poblacion
                  poblacion={@resultado["poblacion"]}
                  metodo={@resultado["metodo_poblacion"]}
                >
                  <.citar clave="poblacion" citando={@citando} citas={@citas} enlace={@cita_enlace} />
                </.poblacion>
              </.renglon>
              <%= for {grupo, bloques} <- grupos(@resultado) do %>
                <h2 class="cotejo-grupo">{grupo}</h2>

                <.renglon
                  :for={b <- bloques}
                  clave={b["clave"]}
                  titulo={b["titulo"]}
                  abierto={@peligro == b["clave"]}
                  celda={celda(@resultado, b["clave"], "zona")}
                >
                  <.detalle bloque={b} citando={@citando} citas={@citas} enlace={@cita_enlace} />
                </.renglon>
              <% end %>
            </div>

            <article
              :if={@vista != "lista" and bloque(@resultado, @peligro)}
              id="detalle"
              class="bloque"
              aria-live="polite"
            >
              <h2><.icono nombre={@peligro} /> {bloque(@resultado, @peligro)["titulo"]}</h2>
              <.detalle
                bloque={bloque(@resultado, @peligro)}
                citando={@citando}
                citas={@citas}
                enlace={@cita_enlace}
              />
            </article>

            <p :if={@vista != "lista" and is_nil(bloque(@resultado, @peligro))} class="secundario">
              Elige un peligro para verlo solo en el plano, con sus hechos, su fuente y su método.
            </p>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  attr :fijas, :list, required: true
  attr :resultado, :map, required: true
  attr :max, :integer, required: true

  defp fijar(assigns) do
    ~H"""
    <div class="cotejo-acciones">
      <button
        type="button"
        id="fijar"
        class="enlace"
        phx-click="fijar"
        disabled={fija?(@fijas, @resultado) or length(@fijas) >= @max}
      >
        {if fija?(@fijas, @resultado),
          do: "Fija: elige otra zona para comparar",
          else: "Dejarla fija para comparar con otra zona"}
      </button>
    </div>
    """
  end

  attr :clave, :string, required: true
  attr :titulo, :string, required: true
  attr :abierto, :boolean, required: true
  attr :celda, :map, default: nil
  attr :cifra, :string, default: nil
  slot :inner_block, required: true

  # Un peligro en un renglón: ícono, nombre y su cifra. Al abrirlo se ve solo en el
  # plano, con sus hechos, su fuente y su método.
  defp renglon(assigns) do
    ~H"""
    <article id={"bloque-#{@clave}"} class={["cotejo-renglon", @abierto && "abierto"]}>
      <h3>
        <button
          type="button"
          id={"ver-#{@clave}"}
          phx-click="ver"
          phx-value-clave={@clave}
          aria-expanded={to_string(@abierto)}
        >
          <.icono nombre={@clave} /> <span class="cotejo-nombre">{@titulo}</span>
          <Cotejo.ficha :if={@celda} celda={@celda} />
          <span :if={@cifra} class="cotejo-ficha"><b class="num">{@cifra}</b></span>
        </button>
      </h3>

      <div :if={@abierto} class="bloque">{render_slot(@inner_block)}</div>
    </article>
    """
  end

  attr :bloque, :map, required: true
  attr :citando, :string, default: nil
  attr :citas, :list, default: []
  attr :enlace, :string, default: nil

  defp detalle(assigns) do
    ~H"""
    <p class="procedencia">
      {@bloque["fuente"]}<span :if={@bloque["fecha_dato"] not in [nil, ""]}> · {@bloque["fecha_dato"]}</span>
      · {@bloque["nivel"]}
    </p>

    <p :if={cerca = @bloque["poblacion_cerca"]} class="cerca">
      {cifra_o_nada(cerca["grupos"]["POBTOT"]["valor"])} personas de la zona {cerca["frase"]}{detalle_grupos(
        cerca["grupos"]
      )}.
    </p>

    <ul>
      <li :for={h <- @bloque["hechos"]}>{h}</li>
    </ul>

    <p :if={recorte = recortada(@bloque["capa"])} class="secundario">{recorte}</p>

    <details
      id={"metodo-#{@bloque["clave"]}"}
      class="metodo"
      phx-mounted={JS.ignore_attributes("open")}
    >
      <summary>Método</summary>
      {@bloque["metodo"]}
    </details>
    <.citar clave={@bloque["clave"]} citando={@citando} citas={@citas} enlace={@enlace} />
    """
  end

  attr :poblacion, :map, required: true
  attr :metodo, :string, required: true
  slot :inner_block

  defp poblacion(assigns) do
    ~H"""
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

    <details id="metodo-poblacion" class="metodo" phx-mounted={JS.ignore_attributes("open")}>
      <summary>Método</summary>
      {@metodo}
    </details>
    {render_slot(@inner_block)}
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

  ## Lista, matriz y mapas (MapoWeb.Cotejo).

  defp bloque(resultado, clave), do: Enum.find(resultado["bloques"], &(&1["clave"] == clave))

  defp grupos(resultado) do
    {contexto, peligros} =
      Enum.split_with(resultado["bloques"], &(&1["clave"] in Cotejo.contexto()))

    Enum.reject([{"Peligros", peligros}, {"Contexto", contexto}], &(elem(&1, 1) == []))
  end

  defp columnas(resultado) do
    for {clave, corto, unidad} <- Cotejo.peligros(), b = bloque(resultado, clave) do
      %{clave: clave, corto: corto, unidad: unidad, titulo: b["titulo"]}
    end
  end

  # Los mapas chicos llevan además las ANP, que no tienen clase.
  defp columnas_mapas(resultado) do
    anp =
      case bloque(resultado, "anp") do
        nil -> []
        b -> [%{clave: "anp", corto: "ANP", titulo: b["titulo"]}]
      end

    columnas(resultado) ++ anp
  end

  # `de` es "zona" o la clave de un municipio.
  defp celda(resultado, clave, de) do
    case bloque(resultado, clave) do
      %{"medida" => %{"tipo" => tipo} = m} ->
        medida = if de == "zona", do: m["zona"], else: m["municipios"][de]
        Cotejo.celda_peligro(tipo, medida, resultado["cerca_m"])

      _ ->
        unless clave in Cotejo.contexto(), do: Cotejo.celda_peligro(nil, nil, nil)
    end
  end

  defp celdas(resultado, de) do
    for {clave, _, _} <- Cotejo.peligros(), into: %{}, do: {clave, celda(resultado, clave, de)}
  end

  defp filas(resultado, fijas) do
    municipios = resultado["zona"]["municipios"]

    de_municipios =
      if varios?(resultado) do
        for m <- municipios do
          %{
            id: m["cvegeo"],
            nombre: m["nombre"] || m["cvegeo"],
            nota: nil,
            gente: m["poblacion"],
            celdas: celdas(resultado, m["cvegeo"])
          }
        end
      else
        []
      end

    [fila_zona(resultado) | de_municipios] ++
      Enum.reject(fijas, &(&1.fija == resultado["zona"]["clave"]))
  end

  defp fila_zona(resultado) do
    %{
      id: "zona",
      nombre: lugar(resultado),
      nota: if(varios?(resultado), do: "toda la zona"),
      gente: entero(resultado["poblacion"]["grupos"]["POBTOT"]["valor"]),
      celdas: celdas(resultado, "zona")
    }
  end

  defp varios?(resultado), do: match?([_, _ | _], resultado["zona"]["municipios"])

  # Varios municipios se comparan; uno solo se lee en lista.
  defp vista_inicial(nil), do: nil
  defp vista_inicial(resultado), do: if(varios?(resultado), do: "matriz", else: "lista")

  defp fija?(fijas, resultado), do: Enum.any?(fijas, &(&1.fija == resultado["zona"]["clave"]))

  defp entero(v) when is_binary(v), do: String.to_integer(v)
  defp entero(v), do: v

  defp cerca_texto(m) when m >= 1000, do: "#{div(m, 1000)} km"
  defp cerca_texto(m), do: "#{m} m"

  defp recortada(%{"total" => total, "features" => f}) when total > length(f),
    do: "En el plano van #{cifra(length(f))} de #{cifra(total)}."

  defp recortada(_capa), do: nil

  # Con un peligro elegido, el acetato de /mapa abre con él; si no, con los de puntos.
  defp ruta_mapa(consultada, peligro) do
    claves =
      if Cotejo.dibujable?(peligro),
        do: peligro,
        else: "agua_superficial,agua_subterranea,descargas,retc,fuego"

    ~p"/mapa" <>
      "?" <>
      ZonaSelector.query(
        zona: consultada[:zona],
        riesgos: claves,
        cerca: consultada[:cerca],
        ver: "riesgos"
      )
  end

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
       vista: nil,
       peligro: nil,
       ajustes?: false,
       fijas: [],
       max_fijas: @max_fijas,
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

    socket =
      assign(socket,
        vista: if(params["vista"] in @vistas, do: params["vista"]),
        peligro: if(is_binary(params["peligro"]), do: params["peligro"])
      )

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

  # La vista solo va si no es la que saldría sola, y el peligro si hay uno abierto.
  defp ruta_riesgos(a) do
    extra =
      Enum.filter(
        [vista: a.vista != vista_inicial(a.resultado) && a.vista, peligro: a.peligro],
        fn {_k, v} -> v end
      )

    ~p"/riesgos" <> "?" <> ZonaSelector.query(a.consultada ++ extra)
  end

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
    socket = assign(socket, form: formulario(params))
    a = socket.assigns

    # Con la zona ya consultada, otra cercanía vuelve a consultar sola.
    if a.consultada && !a.consultando && !a.ajustes? && params["cerca_m"] in @cercas_validas &&
         String.to_integer(params["cerca_m"]) != a.consultada[:cerca],
       do: {:noreply, consultar(socket, params)},
       else: {:noreply, previa(socket)}
  end

  def handle_event("ajustar", _params, socket),
    do: {:noreply, assign(socket, ajustes?: !socket.assigns.ajustes?)}

  def handle_event("vista", %{"vista" => vista}, socket) when vista in @vistas do
    if socket.assigns.resultado,
      do: {:noreply, socket |> assign(vista: vista) |> escribir_url()},
      else: {:noreply, socket}
  end

  # Elegir un peligro lo deja solo en el plano; elegirlo otra vez los regresa todos.
  def handle_event("ver", %{"clave" => clave}, socket) when is_binary(clave) do
    a = socket.assigns

    if a.resultado && (clave == "poblacion" or bloque(a.resultado, clave)) do
      peligro = if a.peligro != clave, do: clave

      {:noreply,
       socket
       |> assign(peligro: peligro, citando: nil)
       |> push_event("solo", %{clave: solo(peligro)})
       |> escribir_url()}
    else
      {:noreply, socket}
    end
  end

  def handle_event("fijar", _params, %{assigns: a} = socket) do
    if a.resultado && not fija?(a.fijas, a.resultado) && length(a.fijas) < @max_fijas do
      clave = a.resultado["zona"]["clave"]

      fija =
        Map.merge(fila_zona(a.resultado), %{
          id: "fija-#{:erlang.phash2(clave)}",
          nota: "fija",
          fija: clave
        })

      {:noreply, assign(socket, fijas: a.fijas ++ [fija], ajustes?: true)}
    else
      {:noreply, socket}
    end
  end

  def handle_event("soltar", %{"clave" => clave}, socket),
    do: {:noreply, assign(socket, fijas: Enum.reject(socket.assigns.fijas, &(&1.fija == clave)))}

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

      is_nil(a.resultado) or is_nil(Cotejo.fuente_peligro(clave)) or
          (clave != "poblacion" and not Enum.any?(a.resultado["bloques"], &(&1["clave"] == clave))) ->
        {:noreply, socket}

      true ->
        enlace = Cita.enlace(ruta_riesgos(a))

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
      Cita.armar(Cotejo.fuente_peligro(clave),
        que: "#{b["titulo"]}, #{lugar(resultado)}, por #{b["nivel"]}",
        datos: b["fecha_dato"] not in [nil, ""] && b["fecha_dato"],
        enlace: enlace
      )
    ]
  end

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

    a = socket.assigns
    resultado = Map.put(resultado, "nombre_zona", a.nombre_pedido)
    # Con un peligro que ya no está en el resultado (o inventado en la URL), ninguno.
    peligro = if a.peligro == "poblacion" or bloque(resultado, a.peligro), do: a.peligro

    {:noreply,
     socket
     |> assign(
       consultando: false,
       resultado: resultado,
       consultada: a.pedida,
       vista: a.vista || vista_inicial(resultado),
       peligro: peligro,
       ajustes?: false,
       # Contadas a otra cercanía no se comparan.
       fijas: if(a.consultada[:cerca] in [nil, a.pedida[:cerca]], do: a.fijas, else: []),
       citando: nil
     )
     |> push_event("zona", %{
       zona: resultado["zona"]["geojson"],
       limites: resultado["zona"]["limites"],
       capas: capas,
       solo: solo(peligro)
     })
     |> escribir_url()}
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

  defp escribir_url(socket),
    do: push_patch(socket, to: ruta_riesgos(socket.assigns), replace: true)

  # Lo que se ve solo en el plano; la población no tiene capa.
  defp solo(peligro), do: if(Cotejo.dibujable?(peligro), do: peligro)

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
