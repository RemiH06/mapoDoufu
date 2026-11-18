defmodule Mapo.Capas.Localidades do
  @moduledoc """
  Distancia de cada renglón de una capa a la localidad del censo 2020 más
  cercana (ITER de INEGI, todo el país), con lo mismo que da la distancia entre
  capas. Las localidades son de `mapo_core`: los renglones van en la petición,
  como en el cruce, y allá no se guardan (docs/fuentes/localidades.md).
  """

  alias Mapo.Accounts.Scope
  alias Mapo.Capas.{Capa, Derivadas, Distancias}
  alias Mapo.MapoCore
  alias Mapo.Repo

  @nombre "Localidades del censo 2020"
  @a_la_vista 20
  @fuente "INEGI, ITER del Censo 2020"
  @fecha "2020-03-15"

  @doc "El destino para la pantalla de distancia, junto a las capas del equipo."
  def destino,
    do: %{id: "localidades", nombre: @nombre, columnas: [], fechas: [], publica: true}

  @doc """
  Calcula sin guardar. `opciones`: `:radio` (metros o `nil`), `:ambito` (`"rural"`,
  `"urbana"` o `nil`), `:etiqueta_origen` y `:filtro_origen`. Regresa lo mismo
  que `Mapo.Capas.Distancias.calcular/2`, más lo que hace falta para guardar.
  """
  def calcular(%Capa{} = origen, opciones) do
    with :ok <- validar(origen, opciones),
         {:ok, filas} <- filas_origen(origen, opciones),
         {:ok, respuesta} <- pedir(filas, opciones) do
      resultado(origen, opciones, filas, respuesta)
    end
  end

  defp validar(origen, opciones) do
    cond do
      not Distancias.medible?(origen) ->
        {:error, "Solo se mide desde capas de puntos o geometrías."}

      opciones[:ambito] not in [nil, "rural", "urbana"] ->
        {:error, "El ámbito es rural o urbana."}

      (r = opciones[:radio]) != nil and not (is_number(r) and r > 0 and r <= 100_000) ->
        {:error, "El radio va de 1 a 100,000 metros."}

      true ->
        :ok
    end
  end

  defp filas_origen(origen, opciones) do
    {filtro, params, n} =
      Derivadas.filtros_sql("a", Derivadas.filtros(opciones[:filtro_origen]), 2)

    %{rows: filas} =
      Repo.query!(
        """
        SELECT a.id, ST_AsGeoJSON(a.geom), a.datos->>$#{n}::text
        FROM capa_filas a
        WHERE a.capa_id = $1 AND a.geom IS NOT NULL AND #{filtro}
        ORDER BY a.id
        """,
        [origen.id | params] ++ [opciones[:etiqueta_origen]],
        timeout: 120_000
      )

    if filas == [],
      do: {:error, "El filtro del origen no deja ningún renglón."},
      else: {:ok, filas}
  end

  defp pedir(filas, opciones) do
    solicitud = %{
      filas:
        Enum.map(filas, fn [id, geojson, _] -> %{id: id, geometria: Jason.decode!(geojson)} end),
      radio: opciones[:radio],
      ambito: opciones[:ambito]
    }

    case MapoCore.localidades_distancia(solicitud) do
      {:ok, %{"localidades" => 0}} ->
        {:error, "No hay localidades cargadas con ese filtro."}

      {:ok, respuesta} ->
        {:ok, respuesta}

      {:error, {:status, 422, %{"detail" => detalle}}} when is_binary(detalle) ->
        {:error, detalle}

      {:error, _} ->
        {:error, "mapo_core no está disponible ahorita mismo."}
    end
  end

  defp resultado(origen, opciones, filas, respuesta) do
    radio = opciones[:radio]
    nuevas = columnas_nuevas(origen, radio)
    nombres = Map.new(filas, fn [id, _, nombre] -> {id, nombre} end)

    por_id =
      Map.new(respuesta["filas"], fn f ->
        valores =
          [
            f["metros"],
            f["nombre"],
            f["nom_mun"],
            f["cvegeo"],
            f["ambito"],
            f["pobtot"],
            @fuente,
            @fecha
          ] ++
            if(radio, do: [f["cuantos"], f["poblacion"]], else: [])

        {f["id"], Map.new(Enum.zip(nuevas, valores))}
      end)

    ordenadas = Enum.sort_by(respuesta["filas"], &{is_nil(&1["metros"]), &1["metros"], &1["id"]})

    {:ok,
     %{
       filas:
         ordenadas
         |> Enum.take(@a_la_vista)
         |> Enum.map(fn f ->
           %{
             nombre: nombres[f["id"]],
             metros: f["metros"],
             cercano: f["nombre"],
             cuantos: f["cuantos"]
           }
         end),
       total: length(filas),
       a_menos: radio && Enum.count(respuesta["filas"], &(&1["metros"] && &1["metros"] <= radio)),
       destino_filas: respuesta["localidades"],
       columnas: nuevas,
       por_id: por_id,
       metodo: metodo(origen, opciones, length(filas), respuesta["localidades"], nuevas)
     }}
  end

  @doc false
  def columnas_nuevas(origen, radio) do
    sufijos =
      ~w(distancia_m_localidades localidades_nombre localidades_municipio localidades_cvegeo
         localidades_ambito localidades_pobtot localidades_fuente localidades_fecha_dato) ++
        if(radio, do: ["localidades_a_#{radio}m", "localidades_pob_a_#{radio}m"], else: [])

    {nombres, _} = Enum.map_reduce(sufijos, origen.columnas, &Derivadas.unica/2)
    nombres
  end

  defp metodo(origen, opciones, total, localidades, nuevas) do
    [distancia, nombre, _mun, _cve, _amb, pob | resto] = nuevas
    ambito = %{"rural" => " rurales", "urbana" => " urbanas"}[opciones[:ambito]] || ""

    [
      "Origen: #{origen.nombre}, #{total} renglones#{Derivadas.filtro_texto(opciones[:filtro_origen])}.",
      "Destino: #{miles(localidades)} localidades#{ambito} del ITER del Censo 2020 de INEGI, todo el país (fecha de referencia #{@fecha}). " <>
        "Rural es de menos de 2,500 habitantes, como lo define INEGI.",
      "#{distancia}: metros en línea recta sobre el elipsoide WGS84 al punto de la localidad más cercana. " <>
        "INEGI ubica cada localidad en un punto, no en un polígono: en una ciudad, ese punto es su centro.",
      "#{nombre}, #{pob} y las demás: de esa localidad más cercana."
    ] ++
      case resto do
        [_fuente, _fecha, cuantos, pob_radio] ->
          [
            "#{cuantos}: localidades a #{opciones[:radio]} m o menos.",
            "#{pob_radio}: población que vive en ellas (la de toda la localidad, aunque parte quede más lejos)."
          ]

        _ ->
          []
      end ++
      ["Cercanía no dice causa.", "Calculado el #{Date.utc_today()}."]
  end

  defp miles(n),
    do: n |> Integer.to_string() |> String.replace(~r/\B(?=(\d{3})+$)/, ",")

  @doc "Guarda el resultado de `calcular/2` como capa del equipo del origen."
  def guardar(%Scope{} = scope, %Capa{} = origen, nombre, resultado) do
    numericas =
      Enum.filter(resultado.columnas, &(&1 =~ ~r/^distancia_m_|_pobtot|_a_\d+m$/))

    attrs = %{
      nombre: nombre,
      columnas: origen.columnas ++ resultado.columnas,
      numericas: origen.numericas ++ numericas,
      num_filas: resultado.total,
      metodo: Enum.join(resultado.metodo, "\n")
    }

    {ids, extras} = resultado.por_id |> Enum.sort() |> Enum.unzip()

    Derivadas.guardar(scope, origen, attrs, fn capa_id ->
      Repo.query!(
        """
        INSERT INTO capa_filas (capa_id, geom, datos)
        SELECT $1, a.geom, a.datos || r.extra
        FROM capa_filas a
        JOIN unnest($2::bigint[], $3::jsonb[]) AS r(id, extra) ON r.id = a.id
        WHERE a.capa_id = $4
        ORDER BY a.id
        """,
        [capa_id, ids, extras, origen.id],
        timeout: 120_000
      )
    end)
  end
end
