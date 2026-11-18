defmodule Mapo.Capas.DistanciasTest do
  use Mapo.DataCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  alias Mapo.Capas
  alias Mapo.Capas.Distancias

  # A 20° de latitud, un grado de longitud mide 104,647 m sobre el elipsoide y
  # uno de latitud, 110,704 m.
  @lat 20.0
  @lon -104.0

  defp capa(scope, team, nombre, tipo, columnas, filas) do
    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: nombre,
          archivo: "#{nombre}.gpkg",
          tamano_bytes: 1_000,
          tipo: tipo,
          columnas: columnas,
          numericas: [],
          num_filas: length(filas),
          num_descartadas: 0
        },
        filas
      )

    capa
  end

  defp punto(lat, lon, datos), do: %{"lat" => lat, "lon" => lon, "datos" => datos}

  # Un cuadro de `lado` grados con su esquina suroeste en (lat, lon).
  defp cuadro(lat, lon, lado, datos) do
    anillo = [
      [lon, lat],
      [lon + lado, lat],
      [lon + lado, lat + lado],
      [lon, lat + lado],
      [lon, lat]
    ]

    %{"geometria" => %{"type" => "Polygon", "coordinates" => [anillo]}, "datos" => datos}
  end

  setup do
    scope = user_scope_fixture()
    team = team_fixture(scope)

    escuelas =
      capa(scope, team, "Escuelas", "puntos", ["nombre", "clase"], [
        punto(@lat, @lon, %{"nombre" => "Primaria", "clase" => "Escuelas de educación primaria"}),
        punto(@lat + 1, @lon, %{"nombre" => "Taller", "clase" => "Reparación de autos"})
      ])

    %{scope: scope, team: team, escuelas: escuelas}
  end

  test "gana el más cercano en metros, no en grados", ctx do
    # El del norte está a 0.0095° (1,052 m) y el del este a 0.01° (1,046 m).
    parcelas =
      capa(ctx.scope, ctx.team, "Parcelas", "vector", ["uso"], [
        cuadro(@lat + 0.0095, @lon - 0.0005, 0.001, %{"uso" => "norte"}),
        cuadro(@lat - 0.0005, @lon + 0.01, 0.001, %{"uso" => "este"})
      ])

    {:ok, r} =
      Distancias.calcular(ctx.escuelas, %{
        destino: parcelas,
        filtro_origen: {"clase", "educacion"},
        etiqueta_origen: "nombre",
        etiqueta_destino: "uso"
      })

    assert r.total == 1
    assert [%{nombre: "Primaria", cercano: "este", metros: metros}] = r.filas
    assert_in_delta metros, 1_046, 2
  end

  test "el filtro del destino ignora mayúsculas y acentos, y el radio cuenta", ctx do
    parcelas =
      capa(ctx.scope, ctx.team, "Uso de suelo", "vector", ["uso"], [
        cuadro(@lat - 0.0005, @lon + 0.001, 0.001, %{"uso" => "BOSQUE DE ENCINO"}),
        cuadro(@lat - 0.0005, @lon + 0.002, 0.001, %{"uso" => "AGRICULTURA DE TEMPORAL"}),
        cuadro(@lat - 0.0005, @lon + 0.02, 0.001, %{"uso" => "Agricultura de riego"})
      ])

    opciones = %{
      destino: parcelas,
      filtro_destino: {"uso", "agricultura"},
      etiqueta_destino: "uso",
      radio: 300
    }

    {:ok, r} = Distancias.calcular(ctx.escuelas, opciones)

    assert r.destino_filas == 2
    assert [%{cercano: "AGRICULTURA DE TEMPORAL", metros: m, cuantos: 1}, _] = r.filas
    assert_in_delta m, 209, 2
    assert r.a_menos == 1

    assert %{distancia: "distancia_m_uso_de_suelo", cuantos: "uso_de_suelo_a_300m"} =
             r.columnas

    {:ok, guardada} =
      Distancias.guardar(ctx.scope, ctx.escuelas, opciones, "Escuelas y parcelas", r)

    assert guardada.tipo == "puntos"
    assert guardada.num_filas == 2
    assert guardada.tamano_bytes > 0
    assert "distancia_m_uso_de_suelo" in guardada.numericas
    assert guardada.metodo =~ "solo donde uso contiene «agricultura»"

    [cerca, lejos] = Capas.puntos(guardada) |> Enum.sort_by(& &1.lat)
    assert {datos, 1} = Capas.ficha(ctx.scope, guardada.id, {:id, cerca.id})
    assert datos["nombre"] == "Primaria"
    assert_in_delta datos["distancia_m_uso_de_suelo"], 209, 2
    assert datos["uso_de_suelo_uso"] == "AGRICULTURA DE TEMPORAL"
    assert datos["uso_de_suelo_a_300m"] == 1

    assert {%{"uso_de_suelo_a_300m" => 0}, 1} =
             Capas.ficha(ctx.scope, guardada.id, {:id, lejos.id})
  end

  test "un punto dentro del polígono está a 0 m", ctx do
    parcelas =
      capa(ctx.scope, ctx.team, "Parcelas", "vector", ["uso"], [
        cuadro(@lat - 0.01, @lon - 0.01, 0.02, %{"uso" => "AGRICULTURA"})
      ])

    {:ok, r} =
      Distancias.calcular(ctx.escuelas, %{destino: parcelas, filtro_origen: {"clase", "Escuelas"}})

    assert [%{metros: 0}] = r.filas
  end

  test "la procedencia del destino viaja sola", ctx do
    pozos =
      capa(ctx.scope, ctx.team, "Pozos", "puntos", ["titulo", "fuente", "fecha_dato"], [
        punto(@lat, @lon + 0.001, %{
          "titulo" => "X",
          "fuente" => "REPDA",
          "fecha_dato" => "2025-06-30"
        })
      ])

    {:ok, r} = Distancias.calcular(ctx.escuelas, %{destino: pozos})
    assert r.columnas.lleva == ["pozos_fuente", "pozos_fecha_dato"]
    assert Enum.any?(r.metodo, &(&1 =~ "pozos_fuente: fuente de ese renglón más cercano"))
  end

  test "un nombre de columna que ya existe no se pisa", ctx do
    pozos =
      capa(ctx.scope, ctx.team, "Escuelas", "puntos", ["nombre"], [
        punto(@lat, @lon, %{"nombre" => "A"})
      ])

    origen = %{ctx.escuelas | columnas: ["distancia_m_escuelas" | ctx.escuelas.columnas]}

    assert %{distancia: "distancia_m_escuelas_2"} =
             Distancias.columnas_nuevas(origen, %{destino: pozos})
  end

  test "filtro vacío, otro equipo y radio fuera de rango se dicen", ctx do
    parcelas =
      capa(ctx.scope, ctx.team, "Parcelas", "vector", ["uso"], [
        cuadro(@lat, @lon, 0.001, %{"uso" => "BOSQUE"})
      ])

    assert {:error, "El filtro del destino no deja ningún renglón."} =
             Distancias.calcular(ctx.escuelas, %{
               destino: parcelas,
               filtro_destino: {"uso", "riego"}
             })

    assert {:error, "El radio" <> _} =
             Distancias.calcular(ctx.escuelas, %{destino: parcelas, radio: 0})

    otro_scope = user_scope_fixture()

    ajena =
      capa(otro_scope, team_fixture(otro_scope), "Ajena", "puntos", ["a"], [
        punto(@lat, @lon, %{"a" => "1"})
      ])

    assert {:error, "Las dos capas tienen que ser del mismo equipo."} =
             Distancias.calcular(ctx.escuelas, %{destino: ajena})
  end

  test "un comodín de LIKE en el filtro se busca tal cual", ctx do
    parcelas =
      capa(ctx.scope, ctx.team, "Parcelas", "vector", ["uso"], [
        cuadro(@lat, @lon, 0.001, %{"uso" => "BOSQUE"})
      ])

    assert {:error, _} =
             Distancias.calcular(ctx.escuelas, %{destino: parcelas, filtro_destino: {"uso", "%"}})
  end

  test "dos condiciones a la vez y alternativas con barra", ctx do
    pozos =
      capa(ctx.scope, ctx.team, "Pozos", "puntos", ["mun"], [
        punto(@lat, @lon + 0.001, %{"mun" => "015"})
      ])

    {:ok, r} =
      Distancias.calcular(ctx.escuelas, %{
        destino: pozos,
        filtro_origen: [{"clase", "educación"}, {"nombre", "Taller | Primaria"}],
        filtro_destino: [{"mun", "037|015"}]
      })

    assert r.total == 1

    assert hd(r.metodo) =~
             "solo donde clase contiene «educación» y nombre contiene «Taller» o «Primaria»"

    assert Enum.at(r.metodo, 1) =~ "solo donde mun contiene «037» o «015»"
  end

  test "un rango de fechas en el destino, con fechas parciales que se traslapan", ctx do
    focos =
      capa(ctx.scope, ctx.team, "Focos", "puntos", ["acq_date"], [
        punto(@lat, @lon + 0.001, %{"acq_date" => "2024-10-31"}),
        punto(@lat, @lon + 0.002, %{"acq_date" => "2024-12-05T21:10"}),
        punto(@lat, @lon + 0.003, %{"acq_date" => "2025-03"}),
        punto(@lat, @lon + 0.004, %{"acq_date" => "2025"}),
        punto(@lat, @lon + 0.005, %{"acq_date" => "2025-06-01"}),
        punto(@lat, @lon + 0.0055, %{})
      ])

    zafra = {:fecha, "acq_date", "2024-11-01", "2025-05-31"}

    {:ok, r} =
      Distancias.calcular(ctx.escuelas, %{
        destino: focos,
        filtro_origen: {"clase", "Escuelas"},
        filtro_destino: [zafra],
        radio: 1_000
      })

    # Entran diciembre, marzo y el año 2025 completo; octubre, junio y el vacío no.
    assert r.destino_filas == 3
    assert [%{cuantos: 3, metros: m}] = r.filas
    assert_in_delta m, 209, 2
    assert Enum.at(r.metodo, 1) =~ "acq_date del 2024-11-01 al 2025-05-31"

    {:ok, r} =
      Distancias.calcular(ctx.escuelas, %{
        destino: focos,
        filtro_destino: [{:fecha, "acq_date", nil, "2024-12-31"}]
      })

    assert r.destino_filas == 2
  end
end
