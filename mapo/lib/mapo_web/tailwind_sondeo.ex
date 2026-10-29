defmodule MapoWeb.TailwindSondeo do
  @moduledoc """
  Watcher de Tailwind para desarrollo en Docker Desktop.

  El código se monta en el contenedor por 9p, que no entrega eventos de
  inotify, así que `tailwind --watch` nunca se entera de los cambios.
  Este revisa el mtime de los archivos que lee Tailwind (los `@source`
  de `assets/css/app.css`) cada segundo y recompila cuando alguno
  cambia. Ver `docs/desarrollo.md`.
  """

  @rutas ~w(assets/css assets/js assets/vendor lib/mapo_web _build/dev/phoenix-colocated)
  @intervalo_ms 1_000

  def run(perfil) do
    Tailwind.install_and_run(perfil, [])
    vigilar(perfil, huella())
  end

  defp vigilar(perfil, anterior) do
    Process.sleep(@intervalo_ms)
    actual = huella()
    if actual != anterior, do: Tailwind.run(perfil, [])
    vigilar(perfil, actual)
  end

  defp huella do
    for ruta <- @rutas,
        archivo <- Path.wildcard(ruta <> "/**/*.*"),
        {:ok, %{mtime: mtime}} <- [File.stat(archivo, time: :posix)],
        do: {archivo, mtime}
  end
end
