defmodule MapoWeb.AccesibilidadLive.Index do
  @moduledoc """
  Accesibilidad a servicios: en una zona (selector común: municipios,
  metrópoli, colonia, CP o dibujo; docs/producto/zona.md), cuánta gente vive a más de N
  minutos (a pie o en auto) de cada servicio, cada uno por separado y con su
  grupo de población. Nunca un índice. Los minutos ya están calculados por
  estado en `mapo_core/accesibilidad.py`; mover el umbral no vuelve a
  consultar: mapo_core manda, por servicio, cuánta gente queda a cada minuto o
  menos, y aquí se resta. Ver docs/producto/accesibilidad.md.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras
  import MapoWeb.Iconos, only: [icono: 1]

  alias Mapo.Limite
  alias Mapo.MapoCore
  alias MapoWeb.Cita
  alias MapoWeb.Cotejo
  alias MapoWeb.ZonaSelector

  @max_consultas 60
  @ventana 3600
  @umbral_inicial 15
  @modos [{"A pie", "pie"}, {"En auto", "auto"}]
  @modos_validos Enum.map(@modos, &elem(&1, 1))
  @vistas ~w(lista matriz mapas)
  # Zonas que se dejan fijas en la matriz para comparar con la siguiente.
  @max_fijas 4
  @frase_modo %{"pie" => "a pie", "auto" => "en auto"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app
      flash={@flash}
      current_scope={@current_scope}
      seccion="accesibilidad"
      full_width?={true}
    >
      <:membrete><span class="mano">Servicios a la mano</span></:membrete>

      <div
        id="accesibilidad-map"
        phx-hook="AccesibilidadMapa"
        phx-update="ignore"
        data-peligros={Cotejo.plano_json()}
        class="plano-gl flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano de la zona por minutos al servicio elegido"
      >
      </div>
      <%!-- Misma hoja que /riesgos: comparten la forma de una consulta por zona. --%>
      <section
        id="hoja"
        class={[
          "hoja pegado riesgos cotejo-servicios",
          @plegada && "plegada",
          @resultado && @vista != "lista" && "ancha"
        ]}
        data-piel="laboral"
        aria-labelledby="t-hoja"
      >
        <div class="hoja-cab">
          <h1 id="t-hoja">
            {if @resultado,
              do: "Servicios de #{@resultado["zona"]["nombre"]}",
              else: "Servicios de la zona"}
          </h1>

          <button
            type="button"
            class="chico plegar"
            phx-click="plegar"
            aria-expanded={to_string(!@plegada)}
          >
            {if @plegada, do: "Ver la hoja", else: "Plegar"}
          </button>
        </div>

        <div class="riesgos-cuerpo">
          <p :if={is_nil(@resultado)} class="pista">
            Cada servicio por separado, con la gente que lo usa, sin índice. Minutos por calle, sin tráfico.
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
              <.link
                :if={@servicio}
                id="abrir-mapa"
                class="enlace"
                navigate={ruta_mapa(@consultada, @umbral, @servicio)}
              >
                Abrir en el mapa
              </.link>
              <.link
                id="abrir-perfil"
                class="enlace"
                navigate={"/perfil?" <> ZonaSelector.query(zona: @consultada.zona)}
              >
                Su perfil
              </.link>
            </div>
          </div>

          <div id="ajustes" hidden={@resultado && !@ajustes?}>
            <.live_component module={ZonaSelector} id="zona" zona={@zona} scope={@current_scope} />
          </div>

          <.form
            for={@form}
            id="accesibilidad_form"
            class={@resultado && "en-linea"}
            phx-change="cambiar"
            phx-submit="consultar"
          >
            <.input field={@form[:modo]} type="select" label="Cómo se llega" options={@modos} />
            <.input
              field={@form[:umbral]}
              type="number"
              min="1"
              max={@max_minutos}
              step="1"
              label="Lejos es más de (minutos)"
            />
            <div class="botones" hidden={@resultado && !@ajustes?}>
              <.button variant="primary" phx-disable-with="Consultando..." disabled={@consultando}>
                {if @consultando, do: "Consultando...", else: "Consultar la zona"}
              </.button>
            </div>
          </.form>

          <p :if={@consultando} class="secundario" role="status">Consultando la zona...</p>

          <p :if={@error} class="aviso" role="alert">{@error}</p>

          <div :if={@resultado} id="accesibilidad-resultado" class="riesgos-resultado">
            <%= if @vista == "matriz" do %>
              <Cotejo.matriz
                id="matriz"
                titulo="Servicios por zona"
                columnas={columnas(@resultado)}
                filas={filas(@resultado, @umbral, @fijas)}
                activa={@servicio}
              />
              <div class="cotejo-acciones">
                <button
                  type="button"
                  id="fijar"
                  class="enlace"
                  phx-click="fijar"
                  disabled={fija?(@fijas, @resultado) or length(@fijas) >= @max_fijas}
                >
                  {if fija?(@fijas, @resultado),
                    do: "Fija: elige otra zona para comparar",
                    else: "Dejarla fija para comparar con otra zona"}
                </button>
              </div>
            <% end %>

            <Cotejo.mapas
              tipo="servicios"
              columnas={columnas(@resultado)}
              celdas={celdas(@resultado["servicios"], "zona", @umbral)}
              activa={@servicio}
              oculta={@vista != "mapas"}
            />
            <Cotejo.leyenda
              :if={@vista == "matriz"}
              que={"Su grupo a más de #{@umbral} minutos #{@frase_modo[@resultado["modo"]]}"}
              sin="no se calcula o sin gente"
            />
            <p :if={@vista == "mapas"} class="secundario">
              Más tinta, más minutos: hasta {cifra(@umbral / 2)}, hasta {@umbral}, hasta {@umbral * 2} y más. Sin tinta, sin dato. La cifra es su grupo a más de {@umbral} minutos.
            </p>
            <div :if={@vista == "lista"} class="cotejo-lista">
              <p class="secundario">
                A más de {@umbral} minutos {@frase_modo[@resultado["modo"]]}, en {cifra(
                  @resultado["agebs"]
                )} AGEB urbanos y {cifra(@resultado["lugares"] - @resultado["agebs"])} localidades sin AGEB.
              </p>

              <article
                :for={s <- @resultado["servicios"]}
                id={"servicio-#{s["clave"]}"}
                class={["cotejo-renglon", @servicio == s["clave"] && "abierto activo"]}
              >
                <h3>
                  <button
                    type="button"
                    id={"ver-#{s["clave"]}"}
                    phx-click="ver"
                    phx-value-clave={s["clave"]}
                    aria-expanded={to_string(@servicio == s["clave"])}
                    disabled={!s["calculado"]}
                  >
                    <.icono nombre={s["clave"]} /> <span class="cotejo-nombre">{s["titulo"]}</span>
                    <Cotejo.ficha celda={celda(s, "zona", @umbral)} />
                  </button>
                </h3>

                <p :if={!s["calculado"]} class="secundario">{por_que_no(s, @resultado)}</p>

                <div :if={@servicio == s["clave"]} class="bloque">
                  <.detalle {detalle_de(assigns, s)} />
                </div>
              </article>
            </div>

            <article
              :for={
                s <- Enum.filter(@resultado["servicios"], &(&1["clave"] == @servicio)) |> Enum.take(1)
              }
              :if={@vista != "lista"}
              id="detalle"
              class="bloque"
              aria-live="polite"
            >
              <h2><.icono nombre={s["clave"]} /> {s["titulo"]}</h2>
              <.detalle {detalle_de(assigns, s)} />
            </article>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  defp detalle_de(a, s) do
    a
    |> Map.take([:umbral, :citando, :citas, :cita_enlace, :resultado])
    |> Map.merge(%{s: s, frase: @frase_modo[a.resultado["modo"]]})
  end

  attr :s, :map, required: true
  attr :umbral, :integer, required: true
  attr :frase, :string, required: true
  attr :resultado, :map, required: true
  attr :citando, :string, default: nil
  attr :citas, :list, default: []
  attr :cita_enlace, :string, default: nil

  defp detalle(assigns) do
    assigns = assign(assigns, r: Cotejo.resumen(assigns.s, assigns.umbral))

    ~H"""
    <p class="procedencia">{@s["fuente"]}</p>

    <p class="cerca">
      <span class="num">{cifra(@r.fuera)}</span> {@s["grupo_etiqueta"]}{porcentaje(@r)} viven a más de {@umbral} minutos {@frase}.
    </p>

    <ul>
      <li>
        <span class="num">{cifra(@r.dentro)}</span> a {@umbral} minutos o menos.
      </li>

      <li :if={@s["sin_ruta"] > 0}>
        <span class="num">{cifra(@s["sin_ruta"])}</span>
        sin ruta por calle a los más cercanos: no se cuentan ni cerca ni lejos.
      </li>

      <li :if={(@s["sin_calcular_lugares"] || 0) > 0}>
        <span class="num">{cifra(@s["sin_calcular"])}</span>
        viven en {cifra(@s["sin_calcular_lugares"])} {if @s["sin_calcular_lugares"] == 1,
          do: "lugar que no se calcula",
          else: "lugares que no se calculan"}: {sin_calcular_por_que(@s)}.
      </li>

      <li :if={@s["reservados"] > 0}>
        INEGI reserva el dato en {cifra(@s["reservados"])} {if @s["reservados"] == 1,
          do: "lugar",
          else: "lugares"} con pocas viviendas: no se cuentan como cero.
      </li>

      <li>
        {cifra(@s["destinos_zona"])} en la zona, {cifra(@s["destinos_estado"])} en {el_estado(
          @resultado
        )}.
      </li>
    </ul>

    <details id={"metodo-#{@s["clave"]}"} class="metodo" phx-mounted={JS.ignore_attributes("open")}>
      <summary>Método</summary>
      Red: {@s["red"]}. {@s["metodo"]} Calculado el {@s["fecha"]}.
    </details>

    <div class="cinta-citar">
      <button
        type="button"
        id={"citar-#{@s["clave"]}"}
        class="enlace"
        phx-click="citar"
        phx-value-clave={@s["clave"]}
        aria-expanded={to_string(@citando == @s["clave"])}
      >
        {if @citando == @s["clave"], do: "Cerrar la cita", else: "Cómo citar"}
      </button>

      <Cita.como_citar
        :if={@citando == @s["clave"]}
        id={"cita-#{@s["clave"]}"}
        citas={@citas}
        enlace={@cita_enlace}
      />
    </div>
    """
  end

  defp varios_estados?(resultado), do: length(resultado["zona"]["estados"] || []) > 1

  defp el_estado(resultado),
    do: if(varios_estados?(resultado), do: "los estados", else: "el estado")

  defp por_que_no(%{"sin_cobertura" => true}, _resultado),
    do:
      "Ningún GTFS cargado tiene paradas en los municipios de esta zona: no se calcula. Fuera de las ciudades con GTFS sí hay camiones, pero nadie publica sus paradas."

  defp por_que_no(_s, resultado) do
    estados = if varios_estados?(resultado), do: "estos estados", else: "este estado"
    "Todavía no se calcula #{@frase_modo[resultado["modo"]]} para #{estados}."
  end

  ## Lista, matriz y mapas (MapoWeb.Cotejo).

  defp columnas(resultado) do
    for {clave, corto, _} <- Cotejo.servicios(resultado["modo"]),
        s = Enum.find(resultado["servicios"], &(&1["clave"] == clave)) do
      %{clave: clave, corto: corto, titulo: s["titulo"], inactiva: !s["calculado"]}
    end
  end

  # `de` es "zona" o la clave de un municipio.
  defp celda(%{"calculado" => false}, _de, _umbral), do: Cotejo.celda_servicio(nil, nil, nil)
  defp celda(s, "zona", umbral), do: Cotejo.celda_servicio(s, umbral, s["grupo_etiqueta"])

  defp celda(s, de, umbral),
    do: Cotejo.celda_servicio(s["municipios"][de], umbral, s["grupo_etiqueta"])

  defp celdas(servicios, de, umbral),
    do: Map.new(servicios, &{&1["clave"], celda(&1, de, umbral)})

  defp filas(resultado, umbral, fijas) do
    zona = resultado["zona"]

    de_municipios =
      if varios?(resultado) do
        for m <- zona["municipios"] do
          %{
            id: m["cvegeo"],
            nombre: m["nombre"],
            nota: nil,
            gente: m["poblacion"],
            celdas: celdas(resultado["servicios"], m["cvegeo"], umbral)
          }
        end
      else
        []
      end

    fila = %{
      id: "zona",
      nombre: zona["nombre"],
      nota: if(varios?(resultado), do: "toda la zona"),
      gente: zona["poblacion"],
      celdas: celdas(resultado["servicios"], "zona", umbral)
    }

    # Las fijas guardan sus curvas: el umbral las mueve igual que a las demás.
    de_fijas =
      for f <- fijas, f.clave != zona["clave"] do
        %{
          id: "fija-#{:erlang.phash2(f.clave)}",
          nombre: f.nombre,
          nota: "fija",
          gente: f.gente,
          fija: f.clave,
          celdas: celdas(f.servicios, "zona", umbral)
        }
      end

    [fila | de_municipios] ++ de_fijas
  end

  defp varios?(resultado), do: match?([_, _ | _], resultado["zona"]["municipios"])

  # Varios municipios se comparan; uno solo se lee en lista.
  defp vista_inicial(nil), do: nil
  defp vista_inicial(resultado), do: if(varios?(resultado), do: "matriz", else: "lista")

  defp fija?(fijas, resultado), do: Enum.any?(fijas, &(&1.clave == resultado["zona"]["clave"]))

  defp ruta_mapa(consultada, umbral, servicio) do
    ~p"/mapa" <>
      "?" <>
      ZonaSelector.query(
        zona: consultada.zona,
        servicio: servicio,
        modo: consultada.modo,
        umbral: umbral,
        ver: "servicios"
      )
  end

  defp sin_calcular_por_que(%{"estados_sin_calcular" => [_ | _]} = s) do
    if s["solo_agebs"],
      do:
        "de un estado sin calcular, o localidades sin AGEB (DENUE casi no registra las escuelas del campo)",
      else: "de un estado que todavía no se calcula"
  end

  defp sin_calcular_por_que(_s),
    do: "localidades sin AGEB, porque DENUE casi no registra las escuelas del campo"

  defp porcentaje(%{con_ruta: 0}), do: ""

  defp porcentaje(%{fuera: f, con_ruta: c}),
    do: ", el #{cifra(f * 100 / c, 1)} % de #{cifra(c)} con ruta,"

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     assign(socket,
       page_title: "Servicios",
       zona: nil,
       modos: @modos,
       frase_modo: @frase_modo,
       max_minutos: 120,
       umbral: @umbral_inicial,
       servicio: nil,
       resultado: nil,
       error: nil,
       consultando: false,
       plegada: false,
       vista: nil,
       ajustes?: false,
       fijas: [],
       max_fijas: @max_fijas,
       form: formulario(%{}),
       consultada: nil,
       pedida: nil,
       citando: nil,
       citas: [],
       cita_enlace: nil
     )}
  end

  # Enlace permanente: zona, modo, umbral y servicio del plano. Cada valor pasa
  # por la misma validación que el formulario; uno raro deja la hoja vacía o
  # cae al valor inicial, sin error. Los de antes de la 29b traen `ent` y `mun`.
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
    with clave when is_binary(clave) <- clave_de_url(params),
         {:ok, zona} <- ZonaSelector.resolver(clave) do
      form = %{
        "modo" => if(params["modo"] in @modos_validos, do: params["modo"], else: "pie"),
        "umbral" =>
          case umbral(params["umbral"]) do
            {:ok, u} -> "#{u}"
            _ -> "#{@umbral_inicial}"
          end
      }

      socket
      |> assign(
        zona: zona,
        servicio: params["servicio"],
        vista: if(params["vista"] in @vistas, do: params["vista"])
      )
      |> push_event("zona_elegida", %{geojson: zona["geojson"]})
      |> consultar(form)
    else
      _ -> socket
    end
  end

  defp clave_de_url(%{"zona" => clave}) when is_binary(clave), do: clave

  defp clave_de_url(%{"ent" => e, "mun" => m}) when is_binary(e) and is_binary(m) do
    if String.match?(e, ~r/^\d{2}$/) and String.match?(m, ~r/^\d{3}$/), do: "mun:#{e}#{m}"
  end

  defp clave_de_url(_params), do: nil

  # La vista solo va si no es la que saldría sola.
  defp ruta(a) do
    params =
      [zona: a.consultada.zona, modo: a.consultada.modo, umbral: a.umbral] ++
        Enum.filter(
          [servicio: a.servicio, vista: a.vista != vista_inicial(a.resultado) && a.vista],
          fn {_k, v} -> v end
        )

    ~p"/accesibilidad" <> "?" <> ZonaSelector.query(params)
  end

  defp escribir_url(socket), do: push_patch(socket, to: ruta(socket.assigns), replace: true)

  defp formulario(params) do
    base = %{"modo" => "pie", "umbral" => "#{@umbral_inicial}"}
    to_form(Map.merge(base, Map.take(params, Map.keys(base))), as: "acc")
  end

  @impl true
  def handle_info({:zona_elegida, zona}, socket) do
    socket = assign(socket, zona: zona)
    {:noreply, consultar(socket, socket.assigns.form.params)}
  end

  @impl true
  def handle_event("cambiar", %{"acc" => params}, socket) do
    socket = assign(socket, form: formulario(params))
    a = socket.assigns

    cond do
      # Con una zona ya consultada, el modo vuelve a pedir (es una lectura de la
      # base) y el umbral solo vuelve a restar.
      not is_nil(a.consultada) and params["modo"] != a.consultada.modo and
        params["modo"] in @modos_validos and
          not a.consultando ->
        {:noreply, consultar(socket, params)}

      a.consultada ->
        case umbral(params["umbral"]) do
          {:ok, u} when u != a.umbral -> {:noreply, cambiar_umbral(socket, u)}
          _ -> {:noreply, socket}
        end

      true ->
        {:noreply, socket}
    end
  end

  def handle_event("plegar", _params, socket),
    do: {:noreply, assign(socket, plegada: !socket.assigns.plegada)}

  def handle_event("consultar", _params, %{assigns: %{consultando: true}} = socket),
    do: {:noreply, socket}

  def handle_event("consultar", %{"acc" => params}, socket),
    do: {:noreply, consultar(socket, params)}

  def handle_event("ajustar", _params, socket),
    do: {:noreply, assign(socket, ajustes?: !socket.assigns.ajustes?)}

  def handle_event("vista", %{"vista" => vista}, socket) when vista in @vistas do
    if socket.assigns.resultado,
      do: {:noreply, socket |> assign(vista: vista) |> escribir_url()},
      else: {:noreply, socket}
  end

  def handle_event("fijar", _params, %{assigns: a} = socket) do
    if a.resultado && not fija?(a.fijas, a.resultado) && length(a.fijas) < @max_fijas do
      zona = a.resultado["zona"]

      fija = %{
        clave: zona["clave"],
        nombre: zona["nombre"],
        gente: zona["poblacion"],
        servicios: Enum.map(a.resultado["servicios"], &Map.delete(&1, "municipios"))
      }

      {:noreply, assign(socket, fijas: a.fijas ++ [fija], ajustes?: true)}
    else
      {:noreply, socket}
    end
  end

  def handle_event("soltar", %{"clave" => clave}, socket),
    do: {:noreply, assign(socket, fijas: Enum.reject(socket.assigns.fijas, &(&1.clave == clave)))}

  def handle_event("ver", %{"clave" => clave}, socket) when is_binary(clave) do
    a = socket.assigns

    if a.resultado && calculado?(a.resultado, clave) do
      {:noreply,
       socket
       |> assign(servicio: clave, citando: nil)
       |> push_event("estilo", %{servicio: clave, umbral: a.umbral})
       |> escribir_url()}
    else
      {:noreply, socket}
    end
  end

  def handle_event("citar", %{"clave" => clave}, socket) when is_binary(clave) do
    a = socket.assigns

    cond do
      a.citando == clave ->
        {:noreply, assign(socket, citando: nil)}

      is_nil(a.resultado) or not calculado?(a.resultado, clave) ->
        {:noreply, socket}

      true ->
        enlace = Cita.enlace(ruta(%{a | servicio: clave}))

        {:noreply,
         assign(socket,
           citando: clave,
           citas: Cotejo.citas_servicio(a.resultado, clave, a.umbral, enlace),
           cita_enlace: enlace
         )}
    end
  end

  defp cambiar_umbral(socket, u) do
    a = socket.assigns

    socket
    |> assign(umbral: u, citando: nil)
    |> push_event("estilo", %{servicio: a.servicio, umbral: u})
    |> escribir_url()
  end

  defp consultar(socket, params) do
    socket = assign(socket, form: formulario(params))

    with {:ok, pedida} <- zona(socket.assigns.zona, params),
         {:ok, u} <- umbral(params["umbral"]),
         :ok <- limite(socket) do
      socket
      |> assign(consultando: true, error: nil, pedida: pedida, umbral: u)
      |> start_async(:accesibilidad, fn ->
        MapoCore.accesibilidad_zona(pedida.zona, pedida.modo)
      end)
    else
      {:error, mensaje} -> assign(socket, error: mensaje)
    end
  end

  @impl true
  def handle_async(:accesibilidad, {:ok, {:ok, resultado}}, socket) do
    a = socket.assigns
    calculados = for s <- resultado["servicios"], s["calculado"], do: s["clave"]
    servicio = if a.servicio in calculados, do: a.servicio, else: List.first(calculados)

    {:noreply,
     socket
     |> assign(
       consultando: false,
       resultado: resultado,
       consultada: a.pedida,
       servicio: servicio,
       vista: a.vista || vista_inicial(resultado),
       ajustes?: false,
       # Contadas con otro modo no se comparan.
       fijas:
         if(a.consultada == nil or a.consultada.modo == a.pedida.modo, do: a.fijas, else: []),
       citando: nil
     )
     |> push_event("zona", %{
       zona: resultado["zona"]["geojson"],
       limites: resultado["zona"]["limites"],
       plano: resultado["plano"],
       destinos: resultado["destinos"],
       titulos: Map.new(resultado["servicios"], &{&1["clave"], &1["titulo"]}),
       servicio: servicio,
       umbral: a.umbral
     })
     |> escribir_url()}
  end

  def handle_async(:accesibilidad, {:ok, {:error, {:status, 404, _}}}, socket),
    do:
      {:noreply,
       assign(socket, consultando: false, error: "Esa zona no toca nada cargado en Mapo.")}

  def handle_async(:accesibilidad, {:ok, {:error, {:status, 422, %{"detail" => d}}}}, socket)
      when is_binary(d),
      do: {:noreply, assign(socket, consultando: false, error: "La zona no sirve: #{d}.")}

  def handle_async(:accesibilidad, _resultado, socket) do
    {:noreply,
     assign(socket,
       consultando: false,
       error: "No se pudo consultar la zona. Inténtalo de nuevo en un momento."
     )}
  end

  defp calculado?(resultado, clave),
    do: Enum.any?(resultado["servicios"], &(&1["clave"] == clave and &1["calculado"]))

  defp zona(nil, _params), do: {:error, "Elige una zona."}

  defp zona(%{"clave" => clave}, params) do
    if params["modo"] in @modos_validos,
      do: {:ok, %{zona: clave, modo: params["modo"]}},
      else: {:error, "Elige cómo se llega."}
  end

  defp umbral(valor) when is_binary(valor) do
    case Integer.parse(valor) do
      {u, ""} when u >= 1 and u <= 120 -> {:ok, u}
      _ -> {:error, "Los minutos van de 1 a 120."}
    end
  end

  defp umbral(_), do: {:error, "Los minutos van de 1 a 120."}

  defp limite(socket) do
    if Limite.permitir?(
         {:accesibilidad, socket.assigns.current_scope.user.id},
         @max_consultas,
         @ventana
       ),
       do: :ok,
       else: {:error, "Llevas #{@max_consultas} consultas en una hora. Espera un poco."}
  end
end
