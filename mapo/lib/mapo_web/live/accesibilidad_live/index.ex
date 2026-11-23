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

  alias Mapo.Limite
  alias Mapo.MapoCore
  alias MapoWeb.Cita
  alias MapoWeb.ZonaSelector

  @max_consultas 60
  @ventana 3600
  @umbral_inicial 15
  @modos [{"A pie", "pie"}, {"En auto", "auto"}]
  @modos_validos Enum.map(@modos, &elem(&1, 1))
  @frase_modo %{"pie" => "a pie", "auto" => "en auto"}

  # De dónde salen los destinos de cada servicio (docs/producto/citar.md).
  @fuente_destinos %{
    "centro_salud" => "clues",
    "umf_imss" => "clues",
    "hospital_publico" => "clues",
    "transporte_masivo" => "osm"
  }

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
        class="plano-gl flex-1 min-h-0 w-full"
        role="region"
        aria-label="Plano de la zona por minutos al servicio elegido"
      >
      </div>
      <%!-- Misma hoja que /riesgos: comparten la forma de una consulta por zona. --%>
      <section
        id="hoja"
        class={["hoja pegado riesgos", @plegada && "plegada"]}
        data-piel="laboral"
        aria-labelledby="t-hoja"
      >
        <div class="hoja-cab">
          <h1 id="t-hoja">Servicios de la zona</h1>

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
          <p class="pista">
            Cada servicio va por separado, con la gente que lo usa: aquí no hay índice. Los minutos son por calle, sin tráfico.
          </p>

          <.live_component module={ZonaSelector} id="zona" zona={@zona} scope={@current_scope} />

          <.form for={@form} id="accesibilidad_form" phx-change="cambiar" phx-submit="consultar">
            <.input field={@form[:modo]} type="select" label="Cómo se llega" options={@modos} />
            <.input
              field={@form[:umbral]}
              type="number"
              min="1"
              max={@max_minutos}
              step="1"
              label="Contar como lejos a más de (minutos)"
            />
            <div class="botones">
              <.button variant="primary" phx-disable-with="Consultando..." disabled={@consultando}>
                {if @consultando, do: "Consultando...", else: "Consultar la zona"}
              </.button>
            </div>
          </.form>

          <p :if={@error} class="aviso" role="alert">{@error}</p>

          <div :if={@resultado} id="accesibilidad-resultado" class="riesgos-resultado">
            <p class="secundario">
              {@resultado["zona"]["nombre"]}: {cifra(@resultado["agebs"])} AGEB urbanos y {cifra(
                @resultado["lugares"] - @resultado["agebs"]
              )} localidades sin AGEB, {@frase_modo[@resultado["modo"]]}.
            </p>

            <article
              :for={s <- @resultado["servicios"]}
              id={"servicio-#{s["clave"]}"}
              class={["bloque", @servicio == s["clave"] && "activo"]}
            >
              <h2>{s["titulo"]}</h2>

              <%= if s["calculado"] do %>
                <% r = resumen(s, @umbral) %>
                <p class="procedencia">{s["fuente"]}</p>

                <p class="cerca">
                  <span class="num">{cifra(r.fuera)}</span> {s["grupo_etiqueta"]}{porcentaje(r)} viven a más de {@umbral} minutos {@frase_modo[
                    @resultado["modo"]
                  ]}.
                </p>

                <ul>
                  <li>
                    <span class="num">{cifra(r.dentro)}</span> a {@umbral} minutos o menos.
                  </li>

                  <li :if={s["sin_ruta"] > 0}>
                    <span class="num">{cifra(s["sin_ruta"])}</span>
                    sin ruta por calle a los más cercanos: no se cuentan ni cerca ni lejos.
                  </li>

                  <li :if={(s["sin_calcular_lugares"] || 0) > 0}>
                    <span class="num">{cifra(s["sin_calcular"])}</span>
                    viven en {cifra(s["sin_calcular_lugares"])} {if s["sin_calcular_lugares"] == 1,
                      do: "lugar que no se calcula",
                      else: "lugares que no se calculan"}: {sin_calcular_por_que(s)}.
                  </li>

                  <li :if={s["reservados"] > 0}>
                    INEGI reserva el dato en {cifra(s["reservados"])} {if s["reservados"] == 1,
                      do: "lugar",
                      else: "lugares"} con pocas viviendas: no se cuentan como cero.
                  </li>

                  <li>
                    {cifra(s["destinos_zona"])} en la zona, {cifra(s["destinos_estado"])} en {if length(
                                                                                                   @resultado[
                                                                                                     "zona"
                                                                                                   ][
                                                                                                     "estados"
                                                                                                   ]
                                                                                                 ) >
                                                                                                   1,
                                                                                                 do:
                                                                                                   "los estados",
                                                                                                 else:
                                                                                                   "el estado"}.
                  </li>
                </ul>

                <p class="metodo">
                  Red: {s["red"]}. Método: {s["metodo"]} Calculado el {s["fecha"]}.
                </p>

                <div class="cinta-citar">
                  <button
                    type="button"
                    id={"ver-#{s["clave"]}"}
                    class="enlace"
                    phx-click="ver"
                    phx-value-servicio={s["clave"]}
                    aria-pressed={to_string(@servicio == s["clave"])}
                  >
                    {if @servicio == s["clave"], do: "En el plano", else: "Ver en el plano"}
                  </button>

                  <button
                    type="button"
                    id={"citar-#{s["clave"]}"}
                    class="enlace"
                    phx-click="citar"
                    phx-value-clave={s["clave"]}
                    aria-expanded={to_string(@citando == s["clave"])}
                  >
                    {if @citando == s["clave"], do: "Cerrar la cita", else: "Cómo citar"}
                  </button>

                  <Cita.como_citar
                    :if={@citando == s["clave"]}
                    id={"cita-#{s["clave"]}"}
                    citas={@citas}
                    enlace={@cita_enlace}
                  />
                </div>
              <% else %>
                <p :if={s["sin_cobertura"]} class="secundario">
                  Ningún GTFS cargado tiene paradas en los municipios de esta zona: no se calcula. Fuera de las ciudades con GTFS sí hay camiones, pero nadie publica sus paradas.
                </p>

                <p :if={!s["sin_cobertura"]} class="secundario">
                  Todavía no se calcula {@frase_modo[@resultado["modo"]]} para {if length(
                                                                                     @resultado[
                                                                                       "zona"
                                                                                     ]["estados"]
                                                                                   ) > 1,
                                                                                   do:
                                                                                     "estos estados",
                                                                                   else: "este estado"}.
                </p>
              <% end %>
            </article>
          </div>
        </div>
      </section>
    </Layouts.app>
    """
  end

  @doc false
  # Lo que se lee de un servicio con el umbral elegido: `dentro[m]` es la gente a
  # m minutos o menos, y la gente sin ruta no cuenta ni cerca ni lejos.
  def resumen(s, umbral) do
    dentro = Enum.at(s["dentro"], min(umbral, length(s["dentro"]) - 1))
    con_ruta = s["total"] - s["sin_ruta"]
    %{dentro: dentro, fuera: con_ruta - dentro, con_ruta: con_ruta}
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
      |> assign(zona: zona, servicio: params["servicio"])
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

  defp ruta(%{zona: clave, modo: modo}, umbral, servicio) do
    params =
      [zona: clave, modo: modo, umbral: umbral] ++
        if(servicio, do: [servicio: servicio], else: [])

    ~p"/accesibilidad" <> "?" <> ZonaSelector.query(params)
  end

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

  def handle_event("ver", %{"servicio" => clave}, socket) when is_binary(clave) do
    a = socket.assigns

    if a.resultado && calculado?(a.resultado, clave) do
      {:noreply,
       socket
       |> assign(servicio: clave)
       |> push_event("estilo", %{servicio: clave, umbral: a.umbral})
       |> push_patch(to: ruta(a.consultada, a.umbral, clave), replace: true)}
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
        enlace = Cita.enlace(ruta(a.consultada, a.umbral, clave))

        {:noreply,
         assign(socket,
           citando: clave,
           citas: citas(a.resultado, clave, a.umbral, enlace),
           cita_enlace: enlace
         )}
    end
  end

  defp cambiar_umbral(socket, u) do
    a = socket.assigns

    socket
    |> assign(umbral: u, citando: nil)
    |> push_event("estilo", %{servicio: a.servicio, umbral: u})
    |> push_patch(to: ruta(a.consultada, u, a.servicio), replace: true)
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
       citando: nil
     )
     |> push_event("zona", %{
       zona: resultado["zona"]["geojson"],
       plano: resultado["plano"],
       destinos: resultado["destinos"],
       titulos: Map.new(resultado["servicios"], &{&1["clave"], &1["titulo"]}),
       servicio: servicio,
       umbral: a.umbral
     })
     |> push_patch(to: ruta(a.pedida, a.umbral, servicio), replace: true)}
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

  defp citas(resultado, clave, umbral, enlace) do
    s = Enum.find(resultado["servicios"], &(&1["clave"] == clave))
    modo = @frase_modo[resultado["modo"]]
    lugar = resultado["zona"]["nombre"]
    version = "calculado el #{s["fecha"]}"

    que = "#{s["titulo"]}: #{s["grupo_etiqueta"]} a más de #{umbral} minutos #{modo}, #{lugar}"

    destinos =
      case s["feeds"] do
        [_ | _] = feeds ->
          for f <- feeds,
              do:
                Cita.gtfs(f,
                  que: que,
                  datos: "frecuencias del #{f["fecha_ref"]}",
                  version: version,
                  enlace: enlace
                )

        _ ->
          [
            Cita.armar(@fuente_destinos[clave] || "denue",
              que: que,
              version: version,
              enlace: enlace
            )
          ]
      end

    destinos ++
      [
        Cita.armar("censo",
          que: "#{s["grupo_etiqueta"]} por AGEB urbano y localidad, #{lugar}",
          datos: "2020",
          enlace: enlace
        ),
        Cita.armar("osm",
          que: "minutos #{modo} por calle; #{s["red"]}",
          version: version,
          enlace: enlace
        )
      ]
  end

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
