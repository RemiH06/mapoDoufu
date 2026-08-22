# This file is responsible for configuring your application
# and its dependencies with the aid of the Config module.
#
# This configuration file is loaded before any dependency and
# is restricted to this project.

# General application configuration
import Config

config :mapo, :scopes,
  user: [
    default: true,
    module: Mapo.Accounts.Scope,
    assign_key: :current_scope,
    access_path: [:user, :id],
    schema_key: :user_id,
    schema_type: :id,
    schema_table: :users,
    test_data_fixture: Mapo.AccountsFixtures,
    test_setup_helper: :register_and_log_in_user
  ]

config :mapo,
  ecto_repos: [Mapo.Repo],
  generators: [timestamp_type: :utc_datetime]

# mapo_core es el motor de datos/decision (Python); mapo le pega por
# HTTP. `mapo_core_req_options` deja inyectar un `plug:` de Req.Test en
# los tests, sin pegarle nunca a la red de verdad.
config :mapo, :mapo_core_url, System.get_env("MAPO_CORE_URL", "http://localhost:8010")
config :mapo, :mapo_core_req_options, []

# Le enseña a Postgrex los tipos de geometria de PostGIS (Geo.Point,
# etc.), para las anotaciones de las sesiones colaborativas.
config :mapo, Mapo.Repo, types: Mapo.PostgresTypes

# Configure the endpoint
config :mapo, MapoWeb.Endpoint,
  url: [host: "localhost"],
  adapter: Bandit.PhoenixAdapter,
  render_errors: [
    formats: [html: MapoWeb.ErrorHTML, json: MapoWeb.ErrorJSON],
    layout: false
  ],
  pubsub_server: Mapo.PubSub,
  live_view: [signing_salt: "/hWJP7g1"]

# Configure LiveView
config :phoenix_live_view,
  # the attribute set on all root tags. Used for Phoenix.LiveView.ColocatedCSS.
  root_tag_attribute: "phx-r"

# Configure the mailer
#
# By default it uses the "Local" adapter which stores the emails
# locally. You can see the emails in your browser, at "/dev/mailbox".
#
# For production it's recommended to configure a different adapter
# at the `config/runtime.exs`.
config :mapo, Mapo.Mailer, adapter: Swoosh.Adapters.Local

# Configure esbuild (the version is required)
config :esbuild,
  version: "0.25.4",
  mapo: [
    args:
      ~w(js/app.js --bundle --target=es2022 --outdir=../priv/static/assets/js --external:/fonts/* --external:/images/* --alias:@=.),
    cd: Path.expand("../assets", __DIR__),
    env: %{"NODE_PATH" => [Path.expand("../deps", __DIR__), Mix.Project.build_path()]}
  ]

# Configure tailwind (the version is required)
config :tailwind,
  version: "4.3.0",
  mapo: [
    args: ~w(
      --input=assets/css/app.css
      --output=priv/static/assets/css/app.css
    ),
    cd: Path.expand("..", __DIR__),
    env: %{"NODE_PATH" => [Path.expand("../deps", __DIR__), Mix.Project.build_path()]}
  ]

# Configure Elixir's Logger
config :logger, :default_formatter,
  format: "$time $metadata[$level] $message\n",
  metadata: [:request_id]

# Use Jason for JSON parsing in Phoenix
config :phoenix, :json_library, Jason

# Mapo es en espanol mexicano unicamente (RNF1), sin soporte bilingue
config :gettext, :default_locale, "es"

# Import environment specific config. This must remain at the bottom
# of this file so it overrides the configuration defined above.
import_config "#{config_env()}.exs"
