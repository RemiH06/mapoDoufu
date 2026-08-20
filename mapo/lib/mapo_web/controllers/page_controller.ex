defmodule MapoWeb.PageController do
  use MapoWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
