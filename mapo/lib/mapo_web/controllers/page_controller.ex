defmodule MapoWeb.PageController do
  use MapoWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end

  def privacidad(conn, _params) do
    render(conn, :privacidad,
      page_title: "Aviso de privacidad",
      contacto: Application.get_env(:mapo, :contacto_privacidad),
      osrm_propio: Application.get_env(:mapo, :osrm_propio, false)
    )
  end

  def a_mapa(conn, _params) do
    redirect(conn, to: ~p"/mapa")
  end
end
