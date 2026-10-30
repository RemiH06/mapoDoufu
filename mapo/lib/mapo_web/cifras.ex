defmodule MapoWeb.Cifras do
  @moduledoc """
  Cifras para leer en pantalla: separador de miles con coma y punto
  decimal, como se escriben en México.
  """

  @doc """
  Un entero va tal cual y un flotante con un decimal, salvo que se pida
  otra cantidad de decimales.

      iex> MapoWeb.Cifras.cifra(1385629)
      "1,385,629"
      iex> MapoWeb.Cifras.cifra(632.0584, 2)
      "632.06"
  """
  def cifra(v) when is_integer(v), do: v |> Integer.to_string() |> miles()
  def cifra(v) when is_float(v), do: cifra(v, 1)
  def cifra(v), do: to_string(v)

  def cifra(v, decimales) when is_number(v),
    do: (v / 1) |> :erlang.float_to_binary(decimals: decimales) |> miles()

  defp miles(texto) do
    {signo, texto} =
      case texto do
        "-" <> resto -> {"-", resto}
        resto -> {"", resto}
      end

    [entero | decimales] = String.split(texto, ".")

    entero =
      entero
      |> String.reverse()
      |> String.graphemes()
      |> Enum.chunk_every(3)
      |> Enum.join(",")
      |> String.reverse()

    signo <> Enum.join([entero | decimales], ".")
  end
end
