defmodule Mapo.Repo do
  use Ecto.Repo,
    otp_app: :mapo,
    adapter: Ecto.Adapters.Postgres
end
