defmodule Mapo.Capas do
  @moduledoc """
  Datos propios de un equipo: archivos ya ubicados que se ven como acetato en
  `/mapa` (docs/producto/datos-propios.md).

  El aislamiento entre equipos vive aquí: toda lectura pasa por un join contra
  la membresía del scope, igual que `Mapo.Sesiones`, así que "no existe" y "no
  es tuya" son el mismo error. Ver, subir y poner la capa en el mapa es para
  cualquier miembro; borrarla, para quien la subió o un titular/admin.
  """

  import Ecto.Query, warn: false

  alias Mapo.Accounts.Scope
  alias Mapo.Capas.{Capa, CapaFila, CapaRaster}
  alias Mapo.Repo
  alias Mapo.Teams
  alias Mapo.Teams.Membership

  @max_bytes_archivo 50 * 1024 * 1024
  @max_bytes_equipo 500 * 1024 * 1024
  # insert_all manda un parámetro por campo; Postgres admite 65,535.
  @lote 1_000
  # Unos 5 m en el plano. Lo guardado conserva todos sus vértices.
  @tolerancia_dibujo 0.00005

  def max_bytes_archivo, do: @max_bytes_archivo
  def max_bytes_equipo, do: @max_bytes_equipo

  defp del_scope(%Scope{} = scope) do
    from c in Capa,
      join: m in Membership,
      on: m.team_id == c.team_id,
      where: m.user_id == ^scope.user.id
  end

  defp ids_del_scope(scope), do: subquery(from c in del_scope(scope), select: %{id: c.id})

  @doc "Capas de un equipo, la más nueva primero. Requiere ser miembro."
  def list_capas(%Scope{} = scope, team_id) do
    Repo.all(
      from c in del_scope(scope),
        where: c.team_id == ^team_id,
        order_by: [desc: c.inserted_at, desc: c.id],
        preload: :user
    )
  end

  @doc "Capas de todos los equipos del scope, para la cinta de `/mapa`."
  def list_capas_del_usuario(%Scope{} = scope) do
    Repo.all(
      from c in del_scope(scope),
        join: t in assoc(c, :team),
        order_by: [t.name, c.nombre, c.id],
        preload: [team: t]
    )
  end

  @doc "Trae una capa o `nil` si no existe o no es de los equipos del scope."
  def get_capa(%Scope{} = scope, id), do: Repo.one(from c in del_scope(scope), where: c.id == ^id)

  @doc "Bytes de archivo que lleva gastados un equipo."
  def uso_equipo(team_id) do
    Repo.one(
      from c in Capa,
        where: c.team_id == ^team_id,
        select: type(coalesce(sum(c.tamano_bytes), 0), :integer)
    )
  end

  @doc "¿Cabe un archivo más de `bytes` en la cuota del equipo?"
  def cabe?(team_id, bytes), do: uso_equipo(team_id) + bytes <= @max_bytes_equipo

  @doc """
  Guarda una capa con sus filas (`%{"lat", "lon", "clave", "geometria",
  "datos"}`) y, si es ráster, su imagen, en una transacción. Toma un candado
  sobre el equipo para que dos subidas al mismo tiempo no se brinquen la cuota.
  """
  def crear_capa(%Scope{} = scope, team_id, attrs, filas, raster \\ nil) do
    true = Teams.role_in_team(scope, team_id) != nil

    Repo.transaction(
      fn ->
        Repo.query!("SELECT pg_advisory_xact_lock(hashtext('capas'), $1)", [team_id])

        if not cabe?(team_id, attrs.tamano_bytes), do: Repo.rollback(:cuota)

        capa =
          %Capa{}
          |> Capa.changeset(Map.merge(attrs, %{team_id: team_id, user_id: scope.user.id}))
          |> Repo.insert()
          |> case do
            {:ok, capa} -> capa
            {:error, changeset} -> Repo.rollback(changeset)
          end

        filas
        |> Stream.map(&fila_para_guardar(&1, capa.id))
        |> Stream.chunk_every(@lote)
        |> Enum.each(&Repo.insert_all(CapaFila, &1))

        if raster, do: Repo.insert!(struct!(CapaRaster, Map.put(raster, :capa_id, capa.id)))

        capa
      end,
      timeout: 120_000
    )
  end

  defp fila_para_guardar(%{"lat" => lat, "lon" => lon, "datos" => datos}, capa_id)
       when is_number(lat) and is_number(lon) do
    %{capa_id: capa_id, geom: %Geo.Point{coordinates: {lon, lat}, srid: 4326}, datos: datos}
  end

  defp fila_para_guardar(%{"geometria" => geometria, "datos" => datos}, capa_id) do
    geom = %{Geo.JSON.decode!(geometria) | srid: 4326}
    %{capa_id: capa_id, geom: geom, datos: datos}
  end

  defp fila_para_guardar(%{"clave" => clave, "datos" => datos}, capa_id),
    do: %{capa_id: capa_id, clave: clave, datos: datos}

  @doc """
  Se cruza lo que cae dentro de una zona. Una geometría puede repartirse entre
  varias, y un ráster no tiene renglones.
  """
  def cruzable?(%Capa{tipo: tipo}), do: tipo in ~w(puntos municipio ageb)

  @doc "Los renglones que `mapo_core` necesita para cruzar, con solo esas columnas."
  def filas_para_cruce(%Capa{id: id}, columnas) do
    Repo.all(
      from f in CapaFila,
        where: f.capa_id == ^id,
        order_by: f.id,
        select: {fragment("ST_Y(?)", f.geom), fragment("ST_X(?)", f.geom), f.clave, f.datos}
    )
    |> Enum.map(fn {lat, lon, clave, datos} ->
      %{lat: lat, lon: lon, clave: clave, valores: Map.take(datos, columnas)}
    end)
  end

  @doc """
  Guarda el resultado de un cruce como capa por zona del equipo de `origen`. Con
  un renglón por zona, se pinta y se abre como cualquier otra.
  """
  def crear_cruce(%Scope{} = scope, %Capa{} = origen, nombre, resultado) do
    filas = resultado["filas"]

    attrs = %{
      nombre: nombre,
      archivo: String.slice(origen.nombre, 0, 255),
      tamano_bytes: byte_size(Jason.encode!(filas)),
      tipo: resultado["nivel"],
      columnas: resultado["columnas"],
      numericas: resultado["numericas"],
      num_filas: length(filas),
      num_descartadas: 0,
      repetidas: 0,
      metodo: Enum.join(resultado["metodo"], "\n")
    }

    crear_capa(scope, origen.team_id, attrs, filas)
  end

  @doc """
  CSV de una capa de cruce, con BOM para que Excel lea bien los acentos. Las
  columnas se llaman como su método (`ventas_suma`), así que el archivo se
  explica sin la pantalla.
  """
  def csv(%Capa{id: id, columnas: columnas}) do
    filas =
      Repo.all(
        from f in CapaFila, where: f.capa_id == ^id, order_by: f.id, select: {f.clave, f.datos}
      )

    renglones =
      Enum.map(filas, fn {clave, datos} ->
        renglon_csv([clave | Enum.map(columnas, &datos[&1])])
      end)

    IO.iodata_to_binary(["\uFEFF", renglon_csv(["clave" | columnas]), renglones])
  end

  defp renglon_csv(celdas), do: [Enum.map_join(celdas, ",", &celda_csv/1), "\r\n"]

  defp celda_csv(nil), do: ""
  defp celda_csv(v) when is_float(v), do: :erlang.float_to_binary(v, [:compact, decimals: 6])
  defp celda_csv(v) when is_number(v), do: to_string(v)

  # Excel ejecuta como fórmula el texto que empieza con estos caracteres, y el
  # nombre de una columna viene del archivo de alguien del equipo.
  defp celda_csv(texto) do
    texto = if String.starts_with?(texto, ~w(= + - @ \t \r)), do: "'" <> texto, else: texto
    ~s("#{String.replace(texto, ~s("), ~s(""))}")
  end

  @doc "¿Puede el scope borrar esta capa?"
  def puede_borrar?(%Scope{} = scope, %Capa{} = capa) do
    case Teams.role_in_team(scope, capa.team_id) do
      nil -> false
      rol when rol in [:owner, :admin] -> true
      _ -> capa.user_id == scope.user.id
    end
  end

  @doc "Borra la capa y sus filas (en cascada)."
  def delete_capa(%Scope{} = scope, %Capa{} = capa) do
    true = puede_borrar?(scope, capa)
    Repo.delete(capa)
  end

  @doc "Puntos de la capa, solo id y lugar: los datos se piden al abrir la ficha."
  def puntos(%Capa{id: id}) do
    Repo.all(
      from f in CapaFila,
        where: f.capa_id == ^id,
        select: %{
          id: f.id,
          lat: fragment("ST_Y(?)", f.geom),
          lon: fragment("ST_X(?)", f.geom)
        }
    )
  end

  @doc """
  FeatureCollection de una capa vectorial, simplificada para dibujar. Cada
  feature lleva `id` y, si se pinta por `columna`, `valor_choropleth`.
  """
  def geojson(%Capa{id: id}, columna \\ nil) do
    filas =
      Repo.all(
        from f in CapaFila,
          where: f.capa_id == ^id,
          order_by: f.id,
          select:
            {f.id, f.datos,
             fragment(
               "ST_AsGeoJSON(ST_SimplifyPreserveTopology(?, ?), 6)",
               f.geom,
               ^@tolerancia_dibujo
             )}
      )

    features =
      Enum.map(filas, fn {id, datos, geometria} ->
        propiedades = if columna, do: %{id: id, valor_choropleth: datos[columna]}, else: %{id: id}

        %{
          "type" => "Feature",
          "properties" => propiedades,
          "geometry" => Jason.decode!(geometria)
        }
      end)

    %{"type" => "FeatureCollection", "features" => features}
  end

  @doc "La imagen de una capa ráster, o `nil` si no es de los equipos del scope."
  def raster(%Scope{} = scope, capa_id) do
    Repo.one(
      from r in CapaRaster,
        join: c in ^ids_del_scope(scope),
        on: c.id == r.capa_id,
        where: r.capa_id == ^capa_id
    )
  end

  @doc "Lo que el mapa necesita de un ráster, sin la imagen."
  def lugar_raster(%Capa{id: id}) do
    Repo.one(
      from r in CapaRaster,
        where: r.capa_id == ^id,
        select: %{
          oeste: r.oeste,
          sur: r.sur,
          este: r.este,
          norte: r.norte,
          limites: r.limites
        }
    )
  end

  @doc "Claves distintas de la capa."
  def claves(%Capa{id: id}) do
    Repo.all(from f in CapaFila, where: f.capa_id == ^id, distinct: true, select: f.clave)
  end

  @doc """
  `%{clave => valor}` de una columna numérica. Solo tiene sentido con una fila
  por clave; `pintable?/2` lo dice.
  """
  def valores(%Capa{id: id}, columna) do
    Repo.all(from f in CapaFila, where: f.capa_id == ^id, select: {f.clave, f.datos})
    |> Map.new(fn {clave, datos} -> {clave, datos[columna]} end)
  end

  @doc "Se pinta por una columna si es numérica y hay una fila por zona."
  def pintable?(%Capa{} = capa, columna) do
    capa.tipo in ~w(municipio ageb vector) and capa.repetidas == 0 and columna in capa.numericas
  end

  @doc """
  La fila que abre la ficha, por `id` (punto o geometría) o `clave` (zona). Pasa
  otra vez por la membresía: el id viene del navegador y a la persona pudieron
  sacarla del equipo con el mapa abierto. Regresa `{datos, cuantas}`.
  """
  def ficha(%Scope{} = scope, capa_id, llave) do
    consulta =
      from f in CapaFila,
        join: c in ^ids_del_scope(scope),
        on: c.id == f.capa_id,
        where: f.capa_id == ^capa_id,
        order_by: f.id,
        select: f.datos

    consulta =
      case llave do
        {:id, id} -> where(consulta, [f], f.id == ^id)
        {:clave, clave} -> where(consulta, [f], f.clave == ^clave)
      end

    case Repo.all(limit(consulta, 1)) do
      [] -> nil
      [datos] -> {datos, Repo.aggregate(exclude(consulta, :order_by), :count)}
    end
  end
end
