defmodule MapoWeb.PerfilLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.MapoCore

  # Sobre el plano del municipio quedan cinco documentos, uno por enfoque y
  # cada uno con su piel (docs/arquitectura/decisiones.md, "Concepto
  # visual"). Nada se resume en un puntaje: cada documento dice su cifra, su
  # fuente y lo que no sabe. La consulta va en la URL para poder compartirla.

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="perfil" amplio?={true}>
      <:membrete><span class="mano">Perfil de zona</span></:membrete>

      <div :if={@plano} class="plano" aria-hidden="true">
        <svg viewBox={@plano.caja} preserveAspectRatio="xMidYMid slice">
          <path
            d={@plano.d}
            fill="none"
            stroke="currentColor"
            stroke-width="1"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </div>

      <.form
        for={@form}
        id="perfil_form"
        phx-change="cambiar_ubicacion"
        phx-submit="ver_perfil"
        class="consulta pegado"
      >
        <h1>{@lugar || "Elige un municipio"}</h1>
        <div class="ubicacion">
          <.input
            field={@form[:cve_ent]}
            type="select"
            options={@estados}
            prompt="Estado"
            class="membrete-select"
            aria-label="Estado"
          /> <span aria-hidden="true">/</span>
          <.input
            field={@form[:cve_mun]}
            type="select"
            options={@municipios}
            prompt="Municipio"
            class="membrete-select"
            aria-label="Municipio"
          />
        </div>
        <.button class="boton primario" phx-disable-with="Consultando...">Ver perfil</.button>
        <p>
          Cinco documentos, uno por enfoque. Ninguno se resume en un puntaje. Si una fuente no
          cubre el municipio, el documento lo dice.
        </p>
        <p :if={@estados == []} class="aviso">
          No se pudo cargar la lista de estados: mapo_core no responde o todavía no hay estados
          descargados.
        </p>
      </.form>

      <p :if={@consultando} class="consultando pegado sin-cinta">
        Consultando las cinco fuentes, tarda unos segundos.
      </p>

      <div :if={@perfil} class="documentos">
        <.cedula datos={@perfil["demografia"]} />
        <.libro datos={@perfil["comercio"]} />
        <.ticket datos={@perfil["consumo"]} />
        <.expediente datos={@perfil["seguridad"]} />
        <.tarjeta datos={@perfil["laboral"]} />
      </div>
    </Layouts.app>
    """
  end

  attr :datos, :map

  defp cedula(assigns) do
    assigns = assign(assigns, reparto: reparto(assigns.datos))

    ~H"""
    <article class="documento pegado d-demografia" data-piel="demografia" aria-labelledby="t-dem">
      <header>
        <h2 id="t-dem">Población</h2>
        <span class="tipo">Cédula censal</span>
      </header>
      <dl :if={@datos} class="casillas">
        <div class="casilla ancha">
          <dt>Población total</dt>
          <dd>{dato(@datos["pobtot"])}</dd>
          <div
            :if={@reparto}
            class="reparto"
            role="img"
            aria-label={"Mujeres #{cifra(@reparto)} por ciento, hombres #{cifra(100 - @reparto)} por ciento"}
          >
            <span style={"width: #{@reparto}%"}></span><span class="flex-1"></span>
          </div>
        </div>
        <div class="casilla">
          <dt>Mujeres</dt>
          <dd>{dato(@datos["pobfem"])}</dd>
        </div>
        <div class="casilla">
          <dt>Hombres</dt>
          <dd>{dato(@datos["pobmas"])}</dd>
        </div>
        <div class="casilla">
          <dt>Escolaridad promedio</dt>
          <dd>{dato(@datos["graproes"], 2)} años</dd>
        </div>
        <div class="casilla">
          <dt>Económicamente activa</dt>
          <dd>{dato(@datos["pea"])}</dd>
        </div>
        <div class="casilla">
          <dt>Ocupada</dt>
          <dd>{dato(@datos["pocupada"])}</dd>
        </div>
        <div class="casilla">
          <dt>Desocupada</dt>
          <dd>{dato(@datos["pdesocup"])}</dd>
        </div>
        <div class="casilla">
          <dt>Hogares</dt>
          <dd>{dato(@datos["tothog"])}</dd>
        </div>
        <div class="casilla">
          <dt>Viviendas</dt>
          <dd>{dato(@datos["vivtot"])}</dd>
        </div>
      </dl>
      <p :if={!@datos} class="falta">El censo no tiene datos de este municipio.</p>
      <p class="fuente">INEGI · Censo de Población y Vivienda 2020</p>
    </article>
    """
  end

  attr :datos, :map

  defp libro(assigns) do
    assigns =
      assign(assigns,
        total: assigns.datos["total_negocios"] || 0,
        clases: assigns.datos["top_clases_actividad"] || []
      )

    assigns =
      assign(assigns, resto: assigns.total - Enum.sum(Enum.map(assigns.clases, &List.last/1)))

    ~H"""
    <article class="documento pegado d-comercio" data-piel="comercio" aria-labelledby="t-com">
      <header>
        <h2 id="t-com">Negocios por giro</h2>
        <span class="tipo">Libro mayor</span>
      </header>
      <table :if={@total > 0} class="libro">
        <thead>
          <tr>
            <th>Clase de actividad</th>
            <th class="n">Negocios</th>
            <th class="n">del total</th>
          </tr>
        </thead>
        <tbody>
          <tr :for={[clase, n] <- @clases}>
            <td>{clase}</td>
            <td class="n">{cifra(n)}</td>
            <td class="n">{cifra(n / @total * 100)}%</td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="resto">
            <td>Las demás clases</td>
            <td class="n">{cifra(@resto)}</td>
            <td class="n">{cifra(@resto / @total * 100)}%</td>
          </tr>
          <tr class="total">
            <td>Total registrado</td>
            <td class="n">{cifra(@total)}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
      <p :if={@total == 0} class="falta">El DENUE no registra negocios en este municipio.</p>
      <p class="fuente">INEGI · DENUE</p>
    </article>
    """
  end

  attr :datos, :map

  defp ticket(assigns) do
    ~H"""
    <article class="documento pegado d-consumo" data-piel="consumo" aria-labelledby="t-con">
      <header>
        <span class="tipo">Ticket de caja</span>
        <h2 id="t-con">Gasto de los hogares</h2>
      </header>
      <%= if @datos do %>
        <p>Gasto {@datos["periodo"]} promedio por hogar</p>
        <p class="grande num">${dato(@datos["promedio_ponderado"], 2)}</p>
        <div class="renglon">
          <span>Mediana</span><span></span><b class="num">${dato(@datos["mediana"], 2)}</b>
        </div>
        <div class="renglon">
          <span>Hogares en la muestra</span><span></span>
          <b class="num">{dato(@datos["n_hogares_muestra"])}</b>
        </div>
        <hr />
        <p class="falta">
          La ENIGH no es representativa por municipio, solo por estado. Úsalo como referencia
          regional.
        </p>
      <% else %>
        <p class="falta">La muestra de la ENIGH no llegó a este municipio.</p>
      <% end %>
      <p class="fuente">INEGI · ENIGH</p>
      <div class="dientes" aria-hidden="true"></div>
    </article>
    """
  end

  attr :datos, :map

  defp expediente(assigns) do
    tipos = (assigns.datos && assigns.datos["por_tipo"]) || []

    assigns =
      assign(assigns,
        tipos: tipos,
        maximo: tipos |> Enum.map(&List.last/1) |> Enum.max(fn -> 0 end)
      )

    ~H"""
    <article class="documento pegado d-seguridad" data-piel="seguridad" aria-labelledby="t-seg">
      <span class="pestana-carpeta">SESNSP{@datos && " · #{@datos["anio"]}"}</span>
      <header>
        <h2 id="t-seg">Incidencia delictiva</h2>
        <span class="tipo">Expediente</span>
      </header>
      <%= if @datos do %>
        <p>
          <span class="num total">{dato(@datos["total_delitos"])}</span>
          delitos registrados en {@datos["anio"]}
        </p>
        <.barras tipos={Enum.take(@tipos, 8)} maximo={@maximo} />
        <details :if={length(@tipos) > 8}>
          <summary>Ver los {length(@tipos)} tipos, incluidos los de cero</summary>
          <.barras tipos={Enum.drop(@tipos, 8)} maximo={@maximo} />
        </details>
      <% else %>
        <p class="falta">
          No hay incidencia del SESNSP cargada para este municipio. La fuente se carga a mano.
        </p>
      <% end %>
      <p class="fuente">SESNSP · incidencia del fuero común, carga manual</p>
    </article>
    """
  end

  attr :tipos, :list
  attr :maximo, :integer

  defp barras(assigns) do
    ~H"""
    <ul class="barras">
      <li :for={[tipo, n] <- @tipos}>
        <span>{tipo}</span>
        <span class="barra" style={"width: #{if @maximo > 0, do: n / @maximo * 100, else: 0}%"}></span>
        <span class="num">{cifra(n)}</span>
      </li>
    </ul>
    """
  end

  attr :datos, :map

  defp tarjeta(assigns) do
    ~H"""
    <article class="documento pegado d-laboral" data-piel="laboral" aria-labelledby="t-lab">
      <header>
        <h2 id="t-lab">Desocupación</h2>
        <span class="tipo">Tarjeta de checador</span>
      </header>
      <%= if @datos do %>
        <p class="sello num">{dato(@datos["tasa_desocupacion"], 2)}%</p>
        <dl>
          <dt>Periodo</dt>
          <dd>{trimestre(@datos["trimestre"])} trimestre de {@datos["anio"]}</dd>
          <dt :if={@datos["pea_ponderada"]}>Población activa del estado</dt>
          <dd :if={@datos["pea_ponderada"]}>{cifra(@datos["pea_ponderada"])}</dd>
        </dl>
        <p class="falta">
          Cifra del estado entero. La ENOE no es representativa por municipio.
        </p>
      <% else %>
        <p class="falta">No hay datos de la ENOE cargados para este estado.</p>
      <% end %>
      <p class="fuente">INEGI · ENOE</p>
    </article>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    estados =
      case MapoCore.estados() do
        {:ok, %{"features" => features}} -> opciones_estados(features)
        {:error, _} -> []
      end

    {:ok,
     assign(socket,
       page_title: "Perfil de zona",
       estados: estados,
       municipios: [],
       form: to_form(%{"cve_ent" => "", "cve_mun" => ""}, as: "perfil"),
       lugar: nil,
       perfil: nil,
       plano: nil,
       consultando: false
     )}
  end

  @impl true
  def handle_params(%{"cve_ent" => cve_ent, "cve_mun" => cve_mun}, _uri, socket)
      when cve_ent != "" and cve_mun != "" do
    {:noreply, consultar(socket, cve_ent, cve_mun)}
  end

  def handle_params(_params, _uri, socket), do: {:noreply, socket}

  @impl true
  def handle_event("cambiar_ubicacion", %{"perfil" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "perfil"))}
  end

  def handle_event(
        "ver_perfil",
        %{"perfil" => %{"cve_ent" => cve_ent, "cve_mun" => cve_mun}},
        socket
      ) do
    if cve_ent in [nil, ""] or cve_mun in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado y un municipio primero.")}
    else
      {:noreply, push_patch(socket, to: ~p"/perfil?#{[cve_ent: cve_ent, cve_mun: cve_mun]}")}
    end
  end

  @impl true
  def handle_async(:perfil, {:ok, {:ok, perfil}}, socket) do
    {:noreply, assign(socket, perfil: perfil, consultando: false)}
  end

  def handle_async(:perfil, _fallo, socket) do
    {:noreply,
     socket
     |> assign(consultando: false)
     |> put_flash(:error, "mapo_core no está disponible ahorita mismo, intenta de nuevo.")}
  end

  # El plano es fondo: si falla, la mesa se queda lisa.
  def handle_async(:plano, {:ok, {:ok, coleccion}}, socket) do
    {:noreply, assign(socket, plano: plano(coleccion))}
  end

  def handle_async(:plano, _fallo, socket), do: {:noreply, socket}

  defp consultar(socket, cve_ent, cve_mun) do
    municipios =
      if cve_ent == socket.assigns.form[:cve_ent].value and socket.assigns.municipios != [],
        do: socket.assigns.municipios,
        else: municipios_de(cve_ent)

    socket =
      assign(socket,
        municipios: municipios,
        form: to_form(%{"cve_ent" => cve_ent, "cve_mun" => cve_mun}, as: "perfil")
      )

    case {nombre_en(socket.assigns.estados, cve_ent), nombre_en(municipios, cve_mun)} do
      {estado, municipio} when is_binary(estado) and is_binary(municipio) ->
        socket
        |> assign(
          page_title: "Perfil de #{municipio}",
          lugar: "#{municipio}, #{estado}",
          perfil: nil,
          plano: nil,
          consultando: true
        )
        |> start_async(:perfil, fn -> MapoCore.perfil_zona(cve_ent, cve_mun) end)
        |> start_async(:plano, fn -> MapoCore.agebs(cve_ent, cve_mun) end)

      _ ->
        put_flash(socket, :error, "Ese municipio no está en el catálogo.")
    end
  end

  # Los AGEB del municipio como un solo trazo SVG. Se escala la longitud por
  # el coseno de la latitud para que el plano no salga estirado.
  defp plano(%{"features" => features}) do
    anillos = Enum.flat_map(features, &anillos(&1["geometry"]))
    puntos = Enum.concat(anillos)

    if puntos == [] do
      nil
    else
      {x0, x1} = puntos |> Enum.map(&Enum.at(&1, 0)) |> Enum.min_max()
      {y0, y1} = puntos |> Enum.map(&Enum.at(&1, 1)) |> Enum.min_max()
      k = :math.cos((y0 + y1) / 2 * :math.pi() / 180) * 10_000
      ancho = round((x1 - x0) * k)
      alto = round((y1 - y0) * 10_000)

      d =
        Enum.map_join(anillos, fn anillo ->
          "M" <>
            Enum.map_join(anillo, "L", fn [x, y | _] ->
              "#{round((x - x0) * k)},#{round((y1 - y) * 10_000)}"
            end) <> "Z"
        end)

      %{caja: "-200 -200 #{ancho + 400} #{alto + 400}", d: d}
    end
  end

  defp anillos(%{"type" => "Polygon", "coordinates" => anillos}), do: anillos

  defp anillos(%{"type" => "MultiPolygon", "coordinates" => poligonos}),
    do: Enum.concat(poligonos)

  defp anillos(_), do: []

  defp reparto(%{"pobfem" => fem, "pobtot" => tot})
       when is_number(fem) and is_number(tot) and tot > 0,
       do: fem / tot * 100

  defp reparto(_), do: nil

  defp dato(v, decimales \\ nil)
  defp dato(nil, _), do: "sin dato"
  defp dato(v, nil), do: cifra(v)
  defp dato(v, decimales), do: cifra(v, decimales)

  defp trimestre(t),
    do:
      Map.get(
        %{"trim1" => "primer", "trim2" => "segundo", "trim3" => "tercer", "trim4" => "cuarto"},
        t,
        t
      )

  defp nombre_en(opciones, clave),
    do: Enum.find_value(opciones, fn {nombre, c} -> c == clave && nombre end)

  defp municipios_de(cve_ent) when cve_ent in [nil, ""], do: []

  defp municipios_de(cve_ent) do
    case MapoCore.municipios(cve_ent) do
      {:ok, %{"features" => features}} -> opciones_municipios(features)
      {:error, _} -> []
    end
  end

  defp opciones_estados(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cvegeo"]} end)
    |> Enum.sort()
  end

  defp opciones_municipios(features) do
    features
    |> Enum.map(fn %{"properties" => props} -> {props["nomgeo"], props["cve_mun"]} end)
    |> Enum.sort()
  end
end
