# render_async y assert_receive esperan esto; los 100 ms por defecto fallaban
# a veces con la máquina cargada, sobre el montaje lento de Docker.
ExUnit.start(assert_receive_timeout: 1000)
Ecto.Adapters.SQL.Sandbox.mode(Mapo.Repo, :manual)
