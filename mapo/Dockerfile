FROM elixir:1.17-slim
WORKDIR /app

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends ca-certificates git inotify-tools build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN mix local.hex --force && mix local.rebar --force

COPY mix.exs ./
RUN mix deps.get

COPY . .

EXPOSE 4000
CMD ["mix", "phx.server"]
