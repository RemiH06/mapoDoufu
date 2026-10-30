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
        orden: ["isocrona", "voronoi", "coloreado", "coropleta"]
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
        MapoWeb.MapaLive.Index.escala_quintiles(coropleta_con_valores([nil, 1, 2, 3, 4, 5, nil]))

      assert escala.nulos == 2
      assert hd(escala.limites) == 1
      assert List.last(escala.limites) == 5
      assert length(escala.cortes) == 4
    end

    test "sin valores con dato no hay escala" do
      assert MapoWeb.MapaLive.Index.escala_quintiles(coropleta_con_valores([nil, nil])) == nil
    end
  end
end
