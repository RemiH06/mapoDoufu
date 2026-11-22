defmodule MapoWeb.AccesibilidadLive.Index do
  @moduledoc """
  Accesibilidad a servicios: en un municipio, cuánta gente vive a más de N
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
        aria-label="Plano del municipio por minutos al servicio elegido"
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
          <h1 id="t-hoja">Servicios del municipio</h1>

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

          <.form for={@form} id="accesibilidad_form" phx-change="cambiar" phx-submit="consultar">
            <.input
              field={@form[:cve_ent]}
              type="select"
              label="Estado"
              prompt="Elige un estado"
              options={@estados}
            />
            <.input
              :if={@municipios != []}
              field={@form[:cve_mun]}
              type="select"
              label="Municipio"
              prompt="Elige un municipio"
              options={@municipios}
            /> <.input field={@form[:modo]} type="select" label="Cómo se llega" options={@modos} />
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
                {if @consultando, do: "Consultando...", else: "Consultar el municipio"}
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
                      do: "localidad",
                      else: "localidades"} sin AGEB: no se calculan, porque DENUE casi no registra las escuelas del campo.
                  </li>

                  <li :if={s["reservados"] > 0}>
                    INEGI reserva el dato en {cifra(s["reservados"])} {if s["reservados"] == 1,
                      do: "lugar",
                      else: "lugares"} con pocas viviendas: no se cuentan como cero.
                  </li>

                  <li>
                    {cifra(s["destinos_zona"])} en el municipio, {cifra(s["destinos_estado"])} en el estado.
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
                  Ningún GTFS cargado tiene paradas en este municipio: no se calcula. Fuera de las ciudades con GTFS sí hay camiones, pero nadie publica sus paradas.
                </p>

                <p :if={!s["sin_cobertura"]} class="secundario">
                  Todavía no se calcula {@frase_modo[@resultado["modo"]]} para este estado.
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

  defp porcentaje(%{con_ruta: 0}), do: ""

  defp porcentaje(%{fuera: f, con_ruta: c}),
    do: ", el #{cifra(f * 100 / c, 1)} % de #{cifra(c)} con ruta,"

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

    {:ok,
     assign(socket,
       page_title: "Servicios",
       estados: estados,
       municipios: [],
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

  # Enlace permanente: municipio, modo, umbral y servicio del plano. Cada valor
  # pasa por la misma validación que el formulario; uno raro deja la hoja vacía
  # o cae al valor inicial, sin error.
  @impl true
  def handle_params(params, _uri, socket) do
    if connected?(socket) and is_nil(socket.assigns.consultada) and params != %{} do
      {:noreply, consultar_de_url(socket, params)}
    else
      {:noreply, socket}
    end
  end

  defp consultar_de_url(socket, %{"ent" => ent, "mun" => mun} = params)
       when is_binary(ent) and is_binary(mun) do
    municipios =
      if Enum.any?(socket.assigns.estados, fn {_, c} -> c == ent end),
        do: municipios_de(ent),
        else: []

    if Enum.any?(municipios, fn {_, c} -> c == mun end) do
      form = %{
        "cve_ent" => ent,
        "cve_mun" => mun,
        "modo" => if(params["modo"] in @modos_validos, do: params["modo"], else: "pie"),
        "umbral" =>
          case umbral(params["umbral"]) do
            {:ok, u} -> "#{u}"
            _ -> "#{@umbral_inicial}"
          end
      }

      socket
      |> assign(municipios: municipios, servicio: params["servicio"])
      |> consultar(form)
    else
      socket
    end
  end

  defp consultar_de_url(socket, _params), do: socket

  defp ruta(%{cve_ent: e, cve_mun: m, modo: modo}, umbral, servicio) do
    params =
      [ent: e, mun: m, modo: modo, umbral: umbral] ++
        if(servicio, do: [servicio: servicio], else: [])

    ~p"/accesibilidad" <> "?" <> URI.encode_query(params)
  end

  defp formulario(params) do
    base = %{"cve_ent" => "", "cve_mun" => "", "modo" => "pie", "umbral" => "#{@umbral_inicial}"}
    to_form(Map.merge(base, Map.take(params, Map.keys(base))), as: "acc")
  end

  @impl true
  def handle_event("cambiar", %{"acc" => params}, socket) do
    anterior = socket.assigns.form.params

    {params, socket} =
      if params["cve_ent"] != anterior["cve_ent"],
        do:
          {Map.put(params, "cve_mun", ""),
           assign(socket, municipios: municipios_de(params["cve_ent"]))},
        else: {params, socket}

    socket = assign(socket, form: formulario(params))
    a = socket.assigns

    cond do
      # Con un municipio ya consultado, el modo vuelve a pedir (es una lectura de
      # la base) y el umbral solo vuelve a restar.
      not is_nil(a.consultada) and params["modo"] != a.consultada.modo and
        params["modo"] in @modos_validos and
          not a.consultando ->
        {:noreply,
         consultar(
           socket,
           Map.merge(params, %{
             "cve_ent" => a.consultada.cve_ent,
             "cve_mun" => a.consultada.cve_mun
           })
         )}

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

    with {:ok, zona} <- zona(params),
         {:ok, u} <- umbral(params["umbral"]),
         :ok <- limite(socket) do
      socket
      |> assign(consultando: true, error: nil, pedida: zona, umbral: u)
      |> start_async(:accesibilidad, fn ->
        MapoCore.accesibilidad_zona(zona.cve_ent, zona.cve_mun, zona.modo)
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
       assign(socket, consultando: false, error: "Ese municipio no está cargado en Mapo.")}

  def handle_async(:accesibilidad, _resultado, socket) do
    {:noreply,
     assign(socket,
       consultando: false,
       error: "No se pudo consultar el municipio. Inténtalo de nuevo en un momento."
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

  defp zona(params) do
    e = params["cve_ent"] || ""
    m = params["cve_mun"] || ""

    cond do
      not (String.match?(e, ~r/^\d{2}$/) and String.match?(m, ~r/^\d{3}$/)) ->
        {:error, "Elige un estado y un municipio."}

      params["modo"] not in @modos_validos ->
        {:error, "Elige cómo se llega."}

      true ->
        {:ok, %{cve_ent: e, cve_mun: m, modo: params["modo"]}}
    end
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

  defp municipios_de(cve_ent) when cve_ent in [nil, ""], do: []

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
