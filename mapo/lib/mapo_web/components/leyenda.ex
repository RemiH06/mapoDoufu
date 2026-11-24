defmodule MapoWeb.Leyenda do
  @moduledoc """
  Leyendas de las capas por clases (docs/producto/escalas.md): las clases de
  color (`MapoWeb.Escala`), los círculos proporcionales, el 3x3, la altura y
  la confianza. Los colores son los mismos que pinta el hook.
  """
  use Phoenix.Component

  alias MapoWeb.Escala

  attr :escala, :map, default: nil
  attr :tinta, :string, default: nil, doc: "enfoque del acetato; sin él, demografía"
  attr :titulo, :string, default: nil
  attr :unidad, :string, default: nil

  def clases(assigns) do
    ~H"""
    <div
      :if={@escala}
      class="escala"
      aria-label={"#{@titulo || "Clases"}: #{@escala.clases} clases"}
      style={"--n: #{@escala.clases};" <> if(@tinta, do: " --tinta-escala: var(--f-#{@tinta})", else: "")}
    >
      <p :if={@titulo} class="escala-titulo">
        {@titulo}<span :if={@unidad} class="escala-unidad">, {@unidad}</span>
      </p>

      <ol>
        <li
          :for={i <- 0..(@escala.clases - 1)}
          class={@escala.colores && "pinta"}
          style={muestra(@escala, i)}
          title={rango(@escala, i)}
        >
        </li>

        <li :if={@escala.nulos > 0} class="nula" title="Sin dato"></li>
      </ol>

      <div class="marcas num">
        <span :for={v <- Enum.take(@escala.limites, @escala.clases)}>{Escala.cifra_leyenda(v)}</span>
        <span>a {Escala.cifra_leyenda(List.last(@escala.limites))}</span>
      </div>

      <p :if={@escala.nulos > 0} class="escala-nota">Sin dato: {@escala.nulos}</p>

      <p :if={@escala.aviso} class="escala-nota">{@escala.aviso}</p>
    </div>
    """
  end

  defp muestra(%{colores: nil, opacidades: o}, i), do: "opacity: #{Enum.at(o, i)}"

  defp muestra(%{colores: c}, i),
    do: "--c: #{Enum.at(c.claro, i)}; --c-osc: #{Enum.at(c.oscuro, i)}"

  defp rango(e, i) do
    "de #{Escala.cifra_leyenda(Enum.at(e.limites, i))} a #{Escala.cifra_leyenda(Enum.at(e.limites, i + 1))}"
  end

  attr :circulos, :map, required: true
  attr :titulo, :string, required: true
  attr :unidad, :string, default: nil

  def circulos(assigns) do
    # Arriba sobra lugar para la cifra del círculo más grande.
    alto = 2 * assigns.circulos.radio + 8
    assigns = assign(assigns, alto: alto)

    ~H"""
    <div class="escala escala-circulos">
      <p class="escala-titulo">
        {@titulo}<span :if={@unidad} class="escala-unidad">, {@unidad}</span>
      </p>

      <div class="circulos-fila">
        <svg
          width={@alto + 70}
          height={@alto}
          viewBox={"0 0 #{@alto + 70} #{@alto}"}
          role="img"
          aria-label={"Círculos: el área va con el valor; el más grande es #{Escala.cifra_leyenda(hd(@circulos.referencias).valor)}"}
        >
          <g :for={r <- @circulos.referencias}>
            <circle cx={@circulos.radio + 1} cy={@alto - 1 - r.radio} r={r.radio} class="circulo-ref" />
            <line
              x1={@circulos.radio + 1}
              x2={@alto + 6}
              y1={@alto - 1 - 2 * r.radio}
              y2={@alto - 1 - 2 * r.radio}
              class="circulo-guia"
            />
            <text x={@alto + 9} y={@alto + 3 - 2 * r.radio} class="circulo-cifra">
              {Escala.cifra_leyenda(r.valor)}
            </text>
          </g>
        </svg>
      </div>

      <p class="escala-nota">
        El área va con el valor; de lejos se encogen todos igual.<span :if={@circulos.negativos}> Hueco: negativo.</span>
        <span :if={@circulos.nulos > 0}>Sin dato: {@circulos.nulos}.</span>
      </p>
    </div>
    """
  end

  attr :bivariado, :map, required: true
  attr :a, :map, required: true, doc: "nombre y unidad del primero (columnas)"
  attr :b, :map, required: true, doc: "nombre y unidad del segundo (renglones)"

  def bivariado(assigns) do
    ~H"""
    <div class="escala escala-bivariada">
      <p class="escala-titulo">Las dos tasas en 3x3 ({metodo(@bivariado.metodo)})</p>

      <div class="bivariada">
        <span class="eje-b">↑ {@b.nombre}</span>
        <ol class="rejilla" aria-label="Rejilla de 3 por 3">
          <li
            :for={i <- [6, 7, 8, 3, 4, 5, 0, 1, 2]}
            style={"background: #{Enum.at(@bivariado.colores, i)}"}
            title={"#{@a.nombre}: #{tercio(rem(i, 3))}; #{@b.nombre}: #{tercio(div(i, 3))}"}
          >
          </li>
        </ol>
        <span class="eje-a">{@a.nombre} →</span>
      </div>

      <p class="escala-nota">
        Cortes →: {cortes(@bivariado.a)}; ↑: {cortes(@bivariado.b)}.
        <span :if={@bivariado.nulos > 0}>Sin uno de los dos: {@bivariado.nulos}.</span>
      </p>
    </div>
    """
  end

  defp cortes(e), do: Enum.map_join(e.cortes, " y ", &Escala.cifra_leyenda/1)

  defp tercio(0), do: "bajo"
  defp tercio(1), do: "medio"
  defp tercio(2), do: "alto"

  defp metodo("cuantiles"), do: "terciles"
  defp metodo("naturales"), do: "cortes naturales"
  defp metodo("iguales"), do: "intervalos iguales"

  attr :altura, :map, required: true
  attr :texto, :map, required: true

  def altura(assigns) do
    ~H"""
    <div class="escala">
      <p class="escala-titulo">Altura: {@texto.nombre}, {@texto.unidad}</p>

      <p class="escala-nota">
        Al ras {Escala.cifra_leyenda(@altura.min)}; la más alta {Escala.cifra_leyenda(@altura.max)}.
        <span :if={@altura.nulos > 0}>Sin dato, al ras y punteada: {@altura.nulos}.</span>
      </p>
    </div>
    """
  end

  attr :tipo, :atom, required: true, doc: ":cv (Intercensal) o :rango (precio estimado)"
  attr :tinta, :string, required: true

  def confianza(assigns) do
    ~H"""
    <div class="escala escala-confianza" style={"--n: 3; --tinta-escala: var(--f-#{@tinta})"}>
      <p class="escala-titulo">
        {if @tipo == :cv, do: "Precisión de la Intercensal", else: "Precio estimado por rango"}
      </p>

      <ol :if={@tipo == :cv}>
        <li style="opacity: 0.8" title="Coeficiente de variación menor a 15 %"></li>

        <li style="opacity: 0.45" title="De 15 a 30 %"></li>

        <li style="opacity: 0.18" title="30 % o más"></li>
      </ol>

      <div :if={@tipo == :cv} class="marcas">
        <span>CV &lt; 15 %</span><span>15 a 30</span><span>30 o más</span>
      </div>

      <p class="escala-nota">
        {if @tipo == :cv,
          do: "Más tenue, menos precisa la estimación por muestra.",
          else:
            "Tenue y punteada: estimada, con su rango entero dentro de esa clase. Solo punteada: su rango cruza clases y no se pinta."}
      </p>
    </div>
    """
  end
end
