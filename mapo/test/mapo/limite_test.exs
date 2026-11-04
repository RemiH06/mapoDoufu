defmodule Mapo.LimiteTest do
  use ExUnit.Case, async: true

  alias Mapo.Limite

  test "permite hasta el máximo y corta después" do
    clave = {:prueba, make_ref()}

    assert Enum.map(1..4, fn _ -> Limite.permitir?(clave, 3, 3600) end) ==
             [true, true, true, false]
  end

  test "las claves no se estorban entre sí" do
    a = {:prueba, make_ref()}
    b = {:prueba, make_ref()}

    refute Enum.all?(1..2, fn _ -> Limite.permitir?(a, 1, 3600) end)
    assert Limite.permitir?(b, 1, 3600)
  end

  test "la limpieza borra ventanas terminadas y deja la vigente" do
    clave = {:prueba, make_ref()}
    assert Limite.permitir?(clave, 1, 3600)

    Limite.limpiar(0)
    refute Limite.permitir?(clave, 1, 3600)

    Limite.limpiar(System.system_time(:second) + 7200)
    assert Limite.permitir?(clave, 1, 3600)
  end
end
