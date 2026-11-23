defmodule MapoWeb.MapaLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  require MapoWeb.Marcas

  alias Mapo.Capas
  alias Mapo.MapoCore
  alias Mapo.Sesiones
  alias Mapo.Sesiones.Anotacion
  alias MapoWeb.Cita
  alias MapoWeb.Marcas

  # Cada capa es un acetato sobre el plano (docs/arquitectura/decisiones.md,
  # "Concepto visual"). El orden de la lista es el orden de la pila: la
  # primera queda encima; se cambia arrastrando las pestañas o con los botones
  # de la cinta. Desde la 29d la mesa es neutra (blanco o negro según el
  # tema): el color es solo de los datos, cada acetato con su tinta.
  #
  # "Tus marcas" no está en esta lista: no es un acetato impreso sino lo que
  # el equipo anota a mano, así que va siempre encima y no se reordena. Sus
  # marcas son las de una sesión del equipo (`?sesion=ID`),
  # las mismas que se ven en /sesiones/:id y en vivo con ella.
  #
  # "propios" junta hasta tres capas del equipo en un solo acetato, cada una
  # con una tinta que ningún otro acetato de esta pantalla ocupa: esos colores
  # son prestados y no dicen nada de los datos.
  @capas %{
    "propios" => %{nombre: "Tus datos", fuente: "Tu equipo", enfoque: "consumo"},
    "coropleta" => %{
      nombre: "Censo por AGEB",
      fuente: "INEGI · Censo 2020",
      enfoque: "demografia"
    },
    "vivienda" => %{
      nombre: "Vivienda",
      fuente: "SHF · SNIIV · INEGI",
      enfoque: "urbanismo"
    },
    "voronoi" => %{nombre: "Área por negocio", fuente: "INEGI · DENUE", enfoque: "comercio"},
    "isocrona" => %{nombre: "Alcance en auto", fuente: "OSRM", enfoque: "movilidad"},
    "transporte" => %{nombre: "Transporte público", fuente: "GTFS · OSM", enfoque: "movilidad"},
    "coloreado" => %{
      nombre: "Municipios",
      fuente: "INEGI · Marco Geoestadístico",
      enfoque: "urbanismo"
    }
  }

  @tonos ~w(consumo seguridad laboral)

  # Los acetatos que se citan: los de fuentes públicas. "Tus datos" es del
  # equipo y nunca va en un enlace permanente (docs/producto/citar.md).
  @citables ~w(coropleta vivienda voronoi coloreado isocrona transporte)

  # Alcances apilados: cada uno con una tinta, en este orden.
  @tintas_isocrona ~w(movilidad urbanismo comercio seguridad demografia)
  @max_isocronas length(@tintas_isocrona)

  # Con estas rutas o menos, cada una va con el color que le da su GTFS; con
  # más, una sola tinta con el grosor por frecuencia (si no, es confeti).
  @max_rutas_con_color 20

  @impl true
  def render(assigns) do
    assigns = assign(assigns, capas: @capas, citables: @citables)

    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="mapa" full_width?={true}>
      <:membrete>
        <div class="ubicacion">
          <.live_component
            module={MapoWeb.ZonaSelector}
            id="zona"
            zona={@zona}
            scope={@current_scope}
          />
        </div>
      </:membrete>

      <h1 class="sr-only">Mapa técnico</h1>

      <div
        id="mapa-tecnico"
        phx-hook="MapaTecnico"
        phx-update="ignore"
        data-mesa="neutra"
        class="plano-gl flex-1 min-h-0 w-full"
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
          abiertas={@abiertas}
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
        /> <.cinta_coloreado :if={id == "coloreado"} activa?={@coloreado_activa?} />
        <.cinta_vivienda
          :if={id == "vivienda"}
          form={@vivienda_form}
          catalogo={@vivienda_catalogo}
          activa?={@vivienda_activa?}
          escala={@vivienda_escala}
          meta={@vivienda_meta}
          ficha={@vivienda_ficha}
        />
        <.cinta_isocrona
          :if={id == "isocrona"}
          form={@isocrona_form}
          isocronas={@isocronas}
          poniendo?={@isocrona_poniendo?}
          poblacion={@isocrona_poblacion}
        />
        <.cinta_transporte
          :if={id == "transporte"}
          activa?={@transporte_activa?}
          meta={@transporte_meta}
          color={@transporte_color}
        />
        <div :if={id in @citables and activa?(assigns, id)} class="cinta-citar">
          <button
            type="button"
            id={"citar-#{id}"}
            class="enlace"
            phx-click="citar"
            phx-value-capa={id}
            aria-expanded={to_string(@citando == id)}
          >
            {if @citando == id, do: "Cerrar la cita", else: "Cómo citar"}
          </button>

          <Cita.como_citar
            :if={@citando == id}
            id={"cita-#{id}"}
            citas={@citas}
            enlace={@cita_enlace}
          />
        </div>

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
      </dl>

      <nav
        id="charola"
        class="charola"
        aria-label="Acetatos"
        aria-describedby="charola-ayuda"
        phx-hook="Charola"
      >
        <p id="charola-ayuda" class="sr-only">
          Arrastra una pestaña para cambiar el orden de la pila; con teclado, abre su cinta y usa Más arriba o Más abajo.
        </p>
        <%!-- Solo en pantallas angostas: la charola se pliega en una lista. --%>
        <button
          type="button"
          class="charola-boton"
          aria-expanded="false"
          aria-controls="charola"
          phx-click={
            JS.toggle_class("abierta", to: "#charola")
            |> JS.toggle_attribute({"aria-expanded", "true", "false"})
          }
        >
          <b>Acetatos</b> <em>{encima(assigns)}</em> <span aria-hidden="true">▴</span>
        </button>

        <button
          type="button"
          class="pestana"
          phx-click={elegir_js("marcas")}
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
          id={"pestana-#{id}"}
          type="button"
          class="pestana"
          data-capa={id}
          phx-click={elegir_js(id)}
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

  attr :form, :any, required: true
  attr :catalogo, :map, default: nil
  attr :activa?, :boolean, required: true
  attr :escala, :map, default: nil
  attr :meta, :map, default: nil
  attr :ficha, :map, default: nil

  defp cinta_vivienda(assigns) do
    ~H"""
    <p :if={is_nil(@catalogo)} class="cinta-texto">
      No se pudo leer la lista de indicadores: mapo_core no responde.
    </p>

    <.form
      :if={@catalogo}
      for={@form}
      id="vivienda_capa_form"
      phx-change="cambiar_vivienda"
      phx-submit="mostrar_vivienda"
      class="cinta-campos"
    >
      <.input
        field={@form[:indicador]}
        type="select"
        label="Indicador"
        options={opciones_vivienda(@catalogo)}
        class="cinta-control"
      />
      <.input
        :if={sniiv?(@form)}
        field={@form[:anio]}
        type="select"
        label="Año"
        prompt="Último completo"
        options={opciones_anios(@catalogo)}
        class="cinta-control"
      />
      <.input
        :if={sniiv?(@form)}
        field={@form[:segmento]}
        type="select"
        label="Segmento"
        prompt="Todos"
        options={@catalogo["segmentos"]}
        class="cinta-control"
      />
      <div class="cinta-botones">
        <.button phx-disable-with="Poniendo..." class="boton primario">
          {if @activa?, do: "Actualizar", else: "Poner"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_vivienda" class="boton">
          Quitar
        </.button>
      </div>
    </.form>

    <div :if={@meta} class="cinta-texto cinta-metodo">
      <p>
        <b>{@meta["indicador"]["etiqueta"]}</b>, {@meta["indicador"]["unidad"]}, por {@meta["nivel"]}.
      </p>

      <p>{@meta["metodo"]}</p>
    </div>
    <.escala escala={@escala} tinta="urbanismo" />
    <p :if={@activa? and is_nil(@ficha)} class="cinta-texto">
      {if @meta["nivel"] == "AGEB",
        do: "Toca una AGEB para ver su valor o su rango.",
        else: "Toca un municipio para ver sus cuatro fuentes por separado."}
    </p>
    <.ficha_vivienda :if={@ficha} ficha={@ficha} />
    """
  end

  attr :ficha, :map, required: true

  defp ficha_vivienda(assigns) do
    ~H"""
    <div id="ficha-vivienda" class="cinta-ficha">
      <div class="cinta-ficha-titulo">
        <h3>{@ficha["nombre"]}</h3>
        <button type="button" phx-click="cerrar_ficha_vivienda" class="enlace">Cerrar</button>
      </div>

      <div class="fuentes">
        <section aria-label="Índice SHF">
          <h4>Índice SHF de precios</h4>

          <%= if shf = @ficha["shf"] do %>
            <p class="nivel">
              {if shf["nivel"] == "municipio",
                do: "Del municipio",
                else: "Del estado: SHF no lo publica para este municipio"} · 2018 = 100
            </p>

            <dl class="ficha-datos">
              <dt>{shf["ultimo"]["anio"]} T{shf["ultimo"]["trimestre"]}</dt>

              <dd>{cifra(shf["ultimo"]["indice"] * 1.0)}</dd>

              <dt>Cambio en un año</dt>

              <dd>{con_unidad(shf["variacion_anual"], "%")}</dd>
            </dl>
            <.serie_shf serie={shf["serie"]} nombre={shf["nombre"]} />
          <% else %>
            <p class="nivel">Sin serie cargada.</p>
          <% end %>
        </section>

        <section aria-label="SNIIV">
          <h4>Créditos y subsidios (SNIIV)</h4>

          <%= if sniiv = @ficha["sniiv"] do %>
            <p class="nivel">
              Del municipio, {sniiv["anio"]}. Lo prestado, no el precio. Acciones · monto promedio.
            </p>

            <dl class="ficha-datos">
              <%= for s <- sniiv["segmentos"] do %>
                <dt>{s["segmento"]}</dt>

                <dd>
                  {cifra(s["acciones"])} · {pesos(s["promedio"])}{con_monto(s)}
                </dd>
              <% end %>
            </dl>

            <p class="nivel">
              Destinos: {Enum.map_join(sniiv["destinos"], ", ", fn [d, n] -> "#{d} (#{cifra(n)})" end)}
            </p>
          <% else %>
            <p class="nivel">Sin registros completos en el SNIIV.</p>
          <% end %>
        </section>

        <section aria-label="Intercensal 2025">
          <h4>Tenencia (Intercensal 2025)</h4>

          <%= if eic = @ficha["eic"] do %>
            <p class="nivel">Del municipio, por muestra. CV: coeficiente de variación.</p>

            <dl class="ficha-datos">
              <%= for e <- eic do %>
                <dt>{e["etiqueta"]}</dt>

                <dd>{valor_eic(e)}</dd>
              <% end %>
            </dl>
          <% else %>
            <p class="nivel">Sin dato de la Intercensal.</p>
          <% end %>
        </section>

        <section aria-label="ENVI 2020">
          <h4>Renta y valor (ENVI 2020)</h4>

          <%= if envi = @ficha["envi"] do %>
            <p class="nivel">Del estado: la ENVI no llega a municipio.</p>

            <dl class="ficha-datos">
              <%= for e <- envi do %>
                <dt>{e["etiqueta"]}</dt>

                <dd>{valor_envi(e)}</dd>
              <% end %>
            </dl>
          <% else %>
            <p class="nivel">Sin dato de la ENVI.</p>
          <% end %>
        </section>
      </div>
    </div>
    """
  end

  attr :serie, :list, required: true
  attr :nombre, :string, required: true

  # Serie trimestral del índice SHF: una línea, sin leyenda (el título la
  # nombra), con la base 2018 = 100 punteada. Cada trimestre lleva su <title>
  # para leer el valor al pasar el cursor, y la tabla completa va plegada.
  defp serie_shf(assigns) do
    assigns = assign(assigns, :g, geometria_serie(assigns.serie))

    ~H"""
    <figure class="serie-shf">
      <div class="serie-eje">
        <span>{cifra(@g.hi * 1.0)}</span>
      </div>

      <svg
        viewBox={"0 0 #{@g.ancho} #{@g.alto}"}
        preserveAspectRatio="none"
        role="img"
        aria-label={"Índice SHF de #{@nombre}: #{@g.resumen}"}
      >
        <line
          x1="0"
          x2={@g.ancho}
          y1={@g.y100}
          y2={@g.y100}
          class="serie-base"
          vector-effect="non-scaling-stroke"
        /> <polyline points={@g.puntos} class="serie-linea" vector-effect="non-scaling-stroke" />
        <rect
          :for={h <- @g.huecos}
          x={h.x}
          y="0"
          width={h.ancho}
          height={@g.alto}
          class="serie-hueco"
        >
          <title>{h.texto}</title>
        </rect>
      </svg>

      <div class="serie-eje">
        <span>{cifra(@g.lo * 1.0)}</span>
      </div>

      <figcaption class="serie-eje">
        <span>{@g.desde}</span> <span>base 2018 = 100</span> <span>{@g.hasta}</span>
      </figcaption>

      <details class="serie-tabla">
        <summary>Ver la serie</summary>

        <table>
          <thead>
            <tr>
              <th scope="col">Trimestre</th><th scope="col">Índice</th>
            </tr>
          </thead>

          <tbody>
            <tr :for={[a, t, v] <- Enum.reverse(@serie)}>
              <td>{a} T{t}</td>

              <td>{cifra(v * 1.0)}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </figure>
    """
  end

  # Coordenadas en un lienzo de 300 x 64; el dominio incluye 100 para que la
  # base siempre se vea. El SVG se estira a lo ancho y el trazo no se deforma.
  defp geometria_serie(serie) do
    {ancho, alto, margen} = {300, 64, 3}
    valores = Enum.map(serie, fn [_a, _t, v] -> v end)
    lo = min(Enum.min(valores), 100)
    hi = max(Enum.max(valores), 100)
    n = length(serie)
    paso = if n > 1, do: ancho / (n - 1), else: ancho
    x = fn i -> if n > 1, do: i * paso, else: ancho / 2 end
    y = fn v -> margen + (hi - v) / max(hi - lo, 1.0e-9) * (alto - 2 * margen) end
    [[a0, t0, v0] | _] = serie
    [an, tn, vn] = List.last(serie)

    %{
      ancho: ancho,
      alto: alto,
      lo: lo,
      hi: hi,
      y100: Float.round(y.(100) * 1.0, 2),
      puntos:
        serie
        |> Enum.with_index()
        |> Enum.map_join(" ", fn {[_a, _t, v], i} ->
          "#{Float.round(x.(i) * 1.0, 2)},#{Float.round(y.(v) * 1.0, 2)}"
        end),
      huecos:
        serie
        |> Enum.with_index()
        |> Enum.map(fn {[a, t, v], i} ->
          %{
            x: Float.round(max(x.(i) - paso / 2, 0) * 1.0, 2),
            ancho: Float.round(paso * 1.0, 2),
            texto: "#{a} T#{t}: #{cifra(v * 1.0)}"
          }
        end),
      desde: "#{a0} T#{t0}",
      hasta: "#{an} T#{tn}",
      resumen: "de #{cifra(v0 * 1.0)} en #{a0} T#{t0} a #{cifra(vn * 1.0)} en #{an} T#{tn}"
    }
  end

  defp sniiv?(form), do: String.starts_with?(form[:indicador].value || "", "sniiv_")

  defp opciones_vivienda(%{"indicadores" => indicadores}) do
    indicadores
    |> Enum.chunk_by(& &1["fuente"])
    |> Enum.map(fn [%{"fuente" => f} | _] = grupo ->
      {f, Enum.map(grupo, &{"#{&1["etiqueta"]} (#{&1["unidad"]})", &1["clave"]})}
    end)
  end

  defp opciones_anios(%{"anios_sniiv" => anios}) do
    Enum.map(anios, fn
      %{"anio" => a, "meses" => 12} -> {to_string(a), a}
      %{"anio" => a, "meses" => m} -> {"#{a} (#{m} de 12 meses)", a}
    end)
  end

  defp con_unidad(nil, _unidad), do: "sin dato"
  defp con_unidad(v, "%"), do: "#{cifra(v * 1.0)} %"

  # El promedio sale solo de las acciones con monto; si no son todas, se dice.
  defp con_monto(%{"con_monto" => c, "acciones" => a}) when is_integer(c) and c < a,
    do: " (#{cifra(c)} con monto)"

  defp con_monto(_segmento), do: ""

  defp pesos(nil), do: "sin dato"
  defp pesos(v), do: "$#{cifra(round(v))}"

  defp valor_eic(%{"valor" => nil, "nota" => nota}), do: "sin dato (#{nota || "no publicado"})"
  defp valor_eic(%{"unidad" => "viviendas", "valor" => v}), do: cifra(round(v))

  defp valor_eic(%{"valor" => v, "cv" => cv}) when is_number(cv),
    do: "#{cifra(v * 1.0)} % · CV #{cifra(cv * 1.0)}"

  defp valor_eic(%{"valor" => v}), do: "#{cifra(v * 1.0)} %"

  defp valor_envi(%{"valor" => nil}), do: "sin dato"
  defp valor_envi(%{"unidad" => "pesos", "valor" => v}), do: pesos(v)

  defp valor_envi(%{"valor" => v, "error_estandar" => ee}) when is_number(ee),
    do: "#{cifra(v * 1.0)} % ± #{cifra(ee * 1.0)}"

  defp valor_envi(%{"valor" => v}), do: "#{cifra(v * 1.0)} %"

  # El catálogo de la vista se pide la primera vez que se abre su cinta (o
  # cuando la URL trae un indicador de vivienda).
  defp cargar_catalogo_vivienda(%{assigns: %{elegida: "vivienda"}} = socket),
    do: catalogo_vivienda(socket)

  defp cargar_catalogo_vivienda(socket), do: socket

  defp catalogo_vivienda(%{assigns: %{vivienda_catalogo: nil}} = socket) do
    case MapoCore.vivienda_catalogo() do
      {:ok, catalogo} -> assign(socket, vivienda_catalogo: catalogo)
      {:error, _} -> socket
    end
  end

  defp catalogo_vivienda(socket), do: socket

  attr :escala, :map, default: nil
  attr :tinta, :string, default: nil, doc: "enfoque del acetato; sin él, demografía"

  defp escala(assigns) do
    ~H"""
    <div
      :if={@escala}
      class="escala"
      aria-label="Clases por quintil"
      style={@tinta && "--tinta-escala: var(--f-#{@tinta})"}
    >
      <ol>
        <li :for={o <- [0.12, 0.26, 0.42, 0.6, 0.8]} style={"opacity: #{o}"}></li>

        <li class="nula" title="Sin dato"></li>
      </ol>

      <div class="marcas num">
        <span :for={v <- Enum.take(@escala.limites, 5)}>{cifra(v)}</span>
        <span :if={@escala.nulos}>sin dato: {@escala.nulos}</span>
      </div>
    </div>
    """
  end

  attr :capas, :list, required: true
  attr :abiertas, :list, required: true

  defp cinta_propios(assigns) do
    abiertas = Enum.map(assigns.abiertas, & &1.capa.id)

    assigns =
      assign(assigns,
        cerradas: Enum.reject(assigns.capas, &(&1.id in abiertas)),
        tope: length(@tonos)
      )

    ~H"""
    <p :if={@capas == []} class="cinta-texto">
      Sube un archivo desde la página de <.link navigate={~p"/teams"} class="enlace">tu equipo</.link>.
    </p>

    <ul :if={@abiertas != []} class="capas-abiertas">
      <li :for={a <- @abiertas} style={"--tinta-escala: var(--f-#{a.tono})"}>
        <div class="capa-abierta">
          <span class="muestra" aria-hidden="true"></span> <b>{a.capa.nombre}</b>
          <button
            type="button"
            phx-click="quitar_capa"
            phx-value-id={a.capa.id}
            aria-label={"Quitar #{a.capa.nombre}"}
          >
            Quitar
          </button>
        </div>

        <.form
          :if={a.capa.tipo not in ~w(puntos raster) and a.capa.numericas != []}
          for={%{}}
          as={:pintar}
          id={"pintar_#{a.capa.id}"}
          phx-change="pintar_capa"
        >
          <input type="hidden" name="capa" value={a.capa.id} />
          <select
            name="columna"
            class="cinta-control"
            aria-label={"Pintar #{a.capa.nombre} por"}
            disabled={a.capa.repetidas > 0}
          >
            <option value="">Sin pintar por columna</option>
            {Phoenix.HTML.Form.options_for_select(a.capa.numericas, a.columna)}
          </select>
        </.form>

        <.form
          :if={a.capa.tipo in ~w(puntos vector) and a.capa.fechas != []}
          for={%{}}
          as={:fechas}
          id={"fechas_#{a.capa.id}"}
          phx-change="fechar_capa"
          class="capa-fechas"
        >
          <input type="hidden" name="capa" value={a.capa.id} />
          <select
            :if={length(a.capa.fechas) > 1}
            name="columna"
            class="cinta-control"
            aria-label={"Columna de fecha de #{a.capa.nombre}"}
          >
            {Phoenix.HTML.Form.options_for_select(a.capa.fechas, a.fecha && elem(a.fecha, 0))}
          </select>

          <input
            :if={length(a.capa.fechas) == 1}
            type="hidden"
            name="columna"
            value={hd(a.capa.fechas)}
          />
          <label>
            Desde
            <input
              type="date"
              name="desde"
              class="cinta-control"
              value={a.fecha && elem(a.fecha, 1)}
            />
          </label>

          <label>
            hasta
            <input
              type="date"
              name="hasta"
              class="cinta-control"
              value={a.fecha && elem(a.fecha, 2)}
            />
          </label>
        </.form>
        <.escala escala={a.escala} />
        <p class="cinta-texto">
          <span :if={a.fecha}>{cifra(a.visibles)} en el rango, de</span> {resumen_capa(a.capa)}
          <span :if={a.capa.repetidas > 0}>
            Hay zonas con más de un renglón: para pintar por columna se necesita uno por zona.
          </span>
        </p>
      </li>
    </ul>

    <.form
      :if={@cerradas != [] and length(@abiertas) < @tope}
      for={%{}}
      as={:propios}
      id="capa_propia_form"
      phx-change="agregar_capa"
      class="cinta-campos"
    >
      <label>
        <span class="etiqueta">Agregar capa</span>
        <select name="capa" class="cinta-control">
          <option value="">Elige una</option>
          {Phoenix.HTML.Form.options_for_select(opciones_capas(@cerradas), nil)}
        </select>
      </label>
    </.form>
    """
  end

  attr :activa?, :boolean, required: true
  attr :meta, :map, default: nil
  attr :color, :string, default: "frecuencia"

  # Las rutas del GTFS con su frecuencia en hora pico; si ningún GTFS toca el
  # municipio, las de OSM, dichas como tales. Cada feed con su productor, su
  # licencia tal como la declara y la fecha con que se contaron las frecuencias.
  defp cinta_transporte(assigns) do
    ~H"""
    <div class="cinta-campos">
      <div class="cinta-botones">
        <.button
          type="button"
          phx-click="mostrar_transporte"
          phx-disable-with="Poniendo..."
          class="boton primario"
        >
          {if @activa?, do: "Actualizar", else: "Poner"}
        </.button>

        <.button :if={@activa?} type="button" phx-click="quitar_transporte" class="boton">
          Quitar
        </.button>
      </div>
    </div>

    <%= cond do %>
      <% is_nil(@meta) -> %>
        <p class="cinta-texto">
          Rutas y paradas de la zona, con cada cuánto pasan de 7 a 9 de la mañana de un día hábil. Hasta 5,000 km²: una metrópoli sí, un estado no.
        </p>
      <% @meta["origen"] == "osm" and @meta["resumen"]["rutas"] == 0 -> %>
        <p class="cinta-texto">
          Ningún GTFS ni OpenStreetMap tiene rutas que pasen por {@meta["zona"]["nombre"]}.
        </p>
      <% @meta["origen"] == "osm" -> %>
        <p class="cinta-texto">
          {cifra(@meta["resumen"]["rutas"])} rutas de OpenStreetMap: ninguna ciudad cercana publica GTFS, así que no hay horarios ni frecuencias, solo el trazo que alguien mapeó.
        </p>
      <% true -> %>
        <p class="cinta-texto">
          {cifra(@meta["resumen"]["rutas"])} rutas pasan por {@meta["zona"]["nombre"]}; {frecuentes(
            @meta
          )} pasan cada {@meta["frecuente_min"]} minutos o menos {@meta["pico"]}.
        </p>

        <.form
          :if={@meta["con_color"] > 0}
          for={%{}}
          as={:rutas}
          id="transporte_color_form"
          phx-change="color_rutas"
          class="cinta-campos"
        >
          <label>
            <span class="etiqueta">Color de las rutas</span>
            <select name="color" class="cinta-control">
              {Phoenix.HTML.Form.options_for_select(
                [{"Una tinta, por frecuencia", "frecuencia"}, {"El de cada ruta (GTFS)", "ruta"}],
                @color
              )}
            </select>
          </label>
        </.form>
        <p class="cinta-texto">
          {if @color == "ruta",
            do: "Cada ruta con el color que le da su GTFS; el grosor dice cada cuánto pasa.",
            else: "Más gruesa y con más tinta, pasa más seguido."} Pasa el cursor por una para resaltarla.
        </p>

        <ul class={["cinta-clases", @color == "ruta" && "sin-tinta"]} aria-label="Cada cuánto pasa">
          <li :for={c <- ~w(10 15 30 mas sin_dato)} :if={@meta["resumen"]["por_clase"][c]}>
            <span class={"muestra-linea linea-#{c}"} aria-hidden="true"></span> {@meta["clases"][c]}: {cifra(
              @meta["resumen"]["por_clase"][c]
            )}
          </li>
        </ul>
    <% end %>

    <ul :if={@meta && @meta["feeds"] != []} class="cinta-fuentes">
      <li :for={f <- @meta["feeds"]}>
        <b>{f["productor"]}</b>: {f["titulo"]}. {licencia_feed(f)}<span :if={f["fecha_ref"]}>; frecuencias del {f[
          "fecha_ref"
        ]}</span><span :if={f["vencido"]}>; vencido el {f["vigencia_fin"]}</span>.
        <span :if={!f["frecuencia_util"] and f["feed"] != "osm"}>
          Trae la misma frecuencia en casi todas sus rutas (de relleno): no se usa.
        </span>
      </li>
    </ul>
    """
  end

  defp frecuentes(%{"resumen" => %{"por_clase" => c}}),
    do: cifra((c["10"] || 0) + (c["15"] || 0))

  defp licencia_feed(%{"licencia" => nil}), do: "Sin licencia declarada"
  defp licencia_feed(%{"licencia" => l}), do: "Licencia #{String.replace(l, "-", " ")}"

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
        "Cada celda es la parte de la zona más cerca de ese negocio que de otro. Celda grande, poca oferta. Los de fuera a 5 km o menos también compiten."}
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
      Los municipios de los estados que toca la zona, sin dos vecinos del mismo tono.
    </p>
    """
  end

  attr :form, :any, required: true
  attr :isocronas, :list, required: true
  attr :poniendo?, :boolean, required: true
  attr :poblacion, :map, default: nil

  # Alcances apilados (docs/producto/isocronas.md): cada uno con su tinta y su
  # número, la gente dentro de cada uno y, con dos o más, en todos y en alguno.
  defp cinta_isocrona(assigns) do
    assigns = assign(assigns, tope: @max_isocronas, tintas: @tintas_isocrona)

    ~H"""
    <.form for={@form} id="isocrona_capa_form" phx-submit="agregar_isocrona" class="cinta-campos">
      <.input
        field={@form[:minutos]}
        type="number"
        label="Minutos"
        min="1"
        max="120"
        class="cinta-control cinta-corto"
      />
      <div class="cinta-botones">
        <.button
          :if={not @poniendo?}
          class="boton primario"
          disabled={length(@isocronas) >= @tope}
        >
          {if @isocronas == [], do: "Poner", else: "Agregar otro"}
        </.button>

        <.button :if={@poniendo?} type="button" phx-click="cancelar_isocrona" class="boton">
          Cancelar
        </.button>

        <.button :if={@isocronas != []} type="button" phx-click="quitar_isocrona" class="boton">
          Quitar todos
        </.button>
      </div>
    </.form>

    <p class="cinta-texto">
      <%= cond do %>
        <% @poniendo? -> %>
          Haz clic en el plano para elegir el punto de salida.
        <% @isocronas == [] -> %>
          Hasta dónde llegas en auto desde un punto. Se apilan hasta {@tope} para comparar cuánta gente queda dentro de cada uno.
        <% length(@isocronas) >= @tope -> %>
          Ya hay {@tope}: quita uno para agregar otro.
        <% true -> %>
          Agrega otro, con otros minutos o desde otro punto, para compararlos.
      <% end %>
    </p>

    <ol :if={@isocronas != []} class="alcances">
      <li
        :for={{iso, i} <- Enum.with_index(@isocronas)}
        style={"--tinta-escala: var(--f-#{Enum.at(@tintas, i)})"}
      >
        <span class="alcance-numero num" aria-hidden="true">{i + 1}</span>
        <span class="alcance-que">
          {minutos_texto(iso.minutos)} min desde
          <span class="num">{cifra(iso.lat, 4)}, {cifra(iso.lon, 4)}</span>
          <em :if={iso.metodo != "osrm_real"}>(círculo aproximado: OSRM no respondió)</em>
          <b class="num">{personas(@poblacion, i)}</b>
        </span>
        <button
          type="button"
          phx-click="quitar_isocrona"
          phx-value-n={i}
          aria-label={"Quitar el alcance #{i + 1}"}
        >
          Quitar
        </button>
      </li>
    </ol>

    <dl :if={@poblacion && @poblacion["en_todas"]} class="alcances-suma">
      <div>
        <dt>En todos</dt>
        <dd class="num">{personas(@poblacion["en_todas"])}</dd>
      </div>
      <div>
        <dt>En alguno</dt>
        <dd class="num">{personas(@poblacion["en_alguna"])}</dd>
      </div>
    </dl>

    <p :if={@poblacion && @poblacion["en_todas"]} class="cinta-texto">
      {if @poblacion["interseccion"],
        do: "El contorno grueso es la parte que comparten todos.",
        else: "No hay una parte que compartan todos."}
    </p>

    <p :if={@poblacion} class="cinta-texto cinta-metodo">{@poblacion["metodo"]}</p>
    <p :if={@isocronas != [] and is_nil(@poblacion)} class="cinta-texto">
      No se pudo contar la gente dentro: mapo_core no respondió.
    </p>
    """
  end

  defp personas(nil, _i), do: ""
  defp personas(%{"cada_una" => cada}, i), do: personas(Enum.at(cada, i))

  defp personas(%{"personas" => n, "reservados" => r}) when r > 0,
    do:
      "#{cifra(n)} personas, sin #{r} #{if r == 1, do: "lugar", else: "lugares"} con dato reservado"

  defp personas(%{"personas" => n}), do: "#{cifra(n)} personas"
  defp personas(_), do: ""

  @impl true
  def mount(_params, _session, socket) do
    sesiones = Sesiones.list_sesiones_del_usuario(socket.assigns.current_scope)

    {:ok,
     assign(socket,
       # La mesa neutra desde el primer render (el hook la pone al navegar).
       piel_raiz: "neutra",
       zona: nil,
       indicadores: Enum.map(MapoCore.indicadores_censo(), fn {c, e} -> {e, c} end),
       form: to_form(%{"cve_ent" => "", "cve_mun" => ""}, as: "mapa"),
       coropleta_form: to_form(%{"indicador" => "pobtot"}, as: "coropleta_capa"),
       voronoi_form: to_form(%{"clase_actividad" => ""}, as: "voronoi_capa"),
       isocrona_form: to_form(%{"minutos" => "10"}, as: "isocrona_capa"),
       isocronas: [],
       isocrona_poniendo?: false,
       isocrona_poblacion: nil,
       coropleta_activa?: false,
       voronoi_activa?: false,
       voronoi_resumen: nil,
       coloreado_activa?: false,
       transporte_activa?: false,
       transporte_meta: nil,
       transporte_color: "frecuencia",
       coropleta_escala: nil,
       vivienda_form:
         to_form(%{"indicador" => "eic_alqui", "anio" => "", "segmento" => ""},
           as: "vivienda_capa"
         ),
       vivienda_catalogo: nil,
       vivienda_activa?: false,
       vivienda_escala: nil,
       vivienda_meta: nil,
       vivienda_ficha: nil,
       capas_propias: Capas.list_capas_del_usuario(socket.assigns.current_scope),
       abiertas: [],
       orden: [
         "propios",
         "isocrona",
         "transporte",
         "voronoi",
         "vivienda",
         "coropleta",
         "coloreado"
       ],
       elegida: nil,
       sesiones: sesiones,
       sesion: nil,
       herramienta: "punto",
       num_marcas: 0,
       url_params: [],
       reconstruida?: false,
       citando: nil,
       citas: [],
       cita_enlace: nil
     )}
  end

  @impl true
  def handle_params(params, _uri, socket) do
    socket =
      socket
      |> cambiar_sesion(params["sesion"])
      |> abrir_capa_de_la_url(params["capa"])

    # La vista se reconstruye de la URL una sola vez, al conectar: los
    # cambios de después los escribe `sincronizar_url` y no hay que volver a
    # aplicarlos. El render estático no llega al hook.
    if connected?(socket) and not socket.assigns.reconstruida? do
      {:noreply,
       socket
       |> assign(reconstruida?: true, url_params: leidos(params))
       |> reconstruir(params)
       |> sincronizar_url()}
    else
      {:noreply, socket}
    end
  end

  @impl true
  def handle_event("elegir", %{"capa" => capa}, socket)
      when is_map_key(@capas, capa) or capa == "marcas" do
    elegida = if socket.assigns.elegida == capa, do: nil, else: capa

    {:noreply,
     socket
     |> assign(elegida: elegida)
     |> cargar_catalogo_vivienda()
     |> modo_marcas()
     |> sincronizar_url()}
  end

  def handle_event("elegir_sesion", %{"sesion" => id}, socket) do
    {:noreply, socket |> cambiar_sesion(vacio_para_nil(id)) |> sincronizar_url()}
  end

  # La cita se arma al pedirla: así la fecha de consulta y el enlace son los
  # de ese momento, y la fecha de carga de la tabla no se pide en cada capa.
  def handle_event("citar", %{"capa" => capa}, socket) when capa in @citables do
    if socket.assigns.citando == capa do
      {:noreply, assign(socket, citando: nil)}
    else
      a = socket.assigns
      enlace = Cita.enlace(ruta_mapa(params_url(%{a | elegida: capa})))

      {:noreply,
       assign(socket, citando: capa, citas: citas(a, capa, enlace), cita_enlace: enlace)}
    end
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

  # El arrastre de las pestañas manda la pila entera; solo se acepta si son
  # las mismas capas en otro orden.
  def handle_event("ordenar", %{"orden" => orden}, socket) when is_list(orden) do
    if Enum.sort(orden) == Enum.sort(socket.assigns.orden),
      do: {:noreply, socket |> assign(orden: orden) |> actualizar_mesa()},
      else: {:noreply, socket}
  end

  def handle_event("ordenar", _params, socket), do: {:noreply, socket}

  def handle_event(
        "mostrar_coropleta",
        %{"coropleta_capa" => %{"indicador" => indicador}},
        socket
      ) do
    {:noreply, socket |> poner_coropleta(indicador) |> sincronizar_url()}
  end

  def handle_event("quitar_coropleta", _params, socket) do
    {:noreply,
     socket
     |> assign(coropleta_activa?: false, coropleta_escala: nil)
     |> push_event("capa_coropleta", %{activa: false})
     |> actualizar_mesa()
     |> sincronizar_url()}
  end

  def handle_event(
        "mostrar_voronoi",
        %{"voronoi_capa" => %{"clase_actividad" => clase_actividad}},
        socket
      ) do
    {:noreply, socket |> poner_voronoi(clase_actividad) |> sincronizar_url()}
  end

  def handle_event("mostrar_transporte", _params, socket) do
    {:noreply, socket |> poner_transporte() |> sincronizar_url()}
  end

  def handle_event("color_rutas", %{"color" => color}, socket)
      when color in ~w(frecuencia ruta) do
    {:noreply,
     socket |> assign(transporte_color: color) |> push_event("color_rutas", %{color: color})}
  end

  def handle_event("quitar_transporte", _params, socket) do
    {:noreply,
     socket
     |> assign(transporte_activa?: false, transporte_meta: nil)
     |> push_event("capa_transporte", %{activa: false})
     |> actualizar_mesa()
     |> sincronizar_url()}
  end

  def handle_event("quitar_voronoi", _params, socket) do
    {:noreply,
     socket
     |> assign(voronoi_activa?: false, voronoi_resumen: nil)
     |> push_event("capa_voronoi", %{activa: false})
     |> actualizar_mesa()
     |> sincronizar_url()}
  end

  def handle_event("agregar_capa", %{"capa" => id}, socket) do
    {:noreply, abrir_capa(socket, id)}
  end

  def handle_event("quitar_capa", %{"id" => id}, socket) do
    {:noreply, cerrar_capa(socket, id)}
  end

  # Repintar trae los datos otra vez: pasan por el scope, como en `abrir_capa`.
  def handle_event("pintar_capa", %{"capa" => id, "columna" => columna}, socket) do
    a = abierta(socket, id)

    case a && Capas.get_capa(socket.assigns.current_scope, a.capa.id) do
      nil -> {:noreply, socket}
      capa -> {:noreply, mostrar_capa(socket, capa, columna, a.tono, a.fecha)}
    end
  end

  # Solo los renglones de un rango de fechas. Una fecha que no se entiende o un
  # rango al revés se ignora: el mapo sigue mostrando lo de antes.
  def handle_event("fechar_capa", %{"capa" => id} = params, socket) do
    a = abierta(socket, id)

    with %{} <- a,
         capa when not is_nil(capa) <- Capas.get_capa(socket.assigns.current_scope, a.capa.id),
         {:ok, fecha} <- rango_fechas(capa, params) do
      {:noreply, mostrar_capa(socket, capa, a.columna, a.tono, fecha)}
    else
      _ -> {:noreply, socket}
    end
  end

  # La ficha se pide al abrirla: mandar los datos de 50 mil renglones al
  # navegador pesaría megas que casi nadie va a abrir.
  # En un ráster, la ficha es el valor del píxel donde se hizo clic.
  def handle_event("ver_fila", %{"capa" => capa_id, "lat" => lat, "lon" => lon}, socket)
      when is_number(lat) and is_number(lon) do
    a = abierta(socket, capa_id)
    respuesta = a && Capas.valor_raster(socket.assigns.current_scope, a.capa.id, lon, lat)
    {:reply, ficha_raster(respuesta), socket}
  end

  def handle_event("ver_fila", %{"capa" => capa_id} = params, socket) do
    llave =
      case params do
        %{"id" => id} when is_integer(id) -> {:id, id}
        %{"clave" => clave} when is_binary(clave) -> {:clave, clave}
        _ -> nil
      end

    a = abierta(socket, capa_id)
    ficha = a && llave && Capas.ficha(socket.assigns.current_scope, a.capa.id, llave)

    case ficha do
      {datos, cuantas} ->
        procedencia = Capas.columnas_procedencia()
        par = fn c -> [c, texto_celda(datos[c])] end

        campos =
          for c <- a.capa.columnas, c not in procedencia, not is_nil(datos[c]), do: par.(c)

        origen = for c <- procedencia, c in a.capa.columnas, not is_nil(datos[c]), do: par.(c)
        {:reply, %{campos: campos, procedencia: origen, otras: cuantas - 1}, socket}

      _ ->
        {:reply, %{campos: [], procedencia: [], otras: 0}, socket}
    end
  end

  def handle_event("cambiar_vivienda", %{"vivienda_capa" => params}, socket) do
    {:noreply, assign(socket, vivienda_form: to_form(params, as: "vivienda_capa"))}
  end

  def handle_event("mostrar_vivienda", %{"vivienda_capa" => params}, socket) do
    {:noreply, socket |> poner_vivienda(params) |> sincronizar_url()}
  end

  def handle_event("quitar_vivienda", _params, socket) do
    {:noreply,
     socket
     |> assign(
       vivienda_activa?: false,
       vivienda_escala: nil,
       vivienda_meta: nil,
       vivienda_ficha: nil
     )
     |> push_event("capa_vivienda", %{activa: false})
     |> actualizar_mesa()
     |> sincronizar_url()}
  end

  # El clic en un municipio del acetato pide su ficha: las cuatro fuentes,
  # cada una con su nivel, en la cinta de la capa.
  def handle_event("ficha_vivienda", %{"cvegeo" => cvegeo}, socket) when is_binary(cvegeo) do
    {:noreply, socket |> abrir_ficha_vivienda(cvegeo) |> sincronizar_url()}
  end

  def handle_event("cerrar_ficha_vivienda", _params, socket),
    do: {:noreply, socket |> assign(vivienda_ficha: nil) |> sincronizar_url()}

  def handle_event("mostrar_coloreado", _params, socket) do
    {:noreply, socket |> poner_coloreado() |> sincronizar_url()}
  end

  def handle_event("quitar_coloreado", _params, socket) do
    {:noreply,
     socket
     |> assign(coloreado_activa?: false)
     |> push_event("capa_coloreado", %{activa: false})
     |> actualizar_mesa()
     |> sincronizar_url()}
  end

  # Agregar un alcance deja el plano esperando el clic del punto de salida.
  def handle_event("agregar_isocrona", %{"isocrona_capa" => %{"minutos" => minutos}}, socket) do
    socket = assign(socket, isocrona_form: to_form(%{"minutos" => minutos}, as: "isocrona_capa"))

    cond do
      length(socket.assigns.isocronas) >= @max_isocronas ->
        {:noreply, socket}

      is_nil(minutos_validos(minutos)) ->
        {:noreply, put_flash(socket, :error, "Los minutos van de 1 a 120.")}

      true ->
        {:noreply,
         socket
         |> assign(isocrona_poniendo?: true)
         |> push_event("modo_isocrona", %{activo: true})
         |> actualizar_mesa()}
    end
  end

  def handle_event("cancelar_isocrona", _params, socket) do
    {:noreply,
     socket
     |> assign(isocrona_poniendo?: false)
     |> push_event("modo_isocrona", %{activo: false})
     |> actualizar_mesa()}
  end

  def handle_event("quitar_isocrona", %{"n" => n}, socket) do
    case Integer.parse(to_string(n)) do
      {i, ""} when i >= 0 ->
        socket = assign(socket, isocronas: List.delete_at(socket.assigns.isocronas, i))
        {:noreply, socket |> pintar_isocronas() |> sincronizar_url()}

      _ ->
        {:noreply, socket}
    end
  end

  def handle_event("quitar_isocrona", _params, socket) do
    {:noreply,
     socket
     |> assign(isocronas: [], isocrona_poniendo?: false, isocrona_poblacion: nil)
     |> push_event("modo_isocrona", %{activo: false})
     |> pintar_isocronas()
     |> sincronizar_url()}
  end

  def handle_event("click_mapa", %{"lat" => lat, "lon" => lon}, socket)
      when is_number(lat) and is_number(lon) do
    if socket.assigns.isocrona_poniendo? do
      minutos = minutos_validos(socket.assigns.isocrona_form[:minutos].value) || 10.0

      {:noreply,
       socket
       |> assign(isocrona_poniendo?: false)
       |> push_event("modo_isocrona", %{activo: false})
       |> calcular_isocrona(lat, lon, minutos)
       |> pintar_isocronas()
       |> sincronizar_url()}
    else
      {:noreply, socket}
    end
  end

  @impl true
  def handle_info({:zona_elegida, zona}, socket) do
    {:noreply, socket |> ubicar(zona) |> reaplicar_capas() |> sincronizar_url()}
  end

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
    # El render inicial no llega al hook: se evita traer la capa dos veces.
    if connected?(socket) and is_nil(abierta(socket, id)) do
      socket |> abrir_capa(id) |> assign(elegida: "propios")
    else
      socket
    end
  end

  defp abierta(socket, id) do
    Enum.find(socket.assigns.abiertas, &(to_string(&1.capa.id) == to_string(id)))
  end

  defp abrir_capa(socket, id) when id in [nil, ""], do: socket

  # La capa se trae otra vez por el scope: la lista es del mount, y pudieron
  # sacar a la persona del equipo o el id pudo venir de la URL.
  defp abrir_capa(socket, id) do
    usados = Enum.map(socket.assigns.abiertas, & &1.tono)
    tono = Enum.find(@tonos, &(&1 not in usados))

    case entero(id) && Capas.get_capa(socket.assigns.current_scope, entero(id)) do
      nil -> put_flash(socket, :error, "Esa capa no es de tus equipos.")
      _ when is_nil(tono) -> put_flash(socket, :error, "Caben #{length(@tonos)} capas a la vez.")
      capa -> mostrar_capa(socket, capa, nil, tono)
    end
  end

  defp rango_fechas(capa, params) do
    dia = fn
      v when v in [nil, ""] -> {:ok, nil}
      v -> with {:ok, d} <- Date.from_iso8601(v), do: {:ok, Date.to_iso8601(d)}
    end

    with true <- params["columna"] in capa.fechas,
         {:ok, desde} <- dia.(params["desde"]),
         {:ok, hasta} <- dia.(params["hasta"]),
         true <- is_nil(desde) or is_nil(hasta) or desde <= hasta do
      {:ok, if(desde || hasta, do: {params["columna"], desde, hasta})}
    else
      _ -> :error
    end
  end

  defp mostrar_capa(socket, capa, columna, tono, fecha \\ nil) do
    columna = if Capas.pintable?(capa, columna), do: columna

    case datos_de_capa(capa, columna, fecha) do
      {:ok, datos, escala} ->
        visibles = if fecha, do: length(datos[:puntos] || datos[:geojson]["features"])

        nueva = %{
          capa: capa,
          columna: columna,
          escala: escala,
          tono: tono,
          fecha: fecha,
          visibles: visibles
        }

        abiertas =
          if abierta(socket, capa.id) do
            Enum.map(socket.assigns.abiertas, &if(&1.capa.id == capa.id, do: nueva, else: &1))
          else
            socket.assigns.abiertas ++ [nueva]
          end

        socket
        |> assign(abiertas: abiertas)
        |> push_event("capa_propios", Map.merge(datos, %{id: capa.id, tono: tono}))
        |> actualizar_mesa()

      {:error, _} ->
        put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
    end
  end

  defp cerrar_capa(socket, id) do
    case abierta(socket, id) do
      nil ->
        socket

      a ->
        socket
        |> update(:abiertas, &List.delete(&1, a))
        |> push_event("capa_propios_fuera", %{id: a.capa.id})
        |> actualizar_mesa()
    end
  end

  defp entero(id) do
    case Integer.parse(to_string(id)) do
      {n, ""} -> n
      _ -> nil
    end
  end

  defp datos_de_capa(%{tipo: "puntos"} = capa, _columna, fecha),
    do: {:ok, %{puntos: Capas.puntos(capa, fecha)}, nil}

  defp datos_de_capa(%{tipo: "raster"} = capa, _columna, _fecha) do
    lugar = Capas.lugar_raster(capa)
    url = ~p"/capas/#{capa.id}/raster.png"
    {:ok, %{raster: Map.put(lugar, :url, url)}, %{limites: lugar.limites, nulos: nil}}
  end

  defp datos_de_capa(%{tipo: "vector"} = capa, columna, fecha) do
    geojson = Capas.geojson(capa, columna, fecha)
    con_escala(geojson, columna)
  end

  defp datos_de_capa(capa, columna, _fecha) do
    with {:ok, geojson} <- MapoCore.geo_por_clave(capa.tipo, Capas.claves(capa)) do
      geojson = if columna, do: con_valores(geojson, Capas.valores(capa, columna)), else: geojson
      con_escala(geojson, columna)
    end
  end

  defp con_escala(geojson, columna) do
    escala = columna && escala_quintiles(geojson)
    {:ok, %{geojson: geojson, cortes: escala && escala.cortes}, escala}
  end

  defp resumen_capa(%{tipo: "raster"} = capa), do: "De #{capa.archivo}."
  defp resumen_capa(capa), do: "#{cifra(capa.num_filas)} renglones de #{capa.archivo}."

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

  defp ficha_raster(%{valor: valor, banda: banda, metros_pixel: metros}) do
    campos = [
      [banda || "valor", if(valor == nil, do: "sin dato", else: texto_celda(valor))],
      ["píxel", "unos #{texto_celda(round(metros))} m de lado"]
    ]

    %{campos: campos, procedencia: [], otras: 0}
  end

  defp ficha_raster(:sin_valores) do
    aviso = "se subió antes de que Mapo guardara los valores: súbela otra vez para consultarlos"
    %{campos: [["valor", aviso]], procedencia: [], otras: 0}
  end

  defp ficha_raster(_), do: %{campos: [], procedencia: [], otras: 0}

  # Sin redondear: la ficha muestra el dato de la persona, no una cifra de lectura.
  defp texto_celda(v) when is_integer(v), do: cifra(v)
  defp texto_celda(v), do: to_string(v)

  ## Poner cada acetato. Sirven igual al botón de la cinta y a la URL.

  defp poner_coropleta(socket, indicador) do
    zona = socket.assigns.zona

    if is_nil(zona) do
      put_flash(socket, :error, "Elige una zona primero.")
    else
      case MapoCore.coropleta_censo_poblacion(indicador, zona["clave"]) do
        {:ok, %{"features" => []}} ->
          put_flash(socket, :error, "Mapo no tiene AGEB o censo cargados en esa zona todavía.")

        {:ok, geojson} ->
          escala = escala_quintiles(geojson)

          socket
          |> assign(
            coropleta_activa?: true,
            coropleta_escala: escala,
            coropleta_form: to_form(%{"indicador" => indicador}, as: "coropleta_capa")
          )
          |> push_event("capa_coropleta", %{
            activa: true,
            geojson: geojson,
            etiqueta: etiqueta_indicador(indicador),
            cortes: escala && escala.cortes
          })
          |> actualizar_mesa()

        {:error, _} ->
          put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
      end
    end
  end

  defp poner_voronoi(socket, clase_actividad) do
    zona = socket.assigns.zona
    clase_actividad = vacio_para_nil(clase_actividad)

    if is_nil(zona) do
      put_flash(socket, :error, "Elige una zona primero.")
    else
      case MapoCore.voronoi_denue(zona["clave"], clase_actividad) do
        {:ok, %{"celdas" => geojson} = respuesta} ->
          socket
          |> assign(
            voronoi_activa?: true,
            voronoi_resumen: resumen_voronoi(respuesta),
            voronoi_form: to_form(%{"clase_actividad" => clase_actividad}, as: "voronoi_capa")
          )
          |> push_event("capa_voronoi", %{activa: true, geojson: geojson})
          |> actualizar_mesa()

        {:error, {:status, 422, body}} ->
          mensaje = if is_map(body), do: body["detail"], else: nil
          put_flash(socket, :error, mensaje || "No hay suficientes negocios con ese filtro.")

        {:error, {:status, 404, _}} ->
          put_flash(socket, :error, "Esa zona no toca nada cargado en Mapo.")

        {:error, _} ->
          put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
      end
    end
  end

  defp poner_transporte(socket) do
    zona = socket.assigns.zona

    if is_nil(zona) do
      put_flash(socket, :error, "Elige una zona primero.")
    else
      case MapoCore.transporte_zona(zona["clave"]) do
        {:ok, %{"rutas" => rutas, "paradas" => paradas} = respuesta} ->
          con_color = Enum.count(rutas["features"], & &1["properties"]["col"])
          total = length(rutas["features"])

          # Al ponerlo, el color de cada ruta si son pocas; luego decide la persona.
          color =
            if socket.assigns.transporte_activa?,
              do: socket.assigns.transporte_color,
              else:
                if(con_color > 0 and total <= @max_rutas_con_color,
                  do: "ruta",
                  else: "frecuencia"
                )

          color = if con_color == 0, do: "frecuencia", else: color

          socket
          |> assign(
            transporte_activa?: true,
            transporte_color: color,
            transporte_meta:
              respuesta |> Map.drop(["rutas", "paradas"]) |> Map.put("con_color", con_color)
          )
          |> push_event("capa_transporte", %{
            activa: true,
            rutas: rutas,
            paradas: paradas,
            origen: respuesta["origen"],
            modos: respuesta["modos"],
            clases: respuesta["clases"],
            color: color
          })
          |> actualizar_mesa()

        {:error, {:status, 422, %{"detail" => detalle}}} when is_binary(detalle) ->
          put_flash(socket, :error, "Transporte: " <> detalle <> ".")

        {:error, {:status, 404, _}} ->
          put_flash(socket, :error, "Esa zona no toca nada cargado en Mapo.")

        {:error, _} ->
          put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
      end
    end
  end

  defp poner_vivienda(socket, params) do
    zona = socket.assigns.zona
    socket = assign(socket, vivienda_form: to_form(params, as: "vivienda_capa"))
    sniiv? = String.starts_with?(params["indicador"] || "", "sniiv_")
    anio = if sniiv?, do: vacio_para_nil(params["anio"])
    segmento = if sniiv?, do: vacio_para_nil(params["segmento"])

    if is_nil(zona) do
      put_flash(socket, :error, "Elige una zona primero.")
    else
      case MapoCore.vivienda_municipios(zona["clave"], params["indicador"], anio, segmento) do
        {:ok, %{"features" => [], "nivel" => "AGEB"}} ->
          put_flash(socket, :error, "Todavía no hay precio de oferta por AGEB en esa zona.")

        {:ok, %{"features" => []}} ->
          put_flash(socket, :error, "No hay municipios cargados en esa zona todavía.")

        {:ok, geojson} ->
          escala = escala_quintiles(geojson)
          meta = Map.take(geojson, ~w(indicador nivel anio meses segmento metodo version))

          socket
          |> assign(vivienda_activa?: true, vivienda_escala: escala, vivienda_meta: meta)
          |> push_event("capa_vivienda", %{
            activa: true,
            geojson: geojson,
            cortes: escala && escala.cortes,
            etiqueta: meta["indicador"]["etiqueta"],
            unidad: meta["indicador"]["unidad"]
          })
          |> actualizar_mesa()

        {:error, {:status, 400, _}} ->
          put_flash(socket, :error, "Ese indicador o segmento no existe.")

        {:error, _} ->
          put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
      end
    end
  end

  # El municipio de la ficha llega como cvegeo; los enlaces de antes de la 29d
  # traen solo el municipio (3 dígitos), del primer estado de la zona.
  defp abrir_ficha_vivienda(socket, <<cve_ent::binary-size(2), cve_mun::binary-size(3)>>),
    do: abrir_ficha_vivienda(socket, cve_ent, cve_mun)

  defp abrir_ficha_vivienda(socket, cve_mun),
    do: abrir_ficha_vivienda(socket, socket.assigns.form[:cve_ent].value, cve_mun)

  defp abrir_ficha_vivienda(socket, cve_ent, cve_mun) do
    case MapoCore.vivienda_ficha(cve_ent, cve_mun) do
      {:ok, ficha} ->
        socket
        |> assign(
          vivienda_ficha: Map.put(ficha, "cvegeo", cve_ent <> cve_mun),
          elegida: "vivienda"
        )
        |> modo_marcas()

      {:error, _} ->
        put_flash(socket, :error, "No se pudo leer la ficha de ese municipio.")
    end
  end

  defp poner_coloreado(socket) do
    zona = socket.assigns.zona

    if is_nil(zona) do
      put_flash(socket, :error, "Elige una zona primero.")
    else
      case MapoCore.coloreado_municipios(zona["clave"]) do
        {:ok, %{"features" => []}} ->
          put_flash(socket, :error, "Mapo no tiene municipios cargados en esa zona todavía.")

        {:ok, geojson} ->
          socket
          |> assign(coloreado_activa?: true)
          |> push_event("capa_coloreado", %{activa: true, geojson: geojson})
          |> actualizar_mesa()

        {:error, _} ->
          put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
      end
    end
  end

  # Un alcance más al final de la pila de alcances. La gente dentro se cuenta
  # aparte (`pintar_isocronas`): al reconstruir de la URL llegan varios juntos.
  defp calcular_isocrona(socket, lat, lon, minutos) do
    case MapoCore.isocrona_calcular(lat, lon, minutos) do
      {:ok, %{"poligono" => poligono, "metodo" => metodo}} ->
        iso = %{lat: lat, lon: lon, minutos: minutos, poligono: poligono, metodo: metodo}
        assign(socket, isocronas: socket.assigns.isocronas ++ [iso])

      {:error, _} ->
        put_flash(socket, :error, "mapo_core no está disponible ahorita mismo.")
    end
  end

  # Cuenta la gente dentro de los alcances y los manda al plano.
  defp pintar_isocronas(%{assigns: %{isocronas: []}} = socket) do
    socket
    |> assign(isocrona_poblacion: nil)
    |> push_event("capa_isocrona", %{activa: false})
    |> actualizar_mesa()
  end

  defp pintar_isocronas(socket) do
    isocronas = socket.assigns.isocronas

    poblacion =
      case MapoCore.isocronas_poblacion(Enum.map(isocronas, & &1.poligono)) do
        {:ok, %{"cada_una" => _} = p} -> p
        _ -> nil
      end

    socket
    |> assign(isocrona_poblacion: poblacion)
    |> push_event("capa_isocrona", %{
      activa: true,
      isocronas:
        isocronas
        |> Enum.with_index()
        |> Enum.map(fn {iso, i} ->
          %{
            poligono: iso.poligono,
            metodo: iso.metodo,
            origen: %{lat: iso.lat, lon: iso.lon},
            tinta: Enum.at(@tintas_isocrona, i)
          }
        end),
      interseccion: poblacion && poblacion["interseccion"]
    })
    |> actualizar_mesa()
  end

  defp minutos_validos(texto) do
    case Float.parse(to_string(texto)) do
      {min, ""} when min >= 1 and min <= 120 -> min
      _ -> nil
    end
  end

  ## Enlace permanente (docs/producto/citar.md).
  #
  # La URL dice lo que se ve: la zona, cada acetato público puesto con sus
  # opciones y la cinta abierta. Se escribe después de
  # cada cambio (sin agregar entradas al historial) y se lee una vez al
  # conectar. Al leerla, cada valor pasa por su catálogo cerrado; uno que no
  # está se ignora sin error. "Tus datos" y las marcas son del equipo: la
  # sesión va en la barra de direcciones (ya iba), nunca en el enlace de la cita.

  defp params_url(a) do
    vivienda = a.vivienda_activa? && a.vivienda_meta

    [
      zona: a.zona && a.zona["clave"],
      censo: a.coropleta_activa? && a.coropleta_form[:indicador].value,
      viv: vivienda && vivienda["indicador"]["clave"],
      anio: vivienda && vivienda["anio"],
      seg: vivienda && vivienda["segmento"],
      ficha: vivienda && a.vivienda_ficha && a.vivienda_ficha["cvegeo"],
      negocios: a.voronoi_activa? && (a.voronoi_form[:clase_actividad].value || ""),
      municipios: a.coloreado_activa? && "1",
      transporte: a.transporte_activa? && "1",
      alcance: alcance_url(a),
      ver: if(a.elegida in Map.keys(@capas) and a.elegida != "propios", do: a.elegida)
    ]
    |> Enum.reject(fn {_k, v} -> v in [nil, false] end)
    |> Enum.map(fn {k, v} -> {k, to_string(v)} end)
  end

  @claves_url ~w(zona censo viv anio seg ficha negocios municipios transporte alcance ver sesion)a

  # Lo que trae la URL, en el orden de `params_url`: si lo reconstruido no es
  # igual (un valor fuera de catálogo), la URL se corrige.
  defp leidos(params) do
    for k <- @claves_url, v = params[Atom.to_string(k)], is_binary(v), do: {k, v}
  end

  # Cada alcance como `lat,lon,minutos`, separados por `;`.
  defp alcance_url(%{isocronas: []}), do: nil

  defp alcance_url(%{isocronas: isocronas}) do
    Enum.map_join(isocronas, ";", fn %{lat: lat, lon: lon, minutos: min} ->
      "#{Float.round(lat / 1, 5)},#{Float.round(lon / 1, 5)},#{minutos_texto(min)}"
    end)
  end

  defp ruta_mapa([]), do: ~p"/mapa"
  # `~p` ordenaría las claves; así el enlace sale en el orden de la vista.
  defp ruta_mapa(params), do: ~p"/mapa" <> "?" <> MapoWeb.ZonaSelector.query(params)

  defp sincronizar_url(socket) do
    a = socket.assigns
    params = params_url(a) ++ if(a.sesion, do: [sesion: to_string(a.sesion.id)], else: [])

    if params == a.url_params do
      socket
    else
      # Lo que se citaba ya no es lo que se ve.
      socket
      |> assign(url_params: params, citando: nil)
      |> push_patch(to: ruta_mapa(params), replace: true)
    end
  end

  defp reconstruir(socket, params) do
    socket
    |> ubicar_de_url(params)
    |> coropleta_de_url(params["censo"])
    |> vivienda_de_url(params)
    |> voronoi_de_url(params["negocios"])
    |> then(&if(params["municipios"] == "1", do: poner_coloreado(&1), else: &1))
    |> then(&if(params["transporte"] == "1", do: poner_transporte(&1), else: &1))
    |> isocrona_de_url(params["alcance"])
    |> ver_de_url(params["ver"])
  end

  # La zona del enlace. Los de antes de la 29b traen `ent` y, quizá, `mun`.
  defp ubicar_de_url(socket, params) do
    clave =
      cond do
        is_binary(params["zona"]) ->
          params["zona"]

        is_binary(params["ent"]) and String.match?(params["ent"], ~r/^\d{2}$/) ->
          if is_binary(params["mun"]) and String.match?(params["mun"], ~r/^\d{3}$/),
            do: "mun:#{params["ent"]}#{params["mun"]}",
            else: "ent:#{params["ent"]}"

        true ->
          nil
      end

    case clave && MapoWeb.ZonaSelector.resolver(clave) do
      {:ok, zona} ->
        socket |> ubicar(zona) |> push_event("zona_elegida", %{geojson: zona["geojson"]})

      # Sin zona en el enlace, la que guardó quien abre.
      nil ->
        case MapoWeb.ZonaSelector.zona_inicial(socket.assigns.current_scope) do
          nil ->
            socket

          zona ->
            socket |> ubicar(zona) |> push_event("zona_elegida", %{geojson: zona["geojson"]})
        end

      {:error, _} ->
        socket
    end
  end

  # Las capas de antes de la 29b piden un estado y, si se puede, un municipio:
  # salen de la zona (su primer estado; su municipio si es uno solo). El
  # Voronoi usa la zona completa.
  defp ubicar(socket, zona) do
    ent = List.first(zona["estados"] || []) || ""

    mun =
      case zona do
        %{"tipo" => "estado"} -> ""
        %{"municipios" => [m]} -> m["cve_mun"]
        _ -> ""
      end

    assign(socket, zona: zona, form: to_form(%{"cve_ent" => ent, "cve_mun" => mun}, as: "mapa"))
  end

  # Con otra zona, las capas puestas que dependen de ella se vuelven a pedir: si
  # no, el plano seguiría con la zona de antes y el enlace ya diría la nueva.
  defp reaplicar_capas(socket) do
    a = socket.assigns

    socket
    |> then(
      &if(a.coropleta_activa?,
        do: poner_coropleta(&1, a.coropleta_form[:indicador].value),
        else: &1
      )
    )
    |> then(
      &if(a.voronoi_activa?,
        do: poner_voronoi(&1, a.voronoi_form[:clase_actividad].value),
        else: &1
      )
    )
    |> then(&if(a.transporte_activa?, do: poner_transporte(&1), else: &1))
    |> then(&if(a.coloreado_activa?, do: poner_coloreado(&1), else: &1))
    |> then(&if(a.vivienda_activa?, do: poner_vivienda(&1, a.vivienda_form.params), else: &1))
  end

  defp coropleta_de_url(socket, indicador) do
    if Enum.any?(MapoCore.indicadores_censo(), fn {c, _} -> c == indicador end),
      do: poner_coropleta(socket, indicador),
      else: socket
  end

  defp vivienda_de_url(socket, %{"viv" => clave} = params) when is_binary(clave) do
    socket = catalogo_vivienda(socket)

    with %{"indicadores" => indicadores} = catalogo <- socket.assigns.vivienda_catalogo,
         true <- Enum.any?(indicadores, &(&1["clave"] == clave)) do
      anios = Enum.map(catalogo["anios_sniiv"] || [], &to_string(&1["anio"]))
      anio = if params["anio"] in anios, do: params["anio"], else: ""
      seg = if params["seg"] in (catalogo["segmentos"] || []), do: params["seg"], else: ""
      socket = poner_vivienda(socket, %{"indicador" => clave, "anio" => anio, "segmento" => seg})

      if socket.assigns.vivienda_activa? and is_binary(params["ficha"]) and
           String.match?(params["ficha"], ~r/^\d{3}$/),
         do: abrir_ficha_vivienda(socket, params["ficha"]),
         else: socket
    else
      _ -> socket
    end
  end

  defp vivienda_de_url(socket, _params), do: socket

  # El giro es texto libre, como en la cinta: mapo_core lo pasa por la tabla
  # de rubros o lo busca como texto con parámetros, nunca en el SQL.
  defp voronoi_de_url(socket, giro) when is_binary(giro) do
    giro = String.trim(giro)
    if String.length(giro) <= 60, do: poner_voronoi(socket, giro), else: socket
  end

  defp voronoi_de_url(socket, _giro), do: socket

  # Hasta cinco alcances; uno con un punto fuera de México o minutos de más se
  # salta sin pedirlo.
  defp isocrona_de_url(socket, alcance) when is_binary(alcance) do
    alcance
    |> String.split(";")
    |> Enum.take(@max_isocronas)
    |> Enum.flat_map(fn parte ->
      with [lat, lon, min] <- String.split(parte, ","),
           {lat, ""} when lat >= 14 and lat <= 33.5 <- Float.parse(lat),
           {lon, ""} when lon >= -119 and lon <= -85 <- Float.parse(lon),
           min when is_float(min) <- minutos_validos(min) do
        [{lat, lon, min}]
      else
        _ -> []
      end
    end)
    |> case do
      [] ->
        socket

      puntos ->
        {_, _, ultimo} = List.last(puntos)

        puntos
        |> Enum.reduce(socket, fn {lat, lon, min}, s -> calcular_isocrona(s, lat, lon, min) end)
        |> assign(
          isocrona_form: to_form(%{"minutos" => minutos_texto(ultimo)}, as: "isocrona_capa")
        )
        |> pintar_isocronas()
    end
  end

  defp isocrona_de_url(socket, _alcance), do: socket

  defp minutos_texto(min) when min == trunc(min), do: Integer.to_string(trunc(min))
  defp minutos_texto(min), do: Float.to_string(min)

  defp ver_de_url(socket, ver) do
    if ver in Map.keys(@capas) and ver != "propios",
      do: socket |> assign(elegida: ver) |> cargar_catalogo_vivienda() |> modo_marcas(),
      else: socket
  end

  ## Cómo citar cada acetato.

  defp citas(a, "coropleta", enlace) do
    [
      Cita.armar("censo",
        que: "#{etiqueta_indicador(a.coropleta_form[:indicador].value)} por AGEB, #{lugar(a)}",
        datos: "2020",
        version: carga("censo", a),
        enlace: enlace
      )
    ]
  end

  defp citas(a, "vivienda", enlace) do
    meta = a.vivienda_meta
    ind = meta["indicador"]
    {fuente, tabla, datos} = fuente_vivienda(meta)

    version =
      case meta["version"] do
        nil ->
          carga(tabla, a)

        v ->
          Enum.join(
            Enum.reject(["tabla #{v} del estudio de precio", carga(tabla, a)], &is_nil/1),
            "; "
          )
      end

    principal =
      Cita.armar(fuente,
        que: "#{ind["etiqueta"]} (#{ind["unidad"]}) por #{meta["nivel"]}, #{lugar(a)}",
        datos: datos,
        version: version,
        enlace: enlace
      )

    # La ficha de un municipio junta cuatro fuentes: cada una con su cita.
    ficha =
      for {f, t, d} <- [
            {"shf", "shf", nil},
            {"sniiv", "sniiv", nil},
            {"eic2025", "eic2025", "2025"},
            {"envi", "envi", "2020, por estado"}
          ],
          a.vivienda_ficha,
          f != fuente do
        Cita.armar(f,
          que: "ficha de vivienda de #{a.vivienda_ficha["nombre"]}",
          datos: d,
          version: carga(t, a),
          enlace: enlace
        )
      end

    [principal | ficha]
  end

  defp citas(a, "voronoi", enlace) do
    giro = vacio_para_nil(a.voronoi_form[:clase_actividad].value)

    [
      Cita.armar("denue",
        que: "área por negocio (Voronoi)#{if giro, do: " de \"#{giro}\""}, #{lugar(a)}",
        version: edicion_denue(fecha_carga("denue", a)),
        enlace: enlace
      )
    ]
  end

  defp citas(a, "transporte", enlace) do
    que = "rutas de transporte público que pasan por #{lugar(a)}"

    for f <- (a.transporte_meta || %{})["feeds"] || [] do
      if f["feed"] == "osm" do
        Cita.armar("osm",
          que: que,
          datos: f["nota"],
          version: "cargado el #{f["cargado"]}",
          enlace: enlace
        )
      else
        Cita.gtfs(f,
          que: "#{que}, con su frecuencia de 7 a 9 de un día hábil",
          datos: f["fecha_ref"] && "frecuencias del #{f["fecha_ref"]}",
          version: "cargado el #{f["cargado"]}",
          enlace: enlace
        )
      end
    end
  end

  defp citas(a, "coloreado", enlace) do
    [
      Cita.armar("marco",
        que: "municipios de #{lugar(a)} coloreados sin dos vecinos del mismo tono",
        version: carga("municipios", a),
        enlace: enlace
      )
    ]
  end

  defp citas(a, "isocrona", enlace) do
    que =
      Enum.map_join(a.isocronas, "; ", fn iso ->
        "#{minutos_texto(iso.minutos)} min desde #{cifra(iso.lat, 5)}, #{cifra(iso.lon, 5)}"
      end)

    metodos = a.isocronas |> Enum.map(& &1.metodo) |> Enum.uniq() |> Enum.join(", ")

    alcance =
      Cita.armar("osm",
        que: "alcance en auto: #{que}",
        version: "método #{metodos}",
        enlace: enlace
      )

    gente =
      if a.isocrona_poblacion do
        [
          Cita.armar("censo",
            que: "población dentro de cada alcance en auto, por AGEB y localidad",
            datos: "2020",
            version: carga("censo", a),
            enlace: enlace
          )
        ]
      else
        []
      end

    [alcance | gente]
  end

  defp fuente_vivienda(%{"indicador" => %{"clave" => "eic_" <> _}}),
    do: {"eic2025", "eic2025", "2025"}

  defp fuente_vivienda(%{"indicador" => %{"clave" => "sniiv_" <> _}} = meta) do
    meses =
      if meta["meses"] && meta["meses"] < 12, do: " (#{meta["meses"]} de 12 meses)", else: ""

    seg = if meta["segmento"], do: ", segmento #{meta["segmento"]}", else: ""
    {"sniiv", "sniiv", "#{meta["anio"]}#{meses}#{seg}"}
  end

  defp fuente_vivienda(%{"indicador" => %{"clave" => "shf_" <> _}}), do: {"shf", "shf", nil}
  defp fuente_vivienda(_meta), do: {"iieg", "precio", "julio de 2024"}

  # La fecha de carga es la versión de las tablas que no traen una propia.
  defp fecha_carga(tabla, a), do: MapoCore.carga(tabla, vacio_para_nil(a.form[:cve_ent].value))

  defp carga(tabla, a) do
    case fecha_carga(tabla, a) do
      nil -> nil
      fecha -> "tabla cargada en Mapo el #{fecha}"
    end
  end

  # DENUE cambia cada semestre con el mismo nombre: la fecha dice cuál edición.
  defp edicion_denue(nil), do: nil
  defp edicion_denue(fecha), do: "edición vigente en INEGI al cargarla en Mapo el #{fecha}"

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

  # Le dice al hook el orden de la pila.
  defp actualizar_mesa(socket),
    do: push_event(socket, "orden_capas", %{orden: socket.assigns.orden})

  defp activa?(assigns, "propios"), do: assigns.abiertas != []
  defp activa?(assigns, "coropleta"), do: assigns.coropleta_activa?
  defp activa?(assigns, "voronoi"), do: assigns.voronoi_activa?
  defp activa?(assigns, "coloreado"), do: assigns.coloreado_activa?
  defp activa?(assigns, "vivienda"), do: assigns.vivienda_activa?
  defp activa?(assigns, "isocrona"), do: assigns.isocronas != [] or assigns.isocrona_poniendo?
  defp activa?(assigns, "transporte"), do: assigns.transporte_activa?

  defp activas(assigns), do: Enum.filter(assigns.orden, &activa?(assigns, &1))

  # Elegir una pestaña también pliega la charola en pantallas angostas.
  defp elegir_js(capa) do
    JS.push("elegir", value: %{capa: capa})
    |> JS.remove_class("abierta", to: "#charola")
    |> JS.set_attribute({"aria-expanded", "false"}, to: "#charola .charola-boton")
  end

  defp encima(assigns) do
    case length(activas(assigns)) + if(assigns.sesion, do: 1, else: 0) do
      0 -> "nada encima"
      n -> "#{n} encima"
    end
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
    |> Enum.map(&fuente_puesta(assigns, &1))
    |> Enum.uniq()
    |> case do
      [] -> "ninguna todavía"
      lista -> Enum.join(lista, ", ")
    end
  end

  # Vivienda junta cuatro fuentes; el rótulo dice la del indicador puesto.
  defp fuente_puesta(%{vivienda_meta: %{"indicador" => %{"fuente" => f}}}, "vivienda"),
    do: f |> String.split(" · ") |> hd()

  defp fuente_puesta(_assigns, id), do: @capas[id].fuente |> String.split(" · ") |> hd()

  defp lugar(%{zona: %{"tipo" => "municipios", "municipios" => [m]}}),
    do: Enum.join(Enum.reject([m["nombre"], m["estado"]], &is_nil/1), ", ")

  defp lugar(%{zona: %{"nombre" => nombre}}), do: nombre
  defp lugar(_assigns), do: "México"

  # Dice qué se dibujó: el filtro pudo reconocer un rubro de la tabla.
  defp resumen_voronoi(%{"num_negocios" => n} = r) do
    que = if is_binary(r["filtro"]), do: "#{r["filtro"]}: ", else: ""

    fuera =
      case r["num_fuera"] do
        f when is_integer(f) and f > 0 ->
          " y #{cifra(f)} de fuera a #{div(r["competencia_m"] || 5000, 1000)} km o menos que compiten"

        _ ->
          ""
      end

    sin_denue =
      if (r["sin_denue"] || []) != [],
        do:
          " Del otro lado del límite hay un estado sin DENUE en Mapo: ahí no se ve la competencia.",
        else: ""

    "#{que}#{cifra(n)} en la zona#{fuera}. Celda grande, poca oferta.#{sin_denue}"
  end

  defp resumen_voronoi(_respuesta), do: nil

  defp vacio_para_nil(nil), do: nil
  defp vacio_para_nil(""), do: nil
  defp vacio_para_nil(valor), do: valor

  defp etiqueta_indicador(codigo) do
    Enum.find_value(MapoCore.indicadores_censo(), codigo, fn {c, e} -> if c == codigo, do: e end)
  end
end
