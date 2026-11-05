defmodule MapoWeb.DatosLive.CruceTest do
  use MapoWeb.ConnCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Phoenix.LiveViewTest

  alias Mapo.Capas

  setup :register_and_log_in_user

  @catalogo %{
    "sectores" => [
      %{
        "sector" => "comida",
        "nombre" => "Comida",
        "rubros" => [%{"rubro" => "taqueria", "nombre" => "Taquería"}]
      }
    ]
  }

  @resultado %{
    "nivel" => "ageb",
    "columnas" => ["municipio", "ageb", "renglones", "ventas_suma", "pobtot"],
    "numericas" => ["renglones", "ventas_suma", "pobtot"],
    "filas" => [
      %{
        "clave" => "1412000010001",
        "datos" => %{
          "municipio" => "Zapopan",
          "ageb" => "0001",
          "renglones" => 2,
          "ventas_suma" => 1500,
          "pobtot" => 800
        }
      },
      %{
        "clave" => "1412000010002",
        "datos" => %{
          "municipio" => "Zapopan",
          "ageb" => "0002",
          "renglones" => 0,
          "ventas_suma" => nil,
          "pobtot" => nil
        }
      }
    ],
    "renglones" => 2,
    "sin_zona" => 1,
    "zonas_con_renglones" => 1,
    "metodo" => ["renglones: cuántos.", "ventas_suma: suma de ventas."],
    "avisos" => ["1 renglones no cayeron en ningún AGEB urbano."]
  }

  setup %{scope: scope} do
    team = team_fixture(scope)

    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "Ventas",
          archivo: "ventas.csv",
          tamano_bytes: 100,
          tipo: "puntos",
          columnas: ["lat", "lon", "a[b]", "ventas"],
          numericas: ["a[b]", "ventas"],
          num_filas: 1,
          num_descartadas: 0
        },
        [
          %{
            "lat" => 20.6,
            "lon" => -103.3,
            "datos" => %{"a[b]" => 1, "ventas" => 750, "n" => "x"}
          }
        ]
      )

    %{team: team, capa: capa}
  end

  defp stub(respuesta \\ @resultado) do
    prueba = self()

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/buscador/catalogo" ->
          Req.Test.json(conn, @catalogo)

        "/cruce/calcular" ->
          {:ok, cuerpo, conn} = Plug.Conn.read_body(conn, length: 1_000_000)
          send(prueba, {:cruce, Jason.decode!(cuerpo)})

          case respuesta do
            {status, json} -> conn |> Plug.Conn.put_status(status) |> Req.Test.json(json)
            json -> Req.Test.json(conn, json)
          end
      end
    end)
  end

  defp cruzar(lv, params \\ %{}) do
    base = %{nivel: "ageb", agregacion: %{"1" => "suma"}, censo: ["", "pobtot"], denue: ""}
    lv |> form("#cruce_form", cruce: Map.merge(base, params)) |> render_submit()
  end

  test "manda solo lo elegido, por posición de columna", %{conn: conn, team: team, capa: capa} do
    stub()
    {:ok, lv, html} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")
    assert html =~ "Taquería"

    html = cruzar(lv)
    assert_received {:cruce, solicitud}

    assert solicitud["tipo"] == "puntos"
    assert solicitud["nivel"] == "ageb"
    assert solicitud["agregaciones"] == %{"ventas" => "suma"}
    assert solicitud["censo"] == ["pobtot"]
    assert solicitud["denue"] == nil
    assert solicitud["minutos"] == false

    assert [%{"lat" => 20.6, "lon" => -103.3, "valores" => valores}] = solicitud["filas"]
    assert valores == %{"ventas" => 750}, "lo que no se agrega no sale de la base"

    assert html =~ "1 de 2 zonas con renglones"
    assert html =~ "1,500"
    assert html =~ "sin dato"
    assert html =~ "no cayeron"
    assert html =~ "suma de ventas"
  end

  test "los minutos solo aparecen con AGEB y un rubro", %{conn: conn, team: team, capa: capa} do
    stub()
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")
    refute has_element?(lv, "#cruce_minutos")

    lv |> form("#cruce_form", cruce: %{denue: "taqueria"}) |> render_change()
    assert has_element?(lv, "#cruce_minutos")

    lv |> form("#cruce_form", cruce: %{nivel: "municipio"}) |> render_change()
    refute has_element?(lv, "#cruce_minutos")
  end

  test "guarda el resultado como capa pintable y con método",
       %{conn: conn, team: team, capa: capa, scope: scope} do
    stub()
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")
    cruzar(lv)

    lv
    |> form("#guardar_form", guardado: %{nombre: "Ventas por AGEB"})
    |> render_submit()

    assert_redirect(lv, ~p"/teams/#{team}/datos")

    nueva = Enum.find(Capas.list_capas(scope, team.id), &(&1.nombre == "Ventas por AGEB"))
    assert nueva.tipo == "ageb"
    assert nueva.num_filas == 2
    assert nueva.archivo == "Ventas"
    assert nueva.metodo =~ "suma de ventas"
    assert Capas.pintable?(nueva, "ventas_suma")
    assert Capas.valores(nueva, "ventas_suma")["1412000010001"] == 1500
  end

  test "cambiar el formulario quita el resultado", %{conn: conn, team: team, capa: capa} do
    stub()
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")
    cruzar(lv)
    assert has_element?(lv, "#guardar_form")

    lv |> form("#cruce_form", cruce: %{nivel: "municipio"}) |> render_change()
    refute has_element?(lv, "#guardar_form")
  end

  test "el motivo de rechazo llega tal cual", %{conn: conn, team: team, capa: capa} do
    stub({422, %{"detail" => "Ningún renglón cae en una zona."}})
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")

    assert cruzar(lv) =~ "Ningún renglón cae en una zona."
    refute has_element?(lv, "#guardar_form")
  end

  test "una capa ajena no se abre", %{conn: conn, team: team} do
    stub()
    otro = user_scope_fixture()
    ajeno = team_fixture(otro)

    {:ok, capa} =
      Capas.crear_capa(
        otro,
        ajeno.id,
        %{
          nombre: "Ajena",
          archivo: "a.csv",
          tamano_bytes: 1,
          tipo: "puntos",
          columnas: [],
          num_filas: 0,
          num_descartadas: 0
        },
        []
      )

    assert {:error, {:live_redirect, %{to: destino}}} =
             live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")

    assert destino == ~p"/teams/#{team}/datos"
  end

  test "una capa con geometrías no se cruza", %{conn: conn, team: team, scope: scope} do
    stub()

    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "Polígonos",
          archivo: "a.geojson",
          tamano_bytes: 1,
          tipo: "vector",
          columnas: [],
          num_filas: 0,
          num_descartadas: 0
        },
        []
      )

    assert {:error, {:live_redirect, _}} = live(conn, ~p"/teams/#{team}/datos/#{capa}/cruce")
  end

  describe "CSV" do
    setup %{scope: scope, capa: capa} do
      resultado =
        Map.merge(@resultado, %{
          "columnas" => ["municipio", "=peligro_suma", "precio_promedio"],
          "numericas" => ["=peligro_suma", "precio_promedio"],
          "filas" => [
            %{
              "clave" => "14120",
              "datos" => %{
                "municipio" => ~s(Tlajo "Viejo", Jal.),
                "=peligro_suma" => 3,
                "precio_promedio" => 12.5
              }
            },
            %{
              "clave" => "14101",
              "datos" => %{
                "municipio" => "Tonalá",
                "=peligro_suma" => nil,
                "precio_promedio" => nil
              }
            }
          ]
        })

      {:ok, cruce} = Capas.crear_cruce(scope, capa, "Cruce", resultado)
      %{cruce: cruce}
    end

    test "sale con BOM, comillas y fórmulas neutralizadas", %{conn: conn, cruce: cruce} do
      conn = get(conn, ~p"/capas/#{cruce}/cruce.csv")

      assert response_content_type(conn, :csv)
      assert get_resp_header(conn, "content-disposition") |> hd() =~ "Cruce.csv"

      assert response(conn, 200) ==
               "﻿" <>
                 ~s("clave","municipio","'=peligro_suma","precio_promedio"\r\n) <>
                 ~s("14120","Tlajo ""Viejo"", Jal.",3,12.5\r\n) <>
                 ~s("14101","Tonalá",,\r\n)
    end

    test "una capa normal no se baja", %{conn: conn, capa: capa} do
      assert conn |> get(~p"/capas/#{capa}/cruce.csv") |> response(404)
    end

    test "un id que no es número da 404", %{conn: conn} do
      assert conn |> get("/capas/abc/cruce.csv") |> response(404)
    end

    test "quien no es del equipo no la baja", %{cruce: cruce} do
      otra = log_in_user(build_conn(), user_fixture())
      assert otra |> get(~p"/capas/#{cruce}/cruce.csv") |> response(404)
    end
  end
end
