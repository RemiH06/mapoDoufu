defmodule MapoWeb.DatosLive.RasterTest do
  use MapoWeb.ConnCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Mapo.RasterFixtures
  import Phoenix.LiveViewTest

  alias Mapo.Capas

  setup :register_and_log_in_user

  setup %{scope: scope} do
    team = team_fixture(scope)

    {:ok, escuelas} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "Escuelas",
          archivo: "e.gpkg",
          tamano_bytes: 100,
          tipo: "puntos",
          columnas: ["nombre"],
          numericas: [],
          num_filas: 1,
          num_descartadas: 0
        },
        [%{"lat" => 19.995, "lon" => -103.995, "datos" => %{"nombre" => "Primaria"}}]
      )

    cobertura =
      capa_raster(scope, team.id, "WorldCover", [tesela([[40, 50], [40, 40]], -104.0, 20.0, 0.01)])

    %{team: team, escuelas: escuelas, cobertura: cobertura}
  end

  test "lee el píxel, la parte de una clase y guarda la capa", ctx do
    {:ok, lista, _} = live(ctx.conn, ~p"/teams/#{ctx.team}/datos")
    assert has_element?(lista, "a[href='/teams/#{ctx.team.id}/datos/#{ctx.escuelas.id}/raster']")

    {:ok, lv, html} = live(ctx.conn, ~p"/teams/#{ctx.team}/datos/#{ctx.escuelas}/raster")
    assert html =~ "Ráster en Escuelas"

    html =
      lv
      |> form("#raster_form", raster: %{raster: to_string(ctx.cobertura.id)})
      |> render_submit()

    assert html =~ "worldcover_valor"
    assert html =~ "1 de 1 con valor"

    html =
      lv
      |> form("#raster_form", raster: %{radio: "1500", valores: "40"})
      |> render_submit()

    assert html =~ "worldcover_parte_40"
    assert html =~ "valor 40"

    lv |> form("#guardar_form", guardado: %{nombre: "Cultivo cerca"}) |> render_submit()
    {path, flash} = assert_redirect(lv)
    assert path == ~p"/teams/#{ctx.team}/datos"
    assert flash["info"] =~ "Valores guardados"
  end

  test "sin rásteres con valores lo dice y la lista no ofrece el botón", %{
    conn: conn,
    scope: scope
  } do
    team = team_fixture(scope)

    {:ok, puntos} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "P",
          archivo: "p.csv",
          tamano_bytes: 1,
          tipo: "puntos",
          columnas: ["a"],
          numericas: [],
          num_filas: 1,
          num_descartadas: 0
        },
        [%{"lat" => 20.0, "lon" => -104.0, "datos" => %{"a" => "x"}}]
      )

    {:ok, lista, _} = live(conn, ~p"/teams/#{team}/datos")
    refute has_element?(lista, "a[href$='/raster']")

    {:ok, _lv, html} = live(conn, ~p"/teams/#{team}/datos/#{puntos}/raster")
    assert html =~ "no tiene ningún ráster con valores"
  end

  test "una capa ajena no se abre", %{conn: conn, team: team} do
    otro = user_scope_fixture()
    ajena = capa_raster(otro, team_fixture(otro).id, "Ajena", [tesela([[1]], -104.0, 20.0, 0.01)])

    assert {:error,
            {:live_redirect, %{flash: %{"error" => "Desde esa capa no se puede leer" <> _}}}} =
             live(conn, ~p"/teams/#{team}/datos/#{ajena}/raster")
  end
end
