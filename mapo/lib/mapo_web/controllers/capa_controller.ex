defmodule MapoWeb.CapaController do
  use MapoWeb, :controller

  alias Mapo.Capas

  @doc """
  La imagen de una capa ráster. Va por HTTP y no por el WebSocket porque pesa
  megas; pasa por el mismo scope que el resto de la capa.
  """
  def raster(conn, %{"id" => id}) do
    capa_id = entero(id)

    case capa_id && Capas.raster(conn.assigns.current_scope, capa_id) do
      nil ->
        send_resp(conn, 404, "")

      raster ->
        conn
        |> put_resp_content_type("image/png", nil)
        |> put_resp_header("cache-control", "private, max-age=3600")
        |> send_resp(200, raster.png)
    end
  end

  @doc "El resultado de un cruce. Solo los cruces: el original ya lo tiene el equipo."
  def csv(conn, %{"id" => id}) do
    capa_id = entero(id)

    case capa_id && Capas.get_capa(conn.assigns.current_scope, capa_id) do
      %{metodo: metodo} = capa when is_binary(metodo) ->
        send_download(conn, {:binary, Capas.csv(capa)},
          filename: "#{capa.nombre}.csv",
          content_type: "text/csv"
        )

      _ ->
        send_resp(conn, 404, "")
    end
  end

  defp entero(texto) do
    case Integer.parse(texto) do
      {n, ""} -> n
      _ -> nil
    end
  end
end
