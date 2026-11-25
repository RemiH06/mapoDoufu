defmodule MapoWeb.CotejoTest do
  use ExUnit.Case, async: true

  doctest MapoWeb.Cotejo

  alias MapoWeb.Cotejo
  alias MapoWeb.Iconos

  test "cada peligro y cada servicio tiene su ícono" do
    claves =
      for({c, _, _} <- Cotejo.peligros(), do: c) ++
        Cotejo.contexto() ++ for({c, _, _} <- Cotejo.servicios("pie"), do: c)

    for c <- claves, do: assert([_ | _] = Iconos.trazos()[c], c)
  end

  test "cada peligro y cada bloque de contexto se puede citar" do
    for({c, _, _} <- Cotejo.peligros(), do: c)
    |> Enum.concat(Cotejo.contexto())
    |> Enum.each(&assert Cotejo.fuente_peligro(&1))
  end

  test "sin medición, sin gente y sin dato no son cero" do
    for m <- [
          %{"sin_medicion" => true, "pct" => 0.0, "total" => 10},
          %{"pct" => nil, "total" => 0, "detalle" => "3 focos", "corto" => "3"},
          %{"pct" => nil, "total" => nil, "detalle" => "0 focos", "corto" => "0"},
          nil
        ] do
      celda = Cotejo.celda_peligro("gente", m, 1000)
      assert celda.clase == nil and celda.estado == "rayada"
      refute celda.cifra =~ "%"
    end
  end

  test "un servicio calculado para menos de la mitad del grupo no da cifra" do
    curva = %{"total" => 337, "sin_ruta" => 0, "dentro" => List.duplicate(337, 121)}
    parcial = Cotejo.celda_servicio(Map.put(curva, "sin_calcular", 3572), 30, "niñas y niños")
    assert parcial.cifra == "parcial"
    assert parcial.titulo =~ "337 de 3,909"
    assert Cotejo.celda_servicio(Map.put(curva, "sin_calcular", 100), 30, "x").cifra == "0 %"
  end
end
