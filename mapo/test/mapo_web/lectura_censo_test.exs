defmodule MapoWeb.LecturaCensoTest do
  use ExUnit.Case, async: true

  alias MapoWeb.LecturaCenso

  doctest MapoWeb.LecturaCenso

  defp props(valor, valores, area \\ 2.0) do
    %{
      "indicador" => "vph_inter",
      "valor_choropleth" => valor,
      "valores" => valores,
      "area_km2" => area
    }
  end

  test "el porcentaje va sobre el denominador natural y sin él no hay dato" do
    assert LecturaCenso.valor(props(50, %{"tvivparhab" => 200}), "vph_inter", "pct") == 25.0
    assert LecturaCenso.valor(props(50, %{"tvivparhab" => nil}), "vph_inter", "pct") == nil
    assert LecturaCenso.valor(props(50, %{"tvivparhab" => 0}), "vph_inter", "pct") == nil
    assert LecturaCenso.valor(props(nil, %{"tvivparhab" => 200}), "vph_inter", "pct") == nil
  end

  test "por km², por 1,000 habitantes y los combinados" do
    p = props(50, %{"pobtot" => 500, "tothog" => 40})
    assert LecturaCenso.valor(p, "vph_inter", "km2") == 25.0
    assert LecturaCenso.valor(p, "vph_inter", "mil") == 100.0
    assert LecturaCenso.valor(p, "vph_inter", "ab", "tothog") == 1.25
    assert LecturaCenso.valor(p, "vph_inter", "dif", "tothog") == 10
    assert LecturaCenso.valor(p, "vph_inter", "cambio", "tothog") == 25.0
  end

  test "las columnas que se piden a mapo_core" do
    l =
      LecturaCenso.normalizar(%{
        "indicador" => "vph_inter",
        "como" => "pct",
        "indicador2" => "pea",
        "como2" => "mil"
      })

    assert LecturaCenso.extras(l) == ["tvivparhab", "pea", "pobtot"]
  end

  test "un conteo se lee en círculos; un promedio no tiene conteo" do
    assert LecturaCenso.normalizar(%{"indicador" => "pobtot"})["como"] == "conteo"

    assert LecturaCenso.normalizar(%{"indicador" => "graproes", "como" => "conteo"})["como"] ==
             "valor"

    refute Enum.any?(LecturaCenso.lecturas("pobtot"), &(elem(&1, 1) == "mil"))
  end

  test "el canal lo decide el tipo de cada lectura" do
    base = %{"indicador" => "vph_inter", "indicador2" => "pobtot"}

    assert {"color_circulos", nil} =
             LecturaCenso.modo(
               LecturaCenso.normalizar(Map.merge(base, %{"como" => "pct", "como2" => "conteo"}))
             )

    assert {"altura", nil} =
             LecturaCenso.modo(
               LecturaCenso.normalizar(
                 Map.merge(base, %{"como" => "pct", "como2" => "km2", "modo2" => "altura"})
               )
             )

    assert {"circulos", aviso} =
             LecturaCenso.modo(
               LecturaCenso.normalizar(
                 Map.merge(base, %{"como" => "conteo", "como2" => "conteo"})
               )
             )

    assert aviso =~ "Dos conteos"
  end

  test "lo que no está en el catálogo vuelve a su valor de omisión" do
    l =
      LecturaCenso.normalizar(%{"indicador" => "drop table", "como" => "x", "indicador2" => "y"})

    assert l["indicador"] == "pobtot"
    assert l["como"] == "conteo"
    assert l["indicador2"] == nil
  end
end
