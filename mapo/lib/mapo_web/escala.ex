defmodule MapoWeb.Escala do
  @moduledoc """
  Cómo se pinta un indicador en clases (docs/producto/escalas.md): paleta,
  método de clasificación, número de clases e invertir. Los mismos cortes
  pintan el plano (el hook) y la leyenda de la cinta.

  Una clase va de su corte de abajo (sin incluirlo) a su corte de arriba
  (incluido): un valor cae en la clase `k` si es mayor que `k` cortes. Lo que
  no trae dato se cuenta aparte, nunca como cero.

  Las paletas son publicadas y aptas para daltonismo (viridis y cividis;
  ColorBrewer las marca así). En tema claro, más es más oscuro; en oscuro, al
  revés (más es más claro), para que más siempre sea más contraste contra la
  mesa. Las divergentes no se voltean con el tema: su centro es claro en los dos.
  """

  import MapoWeb.Cifras, only: [cifra: 1, cifra: 2]

  # De menos a más en tema claro.
  @paletas [
    {"tinta", "La tinta de la capa", :tinta, []},
    {"viridis", "Viridis", :secuencial,
     ~w(#fde725 #b5de2b #6ece58 #35b779 #1f9e89 #26828e #31688e #3e4989 #482878 #440154)},
    {"cividis", "Cividis", :secuencial,
     ~w(#fee838 #e1cc55 #c3b369 #a59c74 #8a8678 #707173 #575d6d #3b496c #123570 #00224e)},
    {"ylgnbu", "Amarillo, verde, azul", :secuencial,
     ~w(#ffffd9 #edf8b1 #c7e9b4 #7fcdbb #41b6c4 #1d91c0 #225ea8 #253494 #081d58)},
    {"orrd", "Naranja, rojo", :secuencial,
     ~w(#fff7ec #fee8c8 #fdd49e #fdbb84 #fc8d59 #ef6548 #d7301f #b30000 #7f0000)},
    {"puor", "Divergente: naranja, morado", :divergente,
     ~w(#7f3b08 #b35806 #e08214 #fdb863 #fee0b6 #f7f7f7 #d8daeb #b2abd2 #8073ac #542788 #2d004b)},
    {"brbg", "Divergente: café, verde azulado", :divergente,
     ~w(#543005 #8c510a #bf812d #dfc27d #f6e8c3 #f5f5f5 #c7eae5 #80cdc1 #35978f #01665e #003c30)},
    {"rdbu", "Divergente: rojo, azul", :divergente,
     ~w(#67001f #b2182b #d6604d #f4a582 #fddbc7 #f7f7f7 #d1e5f0 #92c5de #4393c3 #2166ac #053061)}
  ]
  @claves_paleta Enum.map(@paletas, &elem(&1, 0))

  # Cuantiles: mismas zonas en cada clase. Cortes naturales: grupos parecidos
  # por dentro. Iguales: el mismo ancho de valores. Manual: los cortes escritos.
  @metodos [
    {"cuantiles", "Cuantiles"},
    {"naturales", "Cortes naturales"},
    {"iguales", "Intervalos iguales"},
    {"manual", "Manual"}
  ]
  @claves_metodo Enum.map(@metodos, &elem(&1, 0))

  @min_clases 3
  @max_clases 7

  # Opacidad de la tinta por clase (la escala de antes de la 29e, con 5).
  @tinta [0.12, 0.26, 0.42, 0.6, 0.8]

  # 3x3 de Joshua Stevens: renglón = clase del segundo indicador (de menos a
  # más), columna = clase del primero.
  @bivariado ~w(#e8e8e8 #ace4e4 #5ac8c8 #dfb0d6 #a5add3 #5698b9 #be64ac #8c62aa #3b4994)

  @por_omision %{paleta: "tinta", metodo: "cuantiles", clases: 5, invertir: false, cortes: []}

  def por_omision, do: @por_omision
  def paletas, do: Enum.map(@paletas, fn {c, e, _, _} -> {e, c} end)
  def metodos, do: Enum.map(@metodos, fn {c, e} -> {e, c} end)
  def clases_posibles, do: Enum.to_list(@min_clases..@max_clases)
  def colores_bivariado, do: @bivariado

  @doc """
  Las opciones de un formulario (o del enlace), cada una por su catálogo
  cerrado: lo que no está vuelve a su valor por omisión.

      iex> MapoWeb.Escala.opciones(%{"paleta" => "viridis", "clases" => "9", "metodo" => "manual", "cortes" => "30, 10, x, 20"})
      %{paleta: "viridis", metodo: "manual", clases: 5, invertir: false, cortes: [10.0, 20.0, 30.0]}
  """
  def opciones(params) when is_map(params) do
    clases =
      case Integer.parse(to_string(params["clases"] || "")) do
        {n, ""} when n in @min_clases..@max_clases -> n
        _ -> @por_omision.clases
      end

    %{
      paleta: en(params["paleta"], @claves_paleta, @por_omision.paleta),
      metodo: en(params["metodo"], @claves_metodo, @por_omision.metodo),
      clases: clases,
      invertir: params["invertir"] in ["true", "1", true],
      cortes: cortes_manuales(params["cortes"])
    }
  end

  def opciones(_), do: @por_omision

  defp en(v, catalogo, otro), do: if(v in catalogo, do: v, else: otro)

  # A lo más `@max_clases - 1` cortes: los números, ordenados y sin repetir.
  defp cortes_manuales(texto) when is_binary(texto) do
    texto
    |> String.split([",", ";", " "], trim: true)
    |> Enum.flat_map(fn t ->
      case Float.parse(t) do
        {v, ""} -> [v]
        _ -> []
      end
    end)
    |> Enum.uniq()
    |> Enum.sort()
    |> Enum.take(@max_clases - 1)
  end

  defp cortes_manuales(_), do: []

  @doc "Las opciones de vuelta a parámetros de formulario."
  def params(o) do
    %{
      "paleta" => o.paleta,
      "metodo" => o.metodo,
      "clases" => to_string(o.clases),
      "invertir" => to_string(o.invertir),
      "cortes" => Enum.map_join(o.cortes, ", ", &numero/1)
    }
  end

  @doc """
  En el enlace, una sola clave: `paleta:metodo:clases`, más `:inv`; con
  manual, los cortes en lugar de las clases (`viridis:manual:10,20,30`). `nil`
  si es la de omisión.

      iex> MapoWeb.Escala.a_url(%{paleta: "rdbu", metodo: "manual", clases: 5, invertir: true, cortes: [-5.0, 0.0, 12.5]})
      "rdbu:manual:-5,0,12.5:inv"
      iex> MapoWeb.Escala.de_url("rdbu:manual:-5,0,12.5:inv") |> MapoWeb.Escala.a_url()
      "rdbu:manual:-5,0,12.5:inv"
  """
  def a_url(o) do
    if o == @por_omision do
      nil
    else
      medio = if o.metodo == "manual", do: Enum.map_join(o.cortes, ",", &numero/1), else: o.clases
      Enum.join([o.paleta, o.metodo, medio] ++ if(o.invertir, do: ["inv"], else: []), ":")
    end
  end

  def de_url(texto) when is_binary(texto) do
    case String.split(texto, ":") do
      [paleta, "manual", cortes | resto] ->
        opciones(%{
          "paleta" => paleta,
          "metodo" => "manual",
          "cortes" => cortes,
          "invertir" => resto == ["inv"]
        })

      [paleta, metodo, clases | resto] ->
        opciones(%{
          "paleta" => paleta,
          "metodo" => metodo,
          "clases" => clases,
          "invertir" => resto == ["inv"]
        })

      _ ->
        @por_omision
    end
  end

  def de_url(_), do: @por_omision

  defp numero(v) when v == trunc(v), do: Integer.to_string(trunc(v))
  defp numero(v), do: :erlang.float_to_binary(v / 1, [:short])

  @doc """
  La escala de los valores de una coropleta (`valor_choropleth` de cada
  feature), con las opciones de omisión si no se dan. `nil` si ninguno trae
  dato.
  """
  def de_geojson(%{"features" => features}, o \\ @por_omision) do
    features
    |> Enum.map(&(&1["properties"]["valor_choropleth"] || &1["properties"][:valor_choropleth]))
    |> construir(o)
  end

  @doc """
  Cortes, límites y colores de una lista de valores (con `nil` donde no hay
  dato). `nil` si ninguno trae dato.

  Si el método no alcanza el número de clases pedido (muchos valores iguales,
  o pocos), sale con las que hay y `aviso` lo dice.
  """
  def construir(valores, o) do
    con_dato = valores |> Enum.reject(&is_nil/1) |> Enum.sort()

    case con_dato do
      [] ->
        nil

      _ ->
        {cortes, aviso} = cortes(con_dato, o)
        n = length(cortes) + 1
        {tipo, colores} = colores(o.paleta, n, o.invertir)

        %{
          cortes: cortes,
          limites: [hd(con_dato) | cortes] ++ [List.last(con_dato)],
          nulos: length(valores) - length(con_dato),
          clases: n,
          paleta: o.paleta,
          tipo: tipo,
          colores: colores,
          opacidades: if(tipo == :tinta, do: opacidades(n, o.invertir)),
          metodo: o.metodo,
          aviso: aviso
        }
    end
  end

  # Lo que viaja al hook: los cortes y, por tema, el color de cada clase.
  def para_plano(nil), do: nil

  def para_plano(e) do
    %{
      cortes: e.cortes,
      claro: e.colores && e.colores.claro,
      oscuro: e.colores && e.colores.oscuro,
      opacidades: e.opacidades
    }
  end

  defp cortes(valores, %{metodo: "manual", cortes: []} = o) do
    {cortes, _} = cortes(valores, %{o | metodo: "cuantiles"})
    {cortes, "Sin cortes escritos: van por cuantiles."}
  end

  defp cortes(_valores, %{metodo: "manual", cortes: cortes}), do: {cortes, nil}

  defp cortes(valores, %{metodo: metodo, clases: n}) do
    cortes =
      case metodo do
        "cuantiles" -> cuantiles(valores, n)
        "iguales" -> iguales(valores, n)
        "naturales" -> naturales(valores, n)
      end

    salen = length(cortes) + 1

    aviso =
      if salen < n,
        do:
          "Salen #{salen} #{if salen == 1, do: "clase", else: "clases"} de #{n}: hay muchos valores iguales."

    {cortes, aviso}
  end

  @doc """
  Cortes por cuantiles de una lista ordenada. Con valores repetidos, dos
  cortes iguales se vuelven uno.

      iex> MapoWeb.Escala.cuantiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
      [2, 4, 6, 8]
  """
  def cuantiles(valores, n) do
    m = length(valores)
    t = List.to_tuple(valores)
    tope = List.last(valores)

    1..(n - 1)
    |> Enum.map(&elem(t, floor(&1 / n * (m - 1))))
    |> Enum.dedup()
    |> Enum.reject(&(&1 >= tope))
  end

  @doc """
      iex> MapoWeb.Escala.iguales([0, 3, 10], 5)
      [2.0, 4.0, 6.0, 8.0]
  """
  def iguales(valores, n) do
    {min, max} = {hd(valores), List.last(valores)}
    if max == min, do: [], else: Enum.map(1..(n - 1), &(min + &1 * (max - min) / n))
  end

  @doc """
  Cortes naturales: los `k` grupos con la menor suma de cuadrados dentro de
  cada uno (el óptimo exacto de Jenks en una dimensión, como `ckmeans` de Wang
  y Song, 2011). Programación dinámica con divide y vencerás: cada renglón es
  O(n log n). El corte es el valor más alto de cada grupo menos el último.

      iex> MapoWeb.Escala.naturales([1, 1, 2, 2, 10, 11, 12, 30, 31], 3)
      [2, 12]
  """
  def naturales(valores, k) do
    x = List.to_tuple(valores)
    n = tuple_size(x)
    k = min(k, valores |> Enum.uniq() |> length())

    if k < 2 do
      []
    else
      {s1, s2} = sumas(valores)
      ssq = fn j, i -> suma_cuadrados(s1, s2, j, i) end
      primero = List.to_tuple(for i <- 0..(n - 1), do: ssq.(0, i))

      {_, atras} =
        Enum.reduce(1..(k - 1), {primero, []}, fn q, {previo, atras} ->
          mejores = fila(q, q, n - 1, q, n - 1, previo, ssq, %{})
          costos = List.to_tuple(for i <- 0..(n - 1), do: elem(Map.get(mejores, i, {0.0, 0}), 0))
          inicios = List.to_tuple(for i <- 0..(n - 1), do: elem(Map.get(mejores, i, {0.0, 0}), 1))
          {costos, [inicios | atras]}
        end)

      # De atrás para adelante: cada renglón dice dónde empieza el último grupo.
      {cortes, _} =
        Enum.reduce(atras, {[], n - 1}, fn inicios, {cortes, derecha} ->
          inicio = elem(inicios, derecha)
          {[elem(x, inicio - 1) | cortes], inicio - 1}
        end)

      Enum.dedup(cortes)
    end
  end

  defp sumas(valores) do
    {a, b, _, _} =
      Enum.reduce(valores, {[0.0], [0.0], 0.0, 0.0}, fn v, {a, b, s, c} ->
        {[s + v | a], [c + v * v | b], s + v, c + v * v}
      end)

    {a |> Enum.reverse() |> List.to_tuple(), b |> Enum.reverse() |> List.to_tuple()}
  end

  # Suma de cuadrados respecto a la media de x[j..i].
  defp suma_cuadrados(s1, s2, j, i) do
    suma = elem(s1, i + 1) - elem(s1, j)
    cuadrados = elem(s2, i + 1) - elem(s2, j)
    max(cuadrados - suma * suma / (i - j + 1), 0.0)
  end

  # El mejor inicio del último grupo para cada i en [imin, imax], sabiendo que
  # no baja cuando i sube: se busca solo en [jmin, jmax].
  defp fila(_q, imin, imax, _jmin, _jmax, _previo, _ssq, acc) when imin > imax, do: acc

  defp fila(q, imin, imax, jmin, jmax, previo, ssq, acc) do
    i = div(imin + imax, 2)

    {costo, mejor} =
      Enum.reduce(max(q, jmin)..min(i, jmax)//1, {nil, max(q, jmin)}, fn j, {c, m} ->
        nuevo = elem(previo, j - 1) + ssq.(j, i)
        if is_nil(c) or nuevo < c, do: {nuevo, j}, else: {c, m}
      end)

    acc = Map.put(acc, i, {costo, mejor})
    acc = fila(q, imin, i - 1, jmin, mejor, previo, ssq, acc)
    fila(q, i + 1, imax, mejor, jmax, previo, ssq, acc)
  end

  @doc "La clase de un valor: cuántos cortes deja abajo. `-1` sin dato."
  def clase(nil, _cortes), do: -1
  def clase(v, cortes), do: Enum.count(cortes, &(v > &1))

  ## Colores

  defp colores(clave, n, invertir) do
    {_, _, tipo, anclas} = List.keyfind(@paletas, clave, 0)

    case tipo do
      :tinta ->
        {:tinta, nil}

      :secuencial ->
        claro = muestrear(anclas, n, 0.08, 0.92)
        {tipo, voltear(%{claro: claro, oscuro: Enum.reverse(claro)}, invertir)}

      :divergente ->
        claro = muestrear(anclas, n, 0.06, 0.94)
        {tipo, voltear(%{claro: claro, oscuro: claro}, invertir)}
    end
  end

  defp voltear(c, false), do: c
  defp voltear(c, true), do: %{claro: Enum.reverse(c.claro), oscuro: Enum.reverse(c.oscuro)}

  defp opacidades(n, invertir) do
    o = for i <- 0..(n - 1), do: Float.round(interpolar(@tinta, posicion(i, n)), 3)
    if invertir, do: Enum.reverse(o), else: o
  end

  # `n` colores parejos entre `desde` y `hasta` (0 a 1) del tramo de anclas.
  defp muestrear(anclas, n, desde, hasta) do
    rgb = Enum.map(anclas, &a_rgb/1)

    for i <- 0..(n - 1) do
      t = desde + (hasta - desde) * posicion(i, n)
      [0, 1, 2] |> Enum.map(fn c -> interpolar(Enum.map(rgb, &elem(&1, c)), t) end) |> a_hex()
    end
  end

  # Dónde cae la clase i de n entre 0 y 1; una sola clase, a la mitad.
  defp posicion(_i, 1), do: 0.5
  defp posicion(i, n), do: i / (n - 1)

  defp interpolar(lista, t) do
    tramos = length(lista) - 1
    pos = t * tramos
    i = min(floor(pos), tramos - 1)
    a = Enum.at(lista, i)
    a + (Enum.at(lista, i + 1) - a) * (pos - i)
  end

  defp a_rgb("#" <> hex) do
    <<r::binary-size(2), g::binary-size(2), b::binary-size(2)>> = hex
    {String.to_integer(r, 16), String.to_integer(g, 16), String.to_integer(b, 16)}
  end

  defp a_hex(canales) do
    "#" <>
      Enum.map_join(canales, fn c ->
        c |> round() |> Integer.to_string(16) |> String.pad_leading(2, "0") |> String.downcase()
      end)
  end

  ## Círculos y 3x3

  @radio_max 22

  @doc """
  Círculos proporcionales: el área va con el valor (el radio con su raíz). La
  leyenda trae tres círculos de referencia con cifras redondas, del tamaño que
  tienen de cerca (zoom 12 o más); de lejos el hook los encoge todos igual,
  para que la metrópoli no sea una mancha.
  """
  def circulos(valores) do
    absolutos = valores |> Enum.reject(&is_nil/1) |> Enum.map(&abs/1)

    case absolutos do
      [] ->
        nil

      _ ->
        max = Enum.max(absolutos)

        referencias =
          if max > 0,
            do:
              [redondo(max), redondo(max / 4), redondo(max / 25)]
              |> Enum.uniq()
              |> Enum.filter(&(&1 > 0)),
            else: []

        %{
          max: max,
          radio: @radio_max,
          negativos: Enum.any?(valores, &(is_number(&1) and &1 < 0)),
          nulos: Enum.count(valores, &is_nil/1),
          referencias:
            Enum.map(
              referencias,
              &%{valor: &1, radio: Float.round(@radio_max * :math.sqrt(&1 / max), 1)}
            )
        }
    end
  end

  # Una cifra de dos dígitos significativos, para leer en la leyenda.
  defp redondo(v) when v <= 0, do: 0

  defp redondo(v) do
    paso = :math.pow(10, floor(:math.log10(v)) - 1)
    r = Float.round(v / paso) * paso
    if r == trunc(r), do: trunc(r), else: r
  end

  @doc "Terciles (o el método elegido, en 3) de cada indicador del 3x3."
  def bivariado(valores_a, valores_b, o) do
    o3 = %{o | clases: 3, metodo: if(o.metodo == "manual", do: "cuantiles", else: o.metodo)}

    with %{} = a <- construir(valores_a, o3), %{} = b <- construir(valores_b, o3) do
      nulos =
        Enum.zip(valores_a, valores_b) |> Enum.count(fn {x, y} -> is_nil(x) or is_nil(y) end)

      %{a: a, b: b, colores: @bivariado, nulos: nulos, metodo: o3.metodo}
    else
      _ -> nil
    end
  end

  @doc """
  Una cifra de la leyenda: sin decimales si es grande, con dos si es chica, y
  de 100 mil para arriba en millones (cada cifra tiene unos 46 px).

      iex> MapoWeb.Escala.cifra_leyenda(1_710_000)
      "1.7 M"
      iex> MapoWeb.Escala.cifra_leyenda(25.84)
      "25.8"
  """
  def cifra_leyenda(v) when is_number(v) and abs(v) >= 100_000,
    do: "#{cifra(v / 1_000_000, 1)} M"

  def cifra_leyenda(v) when is_integer(v), do: cifra(v)
  def cifra_leyenda(v) when is_float(v) and v == trunc(v), do: cifra(trunc(v))
  def cifra_leyenda(v) when is_float(v) and abs(v) >= 100, do: cifra(round(v))
  def cifra_leyenda(v) when is_float(v) and abs(v) >= 10, do: cifra(v, 1)
  def cifra_leyenda(v) when is_float(v), do: cifra(v, 2)
  def cifra_leyenda(v), do: to_string(v)
end
