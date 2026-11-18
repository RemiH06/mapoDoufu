defmodule Mapo.Capas.Derivadas do
  @moduledoc """
  Lo que comparten las capas que salen de otra (distancia, valor de un ráster):
  filtros de texto sobre los renglones, nombres de columna nuevos y guardar el
  resultado contra la cuota del equipo.
  """

  alias Mapo.Accounts.Scope
  alias Mapo.Capas
  alias Mapo.Capas.Capa
  alias Mapo.Repo

  @timeout 120_000

  @doc """
  Guarda una capa nueva del equipo del `origen`, del mismo tipo, con `attrs`
  (nombre, columnas, numericas, num_filas y metodo). `insertar` recibe su id y
  mete los renglones. El tamaño se mide ya guardado, y si no cabe en la cuota
  no queda nada.
  """
  def guardar(%Scope{} = scope, %Capa{} = origen, attrs, insertar) do
    Repo.transaction(
      fn ->
        Repo.query!("SELECT pg_advisory_xact_lock(hashtext('capas'), $1)", [origen.team_id])

        capa =
          %Capa{}
          |> Capa.changeset(
            Map.merge(attrs, %{
              team_id: origen.team_id,
              user_id: scope.user.id,
              archivo: String.slice(origen.nombre, 0, 255),
              tamano_bytes: 0,
              tipo: origen.tipo,
              fechas: origen.fechas,
              num_descartadas: 0,
              repetidas: 0
            })
          )
          |> Repo.insert()
          |> case do
            {:ok, capa} -> capa
            {:error, changeset} -> Repo.rollback(changeset)
          end

        insertar.(capa.id)

        %{rows: [[bytes]]} =
          Repo.query!(
            """
            SELECT coalesce(sum(octet_length(datos::text) + ST_MemSize(geom)), 0)::bigint
            FROM capa_filas WHERE capa_id = $1
            """,
            [capa.id]
          )

        if Capas.uso_equipo(origen.team_id) + bytes > Capas.max_bytes_equipo(),
          do: Repo.rollback(:cuota)

        capa |> Ecto.Changeset.change(tamano_bytes: bytes) |> Repo.update!()
      end,
      timeout: @timeout
    )
  end

  @doc """
  SQL de los filtros sobre los renglones de `alias`, con sus parámetros desde
  `$n`: `{sql, params, siguiente_n}`. Sin filtros, `"true"`.
  """
  def filtros_sql(alias, filtros, n) do
    {partes, {params, n}} =
      Enum.map_reduce(filtros, {[], n}, fn
        {:fecha, columna, desde, hasta}, {params, n} ->
          {sql_fecha(alias, n), {params ++ [columna, desde, hasta], n + 3}}

        {columna, patrones}, {params, n} ->
          sql =
            "unaccent(#{alias}.datos->>$#{n}::text) ILIKE ANY " <>
              "(SELECT unaccent(p) FROM unnest($#{n + 1}::text[]) p)"

          {sql, {params ++ [columna, patrones], n + 2}}
      end)

    {if(partes == [], do: "true", else: "(" <> Enum.join(partes, " AND ") <> ")"), params, n}
  end

  # Las fechas van en ISO (mapo_core las normaliza al subir), así que el rango es
  # comparar texto. Una fecha parcial cuenta como su periodo completo: "2018" va
  # del 2018-01-01 al 2018-12-31, y entra si se traslapa con el rango.
  defp sql_fecha(alias, n) do
    v = "#{alias}.datos->>$#{n}::text"
    inicio = "left(#{v} || '-01-01', 10)"

    fin =
      "CASE length(#{v}) WHEN 4 THEN #{v} || '-12-31' WHEN 7 THEN #{v} || '-31' ELSE left(#{v}, 10) END"

    "(#{v} IS NOT NULL AND ($#{n + 1}::text IS NULL OR #{fin} >= $#{n + 1}::text)" <>
      " AND ($#{n + 2}::text IS NULL OR #{inicio} <= $#{n + 2}::text))"
  end

  @doc """
  Los filtros listos para `filtros_sql/3`, sin los vacíos: `{columna, texto}` pasa a
  `{columna, ["%texto%", ...]}`, y `{:fecha, columna, desde, hasta}` (fechas ISO o
  `nil`, al menos una) se queda igual.
  """
  def filtros(nil), do: []
  def filtros({_, _} = filtro), do: filtros([filtro])

  def filtros(lista) do
    Enum.flat_map(lista, fn
      {:fecha, columna, desde, hasta}
      when is_binary(columna) and (desde != nil or hasta != nil) ->
        [{:fecha, columna, desde, hasta}]

      {columna, texto} when is_binary(columna) and is_binary(texto) ->
        case alternativas(texto) do
          [] -> []
          patrones -> [{columna, Enum.map(patrones, &("%" <> escapar(&1) <> "%"))}]
        end

      _ ->
        []
    end)
  end

  defp alternativas(texto),
    do: texto |> String.split("|") |> Enum.map(&String.trim/1) |> Enum.reject(&(&1 == ""))

  defp escapar(texto), do: String.replace(texto, ["\\", "%", "_"], &("\\" <> &1))

  @doc "Un nombre que no esté en `usadas`, con _2, _3... si hace falta: `{nombre, usadas}`."
  def unica(nombre, usadas, n \\ 1) do
    candidato = if n == 1, do: nombre, else: "#{nombre}_#{n}"

    if candidato in usadas,
      do: unica(nombre, usadas, n + 1),
      else: {candidato, [candidato | usadas]}
  end

  @doc "El nombre de una capa sin acentos ni signos, para nombrar columnas."
  def slug(nombre) do
    nombre
    |> String.normalize(:nfd)
    |> String.replace(~r/\p{Mn}/u, "")
    |> String.downcase()
    |> String.replace(~r/[^a-z0-9]+/, "_")
    |> String.trim("_")
    |> String.slice(0, 30)
    |> case do
      "" -> "destino"
      s -> s
    end
  end

  @doc "Los filtros en palabras, para el método."
  def filtro_texto(filtro) do
    condiciones =
      for f <- filtros(filtro) do
        case f do
          {:fecha, col, nil, hasta} ->
            "#{col} hasta el #{hasta}"

          {:fecha, col, desde, nil} ->
            "#{col} desde el #{desde}"

          {:fecha, col, desde, hasta} ->
            "#{col} del #{desde} al #{hasta}"

          {col, patrones} ->
            textos =
              Enum.map_join(
                patrones,
                " o ",
                &"«#{&1 |> String.slice(1..-2//1) |> sin_escape()}»"
              )

            "#{col} contiene #{textos}"
        end
      end

    if condiciones == [], do: "", else: ", solo donde " <> Enum.join(condiciones, " y ")
  end

  defp sin_escape(patron),
    do: String.replace(patron, ["\\\\", "\\%", "\\_"], &String.slice(&1, 1..1))
end
