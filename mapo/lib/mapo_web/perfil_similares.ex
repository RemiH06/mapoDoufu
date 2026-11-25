defmodule MapoWeb.PerfilSimilares do
  @moduledoc """
  Zonas parecidas a la del perfil (docs/producto/perfil.md), con lo que manda
  `mapo_core/similares.py`. Nunca un puntaje: cada variable dice por su cuenta
  si la otra zona cae en la banda de esta, y la lista va por cuántas caen. El
  desglose enseña las dos cifras, la banda y el reparto entre las comparadas.
  """

  use MapoWeb, :html

  import MapoWeb.Cifras

  @margenes [
    {"Muy cerca", "muy_cerca"},
    {"Cerca", "cerca"},
    {"Con holgura", "holgado"}
  ]
  @dondes [
    {"En todo lo comparable", "todo"},
    {"En el mismo municipio", "mismo"},
    {"En otros municipios", "otros"}
  ]

  def margenes_validos, do: Enum.map(@margenes, &elem(&1, 1))
  def dondes_validos, do: Enum.map(@dondes, &elem(&1, 1))

  @areas [
    {"poblacion", "Población"},
    {"vivienda", "Vivienda"},
    {"economia", "Negocios"},
    {"empleo", "Empleo y salud"},
    {"servicios", "Servicios a pie"},
    {"seguridad", "Seguridad"},
    {"hacienda", "Hacienda"}
  ]

  def areas_validas, do: Enum.map(@areas, &elem(&1, 0))

  attr :resultado, :map, default: nil
  attr :buscando, :boolean, required: true
  attr :error, :string, default: nil
  attr :filtro, :map, required: true, doc: "`%{areas, margen, donde}`"
  attr :abierto, :string, default: nil
  attr :nivel, :string, required: true, doc: "municipio | colonia"
  attr :ruta, :any, required: true, doc: "función: clave de zona -> ruta de su perfil"

  def similares(assigns) do
    assigns =
      assign(assigns,
        margenes: @margenes,
        dondes: @dondes,
        # Seguridad y hacienda solo existen por municipio.
        areas:
          if(assigns.nivel == "municipio",
            do: @areas,
            else: Enum.reject(@areas, &(elem(&1, 0) in ~w(seguridad hacienda)))
          )
      )

    ~H"""
    <section
      id="similares"
      class="similares pegado sin-cinta"
      data-piel="urbanismo"
      aria-labelledby="t-sim"
    >
      <header>
        <h2 id="t-sim">Zonas que se parecen</h2>
        <span class="tipo">Cotejo</span>
      </header>

      <form id="similares-form" phx-change="similares" phx-submit="similares">
        <fieldset>
          <legend>En qué</legend>
          <label :for={{clave, titulo} <- @areas} class="chip">
            <input
              type="checkbox"
              name="sim[areas][]"
              value={clave}
              checked={clave in @filtro.areas}
            />
            <span>{titulo}</span>
          </label>
        </fieldset>
        <label class="campo-sim">
          <span>Qué tanto</span>
          <select name="sim[margen]">
            {Phoenix.HTML.Form.options_for_select(@margenes, @filtro.margen)}
          </select>
        </label>
        <label :if={@nivel == "colonia"} class="campo-sim">
          <span>Dónde</span>
          <select name="sim[donde]">
            {Phoenix.HTML.Form.options_for_select(@dondes, @filtro.donde)}
          </select>
        </label>
        <button class="boton" phx-disable-with="Buscando...">Buscar</button>
      </form>
      <p class="pista-sim">
        Sin marcar ninguna, se compara en todas. Nada se junta en un puntaje: cada dato se parece o no por su cuenta, y la lista va por cuántos se parecen.
      </p>

      <p :if={@buscando} class="consultando" role="status">Buscando...</p>
      <p :if={@error} class="aviso" role="alert">{@error}</p>
      <p :if={@resultado && @resultado["motivo"]} class="falta" id="similares-motivo">
        {@resultado["motivo"]}
      </p>

      <div :if={@resultado && !@resultado["motivo"]} id="similares-resultado">
        <p :if={@resultado["referencia"]["chica"]} class="aviso">
          Esta zona tiene menos de {@resultado["min_poblacion"]} habitantes: sus cifras son muy inciertas, y los parecidos también.
        </p>
        <p class="falta">
          Entre {cifra(@resultado["comparadas"])} {@resultado["nivel_nombre"]} de {Enum.join(
            @resultado["estados"],
            ", "
          )}{if @resultado["min_poblacion"],
            do: " con #{@resultado["min_poblacion"]} habitantes o más"}. Un dato se parece si queda en la banda de esta zona, que mide hacia cada lado {frase_margen(
            @resultado["fraccion"]
          )} el tramo donde cae la mitad central de las comparadas.
        </p>

        <p :if={@resultado["resultados"] == []} class="falta">
          Ninguna tiene datos suficientes para compararla.
        </p>

        <ol class="sim-lista">
          <li
            :for={r <- @resultado["resultados"]}
            id={"sim-#{dom(r["clave"])}"}
            class={[@abierto == r["clave"] && "abierto"]}
          >
            <div class="sim-cab">
              <div class="sim-nombre">
                <.link patch={@ruta.(r["clave"])} class="sim-enlace">{r["nombre"]}</.link>
                <small>{r["detalle"]} · {habitantes(r["pobtot"], @resultado["nivel"])}</small>
              </div>
              <p class="sim-cuenta">
                <b class="num">{r["parecidas"]}</b> de {r["con_dato"]} se parecen
              </p>
              <button
                type="button"
                id={"ver-#{dom(r["clave"])}"}
                class="chico"
                phx-click="abrir_similar"
                phx-value-clave={r["clave"]}
                aria-expanded={to_string(@abierto == r["clave"])}
              >
                {if @abierto == r["clave"], do: "Cerrar", else: "En qué"}
              </button>
            </div>
            <ul class="sim-huella" aria-hidden="true">
              <li :for={{titulo, vs} <- por_area(@resultado)} class="sim-grupo">
                <span>{titulo}</span>
                <span class="sim-marcas">
                  <i
                    :for={v <- vs}
                    data-estado={r["valores"][v["clave"]]["estado"]}
                    title={frase(v, r["valores"][v["clave"]])}
                  ></i>
                </span>
              </li>
            </ul>
            <.desglose :if={@abierto == r["clave"]} resultado={@resultado} fila={r} />
          </li>
        </ol>
        <p class="sim-leyenda">
          <span><i data-estado="parecida"></i> se parece</span>
          <span><i data-estado="mayor"></i> tiene más</span>
          <span><i data-estado="menor"></i> tiene menos</span>
          <span><i data-estado="sin_dato"></i> sin dato</span>
        </p>
        <p class="fuente">
          Censo 2020, DENUE{if @resultado["nivel"] == "municipio",
            do:
              ", Censos Económicos 2024, IMSS, SESNSP (promedio de los tres últimos años completos) y EFIPEM"} y minutos a pie de Mapo · calculado el {@resultado[
            "calculado"
          ]}
        </p>
      </div>
    </section>
    """
  end

  attr :resultado, :map, required: true
  attr :fila, :map, required: true

  defp desglose(assigns) do
    ~H"""
    <div class="sim-desglose" tabindex="0" role="region" aria-label={"Desglose de #{@fila["nombre"]}"}>
      <table>
        <thead>
          <tr>
            <th scope="col">Dato</th>
            <th scope="col" class="n">{@resultado["referencia"]["nombre"]}</th>
            <th scope="col" class="n">{@fila["nombre"]}</th>
            <th scope="col" class="sim-col-regla">Entre las comparadas</th>
            <th scope="col">Cómo queda</th>
          </tr>
        </thead>
        <tbody :for={{titulo, vs} <- por_area(@resultado)}>
          <tr class="sim-area">
            <th colspan="5" scope="colgroup">{titulo}</th>
          </tr>
          <tr :for={v <- vs} data-estado={@fila["valores"][v["clave"]]["estado"]}>
            <th scope="row">
              {v["etiqueta"]} <small :if={v["unidad"] != ""}>{v["unidad"]}</small>
            </th>
            <td class="n" data-de="Aquí">{valor(v, v["valor"])}</td>
            <td class="n" data-de="Allá">{valor(v, @fila["valores"][v["clave"]]["valor"])}</td>
            <td class="sim-col-regla">
              <.regla :if={v["banda"]} v={v} otro={@fila["valores"][v["clave"]]["valor"]} />
            </td>
            <td class="sim-estado">
              <i data-estado={@fila["valores"][v["clave"]]["estado"]} aria-hidden="true"></i>
              {estado(@fila["valores"][v["clave"]]["estado"])}
            </td>
          </tr>
        </tbody>
      </table>
      <p class="falta">
        La regla va del 10 % más bajo al 10 % más alto de las comparadas; la franja es la banda, la raya es {@resultado[
          "referencia"
        ]["nombre"]} y el punto, {@fila["nombre"]}.
      </p>
    </div>
    """
  end

  attr :v, :map, required: true
  attr :otro, :any, required: true

  defp regla(assigns) do
    b = assigns.v["banda"]
    log? = assigns.v["log"]
    ref = assigns.v["valor"]
    e = &escala(&1, log?)
    minimo = e.(Enum.min([b["p10"], b["bajo"], ref]))
    maximo = e.(Enum.max([b["p90"], b["alto"], ref]))
    pos = &posicion(e.(&1), minimo, maximo)

    assigns =
      assign(assigns,
        desde: pos.(b["bajo"]),
        ancho: pos.(b["alto"]) - pos.(b["bajo"]),
        ref: pos.(ref),
        mitad: pos.(b["p50"]),
        otro_x: assigns.otro && pos.(assigns.otro),
        fuera: assigns.otro && fuera(e.(assigns.otro), minimo, maximo),
        titulo:
          "Banda: de #{valor(assigns.v, b["bajo"])} a #{valor(assigns.v, b["alto"])}. Mediana de #{cifra(b["comparadas"])} comparadas: #{valor(assigns.v, b["p50"])}"
      )

    ~H"""
    <span class="regla" title={@titulo}>
      <i class="regla-banda" style={"left: #{@desde}%; width: #{@ancho}%"}></i>
      <i class="regla-mitad" style={"left: #{@mitad}%"}></i>
      <i class="regla-ref" style={"left: #{@ref}%"}></i>
      <i :if={@otro_x} class={["regla-otro", @fuera]} style={"left: #{@otro_x}%"}></i>
    </span>
    """
  end

  defp escala(x, true), do: :math.log(max(x, 0.01))
  defp escala(x, _), do: x / 1

  defp posicion(_x, a, b) when b - a <= 0, do: 50.0
  defp posicion(x, a, b), do: Float.round(min(max((x - a) / (b - a), 0.0), 1.0) * 100, 1)

  defp fuera(x, a, b) do
    cond do
      x < a -> "antes"
      x > b -> "despues"
      true -> nil
    end
  end

  # Las variables en el orden de mapo_core, por área.
  defp por_area(resultado) do
    for {clave, titulo} <- @areas,
        vs = Enum.filter(resultado["variables"], &(&1["area"] == clave)),
        vs != [],
        do: {titulo, vs}
  end

  defp valor(_v, nil), do: "sin dato"
  defp valor(%{"decimales" => 0}, x), do: cifra(round(x))
  defp valor(%{"decimales" => d}, x), do: cifra(x / 1, d)

  defp estado("parecida"), do: "se parece"
  defp estado("mayor"), do: "tiene más"
  defp estado("menor"), do: "tiene menos"
  defp estado(_), do: "sin dato"

  defp frase(v, celda),
    do: "#{v["etiqueta"]}: #{valor(v, celda["valor"])} contra #{valor(v, v["valor"])}"

  defp habitantes(nil, _nivel), do: "sin dato de habitantes"
  defp habitantes(n, "municipio"), do: "#{cifra(n)} hab."
  defp habitantes(n, _nivel), do: "#{MapoWeb.PerfilDocumentos.aprox(n)} hab."

  defp frase_margen(0.25), do: "un cuarto de lo que mide"
  defp frase_margen(0.5), do: "la mitad de lo que mide"
  defp frase_margen(_), do: "lo mismo que mide"

  defp dom(clave), do: String.replace(clave, ~r/[^\w]/, "_")
end
