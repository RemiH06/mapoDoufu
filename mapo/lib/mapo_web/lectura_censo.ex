defmodule MapoWeb.LecturaCenso do
  @moduledoc """
  Cómo se lee un indicador del censo por AGEB en `/mapa`
  (docs/producto/escalas.md).

  Un conteo (personas, hogares, viviendas) nunca va como coropleta: una AGEB
  grande tiene más de todo por ser grande. Se ve en círculos proporcionales o
  se vuelve tasa: % de su denominador natural, por cada 1,000 habitantes o por
  km². Los combinados (A ÷ B, A − B, cambio %) son entre indicadores del
  mismo censo y del mismo nivel, con su fórmula y su unidad a la vista; nada
  de índices ponderados.

  Con un segundo indicador, el canal lo decide el tipo: el conteo va en
  círculos y la tasa en color; dos tasas, en 3x3 o con la segunda como altura.
  Dos conteos no se leen juntos.
  """

  alias Mapo.MapoCore

  @promedios %{"graproes" => "años", "prom_ocup" => "personas por vivienda"}

  @personas ~w(pobtot pobfem pobmas p_0a2 p_3a5 p_6a11 p_12a14 p_15a17 p_18a24 p_60ymas pea pea_f pea_m pe_inac pocupada pdesocup pder_ss)
  @unidad Map.merge(
            Map.new(@personas, &{&1, "personas"}),
            %{
              "tothog" => "hogares",
              "vivtot" => "viviendas",
              "tvivhab" => "viviendas",
              "vph_inter" => "viviendas",
              "vph_pc" => "viviendas",
              "vph_autom" => "viviendas",
              "vph_cel" => "viviendas",
              "vph_snbien" => "viviendas"
            }
          )
  @singular %{"personas" => "persona", "hogares" => "hogar", "viviendas" => "vivienda"}

  # El denominador natural de cada conteo: de quién es el porcentaje. Los
  # VPH_* son sobre TVIVPARHAB (con VIVPAR_HAB, 209 AGEB de Jalisco pasaban
  # del 100 %).
  @denominador %{
    "pobfem" => "pobtot",
    "pobmas" => "pobtot",
    "p_0a2" => "pobtot",
    "p_3a5" => "pobtot",
    "p_6a11" => "pobtot",
    "p_12a14" => "pobtot",
    "p_15a17" => "pobtot",
    "p_18a24" => "pobtot",
    "p_60ymas" => "pobtot",
    "pder_ss" => "pobtot",
    "pea" => "p_12ymas",
    "pe_inac" => "p_12ymas",
    "pea_f" => "p_12ymas_f",
    "pea_m" => "p_12ymas_m",
    "pocupada" => "pea",
    "pdesocup" => "pea",
    "tvivhab" => "vivtot",
    "vph_inter" => "tvivparhab",
    "vph_pc" => "tvivparhab",
    "vph_autom" => "tvivparhab",
    "vph_cel" => "tvivparhab",
    "vph_snbien" => "tvivparhab"
  }
  @de_quien %{
    "pobtot" => "la población",
    "p_12ymas" => "la población de 12 años o más",
    "p_12ymas_f" => "las mujeres de 12 años o más",
    "p_12ymas_m" => "los hombres de 12 años o más",
    "pea" => "la población económicamente activa",
    "vivtot" => "las viviendas",
    "tvivparhab" => "las viviendas particulares habitadas"
  }
  @nombre_denominador %{
    "p_12ymas" => "Población de 12 años o más",
    "p_12ymas_f" => "Mujeres de 12 años o más",
    "p_12ymas_m" => "Hombres de 12 años o más",
    "tvivparhab" => "Viviendas particulares habitadas"
  }

  @combinados ~w(ab dif cambio)

  def indicadores, do: MapoCore.indicadores_censo()
  def promedio?(a), do: Map.has_key?(@promedios, a)

  @doc "Las lecturas posibles de un indicador, como opciones de un select."
  def lecturas(a, combinados? \\ true) do
    if promedio?(a) do
      [{"Tal cual (#{@promedios[a]})", "valor"}]
    else
      [{"Conteo, en círculos", "conteo"}] ++
        if(@denominador[a], do: [{"% de #{@de_quien[@denominador[a]]}", "pct"}], else: []) ++
        if(a != "pobtot", do: [{"Por cada 1,000 habitantes", "mil"}], else: []) ++
        [{"Por km²", "km2"}] ++
        if(combinados?,
          do: [
            {"Entre otro indicador (A ÷ B)", "ab"},
            {"Menos otro indicador (A − B)", "dif"},
            {"Contra otro indicador, en % ((A − B) ÷ B × 100)", "cambio"}
          ],
          else: []
        )
    end
  end

  @doc "Los conteos, para el B de un combinado (todos menos A)."
  def conteos_menos(a) do
    for {c, e} <- indicadores(), not promedio?(c), c != a, do: {e, c}
  end

  @doc """
  La lectura de los parámetros del formulario (o del enlace), cada uno por su
  catálogo: lo que no está vuelve a su valor por omisión. `a2` vacío es sin
  segundo indicador.
  """
  def normalizar(params) do
    claves = Enum.map(indicadores(), &elem(&1, 0))
    a = if params["indicador"] in claves, do: params["indicador"], else: "pobtot"
    como = en_lecturas(params["como"], a, true)

    b =
      if como in @combinados do
        opciones_b = Enum.map(conteos_menos(a), &elem(&1, 1))
        if params["b"] in opciones_b, do: params["b"], else: hd(opciones_b)
      end

    a2 = if params["indicador2"] in claves, do: params["indicador2"]
    como2 = a2 && en_lecturas(params["como2"], a2, false)
    modo2 = if params["modo2"] == "altura", do: "altura", else: "bivariado"

    %{
      "indicador" => a,
      "como" => como,
      "b" => b,
      "indicador2" => a2,
      "como2" => como2,
      "modo2" => modo2
    }
  end

  defp en_lecturas(como, a, combinados?) do
    opciones = Enum.map(lecturas(a, combinados?), &elem(&1, 1))
    if como in opciones, do: como, else: hd(opciones)
  end

  @doc "Para el formulario: sin `nil`."
  def params(l), do: Map.new(l, fn {k, v} -> {k, v || ""} end)

  @doc "Si la lectura da un conteo (va en círculos) o una tasa (va en color)."
  def tipo("conteo"), do: :conteo
  def tipo("dif"), do: :conteo
  def tipo(_), do: :tasa

  @doc """
  El canal de cada indicador: `{modo, aviso}`. Modos: `color`, `circulos`,
  `color_circulos`, `bivariado`, `altura`. Con dos conteos el segundo se deja
  y el aviso dice por qué.
  """
  def modo(%{"indicador2" => nil} = l),
    do: {if(tipo(l["como"]) == :conteo, do: "circulos", else: "color"), nil}

  def modo(l) do
    case {tipo(l["como"]), tipo(l["como2"])} do
      {:tasa, :tasa} ->
        {l["modo2"], nil}

      {:conteo, :conteo} ->
        {"circulos",
         "Dos conteos no se leen juntos: pasa uno a tasa (%, por 1,000 habitantes o por km²)."}

      _ ->
        {"color_circulos", nil}
    end
  end

  @doc """
  Las columnas que hay que pedirle a mapo_core además de A, para calcular las
  dos lecturas.
  """
  def extras(l) do
    [
      necesita(l["indicador"], l["como"], l["b"]),
      l["indicador2"],
      l["indicador2"] && necesita(l["indicador2"], l["como2"], nil)
    ]
    |> List.flatten()
    |> Enum.reject(&(is_nil(&1) or &1 == l["indicador"]))
    |> Enum.uniq()
  end

  defp necesita(a, "pct", _), do: [@denominador[a]]
  defp necesita(_a, "mil", _), do: ["pobtot"]
  defp necesita(_a, como, b) when como in @combinados, do: [b]
  defp necesita(_a, _como, _b), do: []

  @doc """
  El valor de una lectura en una AGEB, o `nil` si falta un dato o el
  denominador es cero (nunca un cero inventado).
  """
  def valor(props, a, como, b \\ nil) do
    v = dato(props, a)

    case como do
      c when c in ["conteo", "valor"] ->
        v

      "pct" ->
        entre(v, dato(props, @denominador[a]), 100)

      "mil" ->
        entre(v, dato(props, "pobtot"), 1000)

      "km2" ->
        entre(v, props["area_km2"], 1)

      "ab" ->
        entre(v, dato(props, b), 1)

      "dif" ->
        if is_number(v) and is_number(dato(props, b)), do: v - dato(props, b)

      "cambio" ->
        with w when is_number(w) and is_number(v) <- dato(props, b), do: entre(v - w, w, 100)
    end
  end

  defp dato(props, col) do
    if props["indicador"] == col,
      do: props["valor_choropleth"],
      else: get_in(props, ["valores", col])
  end

  defp entre(v, d, por) when is_number(v) and is_number(d) and d != 0, do: v / d * por
  defp entre(_v, _d, _por), do: nil

  @doc """
  Nombre, fórmula y unidad de una lectura, para la cinta, la leyenda y la ficha.

      iex> MapoWeb.LecturaCenso.describir("vph_inter", "pct", nil)
      %{nombre: "Viviendas con internet", formula: "Viviendas con internet ÷ Viviendas particulares habitadas × 100", unidad: "% de las viviendas particulares habitadas"}
  """
  def describir(a, como, b) do
    ea = etiqueta(a)
    eb = b && etiqueta(b)
    ua = @unidad[a] || @promedios[a]

    {formula, unidad} =
      case como do
        "conteo" ->
          {ea, ua}

        "valor" ->
          {ea, ua}

        "pct" ->
          {"#{ea} ÷ #{etiqueta(@denominador[a])} × 100", "% de #{@de_quien[@denominador[a]]}"}

        "mil" ->
          {"#{ea} ÷ Población total × 1,000", "#{ua} por cada 1,000 habitantes"}

        "km2" ->
          {"#{ea} ÷ área de la AGEB en km²", "#{ua} por km²"}

        "ab" ->
          {"#{ea} ÷ #{eb}", "#{ua} por #{@singular[@unidad[b]] || "unidad"}"}

        "dif" ->
          {"#{ea} − #{eb}", if(@unidad[a] == @unidad[b], do: ua, else: "diferencia")}

        "cambio" ->
          {"(#{ea} − #{eb}) ÷ #{eb} × 100", "% más que #{String.downcase(eb)}"}
      end

    # Un combinado se nombra por su fórmula: "Población femenina: 120" en la
    # ficha diría otra cosa que A − B.
    nombre = if como in @combinados, do: formula, else: ea
    %{nombre: nombre, formula: formula, unidad: unidad}
  end

  def etiqueta(col) do
    Enum.find_value(indicadores(), fn {c, e} -> if c == col, do: e end) ||
      @nombre_denominador[col] || col
  end
end
