defmodule MapoWeb.PerfilDocumentos do
  @moduledoc """
  Los ocho papeles de `/perfil` (docs/producto/perfil.md): cada uno con su piel,
  su fuente, su nivel (la zona, sus municipios o el estado) y lo que no sabe.
  Nada se resume en un puntaje. Reciben el perfil entero de
  `mapo_core/perfil.py` y, en el slot, las notas del equipo.
  """

  use MapoWeb, :html

  import MapoWeb.Cifras
  import MapoWeb.Iconos, only: [icono: 1]

  @doc "Los papeles en su orden: `{clave, título, tipo, piel}`."
  def documentos do
    [
      {"demografia", "Población", "Cédula censal", "demografia"},
      {"vivienda", "Vivienda", "Ficha de obra", "urbanismo"},
      {"servicios", "Servicios a pie", "Hoja de ruta", "movilidad"},
      {"comercio", "Negocios", "Libro mayor", "comercio"},
      {"consumo", "Gasto de los hogares", "Ticket de caja", "consumo"},
      {"seguridad", "Incidencia delictiva", "Expediente", "seguridad"},
      {"laboral", "Empleo", "Tarjeta de checador", "laboral"},
      {"hacienda", "Hacienda municipal", "Cuenta pública", "urbanismo"}
    ]
  end

  ## Cabecera de la zona

  attr :perfil, :map, required: true

  @doc "Lo primero que se lee: cuánta gente, qué tan junta, en cuántas viviendas y con cuántos negocios."
  def portada(assigns) do
    assigns =
      assign(assigns,
        d: assigns.perfil["demografia"],
        v: assigns.perfil["vivienda"],
        c: assigns.perfil["comercio"]
      )

    ~H"""
    <dl class="perfil-cifras">
      <div>
        <dt>Personas</dt>
        <dd class="num">{gente(@d, "pobtot")}</dd>
      </div>
      <div>
        <dt>Por km²</dt>
        <dd class="num">{gente(@d, "densidad")}</dd>
      </div>
      <div>
        <dt>Superficie</dt>
        <dd class="num">{superficie(@perfil["zona"]["km2"])}</dd>
      </div>
      <div>
        <dt>Viviendas habitadas</dt>
        <dd class="num">{vivienda(@perfil, @v && @v["habitadas"])}</dd>
      </div>
      <div>
        <dt>Escolaridad</dt>
        <dd class="num">
          {if @d && @d["graproes"], do: "#{dato(@d["graproes"], 1)} años", else: "sin dato"}
        </dd>
      </div>
      <div>
        <dt>Negocios</dt>
        <dd class="num">{if @c, do: cifra(@c["total_negocios"]), else: "sin dato"}</dd>
      </div>
    </dl>

    <div :if={@d && @d["estimada"]} class="perfil-estimada" id="perfil-estimada">
      <p>{estimacion(@d)}</p>
      <details id="perfil-metodo" phx-mounted={JS.ignore_attributes("open")}>
        <summary>Cómo se estima</summary>
        {@d["metodo"]} Aquí: {cuantos(@perfil["agebs"], "AGEB", "AGEB")} y {cuantos(
          @perfil["localidades"],
          "localidad",
          "localidades"
        )}.
      </details>
    </div>
    """
  end

  defp estimacion(%{"error_pct" => nil}),
    do:
      "Menos de 100 personas por estimación: a este tamaño ninguna cifra del censo es de fiar. Elige una zona más grande."

  defp estimacion(%{"error_pct" => e}),
    do: "Gente y viviendas son estimadas (≈): en zonas de este tamaño fallan por ±#{round(e)} %."

  ## Nivel

  attr :perfil, :map, required: true
  attr :de, :string, required: true, doc: "zona | municipios | estado"

  @doc "De quién es el dato: la zona, los municipios que toca o el estado."
  def nivel(assigns) do
    assigns = assign(assigns, texto: texto_nivel(assigns.perfil["zona"], assigns.de))

    ~H"""
    <p class={["nivel", @texto.ajeno? && "ajeno"]}>{@texto.frase}</p>
    """
  end

  defp texto_nivel(_zona, "zona"), do: %{frase: "De la zona", ajeno?: false}
  defp texto_nivel(_zona, "estado"), do: %{frase: "De todo el estado", ajeno?: true}

  defp texto_nivel(zona, "municipios") do
    nombres = Enum.map(zona["municipios"] || [], & &1["nombre"])

    case {zona["entera"], nombres} do
      {true, [_]} -> %{frase: "De la zona", ajeno?: false}
      {true, _} -> %{frase: "Suma de los #{length(nombres)} municipios", ajeno?: false}
      {_, [n]} -> %{frase: "De #{n} entero, no de la zona", ajeno?: true}
      {_, ns} -> %{frase: "De #{Enum.join(ns, ", ")} enteros, no de la zona", ajeno?: true}
    end
  end

  ## Población

  attr :perfil, :map, required: true
  slot :inner_block

  def cedula(assigns) do
    assigns = assign(assigns, d: assigns.perfil["demografia"], r: assigns.perfil["rezago_social"])

    ~H"""
    <article
      id="doc-demografia"
      class="documento pegado d-demografia"
      data-piel="demografia"
      aria-labelledby="t-dem"
    >
      <header>
        <h2 id="t-dem">Población</h2>
        <span class="tipo">Cédula censal</span>
      </header>
      <.nivel perfil={@perfil} de="zona" />

      <%= if @d do %>
        <.piramide :if={@d["piramide"]} bandas={@d["piramide"]} datos={@d} />

        <dl class="casillas">
          <.casilla titulo="Menores de 15" valor={pct(@d["menores15_pct"])} />
          <.casilla titulo="De 60 o más" valor={pct(@d["mayores60_pct"])} />
          <.casilla titulo="Escolaridad promedio" valor={anios(@d["graproes"])} />
          <.casilla titulo="Nacieron en otro estado" valor={pct(@d["nacidos_fuera_pct"])} />
          <.casilla titulo="Económicamente activa" valor={pct(@d["pea_pct"])} nota="de 12 o más" />
          <.casilla titulo="Sin servicios de salud" valor={pct(@d["sin_salud_pct"])} />
          <.casilla titulo="Hogares" valor={gente(@d, "tothog")} />
          <.casilla titulo="Desocupada" valor={gente(@d, "pdesocup")} />
        </dl>
        <p :if={@d["reservados"] > 0} class="falta">
          INEGI reserva algún dato en {cuantos(@d["reservados"], "lugar", "lugares")} con pocas viviendas: no se cuentan como cero.
        </p>
      <% else %>
        <p class="falta">El censo no tiene datos de esta zona.</p>
      <% end %>

      <p class="fuente">INEGI · Censo de Población y Vivienda 2020</p>

      <section :if={@r} class="anexo" aria-labelledby="t-rezago">
        <h3 id="t-rezago">Rezago social por AGEB urbana</h3>

        <%= if @r["grados"] do %>
          <.tramos
            partes={
              for g <- @r["grados"],
                  do:
                    {g["grado"], g["personas"],
                     "#{if g["personas"], do: "#{personas(@d, g["personas"])} personas en "}#{cifra(g["agebs"])} AGEB"}
            }
            orden={["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"]}
            etiqueta="Personas por grado de rezago social"
          />
          <p class="falta">
            Grado de CONEVAL con 17 indicadores del censo 2020; no mide pobreza ni ingreso. Solo AGEB urbanas: la gente del campo no entra.
          </p>
        <% else %>
          <p class="falta">CONEVAL no publica AGEB urbanas de esta zona.</p>
        <% end %>

        <p class="fuente">CONEVAL · Grado de Rezago Social 2020</p>
      </section>
      {render_slot(@inner_block)}
    </article>
    """
  end

  attr :titulo, :string, required: true
  attr :valor, :string, required: true
  attr :nota, :string, default: nil

  defp casilla(assigns) do
    ~H"""
    <div class="casilla">
      <dt>{@titulo}</dt>
      <dd>{@valor} <small :if={@nota}>{@nota}</small></dd>
    </div>
    """
  end

  attr :bandas, :list, required: true
  attr :datos, :map, required: true

  # Las bandas no miden lo mismo (6 años, 35): el alto son los años y el largo, la
  # gente por año, así que el área es la gente. La última va abierta; se dibuja de
  # 60 a 85.
  defp piramide(assigns) do
    maximo =
      assigns.bandas
      |> Enum.flat_map(&[&1["F"] / &1["anios"], &1["M"] / &1["anios"]])
      |> Enum.max()

    assigns =
      assign(assigns,
        filas:
          for b <- Enum.reverse(assigns.bandas) do
            %{
              etiqueta: b["etiqueta"],
              alto: b["anios"] * 3,
              f: b["F"],
              m: b["M"],
              ancho_f: ancho(b["F"] / b["anios"], maximo),
              ancho_m: ancho(b["M"] / b["anios"], maximo)
            }
          end
      )

    ~H"""
    <figure class="piramide">
      <figcaption>
        <span>Mujeres <b class="num">{gente(@datos, "pobfem")}</b></span>
        <span class="piramide-edad">edad</span>
        <span>Hombres <b class="num">{gente(@datos, "pobmas")}</b></span>
      </figcaption>
      <div
        :for={f <- @filas}
        class="piramide-fila"
        style={"height: #{f.alto}px"}
        title={"#{f.etiqueta} años: #{cifra(f.f)} mujeres y #{cifra(f.m)} hombres"}
      >
        <span class="piramide-lado"><i style={"width: #{f.ancho_f}%"}></i></span>
        <span class="piramide-edad">{f.etiqueta}</span>
        <span class="piramide-lado"><i style={"width: #{f.ancho_m}%"}></i></span>
      </div>
      <p class="sr-only">
        {Enum.map_join(
          @bandas,
          "; ",
          &"#{&1["etiqueta"]} años: #{&1["F"]} mujeres, #{&1["M"]} hombres"
        )}
      </p>
    </figure>
    """
  end

  defp ancho(_v, maximo) when maximo <= 0, do: 0
  defp ancho(v, maximo), do: Float.round(v / maximo * 100, 1)

  attr :partes, :list, required: true, doc: "`{nombre, cantidad o nil, nota}`, en orden"
  attr :etiqueta, :string, required: true

  attr :orden, :list,
    default: nil,
    doc: "todas las partes posibles: su tinta no cambia si falta una"

  # Una tira de partes en orden (de menos a más tinta), con su leyenda en texto: la
  # cifra nunca depende solo del color.
  defp tramos(assigns) do
    total = assigns.partes |> Enum.map(&(elem(&1, 1) || 0)) |> Enum.sum()

    assigns =
      assign(assigns,
        partes:
          assigns.partes
          |> Enum.with_index()
          |> Enum.map(fn {{nombre, n, nota}, i} ->
            %{
              nombre: nombre,
              n: n,
              nota: nota,
              i: if(assigns.orden, do: Enum.find_index(assigns.orden, &(&1 == nombre)), else: i),
              parte: if(n && total > 0, do: n / total * 100)
            }
          end)
      )

    ~H"""
    <div class="tramos" role="img" aria-label={@etiqueta}>
      <i
        :for={p <- @partes}
        :if={p.parte && p.parte > 0}
        data-i={p.i}
        style={"width: #{p.parte}%"}
        title={"#{p.nombre}: #{p.nota}"}
      ></i>
    </div>
    <ul class="tramos-leyenda">
      <li :for={p <- @partes}>
        <span class="muestra" data-i={p.i} aria-hidden="true"></span>
        <span>{p.nombre}</span>
        <b class="num">{if p.parte, do: pct(p.parte), else: "reservado"}</b>
        <small>{p.nota}</small>
      </li>
    </ul>
    """
  end

  ## Vivienda

  attr :perfil, :map, required: true
  slot :inner_block

  def ficha_obra(assigns) do
    assigns = assign(assigns, v: assigns.perfil["vivienda"])

    ~H"""
    <article
      id="doc-vivienda"
      class="documento pegado d-vivienda"
      data-piel="urbanismo"
      aria-labelledby="t-viv"
    >
      <header>
        <h2 id="t-viv">Vivienda</h2>
        <span class="tipo">Ficha de obra</span>
      </header>
      <.nivel perfil={@perfil} de="zona" />

      <%= if @v do %>
        <dl class="casillas">
          <.casilla titulo="Viviendas" valor={vivienda(@perfil, @v["total"])} />
          <.casilla
            titulo="Personas por vivienda"
            valor={if @v["ocupantes"], do: dato(@v["ocupantes"], 2), else: "sin dato"}
          />
          <.casilla
            titulo="Deshabitadas"
            valor={pct(@v["deshabitadas_pct"])}
            nota="de las particulares"
          />
          <.casilla titulo="De uso temporal" valor={vivienda(@perfil, @v["temporales"])} />
        </dl>

        <h3>Viviendas habitadas que tienen</h3>
        <ul class="barras cien">
          <li :for={b <- @v["bienes"]}>
            <span>{b["etiqueta"]}</span>
            <span class="carril"><i :if={b["pct"]} class="barra" style={"width: #{b["pct"]}%"}></i></span>
            <span class="num">{pct(b["pct"])}</span>
          </li>
        </ul>
      <% else %>
        <p class="falta">El censo no tiene viviendas de esta zona.</p>
      <% end %>

      <p class="fuente">INEGI · Censo de Población y Vivienda 2020</p>

      <section :if={p = @v && @v["precio"]} class="anexo" aria-labelledby="t-precio">
        <h3 id="t-precio">Precio de oferta</h3>
        <p class="grande num">${millon(p["mediana"])}</p>
        <p class="falta">
          Mediana entre {p["agebs"]} de {cuantos(p["agebs_zona"], "AGEB", "AGEB")} con anuncios de venta, de ${millon(
            p["bajo"]
          )} a ${millon(p["alto"])}. Es lo que se pide, no lo que se paga.
        </p>
        <p class="fuente">IIEG · anuncios de julio de 2024, por AGEB en Mapo</p>
      </section>

      <section :if={@v && @v["tenencia"] not in [nil, []]} class="anexo" aria-labelledby="t-ten">
        <h3 id="t-ten">Propias y rentadas, 2025</h3>
        <.nivel perfil={@perfil} de="municipios" />
        <table class="libro">
          <thead>
            <tr>
              <th>Municipio</th>
              <th class="n">Propias</th>
              <th class="n">Rentadas</th>
            </tr>
          </thead>
          <tbody>
            <tr :for={t <- @v["tenencia"]}>
              <td>{t["nombre"]}</td>
              <td class="n">{pct(t["propias"])}</td>
              <td class="n">{pct(t["rentadas"])}</td>
            </tr>
          </tbody>
        </table>
        <p class="fuente">INEGI · Encuesta Intercensal 2025</p>
      </section>
      {render_slot(@inner_block)}
    </article>
    """
  end

  ## Servicios a pie

  attr :perfil, :map, required: true
  slot :inner_block

  def hoja_ruta(assigns) do
    servicios = assigns.perfil["servicios"] || []

    assigns =
      assign(assigns,
        calculados: Enum.filter(servicios, & &1["calculado"]),
        sin: Enum.reject(servicios, & &1["calculado"])
      )

    ~H"""
    <article
      id="doc-servicios"
      class="documento pegado d-servicios"
      data-piel="movilidad"
      aria-labelledby="t-ser"
    >
      <header>
        <h2 id="t-ser">Servicios a pie</h2>
        <span class="tipo">Hoja de ruta</span>
      </header>
      <.nivel perfil={@perfil} de="zona" />

      <%= if @calculados != [] do %>
        <ul class="ruta-leyenda" aria-hidden="true">
          <li><span class="muestra" data-i="0"></span> 15 min o menos</li>
          <li><span class="muestra" data-i="1"></span> de 15 a 30</li>
          <li><span class="muestra" data-i="2"></span> más de 30</li>
        </ul>
        <ul class="rutas">
          <li :for={s <- @calculados} title={titulo_servicio(s)}>
            <.icono nombre={s["clave"]} />
            <span class="ruta-nombre">
              {s["titulo"]}
              <small :if={s["grupo_etiqueta"] != "personas"}>{s["grupo_etiqueta"]}</small>
              <small :if={falta_calcular(s)}>{falta_calcular(s)}</small>
            </span>
            <span :if={s["cerca_pct"]} class="tramos" role="img" aria-label={titulo_servicio(s)}>
              <i
                :for={{n, i} <- Enum.with_index(s["tramos"])}
                :if={n > 0}
                data-i={i}
                style={"width: #{n / s["con_ruta"] * 100}%"}
              ></i>
            </span>
            <b :if={s["cerca_pct"]} class="num">{pct(s["cerca_pct"])}</b>
            <span :if={!s["cerca_pct"]} class="falta">{sin_servicio(s)}</span>
          </li>
        </ul>
        <p class="falta">
          La cifra es la gente de su grupo a 15 minutos o menos, por calle. Lo que no tiene ruta o no se calcula no cuenta ni cerca ni lejos.
        </p>
      <% else %>
        <p class="falta">Los minutos a pie todavía no se calculan para este estado.</p>
      <% end %>

      <p :if={@calculados != [] and @sin != []} class="falta">
        Aquí no se calcula: {Enum.map_join(@sin, ", ", &String.downcase(&1["titulo"], :default))}.
      </p>

      <p class="fuente">CLUES, DENUE, GTFS y OSM · OSRM a pie, sobre el censo 2020</p>
      {render_slot(@inner_block)}
    </article>
    """
  end

  defp titulo_servicio(%{"cerca_pct" => nil} = s), do: s["titulo"]

  defp titulo_servicio(s) do
    [a, b, c] = s["tramos"]

    "#{s["titulo"]}: #{cifra(a)} #{s["grupo_etiqueta"]} a 15 minutos o menos, #{cifra(b)} de 15 a 30 y #{cifra(c)} a más de 30" <>
      if(s["sin_ruta"] > 0, do: "; #{cifra(s["sin_ruta"])} sin ruta", else: "") <>
      if(s["sin_calcular"] > 0, do: "; #{cifra(s["sin_calcular"])} sin calcular", else: "")
  end

  # La cifra es de lo calculado: si falta más de 1 de cada 20, se dice de cuántos es.
  defp falta_calcular(%{"cerca_pct" => c, "sin_calcular" => x, "con_ruta" => r} = s)
       when is_number(c) do
    todos = r + s["sin_ruta"] + x
    if x * 20 > todos, do: "calculado para #{cifra(r)} de #{cifra(todos)}"
  end

  defp falta_calcular(_s), do: nil

  defp sin_servicio(%{"parcial" => true} = s),
    do:
      "solo se calcula para #{cifra(s["con_ruta"])} de #{cifra(s["con_ruta"] + s["sin_calcular"])}"

  defp sin_servicio(_s), do: "sin gente de este grupo"

  ## Negocios

  attr :perfil, :map, required: true
  slot :inner_block

  def libro(assigns) do
    c = assigns.perfil["comercio"]
    total = (c && c["total_negocios"]) || 0
    clases = (c && c["top_clases_actividad"]) || []
    sectores = (c && c["sectores"]) || []
    d = assigns.perfil["demografia"]

    assigns =
      assign(assigns,
        c: c,
        total: total,
        clases: clases,
        sectores: Enum.take(sectores, 8),
        otros: sectores |> Enum.drop(8) |> Enum.map(&List.last/1) |> Enum.sum(),
        maximo: maximo(sectores),
        resto: total - Enum.sum(Enum.map(clases, &List.last/1)),
        por_mil: if(d && (d["pobtot"] || 0) >= 100, do: 1000 * total / d["pobtot"]),
        economia: assigns.perfil["economia"]
      )

    ~H"""
    <article
      id="doc-comercio"
      class="documento pegado d-comercio"
      data-piel="comercio"
      aria-labelledby="t-com"
    >
      <header>
        <h2 id="t-com">Negocios</h2>
        <span class="tipo">Libro mayor</span>
      </header>
      <.nivel perfil={@perfil} de="zona" />

      <%= cond do %>
        <% is_nil(@c) -> %>
          <p class="falta">El DENUE de este estado no está cargado en Mapo.</p>
        <% @total == 0 -> %>
          <p class="falta">El DENUE no registra negocios en esta zona.</p>
        <% true -> %>
          <p>
            <span class="num grande">{cifra(@total)}</span>
            negocios{if @por_mil, do: ", #{cifra(@por_mil)} por cada mil habitantes"}
          </p>

          <div class="dos">
            <div>
              <h3>Por sector</h3>
              <ul class="barras">
                <li :for={[sector, n] <- @sectores}>
                  <span>{sector}</span>
                  <span class="carril"><i class="barra" style={"width: #{n / @maximo * 100}%"}></i></span>
                  <span class="num">{cifra(n)} <small>{pct(n / @total * 100)}</small></span>
                </li>
                <li :if={@otros > 0} class="resto">
                  <span>Los demás sectores</span>
                  <span class="carril"></span>
                  <span class="num">{cifra(@otros)} <small>{pct(@otros / @total * 100)}</small></span>
                </li>
              </ul>

              <h3 :if={@c["estratos"] != []}>Por personas que trabajan ahí</h3>
              <.tramos
                :if={@c["estratos"] != []}
                partes={
                  for [e, n] <- agrupar_estratos(@c["estratos"]),
                      do: {e, n, cuantos(n, "negocio", "negocios")}
                }
                etiqueta="Negocios por tamaño"
              />
            </div>
            <div>
              <h3>Los giros más comunes</h3>
              <table class="libro">
                <tbody>
                  <tr :for={[clase, n] <- @clases}>
                    <td>{clase}</td>
                    <td class="n">{cifra(n)}</td>
                    <td class="n">{pct(n / @total * 100)}</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr class="resto">
                    <td>Los demás giros</td>
                    <td class="n">{cifra(@resto)}</td>
                    <td class="n">{pct(@resto / @total * 100)}</td>
                  </tr>
                  <tr class="total">
                    <td>Total registrado</td>
                    <td class="n">{cifra(@total)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
      <% end %>

      <p class="fuente">INEGI · DENUE</p>

      <section :if={@economia} class="anexo" aria-labelledby="t-ce">
        <h3 id="t-ce">Tamaño de la economía, {@economia["anio_datos"] || 2023}</h3>
        <.nivel perfil={@perfil} de="municipios" />

        <%= if t = @economia["total"] do %>
          <div class="dos">
            <table class="libro">
              <tbody>
                <tr :for={
                  {nombre, clave} <- [
                    {"Unidades económicas", "ue"},
                    {"Personal ocupado", "personal"},
                    {"Remuneraciones (millones de pesos)", "remuneraciones"},
                    {"Ingresos (millones de pesos)", "ingresos"},
                    {"Valor agregado (millones de pesos)", "vacb"}
                  ]
                }>
                  <td>{nombre}</td>
                  <td class="n">{entero(t[clave])}</td>
                </tr>
              </tbody>
            </table>

            <table :if={@economia["sectores"] != []} class="libro">
              <thead>
                <tr>
                  <th>Sector (parte del personal)</th>
                  <th class="n">Personal</th>
                </tr>
              </thead>
              <tbody>
                <tr :for={s <- Enum.take(@economia["sectores"], 5)}>
                  <td>{s["nombre"]} ({parte(s["personal"], t["personal"])})</td>
                  <td class="n">{entero(s["personal"])}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p :if={@economia["reservados"] > 0} class="falta">
            INEGI reserva el personal de {cuantos(@economia["reservados"], "sector", "sectores")} con pocas unidades: no se cuentan como cero.
          </p>
        <% else %>
          <p class="falta">Los Censos Económicos no publican este municipio.</p>
        <% end %>

        <p class="fuente">INEGI · Censos Económicos 2024</p>
      </section>
      {render_slot(@inner_block)}
    </article>
    """
  end

  # DENUE trae siete estratos; tres dicen lo mismo en menos tinta.
  defp agrupar_estratos(estratos) do
    de = fn textos ->
      for [e, n] <- estratos, String.starts_with?(e, textos), reduce: 0, do: (s -> s + n)
    end

    [
      ["Hasta 5", de.(["0 a 5"])],
      ["De 6 a 30", de.(["6 a 10", "11 a 30"])],
      ["De 31 a 250", de.(["31 a 50", "51 a 100", "101 a 250"])],
      ["Más de 250", de.(["251"])]
    ]
  end

  ## Gasto

  attr :perfil, :map, required: true
  slot :inner_block

  def ticket(assigns) do
    c = assigns.perfil["consumo"]
    estado? = assigns.perfil["zona"]["tipo"] == "estado"

    assigns =
      assign(assigns,
        zona: if(estado?, do: nil, else: c && c["zona"]),
        estado: c && c["estado"],
        estado?: estado?
      )

    ~H"""
    <article
      id="doc-consumo"
      class="documento pegado d-consumo"
      data-piel="consumo"
      aria-labelledby="t-con"
    >
      <header>
        <span class="tipo">Ticket de caja</span>
        <h2 id="t-con">Gasto de los hogares</h2>
      </header>

      <%= if @estado do %>
        <.nivel perfil={@perfil} de="estado" />
        <p>Gasto diario promedio por hogar</p>
        <p class="grande num">${dato(@estado["promedio_ponderado"], 2)}</p>
        <.renglon_ticket titulo="Mediana" valor={"$#{dato(@estado["mediana"], 2)}"} />
        <.renglon_ticket titulo="Hogares en la muestra" valor={dato(@estado["n_hogares_muestra"])} />
      <% end %>

      <%= cond do %>
        <% @zona -> %>
          <hr />
          <.nivel perfil={@perfil} de="municipios" />
          <.renglon_ticket titulo="Promedio" valor={"$#{dato(@zona["promedio_ponderado"], 2)}"} />
          <.renglon_ticket titulo="Mediana" valor={"$#{dato(@zona["mediana"], 2)}"} />
          <.renglon_ticket titulo="Hogares en la muestra" valor={dato(@zona["n_hogares_muestra"])} />
          <p class="falta">
            La ENIGH no es representativa por municipio, solo por estado. Úsalo como referencia.
          </p>
        <% @estado? -> %>
        <% true -> %>
          <p class="falta">La muestra de la ENIGH no llegó a {suyos(@perfil)}.</p>
      <% end %>

      <p class="fuente">INEGI · ENIGH</p>
      {render_slot(@inner_block)}
      <div class="dientes" aria-hidden="true"></div>
    </article>
    """
  end

  attr :titulo, :string, required: true
  attr :valor, :string, required: true

  defp renglon_ticket(assigns) do
    ~H"""
    <div class="renglon">
      <span>{@titulo}</span><span></span><b class="num">{@valor}</b>
    </div>
    """
  end

  ## Seguridad

  attr :perfil, :map, required: true
  slot :inner_block

  def expediente(assigns) do
    s = assigns.perfil["seguridad"]
    tipos = (s && s["por_tipo"]) || []
    serie = (s && s["serie"]) || []

    assigns =
      assign(assigns,
        s: s,
        tipos: tipos,
        maximo: maximo(tipos),
        serie: serie,
        tope: serie |> Enum.map(& &1["total"]) |> Enum.max(fn -> 0 end)
      )

    ~H"""
    <article
      id="doc-seguridad"
      class="documento pegado d-seguridad"
      data-piel="seguridad"
      aria-labelledby="t-seg"
    >
      <span class="pestana-carpeta">SESNSP{@s && " · #{@s["anio"]}"}</span>
      <header>
        <h2 id="t-seg">Incidencia delictiva</h2>
        <span class="tipo">Expediente</span>
      </header>
      <.nivel perfil={@perfil} de="municipios" />

      <%= if @s do %>
        <p>
          <span class="num total">{dato(@s["total_delitos"])}</span>
          delitos registrados en {@s["anio"]}{if @s["por_mil"],
            do: ", #{cifra(@s["por_mil"], 1)} por cada mil habitantes de 2020"}{if @s["meses"] < 12,
            do: " (#{cuantos(@s["meses"], "mes", "meses")})"}
        </p>

        <figure :if={length(@serie) > 1} class="columnas">
          <figcaption>
            Delitos por año{if Enum.any?(@serie, &(&1["meses"] < 12)),
              do: "; rayado, año incompleto"}
          </figcaption>
          <ol>
            <li :for={a <- @serie} title={"#{a["anio"]}: #{cifra(a["total"])} delitos"}>
              <i
                class={a["meses"] < 12 && "incompleto"}
                style={"height: #{if @tope > 0, do: a["total"] / @tope * 100, else: 0}%"}
              ></i>
              <span>{a["anio"] |> to_string() |> String.slice(2, 2)}</span>
            </li>
          </ol>
          <p class="sr-only">{Enum.map_join(@serie, "; ", &"#{&1["anio"]}: #{&1["total"]}")}</p>
        </figure>

        <.barras tipos={Enum.take(@tipos, 8)} maximo={@maximo} />
        <details
          :if={length(@tipos) > 8}
          id="mas-delitos"
          phx-mounted={JS.ignore_attributes("open")}
        >
          <summary>Ver los {length(@tipos)} tipos, incluidos los de cero</summary>
          <.barras tipos={Enum.drop(@tipos, 8)} maximo={@maximo} />
        </details>
      <% else %>
        <p class="falta">
          No hay incidencia del SESNSP cargada para {suyos(@perfil)}. La fuente se carga a mano.
        </p>
      <% end %>

      <p class="fuente">
        SESNSP · incidencia del fuero común: lo denunciado o investigado, no todo lo que pasa
      </p>
      {render_slot(@inner_block)}
    </article>
    """
  end

  attr :tipos, :list, required: true
  attr :maximo, :any, required: true

  defp barras(assigns) do
    ~H"""
    <ul class="barras">
      <li :for={[tipo, n] <- @tipos}>
        <span>{tipo}</span>
        <span class="carril">
          <i class="barra" style={"width: #{if @maximo > 0, do: n / @maximo * 100, else: 0}%"}></i>
        </span>
        <span class="num">{cifra(n)}</span>
      </li>
    </ul>
    """
  end

  ## Empleo

  attr :perfil, :map, required: true
  slot :inner_block

  # Lo del municipio (IMSS) primero; la desocupación es del estado entero.
  def tarjeta(assigns) do
    e = assigns.perfil["empleo_formal"]
    divisiones = if(e, do: Enum.map(e["por_division"], &[&1["nombre"], &1["puestos"]]), else: [])

    assigns =
      assign(assigns,
        e: e,
        datos: assigns.perfil["laboral"],
        divisiones: divisiones,
        maximo: maximo(divisiones)
      )

    ~H"""
    <article
      id="doc-laboral"
      class="documento pegado d-laboral"
      data-piel="laboral"
      aria-labelledby="t-lab"
    >
      <header>
        <h2 id="t-lab">Empleo</h2>
        <span class="tipo">Tarjeta de checador</span>
      </header>
      <.nivel perfil={@perfil} de="municipios" />

      <%= cond do %>
        <% @e && @e["puestos"] > 0 -> %>
          <p>Puestos de trabajo registrados en el IMSS, {mes(@e["periodo"])}</p>

          <p class="sello num">{cifra(@e["puestos"])}</p>

          <dl>
            <dt>Permanentes</dt>
            <dd>{cifra(@e["permanentes"])}</dd>
            <dt>Eventuales</dt>
            <dd>{cifra(@e["eventuales"])}</dd>
            <dt>Salario diario promedio</dt>
            <dd>${dato(@e["salario_diario"], 2)}</dd>
            <dt>Contra un año antes</dt>
            <dd :if={@e["anual"]}>
              {dato(@e["anual"]["variacion"], 2)} % (desde {mes(@e["anual"]["periodo"])})
            </dd>
            <dd :if={!@e["anual"]}>sin dato: falta el mismo mes del año anterior</dd>
          </dl>
          <.barras tipos={@divisiones} maximo={@maximo} />
          <p class="falta">
            Solo empleo formal, en el municipio donde está registrado el patrón (no donde vive
            ni donde trabaja cada persona). El salario es el de cotización, con tope de 25 UMA: {dato(
              @e["parte_rango_tope"],
              1
            )} % de los puestos está en el último rango.
          </p>
        <% @e && @e["puestos_estado_sin_municipio"] > 0 -> %>
          <p class="falta">
            El IMSS no asigna municipio a {cifra(@e["puestos_estado_sin_municipio"])} puestos
            de este estado ({mes(@e["periodo"])}); en la Ciudad de México, a ninguno.
          </p>
        <% @e -> %>
          <p class="falta">
            El IMSS no registra puestos de trabajo en {suyos(@perfil)} ({mes(@e["periodo"])}).
          </p>
        <% true -> %>
          <p class="falta">No hay datos del IMSS cargados para este estado.</p>
      <% end %>

      <dl :if={@datos}>
        <dt>Desocupación del estado</dt>
        <dd>
          {dato(@datos["tasa_desocupacion"], 2)} % ({trimestre(@datos["trimestre"])} trimestre de {@datos[
            "anio"
          ]})
        </dd>
      </dl>

      <p :if={@datos} class="falta">
        La desocupación es del estado entero: la ENOE no es representativa por municipio.
      </p>

      <p :if={!@datos} class="falta">
        {if length(@perfil["zona"]["estados"] || []) > 1,
          do: "La zona toca varios estados: la desocupación de la ENOE va por estado y no se suma.",
          else: "No hay datos de la ENOE cargados para este estado."}
      </p>

      <p class="fuente">IMSS · datos abiertos de asegurados · INEGI · ENOE</p>
      {render_slot(@inner_block)}
    </article>
    """
  end

  ## Hacienda

  attr :perfil, :map, required: true
  slot :inner_block

  # De dónde saca dinero el municipio y en qué lo gasta (EFIPEM). Pesos corrientes de
  # cada año; nada se ajusta por inflación.
  def cuenta(assigns) do
    d = assigns.perfil["hacienda"]

    assigns =
      assign(assigns,
        datos: d,
        ingresos: if(d && d["ingresos"], do: millones(d["ingresos"]), else: []),
        egresos: if(d && d["egresos"], do: millones(d["egresos"]), else: []),
        planeacion: assigns.perfil["planeacion"]
      )

    ~H"""
    <article
      id="doc-hacienda"
      class="documento pegado d-hacienda"
      data-piel="urbanismo"
      aria-labelledby="t-hac"
    >
      <header>
        <h2 id="t-hac">Hacienda municipal</h2>
        <span class="tipo">Cuenta pública</span>
      </header>
      <.nivel perfil={@perfil} de="municipios" />

      <%= cond do %>
        <% @datos && @datos["varios"] && @datos["total_ingresos"] -> %>
          <p>
            Ingresos de {@datos["anio"]}, millones de pesos, de {@datos["reportaron"]} de {@datos[
              "municipios"
            ]} municipios que reportaron ese año
          </p>
          <p class="sello num">{dato(@datos["total_ingresos"] / 1_000_000)}</p>
          <dl>
            <dt>Recaudan los municipios</dt>
            <dd>{dato(@datos["propios_pct"], 1)} %</dd>
            <dt>Predial</dt>
            <dd>{dato((@datos["predial"] || 0) / 1_000_000)} millones</dd>
          </dl>
          <table class="libro">
            <thead>
              <tr>
                <th>Municipio</th>
                <th class="n">Año</th>
                <th class="n">Millones</th>
                <th class="n">Recauda</th>
              </tr>
            </thead>
            <tbody>
              <tr :for={t <- Enum.take(@datos["tabla"], 12)}>
                <td>{t["nombre"]}</td>
                <td class="n">{t["anio"] || "no reportó"}</td>
                <td class="n">{if t["total"], do: dato(t["total"] / 1_000_000, 0), else: ""}</td>
                <td class="n">
                  {if t["propios_pct"], do: "#{dato(t["propios_pct"], 1)} %", else: ""}
                </td>
              </tr>
            </tbody>
          </table>
          <p :if={length(@datos["tabla"]) > 12} class="falta">
            Los 12 con más ingresos de {length(@datos["tabla"])}.
          </p>
          <p class="falta">Cada municipio con su último año reportado. Pesos de cada año.</p>
        <% @datos && @datos["total_ingresos"] -> %>
          <p>Ingresos de {@datos["anio"]}, millones de pesos</p>

          <p class="sello num">{dato(@datos["total_ingresos"] / 1_000_000)}</p>

          <.tramos
            partes={[
              {"Recauda el municipio", @datos["propios_pct"], "impuestos, derechos, productos"},
              {"Le transfieren", @datos["transferencias_pct"], "participaciones y aportaciones"}
            ]}
            etiqueta="De dónde vienen los ingresos, en por ciento"
          />
          <dl>
            <dt>Predial</dt>
            <dd>
              {if @datos["predial"],
                do: "#{dato(@datos["predial"] / 1_000_000)} millones",
                else: "sin dato"}
            </dd>
            <dt>Recauda, por año</dt>
            <dd>
              {Enum.map_join(@datos["serie_propios"], " · ", fn a ->
                "#{a["anio"]}: #{if a["propios_pct"], do: "#{dato(a["propios_pct"], 1)} %", else: "sin dato"}"
              end)}
            </dd>
          </dl>

          <div class="dos">
            <div>
              <h3>Ingresos por capítulo</h3>
              <.barras tipos={@ingresos} maximo={maximo(@ingresos)} />
            </div>
            <div>
              <h3>Egresos por capítulo</h3>
              <.barras tipos={@egresos} maximo={maximo(@egresos)} />
            </div>
          </div>
          <p class="falta">
            Pesos de cada año, sin ajustar por inflación.
            <span :if={@datos["anio"] < @datos["ultimo_publicado"]}>
              El municipio no reportó {@datos["ultimo_publicado"]}: es su último año con datos.
            </span>
          </p>
        <% @datos && @datos["estado_sin_datos"] -> %>
          <p class="falta">
            EFIPEM no publica finanzas municipales de este estado (en la Ciudad de México, las alcaldías no tienen hacienda propia).
          </p>
        <% @datos && @datos["varios"] -> %>
          <p class="falta">Ningún municipio de la zona reportó sus finanzas de {@datos["anio"]}.</p>
        <% @datos -> %>
          <p class="falta">
            El municipio no reportó sus finanzas a INEGI de 2019 a {@datos["ultimo_publicado"]}.
          </p>
        <% true -> %>
          <p class="falta">No hay finanzas municipales cargadas.</p>
      <% end %>

      <p class="fuente">INEGI · Finanzas Públicas Estatales y Municipales (EFIPEM)</p>

      <section :if={@planeacion} class="anexo" aria-labelledby="t-plan">
        <h3 id="t-plan">Instrumentos de planeación, {@planeacion["anio"] || 2024}</h3>

        <%= cond do %>
          <% @planeacion["varios"] -> %>
            <table class="libro">
              <tbody>
                <tr :for={i <- @planeacion["principales"]}>
                  <td>{corto(i["nombre"])}</td>
                  <td class="n">{i["si"]} de {i["n"]}</td>
                </tr>
              </tbody>
            </table>
            <p class="falta">Municipios que respondieron que sí lo tenían.</p>
          <% @planeacion["principales"] -> %>
            <table class="libro">
              <tbody>
                <tr :for={i <- @planeacion["principales"]}>
                  <td>{corto(i["nombre"])}</td>
                  <td class="n">{i["existio"] || "sin respuesta"}{vigencia(i)}</td>
                </tr>
              </tbody>
            </table>

            <p :if={@planeacion["otros"] != []} class="falta">
              También tenía: {Enum.map_join(@planeacion["otros"], "; ", &corto(&1["nombre"]))}.
            </p>
            <p class="falta">Lo que respondió el municipio; "no se sabe" no es "no".</p>
          <% true -> %>
            <p class="falta">El municipio no aparece en el censo de gobiernos municipales.</p>
        <% end %>

        <p class="fuente">INEGI · Censo Nacional de Gobiernos Municipales 2025</p>
      </section>
      {render_slot(@inner_block)}
    </article>
    """
  end

  # "Atlas de riesgos del municipio o demarcación territorial": en el perfil ya se sabe de quién.
  defp corto(nombre),
    do: String.replace(nombre, ~r/ del municipio o demarcación territorial$/, "")

  # La vigencia viene escrita a mano por cada municipio: un año, "INDEFINIDA" u otra cosa.
  defp vigencia(%{"existio" => "sí", "vigencia" => v}) when is_binary(v) do
    cond do
      String.match?(v, ~r/^\d{4}$/) -> ", vigente hasta #{v}"
      String.upcase(v) == "INDEFINIDA" -> ", sin fecha de término"
      true -> ""
    end
  end

  defp vigencia(_), do: ""

  ## Cifras

  @doc "Un número del perfil, o \"sin dato\"."
  def dato(v, decimales \\ nil)
  def dato(nil, _), do: "sin dato"
  def dato(v, nil), do: cifra(v)
  def dato(v, decimales), do: cifra(v, decimales)

  @doc """
  Gente o viviendas: exacta si la zona son municipios enteros; si es una
  estimación, con dos cifras significativas y ≈, para no fingir precisión.

      iex> MapoWeb.PerfilDocumentos.aprox(2811)
      "≈ 2,800"
      iex> MapoWeb.PerfilDocumentos.aprox(64)
      "≈ 64"
      iex> MapoWeb.PerfilDocumentos.aprox(128_400.7)
      "≈ 130,000"
  """
  def aprox(v) do
    n = round(v)
    paso = Integer.pow(10, max(length(Integer.digits(n)) - 2, 0))
    "≈ #{cifra(round(n / paso) * paso)}"
  end

  defp gente(nil, _clave), do: "sin dato"

  defp gente(d, clave) do
    cond do
      is_nil(d[clave]) -> "sin dato"
      d["estimada"] -> aprox(d[clave])
      true -> cifra(round(d[clave]))
    end
  end

  defp personas(%{"estimada" => true}, n), do: aprox(n)
  defp personas(_d, n), do: cifra(round(n))

  defp vivienda(_perfil, nil), do: "sin dato"

  defp vivienda(perfil, v),
    do: if(perfil["zona"]["entera"], do: cifra(round(v)), else: aprox(v))

  defp superficie(km2) when km2 < 10, do: "#{cifra(km2 / 1, 2)} km²"
  defp superficie(km2), do: "#{cifra(round(km2))} km²"

  defp pct(nil), do: "sin dato"
  defp pct(v) when v > 0 and v < 0.05, do: "<0.1 %"
  defp pct(v), do: "#{cifra(v / 1, 1)} %"

  defp anios(nil), do: "sin dato"
  defp anios(v), do: "#{cifra(v / 1, 1)} años"

  defp millon(v) when v >= 1_000_000, do: "#{cifra(v / 1_000_000, 2)} millones"
  defp millon(v), do: cifra(round(v))

  defp cuantos(1, uno, _varios), do: "1 #{uno}"
  defp cuantos(n, _uno, varios), do: "#{cifra(n)} #{varios}"

  # De quién son los documentos por municipio, dentro de una frase.
  defp suyos(perfil) do
    case perfil["zona"]["municipios"] do
      [m] -> m["nombre"]
      _ -> "estos municipios"
    end
  end

  defp millones(pares), do: Enum.map(pares, fn [c, v] -> [c, round(v / 1_000_000)] end)
  defp maximo(pares), do: pares |> Enum.map(&List.last/1) |> Enum.max(fn -> 0 end)

  # Conteos y millones que llegan como flotantes de mapo_core; null es reservado.
  defp entero(nil), do: "reservado"
  defp entero(x), do: cifra(round(x))

  defp parte(nil, _total), do: "reservado"
  defp parte(_n, total) when total in [nil, 0, +0.0], do: "sin dato"
  defp parte(n, total), do: "#{cifra(n / total * 100)} %"

  defp trimestre(t),
    do:
      Map.get(
        %{"trim1" => "primer", "trim2" => "segundo", "trim3" => "tercer", "trim4" => "cuarto"},
        t,
        t
      )
end
