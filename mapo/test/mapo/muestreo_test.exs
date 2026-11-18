defmodule Mapo.Capas.MuestreoTest do
  use Mapo.DataCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Mapo.RasterFixtures

  alias Mapo.Capas
  alias Mapo.Capas.Muestreo

  # Píxeles de 0.01° desde (-104, 20): a esa latitud, 1,046 m de ancho y 1,107 de alto.
  @paso 0.01

  defp centro(fila, col), do: {-104.0 + @paso * (col + 0.5), 20.0 - @paso * (fila + 0.5)}

  defp puntos(scope, team, lugares) do
    filas =
      for {nombre, {lon, lat}} <- lugares,
          do: %{"lat" => lat, "lon" => lon, "datos" => %{"nombre" => nombre}}

    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "Escuelas",
          archivo: "e.csv",
          tamano_bytes: 1,
          tipo: "puntos",
          columnas: ["nombre"],
          numericas: [],
          num_filas: length(filas),
          num_descartadas: 0
        },
        filas
      )

    capa
  end

  defp vacia(scope, team, nombre, tipo, filas, raster \\ nil) do
    attrs = %{
      nombre: nombre,
      archivo: nombre,
      tamano_bytes: 1,
      tipo: tipo,
      columnas: [],
      numericas: [],
      num_filas: length(filas),
      num_descartadas: 0
    }

    {:ok, capa} = Capas.crear_capa(scope, team.id, attrs, filas, raster)
    capa
  end

  setup do
    scope = user_scope_fixture()
    team = team_fixture(scope)
    # Valor = fila * 10 + columna; la fila 0, columna 0 es sin dato.
    valores =
      for f <- 0..9, do: for(c <- 0..9, do: if(f + c == 0, do: -32768, else: f * 10 + c))

    raster = capa_raster(scope, team.id, "Calor", [tesela(valores, -104.0, 20.0, @paso)])
    %{scope: scope, team: team, raster: raster}
  end

  test "en el punto da el valor del píxel", ctx do
    escuelas =
      puntos(ctx.scope, ctx.team, [
        {"A", centro(2, 3)},
        {"B", centro(0, 0)},
        {"C", {-90.0, 20.0}}
      ])

    {:ok, r} = Muestreo.calcular(escuelas, %{raster: ctx.raster, etiqueta_origen: "nombre"})

    assert r.columnas == ["calor_valor"]
    assert [%{nombre: "A", valores: [23.0]}, %{valores: [nil]}, %{valores: [nil]}] = r.filas
    assert r.sin_dato == 2
  end

  test "en un radio cuentan los píxeles con el centro dentro", ctx do
    escuelas = puntos(ctx.scope, ctx.team, [{"A", centro(2, 3)}])
    opciones = %{raster: ctx.raster, radio: 1_500, valores: "13 | 23"}
    {:ok, r} = Muestreo.calcular(escuelas, opciones)

    assert r.columnas ==
             ["calor_promedio", "calor_min", "calor_max", "calor_pixeles", "calor_parte_13_23"]

    # El centro y sus cuatro vecinos; las diagonales quedan a 1,523 m.
    assert [%{valores: [23.0, 13.0, 33.0, 5, 0.4]}] = r.filas
    assert Enum.any?(r.metodo, &(&1 =~ "Un píxel cuenta si su centro cae en la zona"))

    {:ok, capa} = Muestreo.guardar(ctx.scope, escuelas, opciones, "Calor en escuelas", r)
    [%{id: id}] = Capas.puntos(capa)

    assert {%{"nombre" => "A", "calor_pixeles" => 5, "calor_parte_13_23" => 0.4} = datos, 1} =
             Capas.ficha(ctx.scope, capa.id, {:id, id})

    assert_in_delta datos["calor_promedio"], 23.0, 1.0e-9
    assert "calor_promedio" in capa.numericas
  end

  test "el sin dato no cuenta y una zona sin valores queda vacía", ctx do
    escuelas =
      puntos(ctx.scope, ctx.team, [{"esquina", centro(0, 0)}, {"lejos", {-90.0, 20.0}}])

    {:ok, r} = Muestreo.calcular(escuelas, %{raster: ctx.raster, radio: 400})
    # A 400 m de la esquina solo está su propio píxel, que es sin dato.
    assert [%{valores: [nil, nil, nil, nil]}, %{valores: [nil, nil, nil, nil]}] = r.filas
  end

  test "un polígono toma los píxeles de adentro", ctx do
    # Cubre los centros de las filas 1 y 2, columnas 1 y 2: 11, 12, 21 y 22.
    {o, n} = {-104.0 + @paso, 20.0 - @paso}
    {e, s} = {o + 2 * @paso, n - 2 * @paso}
    cuadro = %{"type" => "Polygon", "coordinates" => [[[o, s], [e, s], [e, n], [o, n], [o, s]]]}

    zona =
      vacia(ctx.scope, ctx.team, "Parcela", "vector", [%{"geometria" => cuadro, "datos" => %{}}])

    {:ok, r} = Muestreo.calcular(zona, %{raster: ctx.raster})
    assert [%{valores: [16.5, 11.0, 22.0, 4]}] = r.filas
  end

  test "un ráster sin valores, de otro equipo o valores que no son número se dicen", ctx do
    escuelas = puntos(ctx.scope, ctx.team, [{"A", centro(2, 3)}])

    viejo =
      vacia(ctx.scope, ctx.team, "Viejo", "raster", [], %{
        png: "x",
        oeste: -104.0,
        sur: 19.0,
        este: -103.0,
        norte: 20.0,
        limites: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
      })

    assert {:error, "Ese ráster se subió antes" <> _} =
             Muestreo.calcular(escuelas, %{raster: viejo})

    otro = user_scope_fixture()

    ajeno =
      capa_raster(otro, team_fixture(otro).id, "Ajeno", [tesela([[1]], -104.0, 20.0, @paso)])

    assert {:error, "Las dos capas" <> _} = Muestreo.calcular(escuelas, %{raster: ajeno})

    assert {:error, "Los valores" <> _} =
             Muestreo.calcular(escuelas, %{raster: ctx.raster, radio: 100, valores: "cultivo"})
  end
end
