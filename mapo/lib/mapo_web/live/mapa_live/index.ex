defmodule MapoWeb.MapaLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  require MapoWeb.Marcas

  alias Mapo.Capas
  alias Mapo.MapoCore
  alias Mapo.Sesiones
  alias Mapo.Sesiones.Anotacion
  alias MapoWeb.Marcas

  # Cada capa es un acetato sobre el plano (docs/arquitectura/decisiones.md,
  # "Concepto visual"). El orden de la lista es el orden de la pila: la
  # primera queda encima. La piel de la mesa la pone la capa visible de más
  # arriba, salvo que la persona fije una.
  #
  # "Tus marcas" no está en esta lista: no es un acetato impreso sino lo que
  # el equipo anota a mano, así que va siempre encima, no se reordena y no
  # pone piel. Sus marcas son las de una sesión del equipo (`?sesion=ID`),
  # las mismas que se ven en /sesiones/:id y en vivo con ella.
  #
  # "propios" muestra una capa del equipo a la vez. Usa la tinta de consumo
  # porque ningún otro acetato de esta pantalla la ocupa, no porque sus datos
  # sean de consumo.
  @capas %{
    "propios" => %{nombre: "Tus datos", fuente: "Tu equipo", enfoque: "consumo"},
    "coropleta" => %{
      nombre: "Censo por AGEB",
      fuente: "INEGI · Censo 2020",
      enfoque: "demografia"
    },
    "voronoi" => %{nombre: "Área por negocio", fuente: "INEGI · DENUE", enfoque: "comercio"},
    "isocrona" => %{nombre: "Alcance en auto", fuente: "OSRM", enfoque: "movilidad"},
    "coloreado" => %{
      nombre: "Municipios",
      fuente: "INEGI · Marco Geoestadístico",
      enfoque: "urbanismo"
    }
  }

  @pieles [
    {"Urbanismo", "urbanismo"},
    {"Demografía", "demografia"},
    {"Comercio", "comercio"},
    {"Consumo", "consumo"},
    {"Seguridad", "seguridad"},
    {"Laboral", "laboral"},
    {"Movilidad", "movilidad"}
  ]

  @impl true
  def render(assigns) do
    assigns = assign(assigns, capas: @capas, pieles: @pieles)

    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="mapa" full_width?={true}>
      <:membrete>
        <.form for={@form} id="ubicacion_form" phx-change="cambiar_ubicacion" class="ubicacion">
          <.input
            field={@form[:cve_ent]}
            type="select"
            options={@estados}
            prompt="Elige un estado"
            class="membrete-select"
            aria-label="Estado"
          /> <span aria-hidden="true">/</span>
          <.input
            field={@form[:cve_mun]}
            type="select"
            options={@municipios}
            prompt="Todo el estado"
            class="membrete-select"
            aria-label="Municipio"
          />
        </.form>
      </:membrete>

      <h1 class="sr-only">Mapa técnico</h1>

      <p :if={@estados == []} class="aviso-plano pegado sin-cinta">
        No se pudo cargar la lista de estados: mapo_core no responde o todavía no hay estados
        descargados.
      </p>

      <div
        id="mapa-tecnico"
        phx-hook="MapaTecnico"
        phx-update="ignore"
        class="plano-leaflet flex-1 min-h-0 w-full"
      >
      </div>

      <section
        id="cinta-marcas"
        class="cinta pegado"
        hidden={@elegida != "marcas"}
        aria-label="Tus marcas"
      >
        <div class="cinta-titulo">
          <h2>Tus marcas</h2>

          <p class="fuente">a mano, del equipo</p>
        </div>

        <p :if={@sesiones == []} class="cinta-texto">
          Las marcas se guardan en una sesión de tu equipo. <.link
            navigate={~p"/teams"}
            class="enlace"
          >Abre o crea una</.link>.
        </p>

        <.form
          :if={@sesiones != []}
          for={%{}}
          as={:marcas}
          id="sesion_marcas_form"
          phx-change="elegir_sesion"
          class="cinta-campos"
        >
          <label>
            <span class="etiqueta">Sesión</span>
            <select name="sesion" class="cinta-control">
              <option value="">Ninguna</option>
              {Phoenix.HTML.Form.options_for_select(
                opciones_sesiones(@sesiones),
                @sesion && @sesion.id
              )}
            </select>
          </label>
        </.form>

        <Marcas.selector :if={@sesion} herramienta={@herramienta} />

        <p :if={@sesiones != []} class="cinta-texto">
          <%= cond do %>
            <% is_nil(@sesion) -> %>
              Elige una sesión para ver sus marcas y poner nuevas.
            <% @herramienta == "circulo" -> %>
              Un clic en el centro y otro en la orilla. {marcas(@num_marcas)}.
            <% true -> %>
              Clic en el plano para poner una marca. {marcas(@num_marcas)}.
          <% end %>
          <.link :if={@sesion} navigate={~p"/sesiones/#{@sesion}"} class="enlace">
            Abrir la sesión
          </.link>
        </p>
      </section>

      <section
        :for={id <- @orden}
        id={"cinta-#{id}"}
        class="cinta pegado"
        hidden={@elegida != id}
        aria-label={@capas[id].nombre}
      >
        <div class="cinta-titulo">
          <h2>{@capas[id].nombre}</h2>

          <p class="fuente">{@capas[id].fuente}</p>
        </div>

        <.cinta_propios
          :if={id == "propios"}
          capas={@capas_propias}
          capa={@capa_propia}
          columna={@columna_propia}
          escala={@propia_escala}
        />
        <.cinta_coropleta
          :if={id == "coropleta"}
          form={@coropleta_form}
          indicadores={@indicadores}
          activa?={@coropleta_activa?}
          escala={@coropleta_escala}
        />
        <.cinta_voronoi
          :if={id == "voronoi"}
          form={@voronoi_form}
          activa?={@voronoi_activa?}
          resumen={@voronoi_resumen}
        />
        <.cinta_coloreado :if={id == "coloreado"} activa?={@coloreado_activa?} />
        <.cinta_isocrona :if={id == "isocrona"} form={@isocrona_form} activa?={@isocrona_activa?} />
        <div :if={activa?(assigns, id)} class="cinta-orden">
          <button
            type="button"
            phx-click="mover"
            phx-value-capa={id}
            phx-value-hacia="arriba"
            disabled={hd(@orden) == id}
          >
            Más arriba
          </button>

          <button
            type="button"
            phx-click="mover"
            phx-value-capa={id}
            phx-value-hacia="abajo"
            disabled={List.last(@orden) == id}
          >
            Más abajo
          </button>
        </div>
      </section>

      <dl class="rotulo pegado">
        <div class="rotulo-titulo">{lugar(assigns)}</div>

        <dt>Lámina</dt>

        <dd>{acetatos(assigns)}</dd>

        <dt :if={@sesion}>Marcas</dt>

        <dd :if={@sesion}>{@sesion.nombre}</dd>

        <dt>Fuentes</dt>

        <dd>{fuentes(assigns)}</dd>

        <dt>Piel</dt>

        <dd>
          <.form for={%{}} as={:piel} id="piel_form" phx-change="fijar_piel">
            <select name="piel" aria-label="Piel de la mesa">
              <option value="" selected={is_nil(@piel_fijada)}>
                Automática · {nombre_piel(piel_automatica(assigns))}
              </option>

              <option :for={{nombre, clave} <- @pieles} value={clave} selected={@piel_fijada == clave}>
                {nombre}
              </option>
            </select>
          </.form>
        </dd>
      </dl>

      <nav class="charola" aria-label="Acetatos">
        <button
          type="button"
          class="pestana"
          phx-click="elegir"
          phx-value-capa="marcas"
          aria-pressed={to_string(@sesion != nil)}
          aria-expanded={to_string(@elegida == "marcas")}
          aria-controls="cinta-marcas"
          style="--capa: var(--accent)"
        >
          <span class="pelicula lapiz" aria-hidden="true"></span> <b>Tus marcas</b>
          <em>{if @sesion, do: @sesion.nombre, else: "sin sesión"}</em>
        </button>

        <button
          :for={id <- @orden}
          type="button"
          class="pestana"
          phx-click="elegir"
          phx-value-capa={id}
          aria-pressed={to_string(activa?(assigns, id))}
          aria-expanded={to_string(@elegida == id)}
          aria-controls={"cinta-#{id}"}
          style={"--capa: var(--f-#{@capas[id].enfoque})"}
        >
          <span class="pelicula" aria-hidden="true"></span> <b>{@capas[id].nombre}</b>
          <em>{if activa?(assigns, id), do: "encima", else: "en la charola"}</em>
        </button>
      </nav>
    </Layouts.app>
    """
  end

  attr :form, :any, required: true
  attr :indicadores, :list, required: true
  attr :activa?, :boolean, required: true
  attr :escala, :map, default: nil

  defp cinta_coropleta(assigns) do
    ~H"""
    <.form for={@form} id="coropleta_capa_form" phx-submit="mostrar_coropleta" class="cinta-campos">
      <.input
        field={@form[:indicador]}
        type="select"
        label="Indicador"
        options={@indicadores}
        class="cinta-control"
      />
      <div class="cinta-botones">
        <.button phx-disable-with="Poniendo..." class="boton primario">
          {if @activa?, do: "Actualizar", else: "Poner"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_coropleta" class="boton">
          Quitar
        </.button>
      </div>
    </.form>

    <.escala escala={@escala} />
    """
  end

  attr :escala, :map, default: nil

  defp escala(assigns) do
    ~H"""
    <div :if={@escala} class="escala" aria-label="Clases por quintil">
      <ol>
        <li :for={o <- [0.12, 0.26, 0.42, 0.6, 0.8]} style={"opacity: #{o}"}></li>

        <li class="nula" title="Sin dato"></li>
      </ol>

      <div class="marcas num">
        <span :for={v <- Enum.take(@escala.limites, 5)}>{cifra(v)}</span>
        <span>sin dato: {@escala.nulos}</span>
      </div>
    </div>
    """
  end

  attr :capas, :list, required: true
  attr :capa, :any, default: nil
  attr :columna, :string, default: nil
  attr :escala, :map, default: nil

  defp cinta_propios(assigns) do
    ~H"""
    <p :if={@capas == []} class="cinta-texto">
      Sube un CSV o un Excel desde la página de <.link navigate={~p"/teams"} class="enlace">tu equipo</.link>.
    </p>

    <.form
      :if={@capas != []}
      for={%{}}
      as={:propios}
      id="capa_propia_form"
      phx-change="elegir_capa"
      class="cinta-campos"
    >
      <label>
        <span class="etiqueta">Capa</span>
        <select name="capa" class="cinta-control">
          <option value="">Ninguna</option>
          {Phoenix.HTML.Form.options_for_select(opciones_capas(@capas), @capa && @capa.id)}
        </select>
      </label>

      <label :if={@capa && @capa.tipo != "puntos" && @capa.numericas != []}>
        <span class="etiqueta">Pintar por</span>
        <select name="columna" class="cinta-control" disabled={@capa.repetidas > 0}>
          <option value="">Nada, solo la zona</option>
          {Phoenix.HTML.Form.options_for_select(@capa.numericas, @columna)}
        </select>
      </label>
    </.form>

    <.escala escala={@escala} />

    <p :if={@capa} class="cinta-texto">
      {cifra(@capa.num_filas)} renglones de {@capa.archivo}.
      <span :if={@capa.repetidas > 0}>
        Hay zonas con más de un renglón: para pintar por columna se necesita uno por zona.
      </span>
      <.link navigate={~p"/teams/#{@capa.team_id}/datos"} class="enlace">Datos del equipo</.link>
    </p>
    """
  end

  attr :form, :any, required: true
  attr :activa?, :boolean, required: true
  attr :resumen, :string, default: nil

  defp cinta_voronoi(assigns) do
    ~H"""
    <.form for={@form} id="voronoi_capa_form" phx-submit="mostrar_voronoi" class="cinta-campos">
      <.input
        field={@form[:clase_actividad]}
        type="text"
        label="Giro"
        placeholder="florería, policía..."
        class="cinta-control"
      />
      <div class="cinta-botones">
        <.button phx-disable-with="Poniendo..." class="boton primario">
          {if @activa?, do: "Actualizar", else: "Poner"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_voronoi" class="boton">
          Quitar
        </.button>
      </div>
    </.form>

    <p class="cinta-texto">
      {@resumen ||
        "Cada celda es la zona más cerca de ese negocio que de otro. Celda grande, poca oferta. Necesita un municipio."}
    </p>
    """
  end

  attr :activa?, :boolean, required: true

  defp cinta_coloreado(assigns) do
    ~H"""
    <div class="cinta-campos">
      <div class="cinta-botones">
        <.button phx-click="mostrar_coloreado" class="boton primario">
          {if @activa?, do: "Actualizar", else: "Poner"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_coloreado" class="boton">
          Quitar
        </.button>
      </div>
    </div>

    <p class="cinta-texto">
      Los municipios del estado, sin dos vecinos del mismo tono.
    </p>
    """
  end

  attr :form, :any, required: true
  attr :activa?, :boolean, required: true

  defp cinta_isocrona(assigns) do
    ~H"""
    <.form for={@form} id="isocrona_capa_form" phx-submit="activar_isocrona" class="cinta-campos">
      <.input
        field={@form[:minutos]}
        type="number"
        label="Minutos"
        min="1"
        class="cinta-control cinta-corto"
      />
      <div class="cinta-botones">
        <.button phx-disable-with="Activando..." class="boton primario">
          {if @activa?, do: "Actualizar", else: "Activar"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_isocrona" class="boton">
          Quitar
        </.button>
      </div>
    </.form>

    <p class="cinta-texto">
      {if @activa?,
        do: "Haz clic en el plano para elegir el punto de salida.",
        else: "Hasta dónde llegas en auto desde un punto."}
    </p>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    sesiones = Sesiones.list_sesiones_del_usuario(socket.assigns.current_scope)

    estados =
      case MapoCore.estados() do
        {:ok, %{"features" => features}} -> opciones_estados(features)
        {:error, _} -> []
      end

    {:ok,
     assign(socket,
       estados: estados,
       municipios: [],
       indicadores: Enum.map(MapoCore.indicadores_censo(), fn {c, e} -> {e, c} end),
       form: to_form(%{"cve_ent" => "", "cve_mun" => ""}, as: "mapa"),
       coropleta_form: to_form(%{"indicador" => "pobtot"}, as: "coropleta_capa"),
       voronoi_form: to_form(%{"clase_actividad" => ""}, as: "voronoi_capa"),
       isocrona_form: to_form(%{"minutos" => "10"}, as: "isocrona_capa"),
       coropleta_activa?: false,
       voronoi_activa?: false,
       voronoi_resumen: nil,
       coloreado_activa?: false,
       isocrona_activa?: false,
       coropleta_escala: nil,
       capas_propias: Capas.list_capas_del_usuario(socket.assigns.current_scope),
       capa_propia: nil,
       columna_propia: nil,
       propia_escala: nil,
       orden: ["propios", "isocrona", "voronoi", "coropleta", "coloreado"],
       elegida: nil,
       piel_fijada: nil,
       piel_pintada: "urbanismo",
       sesiones: sesiones,
       sesion: nil,
       herramienta: "punto",
       num_marcas: 0
     )}
  end

  @impl true
  def handle_params(params, _uri, socket) do
    {:noreply,
     socket
     |> cambiar_sesion(params["sesion"])
     |> abrir_capa_de_la_url(params["capa"])}
  end

  @impl true
  def handle_event("cambiar_ubicacion", %{"mapa" => params}, socket) do
    cve_ent_previo = socket.assigns.form[:cve_ent].value

    socket =
      if params["cve_ent"] != cve_ent_previo do
        assign(socket, municipios: municipios_de(params["cve_ent"]))
      else
        socket
      end

    {:noreply, assign(socket, form: to_form(params, as: "mapa"))}
  end

  def handle_event("elegir", %{"capa" => capa}, socket)
      when is_map_key(@capas, capa) or capa == "marcas" do
    elegida = if socket.assigns.elegida == capa, do: nil, else: capa
    {:noreply, socket |> assign(elegida: elegida) |> modo_marcas()}
  end

  def handle_event("elegir_sesion", %{"sesion" => id}, socket) do
    destino = if id == "", do: ~p"/mapa", else: ~p"/mapa?#{[sesion: id]}"
    {:noreply, push_patch(socket, to: destino)}
  end

  def handle_event(evento, params, socket) when Marcas.evento_de_marca(evento) do
    {:noreply, Marcas.evento(evento, params, socket)}
  end

  def handle_event("mover", %{"capa" => capa, "hacia" => hacia}, socket)
      when is_map_key(@capas, capa) and hacia in ["arriba", "abajo"] do
    orden = socket.assigns.orden
    i = Enum.find_index(orden, &(&1 == capa))
    j = if hacia == "arriba", do: i - 1, else: i + 1

    orden =
      if j < 0 or j >= length(orden) do
        orden
      else
        orden |> List.replace_at(i, Enum.at(orden, j)) |> List.replace_at(j, capa)
      end

    {:noreply, socket |> assign(orden: orden) |> actualizar_mesa()}
  end

  def handle_event("fijar_piel", %{"piel" => piel}, socket) do
    fijada = if Enum.any?(@pieles, fn {_, clave} -> clave == piel end), do: piel, else: nil
    {:noreply, socket |> assign(piel_fijada: fijada) |> actualizar_mesa()}
  end

  def handle_event(
        "mostrar_coropleta",
        %{"coropleta_capa" => %{"indicador" => indicador}},
        socket
      ) do
    cve_ent = socket.assigns.form[:cve_ent].value
    cve_mun = vacio_para_nil(socket.assigns.form[:cve_mun].value)

    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coropleta_censo_poblacion(indicador, cve_ent, cve_mun) do
        {:ok, %{"features" => []}} ->
          {:noreply,
           put_flash(
             socket,
             :error,
             "Gaiarda no tiene AGEBs o censo descargados para ese estado/municipio todavía."
           )}

        {:ok, geojson} ->
          etiqueta = etiqueta_indicador(indicador)
          escala = escala_quintiles(geojson)

          {:noreply,
           socket
           |> assign(
             coropleta_activa?: true,
             coropleta_escala: escala,
             coropleta_form: to_form(%{"indicador" => indicador}, as: "coropleta_capa")
           )
           |> push_event("capa_coropleta", %{
             activa: true,
             geojson: geojson,
             etiqueta: etiqueta,
             cortes: escala && escala.cortes
           })
           |> actualizar_mesa()}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    end
  end

  def handle_event("quitar_coropleta", _params, socket) do
    {:noreply,
     socket
     |> assign(coropleta_activa?: false, coropleta_escala: nil)
     |> push_event("capa_coropleta", %{activa: false})
     |> actualizar_mesa()}
  end

  def handle_event(
        "mostrar_voronoi",
        %{"voronoi_capa" => %{"clase_actividad" => clase_actividad}},
        socket
      ) do
    cve_ent = socket.assigns.form[:cve_ent].value
    cve_mun = vacio_para_nil(socket.assigns.form[:cve_mun].value)
    clase_actividad = vacio_para_nil(clase_actividad)

    cond do
      cve_ent in [nil, ""] or is_nil(cve_mun) ->
        {:noreply, put_flash(socket, :error, "Selecciona un estado y un municipio primero.")}

      true ->
        case MapoCore.voronoi_denue(cve_ent, cve_mun, clase_actividad) do
          {:ok, %{"celdas" => geojson} = respuesta} ->
            {:noreply,
             socket
             |> assign(voronoi_activa?: true, voronoi_resumen: resumen_voronoi(respuesta))
             |> push_event("capa_voronoi", %{activa: true, geojson: geojson})
             |> actualizar_mesa()}

          {:error, {:status, 422, body}} ->
            mensaje = if is_map(body), do: body["detail"], else: nil

            {:noreply,
             put_flash(socket, :error, mensaje || "No hay suficientes negocios con ese filtro.")}

          {:error, {:status, 404, _}} ->
            {:noreply,
             put_flash(socket, :error, "Ese municipio no está descargado en Gaiarda todavía.")}

          {:error, _} ->
            {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
        end
    end
  end

  def handle_event("quitar_voronoi", _params, socket) do
    {:noreply,
     socket
     |> assign(voronoi_activa?: false, voronoi_resumen: nil)
     |> push_event("capa_voronoi", %{activa: false})
     |> actualizar_mesa()}
  end

  def handle_event("elegir_capa", %{"capa" => id} = params, socket) do
    {:noreply, poner_capa(socket, id, params["columna"])}
  end

  # La ficha se pide al abrirla: mandar los datos de 50 mil renglones al
  # navegador pesaría megas que casi nadie va a abrir.
  def handle_event("ver_fila", params, socket) do
    llave =
      case params do
        %{"id" => id} when is_integer(id) -> {:id, id}
        %{"clave" => clave} when is_binary(clave) -> {:clave, clave}
        _ -> nil
      end

    capa = socket.assigns.capa_propia
    ficha = capa && llave && Capas.ficha(socket.assigns.current_scope, capa.id, llave)

    case ficha do
      {datos, cuantas} ->
        campos = for c <- capa.columnas, not is_nil(datos[c]), do: [c, texto_celda(datos[c])]
        {:reply, %{campos: campos, otras: cuantas - 1}, socket}

      _ ->
        {:reply, %{campos: [], otras: 0}, socket}
    end
  end

  def handle_event("mostrar_coloreado", _params, socket) do
    cve_ent = socket.assigns.form[:cve_ent].value

    if cve_ent in [nil, ""] do
      {:noreply, put_flash(socket, :error, "Selecciona un estado primero.")}
    else
      case MapoCore.coloreado_municipios(cve_ent) do
        {:ok, %{"features" => []}} ->
          {:noreply,
           put_flash(
             socket,
             :error,
             "Gaiarda no tiene municipios descargados para ese estado todavía."
           )}

        {:ok, geojson} ->
          {:noreply,
           socket
           |> assign(coloreado_activa?: true)
           |> push_event("capa_coloreado", %{activa: true, geojson: geojson})
           |> actualizar_mesa()}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    end
  end

  def handle_event("quitar_coloreado", _params, socket) do
    {:noreply,
     socket
     |> assign(coloreado_activa?: false)
     |> push_event("capa_coloreado", %{activa: false})
     |> actualizar_mesa()}
  end

  def handle_event("activar_isocrona", %{"isocrona_capa" => %{"minutos" => minutos}}, socket) do
    {:noreply,
     socket
     |> assign(
       isocrona_activa?: true,
       isocrona_form: to_form(%{"minutos" => minutos}, as: "isocrona_capa")
     )
     |> push_event("modo_isocrona", %{activo: true})
     |> actualizar_mesa()}
  end

  def handle_event("quitar_isocrona", _params, socket) do
    {:noreply,
     socket
     |> assign(isocrona_activa?: false)
     |> push_event("modo_isocrona", %{activo: false})
     |> push_event("capa_isocrona", %{activa: false})
     |> actualizar_mesa()}
  end

  def handle_event("click_mapa", %{"lat" => lat, "lon" => lon}, socket) do
    if socket.assigns.isocrona_activa? do
      minutos =
        case socket.assigns.isocrona_form[:minutos].value |> to_string() |> Float.parse() do
          {valor, _} -> valor
          :error -> 10.0
        end

      case MapoCore.isocrona_calcular(lat, lon, minutos) do
        {:ok, %{"poligono" => poligono, "metodo" => metodo}} ->
          {:noreply,
           push_event(socket, "capa_isocrona", %{activa: true, poligono: poligono, metodo: metodo})}

        {:error, _} ->
          {:noreply, put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")}
      end
    else
      {:noreply, socket}
    end
  end

  @impl true
  def handle_info({:anotacion_creada, _} = mensaje, socket),
    do: {:noreply, Marcas.mensaje(mensaje, update(socket, :num_marcas, &(&1 + 1)))}

  def handle_info({:anotacion_borrada, _} = mensaje, socket),
    do: {:noreply, Marcas.mensaje(mensaje, update(socket, :num_marcas, &(&1 - 1)))}

  def handle_info(mensaje, socket) when Marcas.mensaje_de_marca(mensaje),
    do: {:noreply, Marcas.mensaje(mensaje, socket)}

  # El tópico de la sesión también lleva la presencia de /sesiones/:id; aquí
  # no se muestra.
  def handle_info(%Phoenix.Socket.Broadcast{event: "presence_diff"}, socket),
    do: {:noreply, socket}

  # Cambia la sesión de "Tus marcas": deja el tópico de la anterior, se
  # suscribe a la nueva y le manda al hook sus marcas. Solo se aceptan
  # sesiones de los equipos de la persona: la lista `sesiones` es del mount,
  # así que la membresía se vuelve a revisar por si la sacaron del equipo.
  defp cambiar_sesion(socket, id) do
    previa = socket.assigns.sesion
    nueva = id && Enum.find(socket.assigns.sesiones, &(to_string(&1.id) == id))

    nueva =
      nueva && Mapo.Teams.role_in_team(socket.assigns.current_scope, nueva.team_id) && nueva

    cond do
      previa && nueva && previa.id == nueva.id ->
        socket

      is_nil(previa) and is_nil(nueva) ->
        if id, do: put_flash(socket, :error, "Esa sesión no es de tus equipos."), else: socket

      true ->
        if previa && connected?(socket), do: Sesiones.unsubscribe_sesion(previa.id)
        if nueva && connected?(socket), do: Sesiones.subscribe_sesion(nueva.id)
        anotaciones = if nueva, do: Sesiones.list_anotaciones(nueva.id), else: []

        socket
        |> assign(sesion: nueva, num_marcas: length(anotaciones))
        |> assign(elegida: if(nueva, do: "marcas", else: socket.assigns.elegida))
        |> push_event("marcas", %{anotaciones: Enum.map(anotaciones, &Anotacion.a_mapa/1)})
        |> modo_marcas()
    end
  end

  # Viene de "Ver en el mapa" en la página de datos del equipo.
  defp abrir_capa_de_la_url(socket, id) when id in [nil, ""], do: socket

  defp abrir_capa_de_la_url(socket, id) do
    abierta = socket.assigns.capa_propia

    # El render inicial no llega al hook: se evita traer la capa dos veces.
    if not connected?(socket) or (abierta && to_string(abierta.id) == id) do
      socket
    else
      socket |> poner_capa(id, nil) |> assign(elegida: "propios")
    end
  end

  # Prende, cambia o quita el acetato de datos propios. La capa se vuelve a
  # traer por el scope: la lista es del mount y pudieron sacar a la persona
  # del equipo, o el id pudo venir de la URL.
  defp poner_capa(socket, id, _columna) when id in [nil, ""], do: quitar_capa(socket)

  defp poner_capa(socket, id, columna) do
    case entero(id) && Capas.get_capa(socket.assigns.current_scope, entero(id)) do
      nil ->
        socket |> quitar_capa() |> put_flash(:error, "Esa capa no es de tus equipos.")

      capa ->
        columna = if Capas.pintable?(capa, columna), do: columna

        case datos_de_capa(capa, columna) do
          {:ok, datos, escala} ->
            socket
            |> assign(capa_propia: capa, columna_propia: columna, propia_escala: escala)
            |> push_event("capa_propios", Map.put(datos, :activa, true))
            |> actualizar_mesa()

          {:error, _} ->
            put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
        end
    end
  end

  defp quitar_capa(socket) do
    socket
    |> assign(capa_propia: nil, columna_propia: nil, propia_escala: nil)
    |> push_event("capa_propios", %{activa: false})
    |> actualizar_mesa()
  end

  defp entero(id) do
    case Integer.parse(to_string(id)) do
      {n, ""} -> n
      _ -> nil
    end
  end

  defp datos_de_capa(%{tipo: "puntos"} = capa, _columna),
    do: {:ok, %{puntos: Capas.puntos(capa)}, nil}

  defp datos_de_capa(capa, columna) do
    with {:ok, geojson} <- MapoCore.geo_por_clave(capa.tipo, Capas.claves(capa)) do
      geojson = if columna, do: con_valores(geojson, Capas.valores(capa, columna)), else: geojson
      escala = columna && escala_quintiles(geojson)
      {:ok, %{geojson: geojson, etiqueta: columna, cortes: escala && escala.cortes}, escala}
    end
  end

  defp con_valores(geojson, valores) do
    update_in(geojson["features"], fn features ->
      Enum.map(features, fn f ->
        put_in(f, ["properties", "valor_choropleth"], valores[f["properties"]["cvegeo"]])
      end)
    end)
  end

  defp opciones_capas(capas) do
    capas
    |> Enum.group_by(& &1.team.name)
    |> Enum.sort_by(&elem(&1, 0))
    |> Enum.map(fn {equipo, lista} -> {equipo, Enum.map(lista, &{&1.nombre, &1.id})} end)
  end

  # Sin redondear: la ficha muestra el dato de la persona, no una cifra de lectura.
  defp texto_celda(v) when is_integer(v), do: cifra(v)
  defp texto_celda(v), do: to_string(v)

  # Con la cinta de "Tus marcas" abierta y una sesión elegida, el clic en el
  # plano pone marca (le gana a la isócrona).
  defp modo_marcas(socket) do
    activo = socket.assigns.elegida == "marcas" and socket.assigns.sesion != nil
    push_event(socket, "modo_marcas", %{activo: activo})
  end

  defp opciones_sesiones(sesiones) do
    sesiones
    |> Enum.group_by(& &1.team.name)
    |> Enum.sort_by(&elem(&1, 0))
    |> Enum.map(fn {equipo, lista} -> {equipo, Enum.map(lista, &{&1.nombre, &1.id})} end)
  end

  defp marcas(1), do: "1 marca en la sesión"
  defp marcas(n), do: "#{n} marcas en la sesión"

  # Le dice al hook el orden de la pila y, si cambió, la piel de la mesa.
  defp actualizar_mesa(socket) do
    piel = socket.assigns.piel_fijada || piel_automatica(socket.assigns)
    socket = push_event(socket, "orden_capas", %{orden: socket.assigns.orden})

    if piel != socket.assigns.piel_pintada do
      socket |> assign(piel_pintada: piel) |> push_event("piel", %{piel: piel})
    else
      socket
    end
  end

  defp activa?(assigns, "propios"), do: assigns.capa_propia != nil
  defp activa?(assigns, "coropleta"), do: assigns.coropleta_activa?
  defp activa?(assigns, "voronoi"), do: assigns.voronoi_activa?
  defp activa?(assigns, "coloreado"), do: assigns.coloreado_activa?
  defp activa?(assigns, "isocrona"), do: assigns.isocrona_activa?

  defp activas(assigns), do: Enum.filter(assigns.orden, &activa?(assigns, &1))

  defp piel_automatica(assigns) do
    case activas(assigns) do
      [arriba | _] -> @capas[arriba].enfoque
      [] -> "urbanismo"
    end
  end

  defp nombre_piel(clave) do
    Enum.find_value(@pieles, clave, fn {nombre, c} -> if c == clave, do: nombre end)
  end

  defp acetatos(assigns) do
    case length(activas(assigns)) do
      0 -> "sin acetatos"
      1 -> "1 acetato"
      n -> "#{n} acetatos"
    end
  end

  defp fuentes(assigns) do
    assigns
    |> activas()
    |> Enum.map(fn id -> @capas[id].fuente |> String.split(" · ") |> hd() end)
    |> Enum.uniq()
    |> case do
      [] -> "ninguna todavía"
      lista -> Enum.join(lista, ", ")
    end
  end

  defp lugar(assigns) do
    estado = nombre_de(assigns.estados, assigns.form[:cve_ent].value)
    municipio = nombre_de(assigns.municipios, assigns.form[:cve_mun].value)

    case {municipio, estado} do
      {nil, nil} -> "México"
      {nil, e} -> e
      {m, e} -> "#{m}, #{e}"
    end
  end

  defp nombre_de(_opciones, valor) when valor in [nil, ""], do: nil

  defp nombre_de(opciones, valor),
    do: Enum.find_value(opciones, fn {n, v} -> if v == valor, do: n end)

  # Dice qué se dibujó: el filtro pudo reconocer un rubro de la tabla.
  defp resumen_voronoi(%{"num_negocios" => n, "filtro" => filtro}) when is_binary(filtro),
    do: "#{filtro}: #{cifra(n)} en el plano. Celda grande, poca oferta."

  defp resumen_voronoi(%{"num_negocios" => n}),
    do: "#{cifra(n)} en el plano. Celda grande, poca oferta."

  defp resumen_voronoi(_respuesta), do: nil

  defp vacio_para_nil(nil), do: nil
  defp vacio_para_nil(""), do: nil
  defp vacio_para_nil(valor), do: valor

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

  defp etiqueta_indicador(codigo) do
    Enum.find_value(MapoCore.indicadores_censo(), codigo, fn {c, e} -> if c == codigo, do: e end)
  end
end
