defmodule Mapo.SesionesFixtures do
  @moduledoc """
  This module defines test helpers for creating entities via the
  `Mapo.Sesiones` context.
  """

  @doc """
  Generate a sesion. `scope`'s user must already be a member of `team`.
  """
  def sesion_fixture(scope, team, attrs \\ %{}) do
    attrs = Enum.into(attrs, %{"nombre" => "sesion de prueba"})

    {:ok, sesion} = Mapo.Sesiones.create_sesion(scope, team.id, attrs)
    sesion
  end
end
