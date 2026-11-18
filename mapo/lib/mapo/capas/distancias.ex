defmodule Mapo.Capas.Distancias do
  @moduledoc """
  Distancia entre dos capas del mismo equipo, renglón por renglón: de cada
  renglón del origen al más cercano del destino, en metros y sin repartir nada
  (docs/producto/datos-propios.md, "Distancia entre capas").

  Se calcula en PostGIS porque las dos capas ya están en `capa_filas`. El más
  cercano se busca en dos pasos: el índice da un candidato en grados y su
  distancia en metros acota una caja; dentro de esa caja gana el de menos
  metros. Un grado de longitud mide menos que uno de latitud, así que el más
  cercano en grados no siempre lo es en metros.
  """

  import Ecto.Query, warn: false

  alias Mapo.Accounts.Scope
  alias Mapo.Capas.Capa
  alias Mapo.Capas.Derivadas
  alias Mapo.Repo

  # Metros por grado, cota baja dentro de México (latitud de 35° o menos): una
  # caja de `metros / @por_grado` grados cubre seguro esos metros.
  @por_grado 91_000.0
  # Columnas del destino que viajan solas si existen: de dónde salió el dato.
  @procedencia ~w(fuente fecha_dato)
  @a_la_vista 20
  @timeout 120_000

  @doc "Se mide entre capas que traen su propia geometría."
  def medible?(%Capa{tipo: tipo}), do: tipo in ~w(puntos vector)

  @doc """
  Calcula sin guardar. `opciones`:

    * `:destino` - la otra capa, ya autorizada y del mismo equipo
    * `:filtro_origen`, `:filtro_destino` - lista de `{columna, texto}` (o una
      sola tupla, o `nil`): solo los renglones que cumplen todas, es decir,
      cuya columna contiene el texto sin importar mayúsculas ni acentos. Una
      barra separa alternativas: `"039|120"` es una o la otra
    * `:etiqueta_origen`, `:etiqueta_destino` - columna que nombra cada renglón
    * `:radio` - metros, o `nil`: además cuenta los del destino a esa distancia

  Regresa `{:ok, %{filas, total, a_menos, destino_filas, columnas, metodo}}`,
  con `filas` de las #{@a_la_vista} más cercanas, o `{:error, mensaje}`.
  """
  def calcular(%Capa{} = origen, opciones) do
    with :ok <- validar(origen, opciones),
         {:ok, destino_filas} <- contar_destino(opciones) do
      etiqueta = opciones[:etiqueta_origen]
      lleva = lleva(opciones)

      {desde, params} = consulta(origen, opciones)
      n = length(params)

      sql = """
      SELECT a.datos->>$#{n + 1}::text, d.metros, d.datos->>$#{n + 2}::text, c.cuantos
      #{desde}
      ORDER BY d.metros NULLS LAST, a.id
      """

      filas = Repo.query!(sql, params ++ [etiqueta, primera(lleva)], timeout: @timeout).rows

      a_menos =
        if radio = opciones[:radio],
          do: Enum.count(filas, fn [_, metros, _, _] -> metros && metros <= radio end)

      {:ok,
       %{
         filas:
           filas
           |> Enum.take(@a_la_vista)
           |> Enum.map(fn [nombre, metros, cercano, cuantos] ->
             %{nombre: nombre, metros: redondear(metros), cercano: cercano, cuantos: cuantos}
           end),
         total: length(filas),
         a_menos: a_menos,
         destino_filas: destino_filas,
         columnas: columnas_nuevas(origen, opciones),
         metodo: metodo(origen, opciones, length(filas), destino_filas)
       }}
    end
  end

  @doc """
  Guarda el resultado como capa del equipo del origen, con la geometría
  completa del origen y sus columnas más las nuevas. Recalcula: las capas no
  cambian una vez subidas, así que da lo mismo que se vio.
  """
  def guardar(%Scope{} = scope, %Capa{} = origen, opciones, nombre, resultado) do
    nuevas = columnas_nuevas(origen, opciones)
    %{distancia: distancia, lleva: llevadas, cuantos: cuantos} = nuevas
    lleva = lleva(opciones)

    pares =
      [{distancia, "round(d.metros)::bigint"}] ++
        Enum.map(Enum.zip(llevadas, lleva), fn {nombre, col} -> {nombre, {:col, col}} end) ++
        if(cuantos, do: [{cuantos, "c.cuantos"}], else: [])

    {desde, params} = consulta(origen, opciones)
    n = length(params)
    {objeto, extra} = objeto_json(pares, n + 2)

    attrs = %{
      nombre: nombre,
      columnas: origen.columnas ++ Enum.map(pares, &elem(&1, 0)),
      numericas: origen.numericas ++ Enum.reject([distancia, cuantos], &is_nil/1),
      num_filas: resultado.total,
      metodo: Enum.join(resultado.metodo, "\n")
    }

    Derivadas.guardar(scope, origen, attrs, fn capa_id ->
      Repo.query!(
        """
        INSERT INTO capa_filas (capa_id, geom, datos)
        SELECT $#{n + 1}::bigint, a.geom, a.datos || #{objeto}
        #{desde}
        ORDER BY a.id
        """,
        params ++ [capa_id | extra],
        timeout: @timeout
      )
    end)
  end

  # El FROM del cálculo y sus parámetros: $1 origen, $2 destino, $3 radio y
  # luego los filtros, dos parámetros cada uno.
  defp consulta(origen, opciones) do
    radio = opciones[:radio] && opciones[:radio] * 1.0

    {en_a, params_a, n} =
      Derivadas.filtros_sql("a", Derivadas.filtros(opciones[:filtro_origen]), 4)

    {en_b, params_b, _} =
      Derivadas.filtros_sql("b", Derivadas.filtros(opciones[:filtro_destino]), n)

    sql = """
    FROM capa_filas a
    LEFT JOIN LATERAL (
      SELECT ST_Distance(a.geom::geography, b.geom::geography) AS tope
      FROM capa_filas b
      WHERE b.capa_id = $2 AND b.geom IS NOT NULL AND #{en_b}
      ORDER BY a.geom <-> b.geom
      LIMIT 1
    ) cand ON true
    LEFT JOIN LATERAL (
      SELECT ST_Distance(a.geom::geography, b.geom::geography) AS metros, b.datos
      FROM capa_filas b
      WHERE b.capa_id = $2 AND b.geom IS NOT NULL AND #{en_b}
        AND b.geom && ST_Expand(a.geom, cand.tope / #{@por_grado})
      ORDER BY metros, b.id
      LIMIT 1
    ) d ON true
    LEFT JOIN LATERAL (
      SELECT count(*) AS cuantos
      FROM capa_filas b
      WHERE $3::float8 IS NOT NULL AND b.capa_id = $2 AND b.geom IS NOT NULL AND #{en_b}
        AND b.geom && ST_Expand(a.geom, $3::float8 / #{@por_grado})
        AND ST_DWithin(a.geom::geography, b.geom::geography, $3::float8)
    ) c ON true
    WHERE a.capa_id = $1 AND a.geom IS NOT NULL AND #{en_a}
    """

    {sql, [origen.id, opciones[:destino].id, radio] ++ params_a ++ params_b}
  end

  # Nombres de columna vienen de un archivo: van como parámetros, nunca en el SQL.
  defp objeto_json(pares, desde) do
    {partes, _} =
      Enum.map_reduce(pares, desde, fn
        {_, {:col, _}}, n -> {"$#{n}::text, d.datos->$#{n + 1}::text", n + 2}
        {_, expresion}, n -> {"$#{n}::text, #{expresion}", n + 1}
      end)

    extra =
      Enum.flat_map(pares, fn
        {nombre, {:col, col}} -> [nombre, col]
        {nombre, _} -> [nombre]
      end)

    {"jsonb_build_object(#{Enum.join(partes, ", ")})", extra}
  end

  defp validar(origen, opciones) do
    destino = opciones[:destino]

    cond do
      not medible?(origen) or not match?(%Capa{}, destino) or not medible?(destino) ->
        {:error, "Solo se mide entre capas de puntos o geometrías."}

      destino.team_id != origen.team_id ->
        {:error, "Las dos capas tienen que ser del mismo equipo."}

      (r = opciones[:radio]) != nil and not (is_number(r) and r > 0 and r <= 100_000) ->
        {:error, "El radio va de 1 a 100,000 metros."}

      true ->
        :ok
    end
  end

  defp contar_destino(opciones) do
    {en_b, params, _} =
      Derivadas.filtros_sql("b", Derivadas.filtros(opciones[:filtro_destino]), 2)

    %{rows: [[n]]} =
      Repo.query!(
        "SELECT count(*) FROM capa_filas b WHERE b.capa_id = $1 AND b.geom IS NOT NULL AND #{en_b}",
        [opciones[:destino].id | params]
      )

    if n == 0,
      do: {:error, "El filtro del destino no deja ningún renglón."},
      else: {:ok, n}
  end

  defp lleva(opciones) do
    destino = opciones[:destino]
    etiqueta = opciones[:etiqueta_destino]
    propias = Enum.filter(@procedencia, &(&1 in destino.columnas))
    Enum.uniq(Enum.reject([etiqueta | propias], &is_nil/1))
  end

  defp primera([col | _]), do: col
  defp primera([]), do: nil

  @doc false
  def columnas_nuevas(origen, opciones) do
    s = Derivadas.slug(opciones[:destino].nombre)
    {distancia, usadas} = Derivadas.unica("distancia_m_#{s}", origen.columnas)

    {lleva, usadas} =
      Enum.map_reduce(lleva(opciones), usadas, fn col, usadas ->
        Derivadas.unica("#{s}_#{col}", usadas)
      end)

    cuantos =
      if r = opciones[:radio], do: elem(Derivadas.unica("#{s}_a_#{r}m", usadas), 0)

    %{distancia: distancia, lleva: lleva, cuantos: cuantos}
  end

  defp metodo(origen, opciones, total, destino_filas) do
    destino = opciones[:destino]
    %{distancia: distancia, lleva: llevadas, cuantos: cuantos} = columnas_nuevas(origen, opciones)

    [
      "Origen: #{origen.nombre}, #{total} renglones#{Derivadas.filtro_texto(opciones[:filtro_origen])}.",
      "Destino: #{destino.nombre}, #{destino_filas} renglones#{Derivadas.filtro_texto(opciones[:filtro_destino])}.",
      "#{distancia}: metros en línea recta sobre el elipsoide WGS84, de borde a borde, " <>
        "al renglón más cercano del destino. 0 si se tocan o uno contiene al otro."
    ] ++
      Enum.map(Enum.zip(llevadas, lleva(opciones)), fn {nombre, col} ->
        "#{nombre}: #{col} de ese renglón más cercano."
      end) ++
      if(cuantos,
        do: ["#{cuantos}: renglones del destino a #{opciones[:radio]} m o menos."],
        else: []
      ) ++
      [
        "La distancia es tan precisa como las capas: un mapa 1:250 000 puede desviarse " <>
          "cientos de metros en sus bordes. Cercanía no dice causa.",
        "Calculado el #{Date.utc_today()}."
      ]
  end

  defp redondear(nil), do: nil
  defp redondear(metros), do: round(metros)
end
