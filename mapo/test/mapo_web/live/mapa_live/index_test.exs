defmodule MapoWeb.MapaLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  defp estado_feature(cvegeo, nomgeo) do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => cvegeo, "nomgeo" => nomgeo},
      "geometry" => %{}
    }
  end

  defp municipio_feature(cve_ent, cve_mun, nomgeo) do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => cve_ent <> cve_mun, "cve_mun" => cve_mun, "nomgeo" => nomgeo},
      "geometry" => %{}
    }
  end

  defp stub_estados_y_municipio(extra) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [estado_feature("14", "Jalisco")]
          })

        "/geo/municipios" ->
          Req.Test.json(conn, %{
            "type" => "FeatureCollection",
            "features" => [municipio_feature("14", "039", "Guadalajara")]
          })

        _ ->
          extra.(conn)
      end
    end)
  end

  defp montar_con_ubicacion(conn, extra) do
    stub_estados_y_municipio(extra)
    {:ok, lv, _html} = live(conn, ~p"/mapa")

    lv
    |> form("#ubicacion_form", mapa: %{"cve_ent" => "14", "cve_mun" => ""})
    |> render_change()

    lv
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/mapa")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "picking an estado populates municipios", %{conn: conn} do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    html = render(lv)
    assert html =~ "Guadalajara"
  end

  defp montar_con_municipio(conn, extra) do
    lv = montar_con_ubicacion(conn, extra)

    lv
    |> form("#ubicacion_form", mapa: %{"cve_ent" => "14", "cve_mun" => "039"})
    |> render_change()

    lv
  end

  defp coleccion_con_una_feature, do: %{"type" => "FeatureCollection", "features" => [%{}]}

  defp mostrar_voronoi(lv, clase_actividad \\ "") do
    lv
    |> form("#voronoi_capa_form", voronoi_capa: %{"clase_actividad" => clase_actividad})
    |> render_submit()
  end

  test "mostrar_coropleta pushes the layer event", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        assert conn.request_path == "/censo/choropleth"
        Req.Test.json(conn, coleccion_con_una_feature())
      end)

    lv
    |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
    |> render_submit()

    assert_push_event(lv, "capa_coropleta", %{activa: true, etiqueta: "Población total"})
  end

  test "mostrar_coropleta with a municipio sends its cve_mun (3 digits), not the cvegeo", %{
    conn: conn
  } do
    lv =
      montar_con_municipio(conn, fn conn ->
        assert conn.params["cve_mun"] == "039"
        Req.Test.json(conn, coleccion_con_una_feature())
      end)

    lv
    |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
    |> render_submit()

    assert_push_event(lv, "capa_coropleta", %{activa: true})
  end

  test "an empty coropleta from mapo_core shows an honest message", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
      end)

    html =
      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
      |> render_submit()

    assert html =~ "no tiene AGEBs o censo descargados"
  end

  test "mostrar_coropleta without an estado shows a flash", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/mapa")

    html =
      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
      |> render_submit()

    assert html =~ "Selecciona un estado"
  end

  test "quitar_coropleta pushes activa: false", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        Req.Test.json(conn, coleccion_con_una_feature())
      end)

    lv
    |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
    |> render_submit()

    lv |> element("button", "Quitar") |> render_click()

    assert_push_event(lv, "capa_coropleta", %{activa: false})
  end

  test "mostrar_voronoi requires a municipio", %{conn: conn} do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    html =
      lv
      |> form("#voronoi_capa_form", voronoi_capa: %{"clase_actividad" => ""})
      |> render_submit()

    assert html =~ "Selecciona un estado y un municipio"
  end

  test "mostrar_voronoi with a municipio pushes the layer event", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        assert conn.request_path == "/voronoi/denue"
        assert conn.params["cve_mun"] == "039"

        Req.Test.json(conn, %{
          "celdas" => %{"type" => "FeatureCollection", "features" => []},
          "metodo" => "recortado_a_limite"
        })
      end)

    lv
    |> form("#ubicacion_form", mapa: %{"cve_ent" => "14", "cve_mun" => "039"})
    |> render_change()

    mostrar_voronoi(lv)

    assert_push_event(lv, "capa_voronoi", %{activa: true})
  end

  test "mostrar_voronoi includes clase_actividad when given", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        assert conn.params["clase_actividad"] == "papel"

        Req.Test.json(conn, %{
          "celdas" => %{"type" => "FeatureCollection", "features" => []},
          "metodo" => "recortado_a_limite"
        })
      end)

    mostrar_voronoi(lv, "papel")

    assert_push_event(lv, "capa_voronoi", %{activa: true})
  end

  test "a 422 from mapo_core (not enough businesses) shows its detail message", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        conn
        |> Plug.Conn.put_resp_content_type("application/json")
        |> Plug.Conn.send_resp(422, Jason.encode!(%{"detail" => "Solo hay 2 negocios"}))
      end)

    assert mostrar_voronoi(lv) =~ "Solo hay 2 negocios"
  end

  test "a 404 from mapo_core (municipio not found) shows an honest message", %{conn: conn} do
    lv =
      montar_con_municipio(conn, fn conn ->
        Plug.Conn.send_resp(conn, 404, Jason.encode!(%{"detail" => "no encontrado"}))
      end)

    assert mostrar_voronoi(lv) =~ "no está descargado en Gaiarda"
  end

  test "mostrar_coloreado pushes the layer event", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        assert conn.request_path == "/coloreado/municipios"

        Req.Test.json(conn, Map.put(coleccion_con_una_feature(), "num_colores", 1))
      end)

    lv
    |> element("[phx-click='mostrar_coloreado']")
    |> render_click()

    assert_push_event(lv, "capa_coloreado", %{activa: true})
  end

  test "mostrar_coloreado without an estado shows a flash", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/mapa")

    html = lv |> element("[phx-click='mostrar_coloreado']") |> render_click()

    assert html =~ "Selecciona un estado"
  end

  test "an empty coloreado from mapo_core shows an honest message", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
      end)

    html = lv |> element("[phx-click='mostrar_coloreado']") |> render_click()

    assert html =~ "no tiene municipios descargados"
  end

  test "activar_isocrona pushes modo_isocrona and quitar_isocrona turns it off", %{conn: conn} do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    lv
    |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => "10"})
    |> render_submit()

    assert_push_event(lv, "modo_isocrona", %{activo: true})

    lv |> element("button", "Quitar") |> render_click()

    assert_push_event(lv, "modo_isocrona", %{activo: false})
    assert_push_event(lv, "capa_isocrona", %{activa: false})
  end

  test "click_mapa while isocrona is active calls mapo_core and pushes the polygon", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        assert conn.request_path == "/isocronas/calcular"

        Req.Test.json(conn, %{
          "poligono" => %{"type" => "Polygon", "coordinates" => []},
          "metodo" => "osrm_real"
        })
      end)

    lv
    |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => "10"})
    |> render_submit()

    render_hook(lv, "click_mapa", %{"lat" => 19.4, "lon" => -99.1})

    assert_push_event(lv, "capa_isocrona", %{activa: true, metodo: "osrm_real"})
  end

  test "click_mapa while isocrona is not active does nothing (and does not call mapo_core)", %{
    conn: conn
  } do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    render_hook(lv, "click_mapa", %{"lat" => 19.4, "lon" => -99.1})

    # si hubiera llamado a mapo_core, el stub habria lanzado y tumbado
    # el proceso; si sigue vivo y renderiza, no se llamo.
    assert render(lv) =~ "Mapa técnico"
  end

  describe "mesa de planeación" do
    defp coropleta_con_valores(valores) do
      %{
        "type" => "FeatureCollection",
        "features" =>
          Enum.map(valores, fn v ->
            %{"properties" => %{"valor_choropleth" => v}, "geometry" => %{}}
          end)
      }
    end

    test "tocar una pestaña abre su cinta y tocarla otra vez la cierra", %{conn: conn} do
      stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
      {:ok, lv, html} = live(conn, ~p"/mapa")

      assert html =~ ~s(id="cinta-coropleta" class="cinta pegado" hidden)

      html = lv |> element(".pestana[phx-value-capa=coropleta]") |> render_click()
      refute html =~ ~s(id="cinta-coropleta" class="cinta pegado" hidden)

      html = lv |> element(".pestana[phx-value-capa=coropleta]") |> render_click()
      assert html =~ ~s(id="cinta-coropleta" class="cinta pegado" hidden)
    end

    test "la piel sigue a la capa de arriba de la pila", %{conn: conn} do
      lv =
        montar_con_ubicacion(conn, fn conn ->
          case conn.request_path do
            "/censo/choropleth" -> Req.Test.json(conn, coropleta_con_valores([10, 20]))
            "/coloreado/municipios" -> Req.Test.json(conn, coleccion_con_una_feature())
          end
        end)

      lv |> element("[phx-click='mostrar_coloreado']") |> render_click()
      refute_push_event(lv, "piel", %{piel: "urbanismo"})

      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
      |> render_submit()

      # La coropleta va arriba del coloreado en la pila: manda demografía.
      assert_push_event(lv, "piel", %{piel: "demografia"})

      lv
      |> element("button[phx-click=mover][phx-value-capa=coropleta][phx-value-hacia=abajo]")
      |> render_click()

      assert_push_event(lv, "orden_capas", %{
        orden: ["propios", "isocrona", "voronoi", "coloreado", "coropleta"]
      })

      assert_push_event(lv, "piel", %{piel: "urbanismo"})
    end

    test "una piel fijada gana sobre la automática hasta que se suelta", %{conn: conn} do
      stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      lv |> form("#piel_form", %{"piel" => "seguridad"}) |> render_change()
      assert_push_event(lv, "piel", %{piel: "seguridad"})

      lv |> form("#piel_form", %{"piel" => ""}) |> render_change()
      assert_push_event(lv, "piel", %{piel: "urbanismo"})
    end

    test "los quintiles cuentan aparte los AGEB sin dato, nunca como cero" do
      escala =
        MapoWeb.Cifras.escala_quintiles(coropleta_con_valores([nil, 1, 2, 3, 4, 5, nil]))

      assert escala.nulos == 2
      assert hd(escala.limites) == 1
      assert List.last(escala.limites) == 5
      assert length(escala.cortes) == 4
    end

    test "sin valores con dato no hay escala" do
      assert MapoWeb.Cifras.escala_quintiles(coropleta_con_valores([nil, nil])) == nil
    end
  end

  describe "Tus marcas" do
    import Mapo.TeamsFixtures
    import Mapo.SesionesFixtures

    alias Mapo.Sesiones

    defp con_sesion(scope) do
      team = team_fixture(scope, %{name: "Planeación"})
      sesion_fixture(scope, team, %{"nombre" => "Recorrido"})
    end

    test "without sessions it points to the teams", %{conn: conn} do
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      assert has_element?(lv, "#cinta-marcas a[href='/teams']")
      assert has_element?(lv, ".pestana[aria-controls=cinta-marcas]", "sin sesión")
    end

    test "?sesion= opens the strip on that session and pushes its marks", %{
      conn: conn,
      scope: scope
    } do
      sesion = con_sesion(scope)
      {:ok, _} = Sesiones.create_anotacion(scope, sesion, 20.67, -103.35, "aquí")
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?sesion=#{sesion.id}")

      assert_push_event(lv, "marcas", %{anotaciones: [%{texto: "aquí", forma: "punto"}]})
      assert_push_event(lv, "modo_marcas", %{activo: true})
      refute has_element?(lv, "#cinta-marcas[hidden]")
      assert has_element?(lv, "#cinta-marcas", "1 marca en la sesión")
      assert has_element?(lv, "#sesion_marcas_form optgroup[label='Planeación']")
      assert has_element?(lv, ".rotulo dd", "Recorrido")
    end

    test "choosing a session in the strip patches the URL", %{conn: conn, scope: scope} do
      sesion = con_sesion(scope)
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      lv
      |> form("#sesion_marcas_form", %{"sesion" => to_string(sesion.id)})
      |> render_change()

      assert_patch(lv, ~p"/mapa?sesion=#{sesion.id}")
    end

    test "a circle drawn on /mapa is saved in the session and arrives live", %{
      conn: conn,
      scope: scope
    } do
      sesion = con_sesion(scope)
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?sesion=#{sesion.id}")

      render_click(lv, "elegir_herramienta", %{"herramienta" => "circulo"})
      assert_push_event(lv, "herramienta", %{herramienta: "circulo"})

      render_hook(lv, "crear_anotacion", %{
        "lat" => 20.67,
        "lon" => -103.35,
        "texto" => "zona sin papelerías",
        "forma" => "circulo",
        "radio_m" => 600
      })

      assert_push_event(lv, "nueva_anotacion", %{forma: "circulo", radio_m: 600.0})
      assert [%{forma: "circulo"}] = Sesiones.list_anotaciones(sesion.id)
      assert has_element?(lv, "#cinta-marcas", "1 marca en la sesión")
    end

    test "a session of someone else's team is refused", %{conn: conn} do
      ajeno = Mapo.AccountsFixtures.user_scope_fixture()
      sesion = con_sesion(ajeno)
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)

      {:ok, lv, html} = live(conn, ~p"/mapa?sesion=#{sesion.id}")

      assert html =~ "Esa sesión no es de tus equipos."
      render_hook(lv, "crear_anotacion", %{"lat" => 1.0, "lon" => 1.0, "texto" => ""})
      assert Sesiones.list_anotaciones(sesion.id) == []
    end

    test "leaving the team after mount stops the session from opening", %{
      conn: conn,
      scope: scope
    } do
      sesion = con_sesion(scope)
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      Mapo.Repo.delete_all(Mapo.Teams.Membership)

      assert render_patch(lv, ~p"/mapa?sesion=#{sesion.id}") =~
               "Esa sesión no es de tus equipos."
    end
  end

  describe "tus datos" do
    alias Mapo.Capas

    defp capa_fixture(scope, tipo, filas, extra \\ %{}) do
      team = Mapo.TeamsFixtures.team_fixture(scope)

      {:ok, capa} =
        Capas.crear_capa(
          scope,
          team.id,
          Map.merge(
            %{
              nombre: "Ventas",
              archivo: "ventas.csv",
              tamano_bytes: 1,
              tipo: tipo,
              columnas: ["ventas", "tienda"],
              numericas: ["ventas"],
              num_filas: length(filas),
              num_descartadas: 0,
              repetidas: 0
            },
            extra
          ),
          filas
        )

      capa
    end

    defp punto(tienda) do
      %{"lat" => 20.6, "lon" => -103.3, "datos" => %{"tienda" => tienda, "ventas" => 12.345}}
    end

    defp zona(clave, ventas), do: %{"clave" => clave, "datos" => %{"ventas" => ventas}}

    defp feature(clave) do
      %{"type" => "Feature", "properties" => %{"cvegeo" => clave}, "geometry" => %{}}
    end

    test "sin capas la cinta manda a subir una", %{conn: conn} do
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, _lv, html} = live(conn, ~p"/mapa")

      assert html =~ "Tus datos"
      assert html =~ "Sube un archivo"
    end

    test "?capa= prende los puntos sin mandar los datos de cada renglón", %{
      conn: conn,
      scope: scope
    } do
      capa = capa_fixture(scope, "puntos", [punto("secreta")])
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")

      assert_push_event(lv, "capa_propios", %{tono: "consumo", puntos: [%{lat: 20.6} = p]})
      refute Map.has_key?(p, :datos)
    end

    test "la ficha se pide al abrirla, sin redondear", %{conn: conn, scope: scope} do
      capa = capa_fixture(scope, "puntos", [punto("Centro")])
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{puntos: [%{id: id}]})

      render_hook(element(lv, "#mapa-tecnico"), "ver_fila", %{"capa" => capa.id, "id" => id})
      assert_reply(lv, %{campos: [["ventas", "12.345"], ["tienda", "Centro"]], otras: 0})
    end

    test "una capa de otro equipo no abre por URL ni por el select", %{conn: conn} do
      ajena = capa_fixture(Mapo.AccountsFixtures.user_scope_fixture(), "puntos", [punto("x")])
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, html} = live(conn, ~p"/mapa?#{[capa: ajena.id]}")

      assert html =~ "no es de tus equipos"
      refute_push_event(lv, "capa_propios", %{})

      render_hook(element(lv, "#mapa-tecnico"), "ver_fila", %{"capa" => ajena.id, "id" => 1})
      assert_reply(lv, %{campos: []})
    end

    test "un id que no es número no tumba la vista", %{conn: conn} do
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, _lv, html} = live(conn, ~p"/mapa?capa=abc")
      assert html =~ "no es de tus equipos"
    end

    test "las zonas se pintan por columna con quintiles y sin inventar ceros", %{
      conn: conn,
      scope: scope
    } do
      capa = capa_fixture(scope, "municipio", [zona("14039", 10), zona("14120", nil)])

      stub_estados_y_municipio(fn conn ->
        assert conn.request_path == "/geo/por_clave"
        Req.Test.json(conn, %{"features" => [feature("14039"), feature("14120")]})
      end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{cortes: nil})

      html =
        lv
        |> form("#pintar_#{capa.id}")
        |> render_change(%{"capa" => capa.id, "columna" => "ventas"})

      assert html =~ "sin dato: 1"
      assert_push_event(lv, "capa_propios", %{geojson: geojson, tono: "consumo"})
      valores = Enum.map(geojson["features"], & &1["properties"]["valor_choropleth"])
      assert valores == [10, nil]
    end

    test "con zonas repetidas no se pinta, y se dice por qué", %{conn: conn, scope: scope} do
      capa =
        capa_fixture(scope, "municipio", [zona("14039", 1), zona("14039", 2)], %{repetidas: 1})

      stub_estados_y_municipio(fn conn ->
        Req.Test.json(conn, %{"features" => [feature("14039")]})
      end)

      {:ok, lv, html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert html =~ "se necesita uno por zona"

      render_change(lv, "pintar_capa", %{"capa" => capa.id, "columna" => "ventas"})
      assert_push_event(lv, "capa_propios", %{cortes: nil})
    end

    test "una capa vectorial viaja con geometría y se pinta por id", %{conn: conn, scope: scope} do
      fila = %{
        "geometria" => %{
          "type" => "Polygon",
          "coordinates" => [[[-103.4, 20.6], [-103.3, 20.6], [-103.3, 20.7], [-103.4, 20.6]]]
        },
        "datos" => %{"ventas" => 7}
      }

      capa = capa_fixture(scope, "vector", [fila])
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{geojson: %{"features" => [%{"geometry" => geom}]}})
      assert geom["type"] == "Polygon"

      html = render_change(lv, "pintar_capa", %{"capa" => capa.id, "columna" => "ventas"})
      assert html =~ "sin dato: 0"
    end

    test "un ráster manda el lugar y la imagen se sirve por el scope", %{conn: conn, scope: scope} do
      team = Mapo.TeamsFixtures.team_fixture(scope)

      {:ok, capa} =
        Capas.crear_capa(
          scope,
          team.id,
          %{
            nombre: "Altura",
            archivo: "a.tif",
            tamano_bytes: 1,
            tipo: "raster",
            columnas: [],
            numericas: [],
            num_filas: 0,
            num_descartadas: 0,
            repetidas: 0
          },
          [],
          %{
            png: "imagen",
            oeste: -104.0,
            sur: 20.0,
            este: -103.0,
            norte: 21.0,
            limites: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
          }
        )

      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{raster: %{url: url, oeste: -104.0}})

      assert conn |> get(url) |> response(200) == "imagen"
      assert ["image/png" <> _] = conn |> get(url) |> get_resp_header("content-type")

      ajeno = Mapo.AccountsFixtures.user_fixture()
      assert build_conn() |> log_in_user(ajeno) |> get(url) |> response(404) == ""
      assert build_conn() |> get(url) |> redirected_to() =~ "log-in"
    end

    test "caben tres capas, cada una con su tinta, y se quitan una por una", %{
      conn: conn,
      scope: scope
    } do
      ids = for _ <- 1..4, do: capa_fixture(scope, "puntos", [punto("x")]).id
      [a, b, c, d] = ids
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: a]}")
      assert_push_event(lv, "capa_propios", %{id: ^a, tono: "consumo"})

      render_change(lv, "agregar_capa", %{"capa" => b})
      assert_push_event(lv, "capa_propios", %{id: ^b, tono: "seguridad"})
      render_change(lv, "agregar_capa", %{"capa" => c})
      assert_push_event(lv, "capa_propios", %{id: ^c, tono: "laboral"})

      assert render_change(lv, "agregar_capa", %{"capa" => d}) =~ "Caben 3 capas"
      refute has_element?(lv, "#capa_propia_form")

      render_click(lv, "quitar_capa", %{"id" => to_string(b)})
      assert_push_event(lv, "capa_propios_fuera", %{id: ^b})

      render_change(lv, "agregar_capa", %{"capa" => d})
      assert_push_event(lv, "capa_propios", %{id: ^d, tono: "seguridad"})
    end
  end
end
