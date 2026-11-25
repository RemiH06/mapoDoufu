defmodule MapoWeb.PerfilLive.Index do
  @moduledoc """
  Perfil de una zona de la zona común (un estado, municipios, una metrópoli, una
  colonia, un CP o un dibujo): el plano con la gente por AGEB, ocho papeles, uno
  por enfoque y cada uno con su piel, su fuente y su nivel, y las zonas que se le
  parecen. Nada se resume en un puntaje. La zona y la búsqueda de parecidos van
  en la URL. Ver docs/producto/perfil.md.

  Cada papel lleva al pie las notas del equipo sobre esa zona (`Mapo.Notas`): a
  mano y en lápiz, separadas de lo impreso, y en vivo con quien tenga abierto el
  mismo perfil con el mismo equipo.
  """

  use MapoWeb, :live_view

  alias Mapo.Limite
  alias Mapo.MapoCore
  alias Mapo.Notas
  alias Mapo.Teams
  alias MapoWeb.PerfilDocumentos
  alias MapoWeb.PerfilSimilares
  alias MapoWeb.ZonaSelector

  @max_consultas 60
  @ventana 3600
  @filtro %{areas: [], margen: "cerca", donde: "todo"}

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="perfil" amplio?={true}>
      <:membrete><span class="mano">Perfil de zona</span></:membrete>

      <section class="perfil-cabeza pegado" aria-labelledby="t-perfil">
        <div class="perfil-quien">
          <h1 id="t-perfil">{if @zona, do: @zona["nombre"], else: "Elige una zona"}</h1>

          <.live_component
            module={ZonaSelector}
            id="zona"
            zona={@zona}
            scope={@current_scope}
          />

          <div :if={@perfil} id="perfil-portada">
            <PerfilDocumentos.portada perfil={@perfil} />
          </div>

          <p :if={@consultando} class="consultando" role="status">
            Consultando las fuentes, tarda unos segundos.
          </p>
          <p :if={@error} class="aviso" role="alert">{@error}</p>

          <p :if={is_nil(@zona)} class="falta">
            Un estado, un municipio o varios, una metrópoli, una colonia o lo que dibujes en el plano. Ocho documentos, uno por enfoque; ninguno se resume en un puntaje.
          </p>

          <nav :if={@perfil} class="perfil-ir" aria-label="Esta zona en otras vistas">
            <.link id="ir-mapa" navigate={ruta_en("/mapa", @zona)}>En el mapa</.link>
            <.link id="ir-riesgos" navigate={ruta_en("/riesgos", @zona)}>Riesgos</.link>
            <.link id="ir-servicios" navigate={ruta_en("/accesibilidad", @zona)}>Servicios</.link>
          </nav>

          <form :if={length(@equipos) > 1} id="equipo-form" phx-change="equipo" class="notas-de">
            <label>
              <span>Notas de</span>
              <select name="equipo" class="membrete-select">
                {Phoenix.HTML.Form.options_for_select(
                  Enum.map(@equipos, &{&1.name, &1.id}),
                  @equipo_id
                )}
              </select>
            </label>
          </form>
        </div>

        <div
          id="perfil-map"
          phx-hook="PerfilMapa"
          phx-update="ignore"
          class="plano-gl perfil-plano"
          role="region"
          aria-label="Plano de la zona con la gente que vive por kilómetro cuadrado"
        >
        </div>
      </section>

      <nav :if={@perfil} class="perfil-indice" aria-label="Documentos del perfil">
        <a :for={{clave, titulo, _, _} <- PerfilDocumentos.documentos()} href={"#doc-#{clave}"}>
          {titulo}
        </a>
        <a href="#similares">Zonas que se parecen</a>
      </nav>

      <div :if={@consultando and is_nil(@perfil)} class="documentos" aria-hidden="true">
        <article
          :for={{clave, titulo, tipo, piel} <- PerfilDocumentos.documentos()}
          class={"documento pegado esqueleto d-#{clave}"}
          data-piel={piel}
        >
          <header>
            <h2>{titulo}</h2>
            <span class="tipo">{tipo}</span>
          </header>
          <span :for={_ <- 1..4} class="renglon-vacio"></span>
        </article>
      </div>

      <div :if={@perfil} class="documentos" id="documentos">
        <PerfilDocumentos.cedula perfil={@perfil}>
          <.notas_de documento="demografia" {notas(assigns)} />
        </PerfilDocumentos.cedula>
        <PerfilDocumentos.ficha_obra perfil={@perfil}>
          <.notas_de documento="vivienda" {notas(assigns)} />
        </PerfilDocumentos.ficha_obra>
        <PerfilDocumentos.hoja_ruta perfil={@perfil}>
          <.notas_de documento="servicios" {notas(assigns)} />
        </PerfilDocumentos.hoja_ruta>
        <PerfilDocumentos.libro perfil={@perfil}>
          <.notas_de documento="comercio" {notas(assigns)} />
        </PerfilDocumentos.libro>
        <PerfilDocumentos.ticket perfil={@perfil}>
          <.notas_de documento="consumo" {notas(assigns)} />
        </PerfilDocumentos.ticket>
        <PerfilDocumentos.expediente perfil={@perfil}>
          <.notas_de documento="seguridad" {notas(assigns)} />
        </PerfilDocumentos.expediente>
        <PerfilDocumentos.tarjeta perfil={@perfil}>
          <.notas_de documento="laboral" {notas(assigns)} />
        </PerfilDocumentos.tarjeta>
        <PerfilDocumentos.cuenta perfil={@perfil}>
          <.notas_de documento="hacienda" {notas(assigns)} />
        </PerfilDocumentos.cuenta>
      </div>

      <PerfilSimilares.similares
        :if={@perfil}
        resultado={@similares}
        buscando={@buscando}
        error={@error_similares}
        filtro={@filtro}
        abierto={@abierto}
        nivel={nivel(@zona)}
        ruta={&ruta(%{zona: &1, filtro: nil})}
      />
    </Layouts.app>
    """
  end

  # Contra qué se compara: igual que similares.nivel_de en mapo_core.
  defp nivel(%{"tipo" => t}) when t in ~w(municipios metropoli estado), do: "municipio"
  defp nivel(_zona), do: "colonia"

  defp notas(assigns),
    do: %{notas: assigns.notas, equipo?: assigns.equipo_id != nil, ronda: assigns.nota_ronda}

  attr :documento, :string, required: true
  attr :notas, :map, required: true
  attr :equipo?, :boolean, required: true
  attr :ronda, :integer, required: true

  # La forma lleva la ronda en el id: al guardar una nota se vuelve a crear
  # vacía y cerrada.
  defp notas_de(assigns) do
    assigns =
      assign(assigns,
        notas: assigns.notas[assigns.documento] || [],
        forma: "nota-forma-#{assigns.documento}-#{assigns.ronda}"
      )

    ~H"""
    <div class="notas">
      <ul :if={@notas != []}>
        <li :for={nota <- @notas} id={"nota-#{nota.id}"}>
          <span class="nota-texto">{nota.texto}</span>
          <span class="nota-autor">{nota.user.email}</span>
          <button
            type="button"
            class="nota-borrar"
            phx-click="borrar_nota"
            phx-value-id={nota.id}
            data-confirm="¿Borrar esta nota para todo el equipo?"
            aria-label="Borrar nota"
          >
            ×
          </button>
        </li>
      </ul>

      <%= if @equipo? do %>
        <button
          type="button"
          class="nota-mas"
          phx-click={JS.toggle(to: "##{@forma}", display: "flex") |> JS.focus(to: "##{@forma} input")}
          aria-controls={@forma}
        >
          + nota del equipo
        </button>

        <form id={@forma} phx-submit="crear_nota" class="nota-forma" style="display: none">
          <input type="hidden" name="documento" value={@documento} />
          <input
            type="text"
            name="texto"
            maxlength="500"
            required
            aria-label="Nota del equipo"
            class="campo"
          /> <button class="chico primario">Guardar</button>
        </form>
      <% else %>
        <.link navigate={~p"/teams/new"} class="nota-mas">Crea un equipo para anotar</.link>
      <% end %>
    </div>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    equipos = socket.assigns.current_scope |> Teams.list_teams() |> Enum.sort_by(& &1.name)

    {:ok,
     assign(socket,
       page_title: "Perfil de zona",
       zona: nil,
       consultada: nil,
       perfil: nil,
       consultando: false,
       error: nil,
       similares: nil,
       buscando: false,
       error_similares: nil,
       filtro: @filtro,
       abierto: nil,
       equipos: equipos,
       equipo_id: equipos |> List.first() |> then(&(&1 && &1.id)),
       notas_de: nil,
       notas: %{},
       nota_ronda: 0
     )}
  end

  # La URL manda: `zona=` (los enlaces de antes de la 29h traen `cve_ent` y
  # `cve_mun`) y, si se buscaron parecidos, `parecidas=` con sus áreas.
  @impl true
  def handle_params(params, _uri, socket) do
    a = socket.assigns
    clave = clave_de_url(params)
    {filtro, buscar?} = filtro_de_url(params)

    cond do
      not connected?(socket) ->
        {:noreply, socket}

      is_nil(clave) and is_nil(a.consultada) ->
        # Sin zona en el enlace, la que guardó quien abre (sin consultar sola).
        {:noreply, ZonaSelector.con_zona_inicial(socket)}

      is_nil(clave) ->
        {:noreply, socket}

      clave == a.consultada and not buscar? ->
        {:noreply, assign(socket, filtro: filtro, similares: nil, abierto: nil)}

      clave == a.consultada ->
        {:noreply, socket |> assign(filtro: filtro) |> buscar()}

      true ->
        {:noreply, socket |> assign(filtro: filtro) |> abrir(clave, buscar?)}
    end
  end

  defp clave_de_url(%{"zona" => clave}) when is_binary(clave), do: clave

  defp clave_de_url(%{"cve_ent" => e, "cve_mun" => m}) when is_binary(e) and is_binary(m) do
    if String.match?(e, ~r/\A\d{2}\z/) and String.match?(m, ~r/\A\d{3}\z/), do: "mun:#{e}#{m}"
  end

  defp clave_de_url(_params), do: nil

  defp filtro_de_url(%{"parecidas" => areas} = params) when is_binary(areas) do
    {%{
       areas: for(x <- String.split(areas, ","), x in PerfilSimilares.areas_validas(), do: x),
       margen: valido(params["margen"], PerfilSimilares.margenes_validos(), @filtro.margen),
       donde: valido(params["donde"], PerfilSimilares.dondes_validos(), @filtro.donde)
     }, true}
  end

  defp filtro_de_url(_params), do: {@filtro, false}

  defp valido(valor, validos, omision), do: if(valor in validos, do: valor, else: omision)

  # `filtro: nil` es el perfil sin búsqueda de parecidos.
  defp ruta(%{zona: clave, filtro: filtro}) do
    parecidas =
      if filtro do
        # "todas" deja el parámetro con algo: sin él, no hay búsqueda.
        areas = if filtro.areas == [], do: "todas", else: Enum.join(filtro.areas, ",")

        [parecidas: areas, margen: filtro.margen] ++
          if(filtro.donde != "todo", do: [donde: filtro.donde], else: [])
      else
        []
      end

    "/perfil?" <> ZonaSelector.query([zona: clave] ++ parecidas)
  end

  defp ruta_en(vista, zona), do: vista <> "?" <> ZonaSelector.query(zona: zona["clave"])

  defp abrir(socket, clave, buscar?) do
    case zona_resuelta(socket, clave) do
      {:ok, zona} ->
        socket =
          socket
          |> assign(zona: zona, page_title: "Perfil de #{zona["nombre"]}")
          |> push_event("zona_elegida", %{geojson: zona["geojson"]})
          |> consultar(zona["clave"])

        # La dirección lleva la clave canónica: un enlace viejo o con otra escritura
        # de la misma zona no parte las notas del equipo en dos.
        if buscar? and socket.assigns.error == nil, do: buscar(socket), else: socket

      {:error, mensaje} ->
        assign(socket, error: mensaje)
    end
  end

  # La que acaba de elegir el selector ya viene resuelta.
  defp zona_resuelta(%{assigns: %{zona: %{"clave" => clave} = zona}}, clave), do: {:ok, zona}
  defp zona_resuelta(_socket, clave), do: ZonaSelector.resolver(clave)

  defp consultar(socket, clave) do
    if limite?(socket, :perfil) do
      socket
      |> assign(
        consultada: clave,
        perfil: nil,
        consultando: true,
        error: nil,
        similares: nil,
        error_similares: nil,
        buscando: false,
        abierto: nil
      )
      |> cargar_notas(clave)
      |> start_async(:perfil, fn -> MapoCore.perfil_zona(clave) end)
    else
      assign(socket, error: "Llevas #{@max_consultas} consultas en una hora. Espera un poco.")
    end
  end

  defp buscar(%{assigns: a} = socket) do
    if limite?(socket, :similares) do
      %{filtro: filtro, consultada: clave} = a

      socket
      |> assign(buscando: true, error_similares: nil)
      |> start_async(:similares, fn ->
        MapoCore.perfil_similares(clave, Map.to_list(filtro))
      end)
    else
      assign(socket,
        error_similares: "Llevas #{@max_consultas} búsquedas en una hora. Espera un poco."
      )
    end
  end

  defp limite?(socket, que),
    do: Limite.permitir?({que, socket.assigns.current_scope.user.id}, @max_consultas, @ventana)

  @impl true
  def handle_event("similares", params, socket) do
    sim = params["sim"] || %{}
    areas = List.wrap(sim["areas"])

    filtro = %{
      areas: Enum.filter(PerfilSimilares.areas_validas(), &(&1 in areas)),
      margen: valido(sim["margen"], PerfilSimilares.margenes_validos(), @filtro.margen),
      donde: valido(sim["donde"], PerfilSimilares.dondes_validos(), @filtro.donde)
    }

    if socket.assigns.consultada,
      do:
        {:noreply,
         push_patch(socket, to: ruta(%{zona: socket.assigns.consultada, filtro: filtro}))},
      else: {:noreply, socket}
  end

  def handle_event("abrir_similar", %{"clave" => clave}, socket) do
    abierto = if socket.assigns.abierto == clave, do: nil, else: clave
    {:noreply, assign(socket, abierto: abierto)}
  end

  def handle_event("equipo", %{"equipo" => id}, socket),
    do: {:noreply, cambiar_equipo(socket, id)}

  def handle_event("crear_nota", %{"documento" => documento, "texto" => texto}, socket) do
    case socket.assigns.notas_de do
      {equipo, zona} ->
        attrs = %{"zona" => zona, "documento" => documento, "texto" => texto}

        case Notas.create_nota(socket.assigns.current_scope, equipo, attrs) do
          {:ok, _nota} ->
            {:noreply, update(socket, :nota_ronda, &(&1 + 1))}

          {:error, _changeset} ->
            {:noreply, put_flash(socket, :error, "No se pudo guardar la nota.")}
        end

      nil ->
        {:noreply, socket}
    end
  end

  def handle_event("borrar_nota", %{"id" => id}, socket) do
    case socket.assigns.notas_de do
      {equipo, _zona} ->
        {:ok, _nota} = Notas.delete_nota(socket.assigns.current_scope, equipo, id)
        {:noreply, socket}

      nil ->
        {:noreply, socket}
    end
  end

  @impl true
  def handle_info({:zona_elegida, zona}, socket) do
    {:noreply,
     socket
     |> assign(zona: zona)
     |> push_patch(to: ruta(%{zona: zona["clave"], filtro: nil}))}
  end

  # Las notas llegan por PubSub también a quien las escribe: una sola vía
  # para pintarlas, como las marcas de las sesiones.
  def handle_info({:nota_creada, nota}, socket) do
    if socket.assigns.notas_de == {nota.team_id, nota.zona} do
      {:noreply,
       update(socket, :notas, &Map.update(&1, nota.documento, [nota], fn l -> l ++ [nota] end))}
    else
      {:noreply, socket}
    end
  end

  def handle_info({:nota_borrada, id}, socket) do
    quitar = fn lista -> Enum.reject(lista, &(&1.id == id)) end
    {:noreply, update(socket, :notas, &Map.new(&1, fn {doc, lista} -> {doc, quitar.(lista)} end))}
  end

  @impl true
  def handle_async(:perfil, {:ok, {:ok, perfil}}, socket) do
    {plano, perfil} = Map.pop(perfil, "plano")
    {contorno, zona} = Map.pop(perfil["zona"], "geojson")

    {:noreply,
     socket
     # El plano va al navegador y no se guarda: en un estado pesa 2 MB.
     |> assign(perfil: %{perfil | "zona" => zona}, consultando: false)
     |> push_event("perfil_plano", %{zona: contorno, plano: plano})}
  end

  def handle_async(:perfil, {:ok, {:error, {:status, 422, %{"detail" => d}}}}, socket)
      when is_binary(d),
      do: {:noreply, fallo(socket, "No se puede hacer el perfil: #{d}.")}

  def handle_async(:perfil, {:ok, {:error, {:status, 404, _}}}, socket),
    do: {:noreply, fallo(socket, "Esa zona no toca nada cargado en Mapo.")}

  def handle_async(:perfil, _fallo, socket),
    do:
      {:noreply, fallo(socket, "No se pudo consultar la zona. Inténtalo de nuevo en un momento.")}

  def handle_async(:similares, {:ok, {:ok, resultado}}, socket),
    do: {:noreply, assign(socket, similares: resultado, buscando: false, abierto: nil)}

  def handle_async(:similares, _fallo, socket),
    do:
      {:noreply,
       assign(socket,
         buscando: false,
         error_similares: "No se pudo buscar. Inténtalo de nuevo en un momento."
       )}

  # `consultada` se suelta: volver a elegir la misma zona la pide otra vez.
  defp fallo(socket, mensaje),
    do: assign(socket, consultando: false, error: mensaje, consultada: nil)

  defp cambiar_equipo(socket, id) do
    case Enum.find(socket.assigns.equipos, &(to_string(&1.id) == id)) do
      %{id: equipo} when equipo != socket.assigns.equipo_id ->
        socket = assign(socket, equipo_id: equipo)

        case socket.assigns.notas_de do
          {_, zona} -> cargar_notas(socket, zona)
          nil -> socket
        end

      _ ->
        socket
    end
  end

  # Cambia el tópico al equipo y la zona de ahora y trae sus notas.
  defp cargar_notas(socket, zona) do
    %{equipo_id: equipo, notas_de: previa, current_scope: scope} = socket.assigns
    clave = equipo && {equipo, zona}

    if connected?(socket) and previa != clave do
      with {e, z} <- previa, do: Notas.unsubscribe(e, z)
      if clave, do: Notas.subscribe(equipo, zona)
    end

    notas =
      if clave,
        do: scope |> Notas.list_notas(equipo, zona) |> Enum.group_by(& &1.documento),
        else: %{}

    assign(socket, notas_de: clave, notas: notas)
  end
end
