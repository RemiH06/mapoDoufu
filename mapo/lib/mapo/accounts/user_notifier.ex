defmodule Mapo.Accounts.UserNotifier do
  import Swoosh.Email

  alias Mapo.Mailer
  alias Mapo.Accounts.User

  # Delivers the email using the application mailer.
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
  Deliver instructions to update a user email.
  """
  def deliver_update_email_instructions(user, url) do
    deliver(user.email, "Instrucciones para cambiar tu correo", """

    ==============================

    Hola #{user.email},

    Puedes cambiar tu correo visitando el siguiente enlace:

    #{url}

    Si tú no pediste este cambio, puedes ignorar este mensaje.

    ==============================
    """)
  end

  @doc """
  Deliver instructions to log in with a magic link.
  """
  def deliver_login_instructions(user, url) do
    case user do
      %User{confirmed_at: nil} -> deliver_confirmation_instructions(user, url)
      _ -> deliver_magic_link_instructions(user, url)
    end
  end

  defp deliver_magic_link_instructions(user, url) do
    deliver(user.email, "Instrucciones para iniciar sesión", """

    ==============================

    Hola #{user.email},

    Puedes iniciar sesión en tu cuenta visitando el siguiente enlace:

    #{url}

    Si tú no pediste este correo, puedes ignorar este mensaje.

    ==============================
    """)
  end

  defp deliver_confirmation_instructions(user, url) do
    deliver(user.email, "Instrucciones de confirmación", """

    ==============================

    Hola #{user.email},

    Puedes confirmar tu cuenta visitando el siguiente enlace:

    #{url}

    Si tú no creaste una cuenta con nosotros, puedes ignorar este mensaje.

    ==============================
    """)
  end
end
