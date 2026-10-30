defmodule MapoWeb.CifrasTest do
  use ExUnit.Case, async: true

  import MapoWeb.Cifras

  doctest MapoWeb.Cifras

  test "negative numbers keep the sign outside the thousands" do
    assert cifra(-123) == "-123"
    assert cifra(-1234.5) == "-1,234.5"
  end

  test "integers ask for decimals explicitly" do
    assert cifra(632, 2) == "632.00"
  end
end
