defmodule Mapo.Limite do
  @moduledoc """
  Límite de intentos por clave en ventanas fijas de tiempo, en memoria (ETS).

  Es la barrera real del login: la regla de Cloudflare del plan gratis solo
  cuenta por IP en ventanas de 10 s, no ve el enlace mágico (va por el
  WebSocket) y no cubre la entrada por la tailnet (docs/despliegue.md).

  Mapo corre en un solo nodo, así que basta con memoria. Al reiniciar, los
  contadores vuelven a cero, y eso no importa: un atacante no puede reiniciar
  el servidor.
  """

  use GenServer

  @tabla :mapo_limite
  @limpieza :timer.hours(1)

  def start_link(_opts), do: GenServer.start_link(__MODULE__, nil, name: __MODULE__)

  @doc """
  Cuenta un intento y dice si cabe: `true` mientras haya `max` o menos en la
  ventana de `segundos` en curso. Cuenta también los que ya no caben.
  """
  def permitir?(clave, max, segundos) do
    ventana = div(System.system_time(:second), segundos)
    llave = {clave, segundos, ventana}
    :ets.update_counter(@tabla, llave, 1, {llave, 0}) <= max
  end

  @impl true
  def init(nil) do
    :ets.new(@tabla, [:named_table, :public, :set, write_concurrency: true])
    programar_limpieza()
    {:ok, nil}
  end

  @impl true
  def handle_info(:limpiar, estado) do
    limpiar(System.system_time(:second))
    programar_limpieza()
    {:noreply, estado}
  end

  @doc false
  # Borra las ventanas ya terminadas: (ventana + 1) * segundos < ahora.
  def limpiar(ahora) do
    fin = {:*, {:+, :"$2", 1}, :"$1"}
    :ets.select_delete(@tabla, [{{{:_, :"$1", :"$2"}, :_}, [{:<, fin, ahora}], [true]}])
  end

  defp programar_limpieza, do: Process.send_after(self(), :limpiar, @limpieza)
end
