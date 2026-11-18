defmodule MapoWeb.DatosLive.DistanciaTest do
  use MapoWeb.ConnCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Phoenix.LiveViewTest

  alias Mapo.Capas

  setup :register_and_log_in_user

  defp capa(scope, team, nombre, columnas, filas) do
    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: nombre,
          archivo: "#{nombre}.gpkg",
          tamano_bytes: 100,
          tipo: "puntos",
          columnas: columnas,
          numericas: [],
          num_filas: length(filas),
          num_descartadas: 0
        },
        filas
      )

    capa
  end

  setup %{scope: scope} do
    team = team_fixture(scope)

    escuelas =
      capa(scope, team, "Escuelas", ["nombre", "clase"], [
        %{
          "lat" => 20.0,
          "lon" => -104.0,
          "datos" => %{"nombre" => "Primaria", "clase" => "Escuelas"}
        }
      ])

    pozos =
      capa(scope, team, "Pozos", ["titulo", "fuente"], [
        %{"lat" => 20.0, "lon" => -103.998, "datos" => %{"titulo" => "P-1", "fuente" => "REPDA"}},
        %{"lat" => 20.5, "lon" => -104.0, "datos" => %{"titulo" => "P-2", "fuente" => "REPDA"}}
      ])

    %{team: team, escuelas: escuelas, pozos: pozos}
  end

  test "mide, muestra el más cercano y guarda la capa", ctx do
    {:ok, lv, html} = live(ctx.conn, ~p"/teams/#{ctx.team}/datos/#{ctx.escuelas}/distancia")
    assert html =~ "Distancia desde Escuelas"

    html =
      lv
      |> form("#distancia_form",
        distancia: %{
          destino: to_string(ctx.pozos.id),
          etiqueta_origen: "nombre",
          etiqueta_destino: "titulo",
          filtro_origen: %{"0" => %{columna: "clase", texto: "escuela"}},
          radio: "500"
        }
      )
      |> render_submit()

    assert html =~ "1 de 1 a 500 m o menos"
    assert html =~ "P-1"
    assert html =~ "pozos_fuente: fuente de ese renglón más cercano."
    assert html =~ "solo donde clase contiene «escuela»"

    lv |> form("#guardar_form", guardado: %{nombre: "Escuelas y pozos"}) |> render_submit()
    {path, flash} = assert_redirect(lv)
    assert path == ~p"/teams/#{ctx.team}/datos"
    assert flash["info"] =~ "Distancias guardadas"

    [guardada] =
      Enum.filter(Capas.list_capas(ctx.scope, ctx.team.id), &(&1.nombre == "Escuelas y pozos"))

    csv = Capas.csv(guardada)

    assert csv =~
             ~s("lat","lon","nombre","clase","distancia_m_pozos","pozos_titulo","pozos_fuente","pozos_a_500m")

    assert csv =~ ~s(20.0,-104.0,"Primaria","Escuelas",209,"P-1","REPDA",1)
  end

  test "un radio que no es número entero se dice", ctx do
    {:ok, lv, _} = live(ctx.conn, ~p"/teams/#{ctx.team}/datos/#{ctx.escuelas}/distancia")

    html =
      lv
      |> form("#distancia_form", distancia: %{destino: to_string(ctx.pozos.id), radio: "3.5"})
      |> render_submit()

    assert html =~ "El radio va de 1 a 100,000 metros"
  end

  test "la capa de otro equipo no se abre", %{conn: conn, team: team} do
    otro = user_scope_fixture()

    ajena =
      capa(otro, team_fixture(otro), "Ajena", ["a"], [
        %{"lat" => 20.0, "lon" => -104.0, "datos" => %{"a" => "1"}}
      ])

    assert {:error, {:live_redirect, %{flash: %{"error" => "Desde esa capa no se puede medir."}}}} =
             live(conn, ~p"/teams/#{team}/datos/#{ajena}/distancia")
  end
end
