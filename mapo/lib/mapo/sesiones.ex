defmodule Mapo.Sesiones do
  @moduledoc """
  El contexto de Sesiones: mapas colaborativos de un equipo, con
  anotaciones geometricas en tiempo real (via PostGIS + PubSub). Ver
  MAPO_FUNDAMENTOS.md, seccion de base de datos, para el porque de
  PostGIS especificamente para esto.

  Autorizacion: cualquier miembro del equipo (cualquier rol) puede ver,
  anotar, editar y borrar anotaciones de una sesion. No hay niveles
  distintos aqui todavia (a diferencia de Teams, donde editar/borrar el
  equipo si distingue owner/admin/member): es un pizarron compartido
  del equipo, no algo con dueno individual por anotacion.
  """

  import Ecto.Query, warn: false
  alias Mapo.Repo
  alias Mapo.Accounts.Scope
  alias Mapo.Teams
  alias Mapo.Teams.Membership
  alias Mapo.Sesiones.{Sesion, Anotacion}

  @doc "Sesiones de un equipo. Requiere que el scope sea miembro de ese equipo."
  def list_sesiones(%Scope{} = scope, team_id) do
    true = Teams.role_in_team(scope, team_id) != nil

    Repo.all(from s in Sesion, where: s.team_id == ^team_id, order_by: s.inserted_at)
  end

  @doc """
  Trae una sesion. Requiere que el scope sea miembro del equipo dueno.

  Una sola consulta (join contra la membresia), a proposito: si se
  buscara la sesion primero y la autorizacion aparte, alguien sin
  acceso podria distinguir "no existe" de "existe pero no es tuya" por
  el tipo de error. Con el join, ambos casos regresan
  `Ecto.NoResultsError` por igual.
  """
  def get_sesion!(%Scope{} = scope, id) do
    Repo.one!(
      from s in Sesion,
        join: m in Membership,
        on: m.team_id == s.team_id,
        where: s.id == ^id and m.user_id == ^scope.user.id,
        select: s
    )
  end

  @doc "Crea una sesion dentro de un equipo. Requiere ser miembro de ese equipo."
  def create_sesion(%Scope{} = scope, team_id, attrs) do
    true = Teams.role_in_team(scope, team_id) != nil

    %Sesion{}
    |> Sesion.changeset(Map.put(attrs, "team_id", team_id))
    |> Repo.insert()
  end

  @doc "Anotaciones de una sesion, mas antigua primero, con quien las creo precargado."
  def list_anotaciones(sesion_id) do
    Repo.all(from a in Anotacion, where: a.sesion_id == ^sesion_id, order_by: a.inserted_at)
    |> Repo.preload(:user)
  end

  @topic_prefix "sesion:"

  @doc """
  Nombre del topico de PubSub de una sesion. Se comparte entre los
  broadcasts de anotaciones de este modulo y el tracking de presencia
  (`MapoWeb.Presence`) en `SesionLive.Show`: no hay razon para tener
  dos canales separados para "quien esta viendo" y "que esta pasando".
  """
  def topico_sesion(sesion_id), do: @topic_prefix <> to_string(sesion_id)

  def subscribe_sesion(sesion_id) do
    Phoenix.PubSub.subscribe(Mapo.PubSub, topico_sesion(sesion_id))
  end

  defp broadcast_sesion(sesion_id, mensaje) do
    Phoenix.PubSub.broadcast(Mapo.PubSub, topico_sesion(sesion_id), mensaje)
  end

  @doc """
  Crea una anotacion en `lat`/`lon` y la transmite en vivo a todos los
  que esten viendo la misma sesion (incluido quien la crea). Requiere
  que el scope sea miembro del equipo dueno de la sesion.
  """
  def create_anotacion(%Scope{} = scope, %Sesion{} = sesion, lat, lon, texto) do
    true = Teams.role_in_team(scope, sesion.team_id) != nil

    attrs = %{
      "texto" => texto,
      "geom" => %Geo.Point{coordinates: {lon, lat}, srid: 4326},
      "sesion_id" => sesion.id,
      "user_id" => scope.user.id
    }

    with {:ok, anotacion} <- %Anotacion{} |> Anotacion.changeset(attrs) |> Repo.insert() do
      anotacion = Repo.preload(anotacion, :user)
      broadcast_sesion(sesion.id, {:anotacion_creada, anotacion})
      {:ok, anotacion}
    end
  end

  @doc "Trae una anotacion por id. No valida pertenencia a ninguna sesion: eso lo hacen update/delete."
  def get_anotacion!(id), do: Repo.get!(Anotacion, id)

  @doc """
  Cambia el texto de una anotacion existente y transmite el cambio en
  vivo. Requiere que el scope sea miembro del equipo dueno, y que la
  anotacion de verdad pertenezca a `sesion` (no a otra sesion cuyo id
  alguien haya adivinado).
  """
  def update_anotacion(%Scope{} = scope, %Sesion{} = sesion, %Anotacion{} = anotacion, texto) do
    true = Teams.role_in_team(scope, sesion.team_id) != nil
    true = anotacion.sesion_id == sesion.id

    with {:ok, anotacion} <-
           anotacion |> Anotacion.changeset(%{"texto" => texto}) |> Repo.update() do
      anotacion = Repo.preload(anotacion, :user)
      broadcast_sesion(sesion.id, {:anotacion_actualizada, anotacion})
      {:ok, anotacion}
    end
  end

  @doc """
  Borra una anotacion y transmite el borrado en vivo. Mismas
  validaciones que `update_anotacion/4`.
  """
  def delete_anotacion(%Scope{} = scope, %Sesion{} = sesion, %Anotacion{} = anotacion) do
    true = Teams.role_in_team(scope, sesion.team_id) != nil
    true = anotacion.sesion_id == sesion.id

    with {:ok, anotacion} <- Repo.delete(anotacion) do
      broadcast_sesion(sesion.id, {:anotacion_borrada, anotacion.id})
      {:ok, anotacion}
    end
  end
end
