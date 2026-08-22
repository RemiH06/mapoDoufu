defmodule Mapo.Teams.TeamNotifier do
  import Swoosh.Email

  alias Mapo.Mailer

  defp deliver(recipient, subject, body) do
    email =
      new()
      |> to(recipient)
      |> from({"Mapo", "contact@example.com"})
      |> subject(subject)
      |> text_body(body)

    with {:ok, _metadata} <- Mailer.deliver(email) do
      {:ok, email}
    end
  end

  @doc """
  Invita por correo a alguien a un equipo, tenga o no cuenta en Mapo
  todavia.
  """
  def deliver_invitacion(invitacion, team, url) do
    deliver(invitacion.email, "Te invitaron a un equipo en Mapo", """

    ==============================

    Hola,

    Te invitaron a unirte al equipo "#{team.name}" en Mapo.

    Para aceptar, visita el siguiente enlace:

    #{url}

    Si no esperabas esta invitacion, puedes ignorar este correo.

    ==============================
    """)
  end
end
