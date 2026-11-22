defmodule MapoWeb.PerfilLive.Index do
  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.MapoCore
  alias Mapo.Notas
  alias Mapo.Teams

  # Sobre el plano del municipio quedan cinco documentos, uno por enfoque y
  # cada uno con su piel (docs/arquitectura/decisiones.md, "Concepto
  # visual"). Nada se resume en un puntaje: cada documento dice su cifra, su
  # fuente y lo que no sabe. La consulta va en la URL para poder compartirla.
  #
  # Cada documento lleva al pie las notas del equipo sobre ese municipio
  # (`Mapo.Notas`): a mano y en lápiz, separadas de lo impreso, y en vivo con
  # quien tenga abierto el mismo perfil con el mismo equipo.

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
        
        <label :if={length(@equipos) > 1} class="notas-de">
          <span>Notas de</span>
          <select name="perfil[equipo]" class="membrete-select">
            {Phoenix.HTML.Form.options_for_select(
              Enum.map(@equipos, &{&1.name, &1.id}),
              @equipo_id
            )}
          </select>
        </label>
         <.button class="boton primario" phx-disable-with="Consultando...">Ver perfil</.button>
        <p>
          Seis documentos, uno por enfoque. Ninguno se resume en un puntaje. Si una fuente no
          cubre el municipio, el documento lo dice.
        </p>
        
        <p :if={@estados == []} class="aviso">
          No se pudo cargar la lista de estados: mapo_core no responde o todavía no hay estados
          descargados.
        </p>
      </.form>
      
      <p :if={@consultando} class="consultando pegado sin-cinta">
        Consultando las fuentes, tarda unos segundos.
      </p>
      
      <div :if={@consultando} class="documentos" aria-hidden="true">
        <article
          :for={{piel, titulo, tipo} <- esqueleto()}
          class={"documento pegado esqueleto d-#{piel}"}
          data-piel={piel}
        >
          <header>
            <h2>{titulo}</h2>
             <span class="tipo">{tipo}</span>
          </header>
           <span :for={_ <- 1..4} class="renglon-vacio"></span>
        </article>
      </div>
      
      <div :if={@perfil} class="documentos">
        <.cedula datos={@perfil["demografia"]} rezago={@perfil["rezago_social"]}>
          <.notas
            documento="demografia"
            notas={@notas["demografia"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.cedula>
        
        <.libro datos={@perfil["comercio"]} economia={@perfil["economia"]}>
          <.notas
            documento="comercio"
            notas={@notas["comercio"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.libro>
        
        <.ticket datos={@perfil["consumo"]}>
          <.notas
            documento="consumo"
            notas={@notas["consumo"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.ticket>
        
        <.expediente datos={@perfil["seguridad"]}>
          <.notas
            documento="seguridad"
            notas={@notas["seguridad"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.expediente>
        
        <.tarjeta datos={@perfil["laboral"]} empleo={@perfil["empleo_formal"]}>
          <.notas
            documento="laboral"
            notas={@notas["laboral"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.tarjeta>
        
        <.cuenta datos={@perfil["hacienda"]} planeacion={@perfil["planeacion"]}>
          <.notas
            documento="hacienda"
            notas={@notas["hacienda"] || []}
            equipo?={@equipo_id != nil}
            ronda={@nota_ronda}
          />
        </.cuenta>
      </div>
    </Layouts.app>
    """
  end

  # Los seis papeles ya pegados en su lugar mientras llega el perfil, para
  # que la mesa no salte. Sin datos: decir "no hay" sería mentir.
  defp esqueleto do
    [
      {"demografia", "Población", "Cédula censal"},
      {"comercio", "Negocios por giro", "Libro mayor"},
      {"consumo", "Gasto de los hogares", "Ticket de caja"},
      {"seguridad", "Incidencia delictiva", "Expediente"},
      {"laboral", "Empleo", "Tarjeta de checador"},
      {"hacienda", "Hacienda municipal", "Cuenta pública"}
    ]
  end

  attr :datos, :map
  attr :rezago, :map, default: nil
  slot :inner_block

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
      
      <section :if={@rezago} class="anexo" aria-labelledby="t-rezago">
        <h3 id="t-rezago">Rezago social por AGEB urbana</h3>
        
        <%= if @rezago["grados"] do %>
          <table class="libro">
            <thead>
              <tr>
                <th>Grado</th>
                
                <th class="n">AGEB</th>
                
                <th class="n">Personas</th>
              </tr>
            </thead>
            
            <tbody>
              <tr :for={g <- @rezago["grados"]}>
                <td>{g["grado"]}</td>
                
                <td class="n">{cifra(g["agebs"])}</td>
                
                <td class="n">{entero(g["personas"])}</td>
              </tr>
            </tbody>
          </table>
          
          <p class="falta">
            Grado de CONEVAL con 17 indicadores del censo 2020 (educación, salud, vivienda y bienes); no mide pobreza ni ingreso. Solo AGEB urbanas: la gente del campo no entra.
          </p>
        <% else %>
          <p class="falta">CONEVAL no publica AGEB urbanas de este municipio.</p>
        <% end %>
        
        <p class="fuente">CONEVAL · Grado de Rezago Social 2020</p>
      </section>
       {render_slot(@inner_block)}
    </article>
    """
  end

  attr :datos, :map
  slot :inner_block

  attr :economia, :map, default: nil

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
      
      <section :if={@economia} class="anexo" aria-labelledby="t-ce">
        <h3 id="t-ce">Tamaño de la economía, {@economia["anio_datos"] || 2023}</h3>
        
        <%= if t = @economia["total"] do %>
          <table class="libro">
            <tbody>
              <tr>
                <td>Unidades económicas</td>
                
                <td class="n">{entero(t["ue"])}</td>
              </tr>
              
              <tr>
                <td>Personal ocupado</td>
                
                <td class="n">{entero(t["personal"])}</td>
              </tr>
              
              <tr>
                <td>Remuneraciones (millones de pesos)</td>
                
                <td class="n">{entero(t["remuneraciones"])}</td>
              </tr>
              
              <tr>
                <td>Ingresos (millones de pesos)</td>
                
                <td class="n">{entero(t["ingresos"])}</td>
              </tr>
              
              <tr>
                <td>Valor agregado (millones de pesos)</td>
                
                <td class="n">{entero(t["vacb"])}</td>
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
          
          <p :if={@economia["reservados"] > 0} class="falta">
            INEGI reserva el personal de {@economia["reservados"]} {if @economia["reservados"] == 1,
              do: "sector",
              else: "sectores"} con pocas unidades: no se cuentan como cero.
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

  attr :datos, :map
  slot :inner_block

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
       {render_slot(@inner_block)}
      <div class="dientes" aria-hidden="true"></div>
    </article>
    """
  end

  attr :datos, :map
  slot :inner_block

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
       {render_slot(@inner_block)}
    </article>
    """
  end

  attr :documento, :string, required: true
  attr :notas, :list, required: true
  attr :equipo?, :boolean, required: true
  attr :ronda, :integer, required: true

  # La forma lleva la ronda en el id: al guardar una nota se vuelve a crear
  # vacía y cerrada.
  defp notas(assigns) do
    assigns = assign(assigns, forma: "nota-forma-#{assigns.documento}-#{assigns.ronda}")

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
  attr :planeacion, :map, default: nil
  slot :inner_block

  # Cuenta pública: de dónde saca dinero el municipio y en qué lo gasta (EFIPEM).
  # Pesos corrientes de cada año; nada se ajusta por inflación.
  defp cuenta(assigns) do
    d = assigns.datos

    assigns =
      assign(assigns,
        ingresos: if(d && d["ingresos"], do: millones(d["ingresos"]), else: []),
        egresos: if(d && d["egresos"], do: millones(d["egresos"]), else: [])
      )

    ~H"""
    <article class="documento pegado d-hacienda" data-piel="urbanismo" aria-labelledby="t-hac">
      <header>
        <h2 id="t-hac">Hacienda municipal</h2>
         <span class="tipo">Cuenta pública</span>
      </header>
      
      <%= cond do %>
        <% @datos && @datos["total_ingresos"] -> %>
          <p>Ingresos de {@datos["anio"]}, millones de pesos</p>
          
          <p class="sello num">{dato(@datos["total_ingresos"] / 1_000_000)}</p>
          
          <dl>
            <dt>Recauda el municipio</dt>
            
            <dd>
              {dato(@datos["propios_pct"], 1)} % (impuestos, derechos, productos, aprovechamientos)
            </dd>
            
            <dt>Le transfieren</dt>
            
            <dd>{dato(@datos["transferencias_pct"], 1)} % (participaciones y aportaciones)</dd>
            
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
          
          <h3>Ingresos por capítulo</h3>
           <.barras tipos={@ingresos} maximo={maximo(@ingresos)} />
          <h3>Egresos por capítulo</h3>
           <.barras tipos={@egresos} maximo={maximo(@egresos)} />
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
        
        <%= if @planeacion["principales"] do %>
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
        <% else %>
          <p class="falta">El municipio no aparece en el censo de gobiernos municipales.</p>
        <% end %>
        
        <p class="fuente">INEGI · Censo Nacional de Gobiernos Municipales 2025</p>
      </section>
       {render_slot(@inner_block)}
    </article>
    """
  end

  # La vigencia viene escrita a mano por cada municipio: un año, "INDEFINIDA" u otra cosa.
  # "Atlas de riesgos del municipio o demarcación territorial": en el perfil ya se sabe de quién.
  defp corto(nombre),
    do: String.replace(nombre, ~r/ del municipio o demarcación territorial$/, "")

  defp vigencia(%{"existio" => "sí", "vigencia" => v}) when is_binary(v) do
    cond do
      String.match?(v, ~r/^\d{4}$/) -> ", vigente hasta #{v}"
      String.upcase(v) == "INDEFINIDA" -> ", sin fecha de término"
      true -> ""
    end
  end

  defp vigencia(_), do: ""

  defp millones(pares), do: Enum.map(pares, fn [c, v] -> [c, round(v / 1_000_000)] end)
  defp maximo(pares), do: pares |> Enum.map(&List.last/1) |> Enum.max(fn -> 0 end)

  # Conteos y millones que llegan como flotantes de mapo_core; null es reservado.
  defp entero(nil), do: "reservado"
  defp entero(x), do: cifra(round(x))

  defp parte(nil, _total), do: "reservado"
  defp parte(_n, total) when total in [nil, 0, +0.0], do: "sin dato"
  defp parte(n, total), do: "#{cifra(n / total * 100)} %"

  attr :datos, :map
  attr :empleo, :map
  slot :inner_block

  # Lo del municipio (IMSS) primero; la desocupación es del estado entero.
  defp tarjeta(assigns) do
    e = assigns.empleo

    assigns =
      assign(assigns,
        divisiones:
          if(e, do: Enum.map(e["por_division"], &[&1["nombre"], &1["puestos"]]), else: []),
        maximo:
          if(e,
            do: e["por_division"] |> Enum.map(& &1["puestos"]) |> Enum.max(fn -> 0 end),
            else: 0
          )
      )

    ~H"""
    <article class="documento pegado d-laboral" data-piel="laboral" aria-labelledby="t-lab">
      <header>
        <h2 id="t-lab">Empleo</h2>
         <span class="tipo">Tarjeta de checador</span>
      </header>
      
      <%= cond do %>
        <% @empleo && @empleo["puestos"] > 0 -> %>
          <p>Puestos de trabajo registrados en el IMSS, {mes(@empleo["periodo"])}</p>
          
          <p class="sello num">{cifra(@empleo["puestos"])}</p>
          
          <dl>
            <dt>Permanentes</dt>
            
            <dd>{cifra(@empleo["permanentes"])}</dd>
            
            <dt>Eventuales</dt>
            
            <dd>{cifra(@empleo["eventuales"])}</dd>
            
            <dt>Salario diario promedio</dt>
            
            <dd>${dato(@empleo["salario_diario"], 2)}</dd>
            
            <dt>Contra un año antes</dt>
            
            <dd :if={@empleo["anual"]}>
              {cifra(@empleo["anual"]["variacion"], 2)} % (desde {mes(@empleo["anual"]["periodo"])})
            </dd>
            
            <dd :if={!@empleo["anual"]}>sin dato: falta el mismo mes del año anterior</dd>
          </dl>
           <.barras tipos={@divisiones} maximo={@maximo} />
          <p class="falta">
            Solo empleo formal, en el municipio donde está registrado el patrón (no donde vive
            ni donde trabaja cada persona). El salario es el de cotización, con tope de 25 UMA: {dato(
              @empleo["parte_rango_tope"],
              1
            )} % de los puestos está en el último rango.
          </p>
        <% @empleo && @empleo["puestos_estado_sin_municipio"] > 0 -> %>
          <p class="falta">
            El IMSS no asigna municipio a {cifra(@empleo["puestos_estado_sin_municipio"])} puestos
            de este estado ({mes(@empleo["periodo"])}); en la Ciudad de México, a ninguno.
          </p>
        <% @empleo -> %>
          <p class="falta">
            El IMSS no registra puestos de trabajo en este municipio ({mes(@empleo["periodo"])}).
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
      
      <p :if={!@datos} class="falta">No hay datos de la ENOE cargados para este estado.</p>
      
      <p class="fuente">IMSS · datos abiertos de asegurados · INEGI · ENOE</p>
       {render_slot(@inner_block)}
    </article>
    """
  end

  @impl true
  def mount(_params, _session, socket) do
    equipos = socket.assigns.current_scope |> Teams.list_teams() |> Enum.sort_by(& &1.name)

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
       consultando: false,
       equipos: equipos,
       equipo_id: equipos |> List.first() |> then(&(&1 && &1.id)),
       notas_de: nil,
       notas: %{},
       nota_ronda: 0
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
    socket = cambiar_equipo(socket, params["equipo"])

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

  def handle_event("crear_nota", %{"documento" => documento, "texto" => texto}, socket) do
    case socket.assigns.notas_de do
      {equipo, cve_ent, cve_mun} ->
        attrs = %{
          "cve_ent" => cve_ent,
          "cve_mun" => cve_mun,
          "documento" => documento,
          "texto" => texto
        }

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
      {equipo, _, _} ->
        {:ok, _nota} = Notas.delete_nota(socket.assigns.current_scope, equipo, id)
        {:noreply, socket}

      nil ->
        {:noreply, socket}
    end
  end

  # Las notas llegan por PubSub también a quien las escribe: una sola vía
  # para pintarlas, como las marcas de las sesiones.
  @impl true
  def handle_info({:nota_creada, nota}, socket) do
    if socket.assigns.notas_de == {nota.team_id, nota.cve_ent, nota.cve_mun} do
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
        |> cargar_notas(cve_ent, cve_mun)
        |> start_async(:perfil, fn -> MapoCore.perfil_zona(cve_ent, cve_mun) end)
        |> start_async(:plano, fn -> MapoCore.agebs(cve_ent, cve_mun) end)

      _ ->
        put_flash(socket, :error, "Ese municipio no está en el catálogo.")
    end
  end

  defp cambiar_equipo(socket, nil), do: socket

  defp cambiar_equipo(socket, id) do
    case Enum.find(socket.assigns.equipos, &(to_string(&1.id) == id)) do
      %{id: equipo} when equipo != socket.assigns.equipo_id ->
        socket = assign(socket, equipo_id: equipo)

        case socket.assigns.notas_de do
          {_, cve_ent, cve_mun} -> cargar_notas(socket, cve_ent, cve_mun)
          nil -> socket
        end

      _ ->
        socket
    end
  end

  # Cambia el tópico al equipo y municipio de ahora y trae sus notas.
  defp cargar_notas(socket, cve_ent, cve_mun) do
    %{equipo_id: equipo, notas_de: previa, current_scope: scope} = socket.assigns
    clave = equipo && {equipo, cve_ent, cve_mun}

    if connected?(socket) and previa != clave do
      with {e, ent, mun} <- previa, do: Notas.unsubscribe(e, ent, mun)
      if clave, do: Notas.subscribe(equipo, cve_ent, cve_mun)
    end

    notas =
      if clave,
        do: scope |> Notas.list_notas(equipo, cve_ent, cve_mun) |> Enum.group_by(& &1.documento),
        else: %{}

    assign(socket, notas_de: clave, notas: notas)
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
