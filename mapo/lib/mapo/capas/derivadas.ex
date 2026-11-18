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
      Enum.map_reduce(filtros, {[], n}, fn {columna, patrones}, {params, n} ->
        sql =
          "unaccent(#{alias}.datos->>$#{n}::text) ILIKE ANY " <>
            "(SELECT unaccent(p) FROM unnest($#{n + 1}::text[]) p)"

        {sql, {params ++ [columna, patrones], n + 2}}
      end)

    {if(partes == [], do: "true", else: "(" <> Enum.join(partes, " AND ") <> ")"), params, n}
  end

  @doc "`[{columna, [\"%texto%\", ...]}]` a partir de `{columna, texto}`, sin los vacíos."
  def filtros(nil), do: []
  def filtros({_, _} = filtro), do: filtros([filtro])

  def filtros(lista) do
    for {columna, texto} <- lista,
        is_binary(columna) and is_binary(texto),
        patrones = alternativas(texto),
        patrones != [],
        do: {columna, Enum.map(patrones, &("%" <> escapar(&1) <> "%"))}
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
      for {col, patrones} <- filtros(filtro) do
        textos =
          Enum.map_join(patrones, " o ", &"«#{&1 |> String.slice(1..-2//1) |> sin_escape()}»")

        "#{col} contiene #{textos}"
      end

    if condiciones == [], do: "", else: ", solo donde " <> Enum.join(condiciones, " y ")
  end

  defp sin_escape(patron),
    do: String.replace(patron, ["\\\\", "\\%", "\\_"], &String.slice(&1, 1..1))
end
