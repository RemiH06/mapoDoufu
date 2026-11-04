defmodule MapoWeb.DatosLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures
  import Phoenix.LiveViewTest

  alias Mapo.Capas

  setup :register_and_log_in_user

  setup %{scope: scope} do
    %{team: team_fixture(scope)}
  end

  @lectura %{
    "columnas" => ["lat", "lon", "<b>ventas</b>"],
    "muestra" => [["20.6", "-103.3", "<script>x</script>"]],
    "num_filas" => 2,
    "avisos" => ["Solo se leyó la primera hoja"],
    "sugerencia" => %{"tipo" => "puntos", "lat" => "lat", "lon" => "lon"}
  }

  @ubicados %{
    "tipo" => "puntos",
    "filas" => [%{"lat" => 20.6, "lon" => -103.3, "clave" => nil, "datos" => %{"lat" => 20.6}}],
    "descartes" => %{"sin_dato" => 0, "no_es_numero" => 0, "fuera_de_mexico" => 1},
    "numericas" => ["lat"],
    "repetidas" => 0,
    "columnas" => ["lat", "lon", "<b>ventas</b>"],
    "num_filas" => 2,
    "avisos" => []
  }

  defp stub(respuestas \\ %{}) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/datos/leer" -> responder(conn, respuestas[:leer] || @lectura)
        "/datos/ubicar" -> responder(conn, respuestas[:ubicar] || @ubicados)
      end
    end)
  end

  defp responder(conn, {status, cuerpo}),
    do: conn |> Plug.Conn.put_status(status) |> Req.Test.json(cuerpo)

  defp responder(conn, cuerpo), do: Req.Test.json(conn, cuerpo)

  defp subir(lv, nombre \\ "ventas.csv", contenido \\ "lat,lon\n20.6,-103.3\n") do
    archivo =
      file_input(lv, "#subir_form", :archivo, [
        %{name: nombre, content: contenido, type: "text/csv"}
      ])

    render_upload(archivo, nombre)
    lv |> form("#subir_form") |> render_submit()
  end

  test "un equipo ajeno no abre", %{conn: conn} do
    ajeno = team_fixture(user_scope_fixture())

    assert_raise Ecto.NoResultsError, fn -> live(conn, ~p"/teams/#{ajeno}/datos") end
  end

  test "lee, muestra lo sugerido, guarda y dice qué descartó", %{conn: conn, team: team} do
    stub()
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")

    html = subir(lv)
    assert html =~ "2 renglones"
    assert html =~ "Solo se leyó la primera hoja"
    assert html =~ "&lt;script&gt;x&lt;/script&gt;"
    refute html =~ "<script>x</script>"

    html =
      lv
      |> form("#capa_form",
        capa: %{nombre: "Ventas 2026", tipo: "puntos", lat: "lat", lon: "lon"}
      )
      |> render_submit()

    assert html =~ "Capa guardada"
    assert html =~ "1 fuera de México"
    assert html =~ "Ventas 2026"
    assert html =~ "1 de 2 renglones"
    assert has_element?(lv, "#subir_form")
  end

  test "el motivo de rechazo de mapo_core llega tal cual", %{conn: conn, team: team} do
    stub(%{leer: {422, %{"detail" => "El archivo está vacío."}}})
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")

    assert subir(lv) =~ "El archivo está vacío."
    assert has_element?(lv, "#subir_form")
  end

  test "si no se ubicó ningún renglón no se guarda nada", %{conn: conn, team: team, scope: scope} do
    stub(%{ubicar: %{@ubicados | "filas" => []}})
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")
    subir(lv)

    html =
      lv
      |> form("#capa_form", capa: %{nombre: "x", tipo: "puntos", lat: "lat", lon: "lon"})
      |> render_submit()

    assert html =~ "No se ubicó ningún renglón"
    assert Capas.list_capas(scope, team.id) == []
  end

  test "un formato ajeno lo rechaza mapo_core y se dice", %{conn: conn, team: team} do
    stub(%{leer: {422, %{"detail" => "Formato no reconocido."}}})
    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")

    assert subir(lv, "virus.exe", "MZ") =~ "Formato no reconocido."
  end

  test "la clave partida en columnas viaja como varias `clave`", %{conn: conn, team: team} do
    yo = self()

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/datos/leer" ->
          Req.Test.json(conn, %{
            @lectura
            | "columnas" => ["ENTIDAD", "MUN"],
              "muestra" => [["1", "1"]],
              "sugerencia" => %{"tipo" => "municipio", "partes" => ["ENTIDAD", "MUN"]}
          })

        "/datos/ubicar" ->
          send(yo, {:consulta, conn.query_string})

          Req.Test.json(conn, %{
            @ubicados
            | "tipo" => "municipio",
              "filas" => [%{"clave" => "01001", "datos" => %{}}],
              "descartes" => %{}
          })
      end
    end)

    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")
    html = subir(lv)
    assert html =~ "Columna del estado"
    refute html =~ "Columna de la clave"

    lv |> form("#capa_form", capa: %{nombre: "x"}) |> render_submit()

    assert_received {:consulta, consulta}
    assert consulta =~ "clave=ENTIDAD&clave=MUN"
  end

  test "un vectorial guarda el tipo que dice mapo_core y su geometría", %{
    conn: conn,
    team: team,
    scope: scope
  } do
    geometria = %{"type" => "Point", "coordinates" => [-103.3, 20.6]}

    stub(%{
      leer: %{@lectura | "sugerencia" => %{"tipo" => "vector"}},
      ubicar: %{
        @ubicados
        | "tipo" => "vector",
          "filas" => [%{"geometria" => geometria, "clave" => nil, "datos" => %{}}]
      }
    })

    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")
    html = subir(lv, "capa.geojson")
    assert html =~ "Trae su propia ubicación"

    lv |> form("#capa_form", capa: %{nombre: "x"}) |> render_submit()
    assert [%{tipo: "vector", num_filas: 1}] = Capas.list_capas(scope, team.id)
  end

  test "un ráster se guarda sin renglones", %{conn: conn, team: team, scope: scope} do
    stub(%{
      leer: %{
        "columnas" => [],
        "muestra" => [],
        "num_filas" => 0,
        "avisos" => [],
        "sugerencia" => %{"tipo" => "raster"},
        "raster" => %{"ancho" => 100, "alto" => 50, "bandas" => 1}
      },
      ubicar: %{
        "tipo" => "raster",
        "filas" => [],
        "descartes" => %{},
        "numericas" => [],
        "repetidas" => 0,
        "columnas" => [],
        "num_filas" => 0,
        "avisos" => [],
        "raster" => %{
          "png" => Base.encode64("imagen"),
          "oeste" => -104.0,
          "sur" => 20.0,
          "este" => -103.0,
          "norte" => 21.0,
          "limites" => [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        }
      }
    })

    {:ok, lv, _} = live(conn, ~p"/teams/#{team}/datos")
    assert subir(lv, "altura.tif") =~ "100 × 50 píxeles"

    assert lv |> form("#capa_form", capa: %{nombre: "Altura"}) |> render_submit() =~
             "Capa guardada."

    [capa] = Capas.list_capas(scope, team.id)
    assert Capas.raster(scope, capa.id).png == "imagen"
    assert Capas.raster(user_scope_fixture(), capa.id) == nil
  end

  test "un miembro no borra lo que subió otro", %{conn: conn, team: team, scope: scope} do
    miembro = user_scope_fixture()

    Mapo.Repo.insert!(%Mapo.Teams.Membership{
      team_id: team.id,
      user_id: miembro.user.id,
      role: :member
    })

    {:ok, capa} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "De otra persona",
          archivo: "a.csv",
          tamano_bytes: 1,
          tipo: "puntos",
          columnas: ["a"],
          numericas: [],
          num_filas: 1,
          num_descartadas: 0,
          repetidas: 0
        },
        [%{"lat" => 20.0, "lon" => -103.0, "datos" => %{}}]
      )

    {:ok, lv, html} = conn |> log_in_user(miembro.user) |> live(~p"/teams/#{team}/datos")

    assert html =~ "De otra persona"
    refute has_element?(lv, "button", "Borrar")
    assert render_click(lv, "borrar", %{"id" => to_string(capa.id)}) =~ "no se puede borrar"
    assert Capas.get_capa(scope, capa.id)
  end
end
