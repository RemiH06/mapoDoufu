defmodule MapoWeb.EscalaTest do
  use ExUnit.Case, async: true

  alias MapoWeb.Escala

  doctest MapoWeb.Escala

  defp opciones(o), do: Map.merge(Escala.por_omision(), o)

  test "los cortes naturales separan grupos claros y dejan cada valor en el suyo" do
    valores = [1, 2, 2, 3, 50, 52, 55, 200, 210, 220]
    cortes = Escala.naturales(valores, 3)
    assert cortes == [3, 55]
    assert Enum.map(valores, &Escala.clase(&1, cortes)) == [0, 0, 0, 0, 1, 1, 1, 2, 2, 2]
  end

  test "los cortes naturales igualan a la búsqueda exhaustiva en datos al azar" do
    :rand.seed(:exsss, {1, 2, 3})

    for _ <- 1..20 do
      valores = Enum.sort(for _ <- 1..14, do: :rand.uniform(100))
      k = Enum.random(2..4)
      assert costo(valores, Escala.naturales(valores, k)) <= mejor_costo(valores, k) + 1.0e-6
    end
  end

  # Suma de cuadrados dentro de cada grupo.
  defp costo(valores, cortes) do
    valores
    |> Enum.group_by(&Escala.clase(&1, cortes))
    |> Map.values()
    |> Enum.map(fn g ->
      m = Enum.sum(g) / length(g)
      Enum.sum(Enum.map(g, &((&1 - m) * (&1 - m))))
    end)
    |> Enum.sum()
  end

  defp mejor_costo(valores, k) do
    unicos = Enum.uniq(valores)

    combinaciones(Enum.drop(unicos, -1), min(k, length(unicos)) - 1)
    |> Enum.map(&costo(valores, &1))
    |> Enum.min()
  end

  defp combinaciones(_lista, 0), do: [[]]
  defp combinaciones([], _k), do: []

  defp combinaciones([x | resto], k),
    do: Enum.map(combinaciones(resto, k - 1), &[x | &1]) ++ combinaciones(resto, k)

  test "con muchos valores iguales salen menos clases y se dice" do
    e = Escala.construir([0, 0, 0, 0, 0, 0, 0, 0, 1, 9], opciones(%{clases: 5}))
    assert e.clases < 5
    assert e.aviso =~ "Salen"
  end

  test "manual sin cortes cae a cuantiles y lo dice; con cortes, usa esos" do
    e = Escala.construir([1, 2, 3, 4, 5, 6], opciones(%{metodo: "manual"}))
    assert e.aviso =~ "cuantiles"

    e = Escala.construir([1, 2, 3, 4, 5, 6], opciones(%{metodo: "manual", cortes: [2.5]}))
    assert e.cortes == [2.5]
    assert e.clases == 2
  end

  test "una paleta secuencial se voltea en tema oscuro y al invertir" do
    e = Escala.construir([1, 2, 3, 4, 5, 6, 7, 8], opciones(%{paleta: "viridis", clases: 4}))
    assert length(e.colores.claro) == 4
    assert e.colores.oscuro == Enum.reverse(e.colores.claro)
    assert e.opacidades == nil

    inv =
      Escala.construir(
        [1, 2, 3, 4, 5, 6, 7, 8],
        opciones(%{paleta: "viridis", clases: 4, invertir: true})
      )

    assert inv.colores.claro == Enum.reverse(e.colores.claro)
  end

  test "una divergente no se voltea con el tema" do
    e = Escala.construir([1, 2, 3, 4, 5], opciones(%{paleta: "rdbu", clases: 3}))
    assert e.colores.oscuro == e.colores.claro
  end

  test "una sola clase no divide entre cero" do
    assert %{clases: 1, opacidades: [_]} = Escala.construir([4, 4, 4], Escala.por_omision())
    assert %{clases: 1} = Escala.construir([4, 4], opciones(%{paleta: "cividis"}))
  end

  test "lo que no está en el catálogo vuelve a su valor de omisión" do
    assert Escala.opciones(%{"paleta" => "<script>", "metodo" => "x", "clases" => "2"}) ==
             Escala.por_omision()

    assert Escala.de_url("viridis:naturales:7") ==
             opciones(%{paleta: "viridis", metodo: "naturales", clases: 7})

    assert Escala.de_url("basura") == Escala.por_omision()
    assert Escala.a_url(Escala.por_omision()) == nil
  end

  test "los círculos de la leyenda van con el área, no con el radio" do
    c = Escala.circulos([100, 25, nil, 4])
    assert c.nulos == 1
    [grande, mediano | _] = c.referencias
    assert grande.valor == 100
    assert_in_delta mediano.radio / grande.radio, :math.sqrt(mediano.valor / grande.valor), 0.01
  end

  test "el 3x3 usa terciles aunque se haya pedido manual" do
    b = Escala.bivariado([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, nil], opciones(%{metodo: "manual"}))
    assert b.metodo == "cuantiles"
    assert length(b.a.cortes) == 2
    assert b.nulos == 1
    assert length(b.colores) == 9
  end
end
