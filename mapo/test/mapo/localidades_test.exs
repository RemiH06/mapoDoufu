defmodule Mapo.Capas.LocalidadesTest do
  use Mapo.DataCase, async: true

  import Mapo.AccountsFixtures
  import Mapo.TeamsFixtures

  alias Mapo.Capas
  alias Mapo.Capas.Localidades

  setup do
    scope = user_scope_fixture()
    team = team_fixture(scope)

    {:ok, escuelas} =
      Capas.crear_capa(
        scope,
        team.id,
        %{
          nombre: "Escuelas",
          archivo: "e.gpkg",
          tamano_bytes: 1,
          tipo: "puntos",
          columnas: ["nombre", "clase"],
          numericas: [],
          num_filas: 2,
          num_descartadas: 0
        },
        [
          %{
            "lat" => 20.0,
            "lon" => -104.0,
            "datos" => %{"nombre" => "Primaria", "clase" => "Escuelas"}
          },
          %{
            "lat" => 20.5,
            "lon" => -104.0,
            "datos" => %{"nombre" => "Taller", "clase" => "Autos"}
          }
        ]
      )

    %{scope: scope, escuelas: escuelas}
  end

  # mapo_core de mentiras: a cada renglón le da un rancho a 209 m.
  defp stub do
    prueba = self()

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      {:ok, cuerpo, conn} = Plug.Conn.read_body(conn)
      solicitud = Jason.decode!(cuerpo)
      send(prueba, {:solicitud, solicitud})

      filas =
        for f <- solicitud["filas"] do
          %{
            "id" => f["id"],
            "metros" => 209,
            "cvegeo" => "140150042",
            "nombre" => "Rancho",
            "nom_mun" => "Autlán de Navarro",
            "ambito" => "rural",
            "pobtot" => 12,
            "cuantos" => if(solicitud["radio"], do: 1),
            "poblacion" => if(solicitud["radio"], do: 12)
          }
        end

      Req.Test.json(conn, %{"filas" => filas, "localidades" => 185_243})
    end)
  end

  test "manda solo los renglones filtrados y guarda la capa con la procedencia", ctx do
    stub()

    opciones = %{
      radio: 300,
      ambito: "rural",
      etiqueta_origen: "nombre",
      filtro_origen: [{"clase", "Escuelas"}]
    }

    {:ok, r} = Localidades.calcular(ctx.escuelas, opciones)

    assert_received {:solicitud,
                     %{
                       "filas" => [%{"geometria" => %{"type" => "Point"}}],
                       "radio" => 300,
                       "ambito" => "rural"
                     }}

    assert [%{nombre: "Primaria", metros: 209, cercano: "Rancho", cuantos: 1}] = r.filas
    assert r.a_menos == 1 and r.destino_filas == 185_243
    assert "localidades_pob_a_300m" in r.columnas
    assert Enum.at(r.metodo, 1) =~ "185,243 localidades rurales del ITER"

    {:ok, capa} = Localidades.guardar(ctx.scope, ctx.escuelas, "Escuelas y ranchos", r)
    [%{id: id}] = Capas.puntos(capa)

    assert {%{"nombre" => "Primaria", "distancia_m_localidades" => 209} = datos, 1} =
             Capas.ficha(ctx.scope, capa.id, {:id, id})

    assert datos["localidades_fuente"] =~ "ITER"
    assert datos["localidades_fecha_dato"] == "2020-03-15"
    assert "localidades_pob_a_300m" in capa.numericas
    assert capa.tipo == "puntos" and capa.num_filas == 1
  end

  test "sin localidades cargadas o con mapo_core caído se dice", ctx do
    Req.Test.stub(Mapo.MapoCore, &Req.Test.json(&1, %{"filas" => [], "localidades" => 0}))
    assert {:error, "No hay localidades" <> _} = Localidades.calcular(ctx.escuelas, %{})

    Req.Test.stub(Mapo.MapoCore, &Req.Test.transport_error(&1, :econnrefused))
    assert {:error, "mapo_core no está" <> _} = Localidades.calcular(ctx.escuelas, %{})

    assert {:error, "El ámbito" <> _} = Localidades.calcular(ctx.escuelas, %{ambito: "otro"})
  end
end
