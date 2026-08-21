defmodule MapoWeb.Presence do
  @moduledoc """
  Quien esta viendo una sesion colaborativa ahorita mismo. Se usa en
  `SesionLive.Show`: el proceso de la LiveView se registra al montar
  (conectado) y Phoenix.Presence lo da de baja solo si esa LiveView
  termina (se cierra la pestana, se navega a otro lado), sin limpieza
  manual de nuestro lado.
  """

  use Phoenix.Presence,
    otp_app: :mapo,
    pubsub_server: Mapo.PubSub
end
