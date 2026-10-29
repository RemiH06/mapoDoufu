defmodule MapoWeb.PageController do
  use MapoWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end

  def a_mapa(conn, _params) do
    redirect(conn, to: ~p"/mapa")
  end
end
