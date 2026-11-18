defmodule Mapo.Capas.Muestreo do
  @moduledoc """
  Valor de un ráster en cada renglón de una capa de puntos o geometrías del
  mismo equipo: el del píxel en el punto, o un resumen de los píxeles en una
  zona (el polígono, o un círculo alrededor). Ver docs/producto/datos-propios.md,
  "Valor de un ráster".

  Se calcula en PostGIS con las teselas de `capa_raster_teselas`. Las teselas
  se eligen por su caja (`ST_ConvexHull(rast) && zona`, con índice) y no con
  `ST_Intersects`, que revisa píxel por píxel cada tesela: con 266 teselas, eso
  costaba 100 ms por renglón. La zona se calcula una vez por renglón (`OFFSET 0`
  impide que Postgres la repita en cada tesela). Los valores
  salen tal como vienen en el archivo: si la banda es NDVI × 10000, el promedio
  también.
  """

  import Ecto.Query, only: [from: 2]

  alias Mapo.Accounts.Scope
  alias Mapo.Capas.{Capa, CapaRaster, Derivadas}
  alias Mapo.Repo

  @a_la_vista 20
  @timeout 120_000

  @doc "Se muestrea desde una capa con geometría propia."
  def muestreable?(%Capa{tipo: tipo}), do: tipo in ~w(puntos vector)

  @doc """
  Calcula sin guardar. `opciones`:

    * `:raster` - la capa ráster, ya autorizada y del mismo equipo
    * `:radio` - metros, o `nil`: sin radio, el punto o el polígono mismo
    * `:valores` - texto como `"40|50"`, o `nil`: además, qué parte de la zona
      tiene alguno de esos valores
    * `:filtro_origen`, `:etiqueta_origen` - como en `Mapo.Capas.Distancias`

  Regresa `{:ok, %{filas, total, sin_dato, columnas, metodo}}` o `{:error, mensaje}`.
  """
  def calcular(%Capa{} = origen, opciones) do
    with {:ok, meta} <- validar(origen, opciones),
         {:ok, valores} <- valores(opciones[:valores]) do
      opciones = preparar(origen, opciones, valores, meta)
      {desde, params} = consulta(origen, opciones)
      n = length(params)
      columnas = columnas_nuevas(origen, opciones)

      # Con valores pedidos, lo que importa es su parte: en un ráster de clases el
      # promedio no dice nada.
      orden =
        cond do
          opciones.puntual -> "r.valor"
          opciones.valores_num -> "r.en_valores::numeric / nullif(r.pixeles, 0)"
          true -> "r.promedio"
        end

      filas =
        Repo.query!(
          """
          SELECT a.datos->>$#{n + 1}::text, #{expresiones(opciones) |> Enum.map_join(", ", &elem(&1, 1))}
          #{desde}
          ORDER BY #{orden} DESC NULLS LAST, a.id
          """,
          params ++ [opciones[:etiqueta_origen]],
          timeout: @timeout
        ).rows

      sin_dato = Enum.count(filas, fn [_, primero | _] -> primero == nil end)

      {:ok,
       %{
         filas:
           filas
           |> Enum.take(@a_la_vista)
           |> Enum.map(fn [nombre | resto] ->
             %{nombre: nombre, valores: Enum.map(resto, &redondear/1)}
           end),
         total: length(filas),
         sin_dato: sin_dato,
         columnas: columnas,
         metodo: metodo(origen, opciones, length(filas), columnas)
       }}
    end
  end

  @doc "Guarda el resultado como capa del equipo del origen, como la distancia."
  def guardar(%Scope{} = scope, %Capa{} = origen, opciones, nombre, resultado) do
    {:ok, meta} = validar(origen, opciones)
    {:ok, valores} = valores(opciones[:valores])
    opciones = preparar(origen, opciones, valores, meta)
    {desde, params} = consulta(origen, opciones)
    n = length(params)
    columnas = resultado.columnas

    {partes, _} =
      columnas
      |> Enum.zip(expresiones(opciones))
      |> Enum.map_reduce(n + 2, fn {_nombre, {_, expresion}}, i ->
        {"$#{i}::text, #{expresion}", i + 1}
      end)

    attrs = %{
      nombre: nombre,
      columnas: origen.columnas ++ columnas,
      numericas: origen.numericas ++ columnas,
      num_filas: resultado.total,
      metodo: Enum.join(resultado.metodo, "\n")
    }

    Derivadas.guardar(scope, origen, attrs, fn capa_id ->
      Repo.query!(
        """
        INSERT INTO capa_filas (capa_id, geom, datos)
        SELECT $#{n + 1}::bigint, a.geom,
               a.datos || jsonb_build_object(#{Enum.join(partes, ", ")})
        #{desde}
        ORDER BY a.id
        """,
        params ++ [capa_id | columnas],
        timeout: @timeout
      )
    end)
  end

  defp puntual?(origen, opciones), do: origen.tipo == "puntos" and is_nil(opciones[:radio])

  defp preparar(origen, opciones, valores, meta) do
    Map.merge(opciones, %{valores_num: valores, meta: meta, puntual: puntual?(origen, opciones)})
  end

  # Columnas que salen, en orden, con su expresión sobre el renglón `r`.
  defp expresiones(opciones) do
    if opciones[:puntual] do
      [{:valor, "r.valor"}]
    else
      [
        {:promedio, "r.promedio"},
        {:min, "r.minimo"},
        {:max, "r.maximo"},
        {:pixeles, "r.pixeles"}
      ] ++
        if opciones[:valores_num],
          do: [{:parte, "round((r.en_valores::numeric / nullif(r.pixeles, 0)), 3)"}],
          else: []
    end
  end

  # $1 origen, $2 ráster; en una zona, $3 radio y $4 valores para la parte;
  # luego los filtros.
  defp consulta(origen, opciones) do
    puntual = puntual?(origen, opciones)
    radio = opciones[:radio] && opciones[:radio] * 1.0
    propios = if puntual, do: [], else: [radio, opciones[:valores_num]]

    {en_a, params_a, _} =
      Derivadas.filtros_sql("a", Derivadas.filtros(opciones[:filtro_origen]), 3 + length(propios))

    resumen =
      if puntual do
        """
        LEFT JOIN LATERAL (
          SELECT max(ST_Value(t.rast, 1, a.geom)) AS valor
          FROM capa_raster_teselas t
          WHERE t.capa_id = $2 AND ST_ConvexHull(t.rast) && a.geom
        ) r ON true
        """
      else
        """
        CROSS JOIN LATERAL (
          SELECT CASE WHEN $3::float8 IS NULL THEN a.geom
                      ELSE ST_Buffer(a.geom::geography, $3::float8)::geometry END AS zona
          OFFSET 0
        ) z
        LEFT JOIN LATERAL (
          SELECT sum((st).count)::bigint AS pixeles,
                 sum((st).sum) / nullif(sum((st).count), 0) AS promedio,
                 min((st).min) AS minimo,
                 max((st).max) AS maximo,
                 (SELECT sum((vc).count)::bigint
                  FROM (SELECT ST_ValueCount(ST_Clip(t.rast, 1, z.zona, true), 1, true, $4::float8[]) AS vc
                        FROM capa_raster_teselas t
                        WHERE $4::float8[] IS NOT NULL AND t.capa_id = $2
                          AND ST_ConvexHull(t.rast) && z.zona) v) AS en_valores
          FROM (SELECT ST_SummaryStats(ST_Clip(t.rast, 1, z.zona, true), 1, true) AS st
                FROM capa_raster_teselas t
                WHERE t.capa_id = $2 AND ST_ConvexHull(t.rast) && z.zona) x
          WHERE (st).count > 0
        ) r ON true
        """
      end

    sql = """
    FROM capa_filas a
    #{resumen}
    WHERE a.capa_id = $1 AND a.geom IS NOT NULL AND #{en_a}
    """

    {sql, [origen.id, opciones[:raster].id] ++ propios ++ params_a}
  end

  defp validar(origen, opciones) do
    raster = opciones[:raster]

    # Sin la imagen, que puede pesar megas.
    meta =
      if match?(%Capa{tipo: "raster"}, raster),
        do:
          Repo.one(
            from r in CapaRaster,
              where: r.capa_id == ^raster.id,
              select: map(r, [:banda, :metros_pixel, :reducido])
          )

    cond do
      not muestreable?(origen) or is_nil(meta) ->
        {:error, "Se muestrea un ráster desde una capa de puntos o geometrías."}

      raster.team_id != origen.team_id ->
        {:error, "Las dos capas tienen que ser del mismo equipo."}

      is_nil(meta.metros_pixel) ->
        {:error,
         "Ese ráster se subió antes de que Mapo guardara sus valores: súbelo otra vez para consultarlo."}

      (r = opciones[:radio]) != nil and not (is_number(r) and r > 0 and r <= 100_000) ->
        {:error, "El radio va de 1 a 100,000 metros."}

      true ->
        {:ok, meta}
    end
  end

  defp valores(nil), do: {:ok, nil}

  defp valores(texto) do
    partes = texto |> String.split("|") |> Enum.map(&String.trim/1) |> Enum.reject(&(&1 == ""))

    numeros =
      Enum.map(partes, fn p ->
        case Float.parse(p) do
          {n, ""} -> n
          _ -> nil
        end
      end)

    cond do
      partes == [] ->
        {:ok, nil}

      Enum.any?(numeros, &is_nil/1) ->
        {:error, "Los valores para la parte van en números: 40|50."}

      true ->
        {:ok, numeros}
    end
  end

  @doc false
  def columnas_nuevas(origen, opciones) do
    s = Derivadas.slug(opciones[:raster].nombre)

    sufijos =
      Enum.map(expresiones(opciones), fn
        {:parte, _} -> "parte_" <> Enum.map_join(opciones[:valores_num], "_", &numero/1)
        {nombre, _} -> to_string(nombre)
      end)

    {nombres, _} =
      Enum.map_reduce(sufijos, origen.columnas, fn sufijo, usadas ->
        Derivadas.unica("#{s}_#{sufijo}", usadas)
      end)

    nombres
  end

  defp metodo(origen, opciones, total, columnas) do
    %{raster: raster, meta: meta} = opciones
    banda = if meta.banda, do: " (banda #{meta.banda})", else: ""

    pixel =
      "píxel de unos #{round(meta.metros_pixel)} m" <>
        if(meta.reducido,
          do: ", reducido #{meta.reducido} veces del archivo para caber",
          else: ""
        )

    zona =
      cond do
        opciones.puntual ->
          "Se toma el valor del píxel donde cae cada punto."

        opciones[:radio] ->
          "Se toman los píxeles a #{opciones[:radio]} m o menos de cada renglón, de su borde " <>
            "si es polígono. Un píxel cuenta si su centro cae en la zona; el sin dato no cuenta."

        true ->
          "Se toman los píxeles dentro de cada polígono. Un píxel cuenta si su centro cae " <>
            "en la zona; el sin dato no cuenta."
      end

    [
      "Origen: #{origen.nombre}, #{total} renglones#{Derivadas.filtro_texto(opciones[:filtro_origen])}.",
      "Ráster: #{raster.nombre}#{banda}, #{pixel}.",
      zona
    ] ++
      Enum.map(columnas, &explicar(&1, opciones)) ++
      [
        "Los valores salen tal como vienen en el archivo, con su escala: si la banda es NDVI × 10000, el promedio también.",
        "Calculado el #{Date.utc_today()}."
      ]
  end

  defp explicar(columna, opciones) do
    cond do
      String.ends_with?(columna, "_valor") ->
        "#{columna}: valor del píxel. Vacío si es sin dato o cae fuera."

      String.contains?(columna, "_promedio") ->
        "#{columna}: promedio de los píxeles. Vacío si la zona no toca ninguno con valor."

      String.ends_with?(columna, "_min") ->
        "#{columna}: el menor."

      String.ends_with?(columna, "_max") ->
        "#{columna}: el mayor."

      String.ends_with?(columna, "_pixeles") ->
        "#{columna}: cuántos píxeles con valor entraron."

      true ->
        "#{columna}: parte de esos píxeles (0 a 1) con valor #{Enum.map_join(opciones[:valores_num], " o ", &numero/1)}."
    end
  end

  defp numero(n) when n == trunc(n), do: Integer.to_string(trunc(n))
  defp numero(n), do: Float.to_string(n)

  defp redondear(v) when is_float(v), do: Float.round(v, 2)
  defp redondear(%Decimal{} = v), do: Decimal.to_float(v)
  defp redondear(v), do: v
end
