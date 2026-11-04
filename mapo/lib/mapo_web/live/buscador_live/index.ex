defmodule MapoWeb.BuscadorLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.MapoCore

  # Modo buscador (docs/producto/buscador.md): una pregunta en español común
  # se vuelve una plantilla con huecos, y la plantilla se resuelve con la misma
  # lógica del modo técnico. Las dos entradas llevan a lo mismo: escribir la
  # pregunta (mapo_core la interpreta, sin modelo de lenguaje) o llenar la
  # plantilla a mano. Qué huecos lleva cada intención lo dice mapo_core en su
  # catálogo; aquí solo se dibujan.
  #
  # El plano es el mismo hook de /mapa (MapaTecnico): recibe las mismas capas
  # y pinta con la piel del enfoque de la respuesta. La pregunta va en la URL
  # (`?q=`) para poder compartirla.

  @vacia %{
    "intencion" => nil,
    "rubro" => nil,
    "sector" => nil,
    "municipios" => [],
    "minutos" => nil,
    "edad" => nil,
    "solo_publicos" => false,
    "lat" => nil,
    "lon" => nil
  }

  # La capa de más arriba de cada respuesta pone la piel de la mesa.
  @piel %{
    "donde_poner" => "comercio",
    "cuantos" => "comercio",
    "cuantos_cerca" => "movilidad",
    "donde_contratar" => "demografia"
  }

  @capas ~w(puntos coropleta voronoi isocrona zonas)

  # Sin mínimo ni minutos, mapo_core arranca en la mediana de cada uno.
  @criterios %{"indicador" => "pobtot", "minimo" => nil, "minutos" => nil, "orden" => "indicador"}

  @ejemplos [
    "¿Dónde pongo una florería en Zapopan?",
    "¿Cuántos supermercados hay en Guadalajara y Tlaquepaque?",
    "¿Cuántas farmacias hay a 10 minutos de aquí?",
    "¿Dónde busco gente de 18 a 24 años en Zapopan?",
    "¿Cómo es Tlaquepaque?"
  ]

  @impl true
  def render(assigns) do
    assigns = assign(assigns, ejemplos: @ejemplos)

    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="buscador" full_width?={true}>
      <:membrete>
        <.form for={%{}} as={:lugar} id="estado_form" phx-change="cambiar_estado" class="ubicacion">
          <select name="cve_ent" class="membrete-select" aria-label="Estado">
            {Phoenix.HTML.Form.options_for_select(@estados, @cve_ent)}
          </select>
        </.form>
      </:membrete>

      <div
        id="mapa-tecnico"
        phx-hook="MapaTecnico"
        phx-update="ignore"
        data-margen="520"
        data-margen-der="470"
        class="plano-leaflet flex-1 min-h-0 w-full"
      >
      </div>

      <section
        id="pregunta"
        class={["pregunta pegado", @resultado && "resuelta"]}
        aria-labelledby="pregunta-titulo"
      >
        <h1 id="pregunta-titulo">Pregúntale al plano</h1>

        <.form
          for={%{}}
          as={:pregunta}
          id="pregunta_form"
          phx-submit="entender"
          class="pregunta-texto"
        >
          <input
            type="text"
            name="pregunta[texto]"
            value={@texto}
            maxlength="300"
            placeholder="¿Dónde pongo una florería en Zapopan?"
            aria-label="Pregunta"
            class="campo"
            autocomplete="off"
          />
          <button class="boton primario" phx-disable-with="Leyendo...">Entender</button>
        </.form>

        <button
          :if={@resultado}
          type="button"
          class="editar-plantilla"
          phx-click={JS.toggle_class("abierta", to: "#pregunta")}
        >
          Editar la plantilla
        </button>

        <p :if={@catalogo == nil} class="aviso">
          mapo_core no responde: no se pueden armar las plantillas ahorita.
        </p>

        <.form
          :if={@catalogo}
          for={%{}}
          as={:plantilla}
          id="plantilla_form"
          phx-change="editar"
          phx-submit="resolver"
          class="plantilla"
        >
          <label class="tipo-pregunta">
            <span class="etiqueta">Tipo de pregunta</span>
            <select
              name="plantilla[intencion]"
              class={["hueco", is_nil(@plantilla["intencion"]) && "vacio"]}
            >
              <option value="">elige una</option>
              {Phoenix.HTML.Form.options_for_select(
                Enum.map(@catalogo["intenciones"], &{&1["nombre"], &1["intencion"]}),
                @plantilla["intencion"]
              )}
            </select>
          </label>

          <p :if={@plantilla["intencion"]} class="frase">
            <.frase
              intencion={@plantilla["intencion"]}
              plantilla={@plantilla}
              catalogo={@catalogo}
              municipios={@municipios}
            />
          </p>

          <label
            :if={@plantilla["intencion"] in ["donde_poner", "cuantos", "cuantos_cerca"]}
            class="publicos"
          >
            <input type="hidden" name="plantilla[solo_publicos]" value="false" />
            <input
              type="checkbox"
              name="plantilla[solo_publicos]"
              value="true"
              checked={@plantilla["solo_publicos"]}
            /> Solo del sector público
          </label>

          <div class="plantilla-pie">
            <button
              class="boton primario"
              disabled={huecos_vacios(@plantilla, @catalogo) != []}
              phx-disable-with="Resolviendo..."
            >
              Resolver
            </button>
            <span :if={@plantilla["intencion"] && huecos_vacios(@plantilla, @catalogo) != []}>
              Falta: {Enum.map_join(huecos_vacios(@plantilla, @catalogo), ", ", &nombre_hueco/1)}.
            </span>
          </div>
        </.form>

        <ul :if={@avisos != []} class="avisos">
          <li :for={aviso <- @avisos}>{aviso}</li>
        </ul>

        <p :if={@reconocidos != []} class="reconocidos">
          Entendí:
          <span :for={r <- @reconocidos} class="recorte">
            {r["nombre"]} <em>{tipo(r["tipo"])}</em>
          </span>
        </p>

        <div :if={is_nil(@plantilla["intencion"]) and @texto == ""} class="ejemplos">
          <span>Por ejemplo:</span>
          <.link :for={e <- @ejemplos} patch={~p"/buscador?#{[q: e]}"}>{e}</.link>
        </div>
      </section>

      <p :if={@resolviendo} class="consultando aviso-plano pegado sin-cinta">
        Resolviendo con las fuentes, tarda unos segundos.
      </p>

      <.respuesta
        :if={@resultado}
        resultado={@resultado}
        escala={@escala}
        catalogo={@catalogo}
        zonas={@zonas}
        zonas_error={@zonas_error}
        criterios={@criterios}
        zona_vista={@zona_vista}
      />
    </Layouts.app>
    """
  end

  attr :intencion, :string, required: true
  attr :plantilla, :map, required: true
  attr :catalogo, :map, required: true
  attr :municipios, :list, required: true

  defp frase(%{intencion: "donde_poner"} = assigns) do
    ~H"""
    ¿Dónde poner <.que plantilla={@plantilla} catalogo={@catalogo} /> en
    <.lugares plantilla={@plantilla} municipios={@municipios} />?
    """
  end

  defp frase(%{intencion: "cuantos"} = assigns) do
    ~H"""
    ¿Cuántos negocios de <.que plantilla={@plantilla} catalogo={@catalogo} /> hay en
    <.lugares plantilla={@plantilla} municipios={@municipios} />?
    """
  end

  defp frase(%{intencion: "cuantos_cerca"} = assigns) do
    ~H"""
    ¿Cuántos negocios de <.que plantilla={@plantilla} catalogo={@catalogo} /> hay a
    <input
      type="number"
      name="plantilla[minutos]"
      value={@plantilla["minutos"]}
      min="1"
      phx-debounce="400"
      aria-label="Minutos"
      class={["hueco corto", is_nil(@plantilla["minutos"]) && "vacio"]}
    /> minutos en auto de
    <%= if @plantilla["lat"] do %>
      <span class="hueco lleno">
        {cifra(@plantilla["lat"], 4)}, {cifra(@plantilla["lon"], 4)}
      </span>?
    <% else %>
      <span class="hueco vacio">un punto: clic en el plano</span>?
    <% end %>
    <button type="button" phx-click="usar_ubicacion" class="enlace">Usar mi ubicación</button>
    """
  end

  defp frase(%{intencion: "donde_contratar"} = assigns) do
    ~H"""
    ¿Dónde busco gente de
    <select
      name="plantilla[edad]"
      aria-label="Edad"
      class={["hueco", is_nil(@plantilla["edad"]) && "vacio"]}
    >
      <option value="">qué edad</option>
      {Phoenix.HTML.Form.options_for_select(
        Enum.map(@catalogo["edades"], &{&1["nombre"], &1["edad"]}),
        @plantilla["edad"]
      )}
    </select>
    en <.lugares plantilla={@plantilla} municipios={@municipios} />?
    """
  end

  defp frase(%{intencion: "perfil"} = assigns) do
    ~H"""
    ¿Cómo es <select
      name="plantilla[municipio]"
      aria-label="Municipio"
      class={["hueco", length(@plantilla["municipios"]) != 1 && "vacio"]}
    >
      <option value="">qué municipio</option>
      {Phoenix.HTML.Form.options_for_select(@municipios, List.first(@plantilla["municipios"]))}
    </select>?
    """
  end

  attr :plantilla, :map, required: true
  attr :catalogo, :map, required: true

  defp que(assigns) do
    ~H"""
    <select
      name="plantilla[que]"
      aria-label="Rubro o sector"
      class={["hueco", is_nil(@plantilla["rubro"] || @plantilla["sector"]) && "vacio"]}
    >
      <option value="">qué rubro</option>
      {Phoenix.HTML.Form.options_for_select(opciones_que(@catalogo), valor_que(@plantilla))}
    </select>
    """
  end

  attr :plantilla, :map, required: true
  attr :municipios, :list, required: true

  defp lugares(assigns) do
    ~H"""
    <span :for={cve <- @plantilla["municipios"]} class="recorte">
      <input type="hidden" name="plantilla[municipios][]" value={cve} />
      {nombre_de(@municipios, cve)}
      <button
        type="button"
        phx-click="quitar_municipio"
        phx-value-cve={cve}
        aria-label={"Quitar #{nombre_de(@municipios, cve)}"}
      >
        ×
      </button>
    </span>
    <select
      name="plantilla[agregar]"
      aria-label="Agregar municipio"
      class={["hueco", @plantilla["municipios"] == [] && "vacio"]}
    >
      <option value="" selected>
        {if @plantilla["municipios"] == [], do: "qué municipios", else: "otro"}
      </option>
      {Phoenix.HTML.Form.options_for_select(
        Enum.reject(@municipios, fn {_, cve} -> cve in @plantilla["municipios"] end),
        nil
      )}
    </select>
    """
  end

  attr :resultado, :map, required: true
  attr :escala, :map, default: nil
  attr :catalogo, :map, required: true
  attr :zonas, :map, default: nil
  attr :zonas_error, :string, default: nil
  attr :criterios, :map, required: true
  attr :zona_vista, :map, default: nil

  defp respuesta(assigns) do
    ~H"""
    <section
      class="respuesta pegado"
      data-piel={piel(@resultado["intencion"])}
      aria-labelledby="respuesta-titulo"
    >
      <h2 id="respuesta-titulo">{@resultado["cifras"]["que"]}</h2>

      <%= case @resultado["intencion"] do %>
        <% "cuantos_cerca" -> %>
          <p class="grande num">{cifra(@resultado["cifras"]["total_negocios"])}</p>
          <p>
            {unidad(@resultado["cifras"])} a {@resultado["cifras"]["minutos"]} minutos en auto, {metodo(
              @resultado["cifras"]["metodo"]
            )}.
          </p>
        <% "donde_contratar" -> %>
          <table class="cifras">
            <thead>
              <tr>
                <th>Municipio</th>
                <th class="num">Personas</th>
              </tr>
            </thead>
            <tbody>
              <tr :for={m <- @resultado["cifras"]["municipios"]}>
                <td>{m["nombre"]}</td>
                <td class="num">{dato(m["poblacion"])}</td>
              </tr>
            </tbody>
          </table>
          <p :if={@resultado["cifras"]["laboral"]}>
            Desocupación del estado:
            <b class="num">{cifra(@resultado["cifras"]["laboral"]["tasa_desocupacion"], 2)} %</b>
            (ENOE {@resultado["cifras"]["laboral"]["anio"]}, {trimestre(
              @resultado["cifras"]["laboral"]["trimestre"]
            )}).
          </p>
        <% intencion -> %>
          <table class="cifras">
            <thead>
              <tr>
                <th>Municipio</th>
                <th class="num">{String.capitalize(unidad(@resultado["cifras"]))}</th>
                <th :if={intencion == "donde_poner"} class="num">Población</th>
                <th :if={intencion == "donde_poner"} class="num">
                  Hab. por {singular(@resultado["cifras"])}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr :for={m <- @resultado["cifras"]["municipios"]}>
                <td>{m["nombre"]}</td>
                <td class="num">{cifra(m["negocios"])}</td>
                <td :if={intencion == "donde_poner"} class="num">{dato(m["poblacion"])}</td>
                <td :if={intencion == "donde_poner"} class="num">
                  {dato(m["habitantes_por_negocio"])}
                </td>
              </tr>
            </tbody>
            <tfoot :if={length(@resultado["cifras"]["municipios"]) > 1}>
              <tr>
                <td>Juntos</td>
                <td class="num">{cifra(@resultado["cifras"]["total_negocios"])}</td>
                <td :if={intencion == "donde_poner"} class="num">
                  {dato(@resultado["cifras"]["total_poblacion"])}
                </td>
                <td :if={intencion == "donde_poner"} class="num">
                  {dato(@resultado["cifras"]["habitantes_por_negocio"])}
                </td>
              </tr>
            </tfoot>
          </table>
          <p :if={@resultado["cifras"]["formula"]} class="formula">
            {@resultado["cifras"]["formula"]}
          </p>
          <p :if={intencion == "donde_poner"} class="leyenda">
            {leyenda(@resultado["cifras"])} La tinta es la población por AGEB. Ninguna cifra decide
            sola.
          </p>
      <% end %>

      <div :if={@escala} class="escala" aria-label="Población por AGEB, clases por quintil">
        <ol>
          <li :for={o <- [0.12, 0.26, 0.42, 0.6, 0.8]} style={"opacity: #{o}"}></li>
          <li class="nula" title="Sin dato"></li>
        </ol>
        <div class="marcas num">
          <span :for={v <- Enum.take(@escala.limites, 5)}>{cifra(v)}</span>
          <span>sin dato: {@escala.nulos}</span>
        </div>
      </div>

      <ul :if={@resultado["avisos"] != []} class="avisos">
        <li :for={aviso <- @resultado["avisos"]}>{aviso}</li>
      </ul>

      <.zonas
        :if={@resultado["intencion"] == "donde_poner"}
        catalogo={@catalogo}
        zonas={@zonas}
        error={@zonas_error}
        criterios={@criterios}
        cifras={@resultado["cifras"]}
        zona_vista={@zona_vista}
      />

      <p class="fuente">{fuentes(@resultado["intencion"])}</p>
    </section>
    """
  end

  attr :catalogo, :map, required: true
  attr :zonas, :map, default: nil
  attr :error, :string, default: nil
  attr :criterios, :map, required: true
  attr :cifras, :map, required: true
  attr :zona_vista, :map, default: nil

  # Criterios a la vista, nunca un puntaje (RNF5): cada AGEB cumple los dos o
  # no, y se dice cuántas dejó fuera cada uno.
  defp zonas(assigns) do
    assigns =
      assign(
        assigns,
        :con_minutos,
        is_nil(assigns.zonas) or assigns.zonas["metodo"] != "sin_negocios"
      )

    ~H"""
    <section class="zonas" aria-labelledby="zonas-titulo">
      <h3 id="zonas-titulo">Zonas candidatas</h3>

      <.form for={%{}} as={:criterios} id="criterios_form" phx-change="criterios" class="criterios">
        <fieldset disabled={is_nil(@zonas)}>
          <label>
            <span class="etiqueta">Indicador</span>
            <select name="criterios[indicador]" class="campo">
              {Phoenix.HTML.Form.options_for_select(
                Enum.map(@catalogo["indicadores_zonas"], &{&1["nombre"], &1["indicador"]}),
                @criterios["indicador"]
              )}
            </select>
          </label>
          <label>
            <span class="etiqueta">Desde</span>
            <input
              type="number"
              name="criterios[minimo]"
              value={@criterios["minimo"]}
              min="0"
              phx-debounce="400"
              class="campo num"
            />
          </label>
          <label :if={@con_minutos}>
            <span class="etiqueta">Sin {singular(@cifras)} a menos de (min)</span>
            <input
              type="number"
              name="criterios[minutos]"
              value={@criterios["minutos"]}
              min="0"
              step="1"
              phx-debounce="400"
              class="campo num"
            />
          </label>
          <label :if={@con_minutos}>
            <span class="etiqueta">Ordenar por</span>
            <select name="criterios[orden]" class="campo">
              {Phoenix.HTML.Form.options_for_select(
                [{"El indicador", "indicador"}, {"Los minutos", "minutos"}],
                @criterios["orden"]
              )}
            </select>
          </label>
        </fieldset>
      </.form>

      <p :if={@error} class="aviso">{@error}</p>
      <p :if={is_nil(@zonas) and is_nil(@error)} class="consultando-zonas">
        Calculando tiempos por calle, tarda unos segundos.
      </p>

      <%= if @zonas do %>
        <p>
          <b class="num">{cifra(@zonas["total_candidatas"])}</b>
          de {cifra(@zonas["total"])} AGEB cumplen {if @con_minutos,
            do: "los dos criterios",
            else: "el criterio"}.
        </p>

        <table :if={@zonas["filas"] != []} class="cifras">
          <thead>
            <tr>
              <th>Zona</th>
              <th class="num">{@zonas["etiqueta"]}</th>
              <th :if={@con_minutos} class="num">Min.</th>
              <th><span class="sr-only">Ver en el plano</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              :for={f <- @zonas["filas"]}
              class={[@zona_vista && @zona_vista["cvegeo"] == f["cvegeo"] && "vista"]}
            >
              <td>{f["municipio"]} · {f["ageb"]}</td>
              <td class="num">{cifra(f["valor"])}</td>
              <td :if={@con_minutos} class="num">{cifra(f["minutos"], 1)}</td>
              <td>
                <button
                  type="button"
                  class="enlace"
                  phx-click="ver_zona"
                  phx-value-cvegeo={f["cvegeo"]}
                  aria-label={"Ver #{f["municipio"]} #{f["ageb"]} en el plano"}
                >
                  Ver
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p :if={@zonas["total_candidatas"] > length(@zonas["filas"])} class="leyenda">
          Se listan {length(@zonas["filas"])}; en el plano van todas, con borde.
        </p>

        <p :if={@zona_vista} class="zona-vista">
          {cifra(@zona_vista["total"])} {unidad(@cifras)} a {@zona_vista["minutos"]} minutos en auto de {@zona_vista[
            "ageb"
          ]}, {metodo(@zona_vista["metodo"])}.
        </p>

        <p class="leyenda">
          Fuera: {cifra(@zonas["descartes"]["por_indicador"])} por el indicador{if @con_minutos,
            do: ", #{cifra(@zonas["descartes"]["por_minutos"])} por los minutos"}, {cifra(
            @zonas["descartes"]["sin_dato"]
          )} sin dato. Una AGEB puede fallar los dos.
        </p>
        <p class="leyenda">
          Los criterios arrancan en la mediana. Los minutos son en auto, desde un punto dentro de la
          AGEB, y cuentan a los de otros municipios. El censo dice dónde vive la gente, no dónde
          trabaja o pasa.
        </p>

        <ul :if={@zonas["avisos"] != []} class="avisos">
          <li :for={aviso <- @zonas["avisos"]}>{aviso}</li>
        </ul>
      <% end %>
    </section>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    estados =
      case MapoCore.estados() do
        {:ok, %{"features" => features}} ->
          features
          |> Enum.map(fn %{"properties" => p} -> {p["nomgeo"], p["cvegeo"]} end)
          |> Enum.sort()

        {:error, _} ->
          []
      end

    catalogo =
      case MapoCore.buscador_catalogo() do
        {:ok, catalogo} -> catalogo
        {:error, _} -> nil
      end

    # Por ahora solo Jalisco tiene DENUE y censo cargados; si hay más estados,
    # se elige en el membrete.
    cve_ent =
      cond do
        Enum.any?(estados, &(elem(&1, 1) == "14")) -> "14"
        estados != [] -> estados |> hd() |> elem(1)
        true -> nil
      end

    {:ok,
     assign(socket,
       page_title: "Buscador",
       estados: estados,
       cve_ent: cve_ent,
       municipios: municipios_de(cve_ent),
       catalogo: catalogo,
       texto: "",
       plantilla: @vacia,
       reconocidos: [],
       avisos: [],
       resultado: nil,
       escala: nil,
       resolviendo: false,
       resuelta: nil,
       zonas: nil,
       zonas_error: nil,
       criterios: @criterios,
       zona_vista: nil
     )}
  end

  @impl true
  def handle_params(%{"q" => texto}, _uri, socket) when texto != "" do
    {:noreply, interpretar(socket, String.slice(texto, 0, 300))}
  end

  def handle_params(_params, _uri, socket), do: {:noreply, socket}

  @impl true
  def handle_event("cambiar_estado", %{"cve_ent" => cve_ent}, socket) do
    {:noreply,
     socket
     |> assign(cve_ent: cve_ent, municipios: municipios_de(cve_ent))
     |> cambiar_plantilla(%{socket.assigns.plantilla | "municipios" => []})
     |> limpiar_resultado()}
  end

  def handle_event("entender", %{"pregunta" => %{"texto" => texto}}, socket) do
    case String.trim(texto) do
      "" -> {:noreply, socket}
      texto -> {:noreply, push_patch(socket, to: ~p"/buscador?#{[q: texto]}")}
    end
  end

  def handle_event("editar", %{"plantilla" => params}, socket) do
    {:noreply, cambiar_plantilla(socket, editar(socket.assigns.plantilla, params, socket))}
  end

  def handle_event("quitar_municipio", %{"cve" => cve}, socket) do
    plantilla = Map.update!(socket.assigns.plantilla, "municipios", &List.delete(&1, cve))
    {:noreply, cambiar_plantilla(socket, plantilla)}
  end

  def handle_event("click_mapa", %{"lat" => lat, "lon" => lon}, socket) do
    # Acerca el plano al punto: un clic a escala de país cae en cualquier
    # parte, y así se ve dónde quedó para corregirlo.
    if socket.assigns.plantilla["intencion"] == "cuantos_cerca" do
      {:noreply,
       socket
       |> cambiar_plantilla(%{socket.assigns.plantilla | "lat" => lat, "lon" => lon})
       |> push_event("centrar", %{lat: lat, lon: lon, zoom: 12})}
    else
      {:noreply, socket}
    end
  end

  def handle_event("usar_ubicacion", _params, socket),
    do: {:noreply, push_event(socket, "pedir_ubicacion", %{})}

  def handle_event("ubicacion_fallida", _params, socket) do
    {:noreply,
     put_flash(socket, :error, "El navegador no dio la ubicación. Haz clic en el plano.")}
  end

  def handle_event("resolver", _params, socket) do
    %{cve_ent: cve_ent, plantilla: plantilla} = socket.assigns

    {:noreply,
     socket
     |> assign(resolviendo: true, resuelta: plantilla)
     |> start_async(:resolver, fn -> MapoCore.buscador_resolver(cve_ent, plantilla) end)}
  end

  def handle_event("criterios", %{"criterios" => params}, socket) do
    actual = socket.assigns.criterios
    indicador = params["indicador"] || actual["indicador"]

    criterios = %{
      "indicador" => indicador,
      # El mínimo de otro indicador no significa nada: regresa a su mediana.
      "minimo" => if(indicador == actual["indicador"], do: numero(params["minimo"])),
      "minutos" => numero(params["minutos"]),
      "orden" => params["orden"] || actual["orden"]
    }

    {:noreply, socket |> assign(criterios: criterios) |> quitar_zona_vista() |> pedir_zonas()}
  end

  def handle_event("ver_zona", %{"cvegeo" => cvegeo}, socket) do
    %{cve_ent: cve_ent, resuelta: plantilla, zonas: zonas} = socket.assigns

    case zonas && Enum.find(zonas["filas"], &(&1["cvegeo"] == cvegeo)) do
      nil ->
        {:noreply, socket}

      fila ->
        minutos = max(ceil(zonas["criterios"]["minutos"] || 5), 1)

        cerca =
          Map.merge(plantilla, %{
            "intencion" => "cuantos_cerca",
            "minutos" => minutos,
            "lat" => fila["lat"],
            "lon" => fila["lon"]
          })

        {:noreply,
         start_async(socket, :ver_zona, fn ->
           {fila, minutos, MapoCore.buscador_resolver(cve_ent, cerca)}
         end)}
    end
  end

  @impl true
  def handle_async(:resolver, {:ok, {:ok, %{"perfil" => perfil}}}, socket) do
    {:noreply, push_navigate(socket, to: ~p"/perfil?#{Map.take(perfil, ["cve_ent", "cve_mun"])}")}
  end

  def handle_async(:resolver, {:ok, {:ok, resultado}}, socket) do
    capas = resultado["capas"]
    escala = capas["coropleta"] && escala_quintiles(capas["coropleta"]["geojson"])

    socket =
      Enum.reduce(@capas, socket, fn id, socket ->
        push_event(socket, "capa_#{id}", datos_capa(id, capas[id], escala))
      end)

    {:noreply,
     socket
     |> assign(
       resultado: resultado,
       escala: escala,
       resolviendo: false,
       zonas: nil,
       zonas_error: nil,
       criterios: @criterios,
       zona_vista: nil
     )
     |> push_event("piel", %{piel: piel(resultado["intencion"])})
     |> pedir_zonas()}
  end

  def handle_async(
        :resolver,
        {:ok, {:error, {:status, 422, %{"detail" => %{"mensaje" => m}}}}},
        socket
      ) do
    {:noreply, socket |> assign(resolviendo: false) |> put_flash(:error, m)}
  end

  def handle_async(:resolver, _fallo, socket) do
    {:noreply,
     socket
     |> assign(resolviendo: false)
     |> put_flash(:error, "mapo_core no está disponible ahorita mismo.")}
  end

  # Una respuesta que llega después de cambiar de pregunta ya no aplica.
  def handle_async(:zonas, _respuesta, %{assigns: %{resultado: nil}} = socket),
    do: {:noreply, socket}

  def handle_async(:zonas, {:ok, {:ok, zonas}}, socket) do
    {:noreply,
     socket
     |> assign(
       zonas: zonas,
       zonas_error: nil,
       criterios: Map.merge(socket.assigns.criterios, zonas["criterios"])
     )
     |> push_event("capa_zonas", %{activa: true, cvegeos: zonas["cvegeos"]})}
  end

  def handle_async(
        :zonas,
        {:ok, {:error, {:status, 422, %{"detail" => %{"mensaje" => m}}}}},
        socket
      ) do
    {:noreply, assign(socket, zonas_error: m)}
  end

  def handle_async(:zonas, _fallo, socket) do
    {:noreply, assign(socket, zonas_error: "No se pudieron calcular las zonas candidatas.")}
  end

  def handle_async(:ver_zona, {:ok, {fila, minutos, {:ok, resultado}}}, socket) do
    capas = resultado["capas"]

    {:noreply,
     socket
     |> assign(
       zona_vista: %{
         "cvegeo" => fila["cvegeo"],
         "ageb" => fila["ageb"],
         "minutos" => minutos,
         "total" => resultado["cifras"]["total_negocios"],
         "metodo" => resultado["cifras"]["metodo"]
       }
     )
     |> push_event("capa_puntos", datos_capa("puntos", capas["puntos"], nil))
     |> push_event(
       "capa_isocrona",
       datos_capa("isocrona", capas["isocrona"], nil)
       |> Map.put("origen", Map.take(fila, ~w(lat lon)))
     )}
  end

  def handle_async(:ver_zona, _fallo, socket) do
    {:noreply, put_flash(socket, :error, "No se pudo calcular la isócrona de esa zona.")}
  end

  defp pedir_zonas(%{assigns: %{resultado: %{"intencion" => "donde_poner"}}} = socket) do
    %{cve_ent: cve_ent, resuelta: plantilla, criterios: criterios} = socket.assigns
    start_async(socket, :zonas, fn -> MapoCore.buscador_zonas(cve_ent, plantilla, criterios) end)
  end

  defp pedir_zonas(socket), do: socket

  # La zona vista puede dejar de ser candidata: su isócrona no se queda sola.
  defp quitar_zona_vista(%{assigns: %{zona_vista: nil}} = socket), do: socket

  defp quitar_zona_vista(socket) do
    socket
    |> assign(zona_vista: nil)
    |> push_event("capa_isocrona", %{activa: false})
    |> push_event("capa_puntos", %{activa: false})
  end

  defp interpretar(socket, texto) do
    case socket.assigns.cve_ent && MapoCore.buscador_interpretar(texto, socket.assigns.cve_ent) do
      {:ok, %{"plantilla" => plantilla} = respuesta} ->
        socket
        |> assign(
          texto: texto,
          reconocidos: respuesta["reconocidos"],
          avisos: respuesta["avisos"]
        )
        |> cambiar_plantilla(Map.merge(@vacia, plantilla))
        |> limpiar_resultado()

      _ ->
        socket
        |> assign(texto: texto)
        |> put_flash(:error, "mapo_core no está disponible ahorita mismo.")
    end
  end

  # Los cambios de la plantilla a mano. "que" es "rubro:clave" o
  # "sector:clave"; "agregar" suma un municipio; "municipio" es el único del
  # perfil. Lo que no viene en `params` no se toca.
  defp editar(plantilla, params, socket) do
    plantilla
    |> poner_intencion(params["intencion"])
    |> poner_que(params["que"])
    |> poner_municipios(params, socket.assigns.municipios)
    |> poner_entero("minutos", params["minutos"])
    |> poner_valor("edad", params["edad"])
    |> poner_publicos(params["solo_publicos"])
  end

  defp poner_intencion(plantilla, nil), do: plantilla
  defp poner_intencion(plantilla, ""), do: %{plantilla | "intencion" => nil}
  defp poner_intencion(plantilla, intencion), do: %{plantilla | "intencion" => intencion}

  defp poner_que(plantilla, nil), do: plantilla
  defp poner_que(plantilla, "rubro:" <> r), do: %{plantilla | "rubro" => r, "sector" => nil}
  defp poner_que(plantilla, "sector:" <> s), do: %{plantilla | "rubro" => nil, "sector" => s}
  defp poner_que(plantilla, _), do: %{plantilla | "rubro" => nil, "sector" => nil}

  defp poner_municipios(plantilla, params, municipios) do
    validos = MapSet.new(municipios, &elem(&1, 1))

    lista =
      cond do
        Map.has_key?(params, "municipio") -> List.wrap(vacio_para_nil(params["municipio"]))
        Map.has_key?(params, "municipios") -> params["municipios"]
        Map.has_key?(params, "agregar") -> []
        true -> plantilla["municipios"]
      end

    lista = lista ++ List.wrap(vacio_para_nil(params["agregar"]))
    %{plantilla | "municipios" => lista |> Enum.filter(&(&1 in validos)) |> Enum.uniq()}
  end

  defp poner_entero(plantilla, _campo, nil), do: plantilla

  defp poner_entero(plantilla, campo, texto) do
    case Integer.parse(texto) do
      {n, ""} when n > 0 -> %{plantilla | campo => n}
      _ -> %{plantilla | campo => nil}
    end
  end

  defp poner_valor(plantilla, _campo, nil), do: plantilla
  defp poner_valor(plantilla, campo, valor), do: %{plantilla | campo => vacio_para_nil(valor)}

  defp poner_publicos(plantilla, nil), do: plantilla
  defp poner_publicos(plantilla, valor), do: %{plantilla | "solo_publicos" => valor == "true"}

  # Con la pregunta "cuántos cerca", el clic en el plano elige el punto.
  defp cambiar_plantilla(socket, plantilla) do
    socket
    |> assign(plantilla: plantilla)
    |> push_event("modo_isocrona", %{activo: plantilla["intencion"] == "cuantos_cerca"})
  end

  defp limpiar_resultado(%{assigns: %{resultado: nil}} = socket), do: socket

  defp limpiar_resultado(socket) do
    socket = Enum.reduce(@capas, socket, &push_event(&2, "capa_#{&1}", %{activa: false}))
    assign(socket, resultado: nil, escala: nil, zonas: nil, zonas_error: nil, zona_vista: nil)
  end

  defp datos_capa(_id, nil, _escala), do: %{activa: false}

  defp datos_capa("coropleta", capa, escala) do
    %{
      activa: true,
      geojson: capa["geojson"],
      etiqueta: capa["etiqueta"],
      cortes: escala && escala.cortes
    }
  end

  defp datos_capa("voronoi", capa, _), do: %{activa: true, geojson: capa["celdas"]}
  defp datos_capa("isocrona", capa, _), do: Map.put(capa, "activa", true)
  defp datos_capa("puntos", puntos, _), do: %{activa: true, puntos: puntos}
  defp datos_capa("zonas", _capa, _), do: %{activa: false}

  # Los huecos de la intención elegida que siguen vacíos. Cuáles lleva cada
  # intención lo dice el catálogo de mapo_core, que también lo valida al
  # resolver.
  defp huecos_vacios(%{"intencion" => nil}, _catalogo), do: ["intencion"]

  defp huecos_vacios(plantilla, catalogo) do
    huecos =
      Enum.find_value(catalogo["intenciones"], [], fn i ->
        i["intencion"] == plantilla["intencion"] && i["huecos"]
      end)

    Enum.reject(huecos, &lleno?(&1, plantilla))
  end

  defp lleno?("rubro", p), do: (p["rubro"] || p["sector"]) != nil
  defp lleno?("municipios", p), do: p["municipios"] != []
  defp lleno?("municipio", p), do: length(p["municipios"]) == 1
  defp lleno?("punto", p), do: p["lat"] != nil
  defp lleno?(campo, p), do: p[campo] != nil

  defp nombre_hueco("intencion"), do: "la pregunta"
  defp nombre_hueco("rubro"), do: "el rubro"
  defp nombre_hueco("municipios"), do: "al menos un municipio"
  defp nombre_hueco("municipio"), do: "un municipio"
  defp nombre_hueco("punto"), do: "el punto de partida"
  defp nombre_hueco("minutos"), do: "los minutos"
  defp nombre_hueco("edad"), do: "la edad"

  defp opciones_que(catalogo) do
    Enum.map(catalogo["sectores"], fn s ->
      {s["nombre"],
       [{"Todo el sector", "sector:#{s["sector"]}"}] ++
         Enum.map(s["rubros"], &{&1["nombre"], "rubro:#{&1["rubro"]}"})}
    end)
  end

  defp valor_que(%{"rubro" => r}) when is_binary(r), do: "rubro:#{r}"
  defp valor_que(%{"sector" => s}) when is_binary(s), do: "sector:#{s}"
  defp valor_que(_), do: nil

  defp unidad(cifras), do: cifras["unidad"] || "negocios"

  # Un servicio público no compite: lo que se lee en la celda es cobertura.
  defp leyenda(%{"unidad" => "unidades"}),
    do:
      "Las celdas son la zona más cerca de cada unidad que de otra: celda grande, menos cobertura."

  defp leyenda(_),
    do:
      "Las celdas son la zona más cerca de cada negocio que de otro: celda grande, poca competencia."

  defp singular(cifras), do: if(unidad(cifras) == "unidades", do: "unidad", else: "negocio")

  defp tipo("rubro"), do: "rubro"
  defp tipo("sector"), do: "sector"
  defp tipo("municipio"), do: "municipio"

  defp piel(intencion), do: Map.get(@piel, intencion, "urbanismo")

  defp metodo("osrm_real"), do: "por carretera real (OSRM)"
  defp metodo(_), do: "en un círculo aproximado: OSRM no respondió"

  defp trimestre("trim" <> n), do: "trimestre #{n}"
  defp trimestre(t), do: t

  defp dato(nil), do: "sin dato"
  defp dato(v), do: cifra(v)

  defp fuentes("donde_poner"), do: "INEGI · DENUE y Censo 2020 · OSRM"
  defp fuentes("cuantos"), do: "INEGI · DENUE"
  defp fuentes("cuantos_cerca"), do: "INEGI · DENUE · OSRM"
  defp fuentes("donde_contratar"), do: "INEGI · Censo 2020 y ENOE"

  defp nombre_de(opciones, valor),
    do: Enum.find_value(opciones, valor, fn {n, v} -> if v == valor, do: n end)

  # Vacío o inválido es nil: mapo_core regresa a la mediana.
  defp numero(nil), do: nil

  defp numero(texto) do
    case Float.parse(texto) do
      {n, ""} when n >= 0 -> if trunc(n) == n, do: trunc(n), else: n
      _ -> nil
    end
  end

  defp vacio_para_nil(""), do: nil
  defp vacio_para_nil(valor), do: valor

  defp municipios_de(nil), do: []

  defp municipios_de(cve_ent) do
    case MapoCore.municipios(cve_ent) do
      {:ok, %{"features" => features}} ->
        features
        |> Enum.map(fn %{"properties" => p} -> {p["nomgeo"], p["cve_mun"]} end)
        |> Enum.sort()

      {:error, _} ->
        []
    end
  end
end
