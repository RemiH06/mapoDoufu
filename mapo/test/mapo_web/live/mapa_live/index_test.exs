defmodule MapoWeb.MapaLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.ZonaFixtures

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
      responder_zona(conn) || otra_ruta(conn, extra)
    end)
  end

  defp otra_ruta(conn, extra) do
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
  end

  defp montar_con_ubicacion(conn, extra) do
    stub_estados_y_municipio(extra)
    {:ok, lv, _html} = live(conn, ~p"/mapa")
    elegir_zona(lv, "ent:14")
  end

  test "sin mapo_core, buscar una zona lo dice", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, lv, _html} = live(conn, ~p"/mapa")

    html = lv |> form("#zona-form", zona_q: %{q: "Jalisco"}) |> render_change()
    assert html =~ "No se pudo buscar"
  end

  test "elegir una zona la pone en el membrete y la manda al plano", %{conn: conn} do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    assert has_element?(lv, ".ubicacion .zona-nombre", "Jalisco")
    assert_push_event(lv, "zona_elegida", %{geojson: %{"type" => "Polygon"}})
  end

  defp montar_con_municipio(conn, extra) do
    stub_estados_y_municipio(extra)
    {:ok, lv, _html} = live(conn, ~p"/mapa")
    elegir_zona(lv, "mun:14039")
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

    # Un conteo va en círculos, nunca en color.
    assert_push_event(lv, "capa_coropleta", %{
      activa: true,
      modo: "circulos",
      textos: %{s: %{nombre: "Población total", unidad: "personas"}}
    })
  end

  describe "escalas y dos indicadores" do
    defp ageb(cvegeo, valor, valores) do
      %{
        "type" => "Feature",
        "geometry" => %{},
        "properties" => %{
          "cvegeo" => cvegeo,
          "indicador" => "vph_inter",
          "valor_choropleth" => valor,
          "valores" => valores,
          "area_km2" => 1.0,
          "centro" => [-103.3, 20.6]
        }
      }
    end

    defp agebs_internet do
      %{
        "type" => "FeatureCollection",
        "features" => [
          ageb("1", 10, %{"tvivparhab" => 100, "pobtot" => 400}),
          ageb("2", 30, %{"tvivparhab" => 60, "pobtot" => 200}),
          ageb("3", 45, %{"tvivparhab" => 50, "pobtot" => 150}),
          ageb("4", 5, %{"tvivparhab" => nil, "pobtot" => 20})
        ]
      }
    end

    # Como en la cinta: primero el indicador (cambian las lecturas), luego "%".
    defp poner_internet_pct(lv) do
      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "vph_inter"})
      |> render_change()

      lv
      |> form("#coropleta_capa_form",
        coropleta_capa: %{"indicador" => "vph_inter", "como" => "pct"}
      )
      |> render_submit()
    end

    defp montar_internet(conn) do
      yo = self()

      montar_con_ubicacion(conn, fn conn ->
        send(yo, {:censo, conn.query_string})
        Req.Test.json(conn, agebs_internet())
      end)
    end

    test "una tasa va en color, con su denominador pedido a mapo_core y su fórmula", %{conn: conn} do
      lv = montar_internet(conn)

      html = poner_internet_pct(lv)

      assert_receive {:censo, query}
      assert query =~ "extra=tvivparhab"

      assert_push_event(lv, "capa_coropleta", %{modo: "color", geojson: %{"features" => features}})

      assert Enum.map(features, & &1["properties"]["v"]) == [10.0, 50.0, 90.0, nil]
      assert html =~ "Viviendas con internet ÷ Viviendas particulares habitadas × 100"
      assert html =~ "Sin dato: 1"
      assert_patch(lv, "/mapa?zona=ent:14&censo=vph_inter&como=pct")
    end

    test "cambiar la escala repinta sin pedir datos y queda en el enlace", %{conn: conn} do
      lv = montar_internet(conn)

      poner_internet_pct(lv)

      assert_receive {:censo, _}

      lv
      |> form("#coropleta_escala_form",
        escala: %{"paleta" => "viridis", "metodo" => "naturales", "clases" => "3"}
      )
      |> render_change()

      # Cada paleta se ve como su rampa, y la elegida queda marcada.
      assert has_element?(
               lv,
               "label.paleta[title=Viridis][style*='linear-gradient'] input[checked]"
             )

      assert has_element?(lv, "label.paleta[title='La tinta de la capa'][style*='color-mix']")

      refute_receive {:censo, _}
      assert_push_event(lv, "escala_coropleta", %{escala: %{claro: [_, _, _], cortes: [_, _]}})
      assert_patch(lv, "/mapa?zona=ent:14&censo=vph_inter&como=pct&esc=viridis:naturales:3")
    end

    test "el enlace reconstruye la lectura, el segundo indicador y la escala", %{conn: conn} do
      stub_estados_y_municipio(fn conn -> Req.Test.json(conn, agebs_internet()) end)

      {:ok, lv, html} =
        live(
          conn,
          ~p"/mapa?zona=ent:14&censo=vph_inter&como=pct&censo2=pobtot&esc=cividis:iguales:4:inv"
        )

      assert_push_event(lv, "capa_coropleta", %{
        modo: "color_circulos",
        escala: %{cortes: [_, _, _]},
        circulos: %{max: 400}
      })

      assert html =~ "El área va con el valor"
    end

    test "dos conteos no se leen juntos y se dice", %{conn: conn} do
      lv = montar_internet(conn)

      html =
        lv
        |> form("#coropleta_capa_form",
          coropleta_capa: %{
            "indicador" => "vph_inter",
            "como" => "conteo",
            "indicador2" => "pobtot"
          }
        )
        |> render_change()

      assert html =~ "Dos conteos no se leen juntos"
    end
  end

  test "mostrar_coropleta manda la clave de la zona, no un estado y un municipio", %{
    conn: conn
  } do
    lv =
      montar_con_municipio(conn, fn conn ->
        assert conn.params["zona"] == "mun:14039"
        refute Map.has_key?(conn.params, "cve_ent")
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

    assert html =~ "no tiene AGEB o censo cargados en esa zona"
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

    assert html =~ "Elige una zona"
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

  test "mostrar_voronoi requires a zone", %{conn: conn} do
    stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
    {:ok, lv, _html} = live(conn, ~p"/mapa")

    html =
      lv
      |> form("#voronoi_capa_form", voronoi_capa: %{"clase_actividad" => ""})
      |> render_submit()

    assert html =~ "Elige una zona"
  end

  test "mostrar_voronoi with a municipio pushes the layer event", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        assert conn.request_path == "/voronoi/denue"
        assert conn.params["zona"] == "mun:14039"

        Req.Test.json(conn, %{
          "celdas" => %{"type" => "FeatureCollection", "features" => []},
          "metodo" => "recortado_a_limite"
        })
      end)

    elegir_zona(lv, "mun:14039")
    mostrar_voronoi(lv)

    assert_push_event(lv, "capa_voronoi", %{activa: true})
  end

  test "cambiar de zona vuelve a pedir el Voronoi puesto, con la zona nueva", %{conn: conn} do
    yo = self()

    lv =
      montar_con_municipio(conn, fn conn ->
        send(yo, {:voronoi, conn.params["zona"]})

        Req.Test.json(conn, %{
          "celdas" => %{"type" => "FeatureCollection", "features" => []},
          "metodo" => "recortado_a_limite",
          "num_negocios" => 3,
          "num_fuera" => 2,
          "competencia_m" => 5000
        })
      end)

    assert mostrar_voronoi(lv, "farmacia") =~ "3 en la zona y 2 de fuera a 5 km o menos"
    assert_receive {:voronoi, "mun:14039"}

    lv |> element("#zona-sumar") |> render_click()
    lv |> form("#zona-form", zona_q: %{q: "Zapopan"}) |> render_change()
    lv |> form("#zona-form", zona_q: %{q: "Zapopan"}) |> render_submit()

    assert_receive {:voronoi, "mun:14039,14120"}
    assert has_element?(lv, ".zona-chips", "Zapopan")
    assert_patch(lv, "/mapa?zona=mun:14039,14120&negocios=farmacia")
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

    assert mostrar_voronoi(lv) =~ "no toca nada cargado en Mapo"
  end

  describe "transporte" do
    defp respuesta_transporte(origen, feeds, rutas \\ []) do
      %{
        "zona" => %{"clave" => "mun:14039", "nombre" => "Guadalajara"},
        "origen" => origen,
        "rutas" => %{"type" => "FeatureCollection", "features" => rutas},
        "paradas" => %{"type" => "FeatureCollection", "features" => []},
        "resumen" => %{
          "rutas" => 3,
          "por_modo" => %{},
          "por_clase" => %{"10" => 2, "mas" => 1},
          "paradas" => 0
        },
        "clases" => %{"10" => "cada 10 min o menos", "mas" => "más de 30 min"},
        "modos" => %{"autobus" => "Autobús"},
        "frecuente_min" => 15,
        "pico" => "de 7:00 a 9:00 de un día hábil",
        "feeds" => feeds
      }
    end

    test "necesita una zona y dice por qué una muy grande no se calcula", %{conn: conn} do
      stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")
      assert render_click(lv, "mostrar_transporte", %{}) =~ "Elige una zona primero"

      lv =
        montar_con_ubicacion(conn, fn conn ->
          assert conn.params["zona"] == "ent:14"

          conn
          |> Plug.Conn.put_status(422)
          |> Req.Test.json(%{
            "detail" => "la zona mide 78,601 km² y aquí se calcula hasta 5,000 km²"
          })
        end)

      assert render_click(lv, "mostrar_transporte", %{}) =~
               "Transporte: la zona mide 78,601 km² y aquí se calcula hasta 5,000 km²."
    end

    test "pone las rutas, dice cuántas son frecuentes y la licencia de cada feed", %{conn: conn} do
      ruta = %{
        "type" => "Feature",
        "properties" => %{"id" => "R1", "col" => "#FF8800"},
        "geometry" => %{}
      }

      feed = %{
        "feed" => "jal-setran",
        "titulo" => "Jalisco",
        "productor" => "SETRAN",
        "licencia" => nil,
        "pagina" => "https://x.test",
        "fecha_ref" => "2026-11-25",
        "vencido" => false,
        "frecuencia_util" => true,
        "cargado" => "2026-11-22"
      }

      lv =
        montar_con_municipio(conn, fn conn ->
          assert conn.request_path == "/transporte/zona"
          assert conn.params["zona"] == "mun:14039"
          Req.Test.json(conn, respuesta_transporte("gtfs", [feed], [ruta]))
        end)

      html = render_click(lv, "mostrar_transporte", %{})
      # Pocas rutas y con color en su GTFS: cada una con el suyo.
      assert_push_event(lv, "capa_transporte", %{activa: true, origen: "gtfs", color: "ruta"})
      assert html =~ "Cada ruta con el color que le da su GTFS"

      html = lv |> form("#transporte_color_form", %{"color" => "frecuencia"}) |> render_change()
      assert_push_event(lv, "color_rutas", %{color: "frecuencia"})
      assert html =~ "Más gruesa y con más tinta, pasa más seguido."
      assert html =~ "3 rutas pasan por Guadalajara; 2 pasan cada 15 minutos o menos"
      assert html =~ "Sin licencia declarada"
      assert html =~ "frecuencias del 2026-11-25"
      assert_patch(lv) =~ "transporte=1"

      render_click(lv, "quitar_transporte", %{})
      assert_push_event(lv, "capa_transporte", %{activa: false})
    end

    test "sin GTFS ni OSM lo dice en vez de pintar nada", %{conn: conn} do
      lv =
        montar_con_municipio(conn, fn conn ->
          Req.Test.json(conn, put_in(respuesta_transporte("osm", []), ["resumen", "rutas"], 0))
        end)

      assert render_click(lv, "mostrar_transporte", %{}) =~
               "Ningún GTFS ni OpenStreetMap tiene rutas que pasen por Guadalajara"
    end
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

    assert html =~ "Elige una zona"
  end

  test "an empty coloreado from mapo_core shows an honest message", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
      end)

    html = lv |> element("[phx-click='mostrar_coloreado']") |> render_click()

    assert html =~ "no tiene municipios cargados en esa zona"
  end

  test "agregar un alcance espera el clic; cancelar y quitar apagan el modo", %{conn: conn} do
    lv = montar_con_ubicacion(conn, fn _conn -> raise "no debería llamarse" end)

    lv
    |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => "10"})
    |> render_submit()

    assert_push_event(lv, "modo_isocrona", %{activo: true})
    assert render(lv) =~ "Haz clic en el plano para elegir el punto de salida."

    lv |> element("button", "Cancelar") |> render_click()
    assert_push_event(lv, "modo_isocrona", %{activo: false})

    html =
      lv
      |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => "500"})
      |> render_submit()

    assert html =~ "Los minutos van de 1 a 120."
  end

  defp cuerpo(conn) do
    {:ok, cuerpo, _conn} = Plug.Conn.read_body(conn)
    Jason.decode!(cuerpo)
  end

  defp isocrona(lat) do
    %{
      "poligono" => %{
        "type" => "Polygon",
        "coordinates" => [[[lat, 0], [lat, 1], [0, 1], [lat, 0]]]
      },
      "metodo" => "osrm_real"
    }
  end

  defp poblacion(n) do
    cada = for i <- 1..n, do: %{"personas" => 1000 * i, "lugares" => i, "reservados" => 0}

    %{
      "cada_una" => cada,
      "en_todas" => if(n > 1, do: %{"personas" => 500, "lugares" => 1, "reservados" => 2}),
      "en_alguna" => if(n > 1, do: %{"personas" => 2500, "lugares" => 3, "reservados" => 0}),
      "interseccion" => if(n > 1, do: %{"type" => "Polygon", "coordinates" => []}),
      "metodo" => "Censo 2020 por su punto."
    }
  end

  test "los alcances se apilan con la gente dentro de cada uno, en todos y en alguno", %{
    conn: conn
  } do
    yo = self()

    lv =
      montar_con_ubicacion(conn, fn conn ->
        case conn.request_path do
          "/isocronas/calcular" ->
            Req.Test.json(conn, isocrona(cuerpo(conn)["lat"]))

          "/isocronas/poblacion" ->
            n = length(cuerpo(conn)["poligonos"])
            send(yo, {:poblacion, n})
            Req.Test.json(conn, poblacion(n))
        end
      end)

    for {lat, min} <- [{20.6, "10"}, {20.7, "20"}] do
      lv
      |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => min})
      |> render_submit()

      render_hook(lv, "click_mapa", %{"lat" => lat, "lon" => -103.3})
    end

    assert_receive {:poblacion, 1}
    assert_receive {:poblacion, 2}
    assert_push_event(lv, "capa_isocrona", %{activa: true, isocronas: [_], interseccion: nil})

    assert_push_event(lv, "capa_isocrona", %{
      activa: true,
      isocronas: [%{tinta: "movilidad"}, %{tinta: "urbanismo"}],
      interseccion: %{"type" => "Polygon"}
    })

    html = render(lv)
    assert html =~ "1,000 personas" and html =~ "2,000 personas"
    assert has_element?(lv, ".alcances-suma", "500 personas, sin 2 lugares con dato reservado")
    assert has_element?(lv, ".alcances-suma", "2,500 personas")
    assert html =~ "El contorno grueso es la parte que comparten todos."
    assert_patch(lv) =~ "alcance=20.6,-103.3,10;20.7,-103.3,20"

    lv |> element("button[aria-label='Quitar el alcance 1']") |> render_click()
    assert_receive {:poblacion, 1}
    assert_patch(lv) =~ "alcance=20.7,-103.3,20"

    lv |> element("button", "Quitar todos") |> render_click()
    assert_push_event(lv, "capa_isocrona", %{activa: false})
  end

  test "sin mapo_core para contar, el alcance se pinta y se dice", %{conn: conn} do
    lv =
      montar_con_ubicacion(conn, fn conn ->
        case conn.request_path do
          "/isocronas/calcular" -> Req.Test.json(conn, isocrona(20.6))
          "/isocronas/poblacion" -> Plug.Conn.send_resp(conn, 502, "{}")
        end
      end)

    lv
    |> form("#isocrona_capa_form", isocrona_capa: %{"minutos" => "10"})
    |> render_submit()

    html = render_hook(lv, "click_mapa", %{"lat" => 20.6, "lon" => -103.3})
    assert_push_event(lv, "capa_isocrona", %{activa: true, isocronas: [_]})
    assert html =~ "No se pudo contar la gente dentro"
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

  defp pestanas(lv) do
    lv
    |> render()
    |> LazyHTML.from_fragment()
    |> LazyHTML.query(".pestana[data-capa]")
    |> LazyHTML.attribute("id")
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

      html = lv |> element(".pestana[aria-controls=cinta-coropleta]") |> render_click()
      refute html =~ ~s(id="cinta-coropleta" class="cinta pegado" hidden)

      html = lv |> element(".pestana[aria-controls=cinta-coropleta]") |> render_click()
      assert html =~ ~s(id="cinta-coropleta" class="cinta pegado" hidden)
    end

    test "la mesa es neutra y sin selector de piel", %{conn: conn} do
      stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
      {:ok, _lv, html} = live(conn, ~p"/mapa")

      assert html =~ ~s(lang="es" data-piel="neutra">)
      assert html =~ ~s(data-mesa="neutra")
      refute html =~ "piel_form"
    end

    test "arrastrar las pestañas cambia la pila; un orden con otras capas se ignora", %{
      conn: conn
    } do
      stub_estados_y_municipio(fn _conn -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      orden = ~w(coropleta propios isocrona transporte voronoi vivienda coloreado)
      render_hook(lv, "ordenar", %{"orden" => orden})
      assert_push_event(lv, "orden_capas", %{orden: ^orden})
      assert ["pestana-coropleta" | _] = pestanas(lv)

      render_hook(lv, "ordenar", %{"orden" => ~w(coropleta propios inventada)})
      render_hook(lv, "ordenar", %{"orden" => "coropleta"})
      assert ["pestana-coropleta", "pestana-propios" | _] = pestanas(lv)
    end

    test "los botones de la cinta también mueven la pila", %{conn: conn} do
      lv =
        montar_con_ubicacion(conn, fn conn ->
          Req.Test.json(conn, coropleta_con_valores([10, 20]))
        end)

      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
      |> render_submit()

      lv
      |> element("button[phx-click=mover][phx-value-capa=coropleta][phx-value-hacia=abajo]")
      |> render_click()

      assert_push_event(lv, "orden_capas", %{
        orden: [
          "propios",
          "isocrona",
          "transporte",
          "voronoi",
          "vivienda",
          "coloreado",
          "coropleta"
        ]
      })
    end

    test "los quintiles cuentan aparte los AGEB sin dato, nunca como cero" do
      escala = MapoWeb.Escala.de_geojson(coropleta_con_valores([nil, 1, 2, 3, 4, 5, nil]))

      assert escala.nulos == 2
      assert hd(escala.limites) == 1
      assert List.last(escala.limites) == 5
      assert length(escala.cortes) == 4
    end

    test "sin valores con dato no hay escala" do
      assert MapoWeb.Escala.de_geojson(coropleta_con_valores([nil, nil])) == nil
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

      {:ok, _} =
        Sesiones.create_anotacion(scope, sesion, %{
          "lat" => 20.67,
          "lon" => -103.35,
          "texto" => "aquí"
        })

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

    test "un rango de fechas deja solo esos renglones en el plano", %{conn: conn, scope: scope} do
      fila = fn fecha ->
        %{"lat" => 20.6, "lon" => -103.3, "datos" => %{"tienda" => "x", "fecha" => fecha}}
      end

      capa =
        capa_fixture(
          scope,
          "puntos",
          [fila.("2024-03-15"), fila.("2025-01-02"), fila.("2025")],
          %{
            columnas: ["tienda", "fecha"],
            fechas: ["fecha"]
          }
        )

      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{puntos: [_, _, _]})

      html =
        lv
        |> form("#fechas_#{capa.id}", %{columna: "fecha", desde: "2025-01-01", hasta: ""})
        |> render_change()

      assert_push_event(lv, "capa_propios", %{puntos: [_, _]})
      assert html =~ "2 en el rango"

      # Al revés no hace nada: sigue lo de antes.
      lv
      |> form("#fechas_#{capa.id}", %{columna: "fecha", desde: "2025-02-01", hasta: "2025-01-01"})
      |> render_change()

      refute_push_event(lv, "capa_propios", %{})
    end

    test "la procedencia va aparte en la ficha, en su orden", %{conn: conn, scope: scope} do
      fila = %{
        "lat" => 20.6,
        "lon" => -103.3,
        "datos" => %{"tienda" => "Centro", "url" => "https://x.mx", "fuente" => "INEGI"}
      }

      capa = capa_fixture(scope, "puntos", [fila], %{columnas: ["url", "tienda", "fuente"]})
      stub_estados_y_municipio(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{puntos: [%{id: id}]})

      render_hook(element(lv, "#mapa-tecnico"), "ver_fila", %{"capa" => capa.id, "id" => id})

      assert_reply(lv, %{
        campos: [["tienda", "Centro"]],
        procedencia: [["fuente", "INEGI"], ["url", "https://x.mx"]]
      })
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

    test "si sacan a la persona del equipo, repintar ya no trae datos", %{
      conn: conn,
      scope: scope
    } do
      capa = capa_fixture(scope, "municipio", [zona("14039", 10)])

      stub_estados_y_municipio(fn conn ->
        Req.Test.json(conn, %{"features" => [feature("14039")]})
      end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?#{[capa: capa.id]}")
      assert_push_event(lv, "capa_propios", %{escala: nil})

      Mapo.Repo.delete_all(Mapo.Teams.Membership)
      render_change(lv, "pintar_capa", %{"capa" => capa.id, "columna" => "ventas"})
      refute_push_event(lv, "capa_propios", %{})
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
      assert_push_event(lv, "capa_propios", %{escala: nil})

      html =
        lv
        |> form("#pintar_#{capa.id}")
        |> render_change(%{"capa" => capa.id, "columna" => "ventas"})

      assert html =~ "Sin dato: 1"
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
      assert_push_event(lv, "capa_propios", %{escala: nil})
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
      assert html =~ "a 7"
      refute html =~ "Sin dato"
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

      # Una capa de antes de guardar valores lo dice en vez de inventar uno.
      render_hook(element(lv, "#mapa-tecnico"), "ver_fila", %{
        "capa" => capa.id,
        "lat" => 20.5,
        "lon" => -103.5
      })

      assert_reply(lv, %{campos: [["valor", "se subió antes" <> _]]})

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

  describe "vivienda por municipio" do
    defp catalogo_vivienda do
      %{
        "indicadores" => [
          %{
            "clave" => "eic_alqui",
            "fuente" => "INEGI · Intercensal 2025",
            "etiqueta" => "Viviendas rentadas",
            "unidad" => "% de las habitadas"
          },
          %{
            "clave" => "sniiv_acciones",
            "fuente" => "SNIIV · Financiamientos",
            "etiqueta" => "Créditos y subsidios otorgados",
            "unidad" => "acciones en el año"
          }
        ],
        "segmentos" => ["Media", "Residencial"],
        "anios_sniiv" => [%{"anio" => 2026, "meses" => 8}, %{"anio" => 2025, "meses" => 12}]
      }
    end

    defp municipios_vivienda(conn) do
      Req.Test.json(conn, %{
        "type" => "FeatureCollection",
        "features" => [
          %{
            "properties" => %{"cve_mun" => "039", "valor_choropleth" => 34.1, "cv" => 3.3},
            "geometry" => %{}
          },
          %{"properties" => %{"cve_mun" => "098", "valor_choropleth" => nil}, "geometry" => %{}}
        ],
        "indicador" => hd(catalogo_vivienda()["indicadores"]),
        "nivel" => "municipio",
        "metodo" => "Estimación por muestra de la Intercensal 2025."
      })
    end

    defp ficha(conn) do
      Req.Test.json(conn, %{
        "nombre" => "Guadalajara",
        "shf" => %{
          "nivel" => "municipio",
          "nombre" => "Guadalajara",
          "serie" => [[2005, 1, 50.0], [2026, 2, 238.62]],
          "ultimo" => %{"anio" => 2026, "trimestre" => 2, "indice" => 238.62},
          "variacion_anual" => 9.64
        },
        "sniiv" => %{
          "anio" => 2025,
          "segmentos" => [
            %{
              "segmento" => "No disponible",
              "acciones" => 1011,
              "monto" => 40500.0,
              "con_monto" => 3,
              "promedio" => 13500.0
            }
          ],
          "destinos" => [["Mejoramientos", 1007]]
        },
        "eic" => [
          %{
            "indicador" => "PCN_VPH_ALQUI",
            "etiqueta" => "Rentadas",
            "unidad" => "% de las habitadas",
            "valor" => 34.1,
            "cv" => 3.3,
            "nota" => nil
          },
          %{
            "indicador" => "PCN_VPH_NOESCRI",
            "etiqueta" => "Sin escrituras",
            "unidad" => "% de las propias",
            "valor" => nil,
            "cv" => nil,
            "nota" => "MI"
          }
        ],
        "envi" => [
          %{
            "indicador" => "renta_mensual_mediana",
            "etiqueta" => "Renta mensual, mediana",
            "unidad" => "pesos",
            "valor" => 2000.0,
            "error_estandar" => nil
          }
        ]
      })
    end

    defp montar_vivienda(
           conn,
           extra \\ fn conn -> raise "no debería llamarse: #{conn.request_path}" end
         ) do
      lv =
        montar_con_ubicacion(conn, fn conn ->
          case conn.request_path do
            "/vivienda/catalogo" -> Req.Test.json(conn, catalogo_vivienda())
            "/vivienda/municipios" -> municipios_vivienda(conn)
            "/vivienda/ficha" -> ficha(conn)
            _ -> extra.(conn)
          end
        end)

      lv |> element(".pestana[aria-controls=cinta-vivienda]") |> render_click()
      lv
    end

    test "abrir la cinta trae el catálogo por fuente; año y segmento solo con el SNIIV", %{
      conn: conn
    } do
      lv = montar_vivienda(conn)
      html = render(lv)

      assert html =~ ~s(<optgroup label="INEGI · Intercensal 2025">)
      refute html =~ "Último completo"

      html =
        lv
        |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "sniiv_acciones"})
        |> render_change()

      assert html =~ "Último completo"
      assert html =~ "2026 (8 de 12 meses)"
    end

    test "poner pinta el acetato con su método y deja los sin dato aparte", %{conn: conn} do
      lv = montar_vivienda(conn)

      html =
        lv
        |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
        |> render_submit()

      assert_push_event(lv, "capa_vivienda", %{activa: true, etiqueta: "Viviendas rentadas"})
      assert html =~ "Estimación por muestra de la Intercensal 2025."
      assert html =~ "Sin dato: 1"
      # La Intercensal trae su CV: la confianza va como transparencia.
      assert html =~ "Precisión de la Intercensal"
    end

    test "con un indicador del censo no manda año ni segmento", %{conn: conn} do
      lv =
        montar_con_ubicacion(conn, fn conn ->
          case conn.request_path do
            "/vivienda/catalogo" ->
              Req.Test.json(conn, catalogo_vivienda())

            "/vivienda/municipios" ->
              refute Map.has_key?(conn.params, "anio")
              refute Map.has_key?(conn.params, "segmento")
              municipios_vivienda(conn)
          end
        end)

      lv |> element(".pestana[aria-controls=cinta-vivienda]") |> render_click()

      lv
      |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
      |> render_submit(%{vivienda_capa: %{"anio" => "2025", "segmento" => "Media"}})

      assert_push_event(lv, "capa_vivienda", %{activa: true})
    end

    test "el clic en un municipio abre su ficha con cada fuente y su nivel", %{conn: conn} do
      lv = montar_vivienda(conn)

      lv
      |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
      |> render_submit()

      html = render_hook(lv, "ficha_vivienda", %{"cvegeo" => "14039"})

      assert html =~ "Guadalajara"
      assert html =~ "Del municipio"
      assert html =~ "9.6 %"
      assert html =~ "1,011 · $13,500 (3 con monto)"
      # Serie del SHF: la línea, la base 2018 y la tabla plegada.
      assert html =~ ~s(class="serie-linea")
      assert html =~ "Índice SHF de Guadalajara: de 50.0 en 2005 T1 a 238.6 en 2026 T2"
      assert html =~ "<title>2026 T2: 238.6</title>"
      assert html =~ "Ver la serie"
      assert html =~ "34.1 % · CV 3.3"
      assert html =~ "sin dato (MI)"
      assert html =~ "Del estado: la ENVI no llega a municipio."
      assert html =~ "$2,000"

      html = lv |> element("#ficha-vivienda button", "Cerrar") |> render_click()
      refute html =~ ~s(id="ficha-vivienda")
    end

    test "el precio de oferta va por AGEB y sin datos del estado lo dice", %{conn: conn} do
      precio = fn features ->
        fn conn ->
          case conn.request_path do
            "/vivienda/catalogo" ->
              Req.Test.json(conn, catalogo_vivienda())

            "/vivienda/municipios" ->
              Req.Test.json(conn, %{
                "type" => "FeatureCollection",
                "features" => features,
                "indicador" => %{
                  "clave" => "precio_ageb",
                  "fuente" => "IIEG, anuncios de venta · Mapo",
                  "etiqueta" => "Precio de oferta",
                  "unidad" => "pesos por vivienda, julio de 2024"
                },
                "nivel" => "AGEB",
                "metodo" => "Precio pedido por vivienda; no es precio de cierre ni avalúo."
              })
          end
        end
      end

      lv =
        montar_con_ubicacion(
          conn,
          precio.([
            %{
              "properties" => %{
                "cve_mun" => "039",
                "valor_choropleth" => 2_704_000,
                "fuente" => "anuncios"
              },
              "geometry" => %{}
            },
            %{"properties" => %{"cve_mun" => "098", "fuente" => "sin_base"}, "geometry" => %{}}
          ])
        )

      lv |> element(".pestana[aria-controls=cinta-vivienda]") |> render_click()

      html =
        lv
        |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
        |> render_submit(%{vivienda_capa: %{"indicador" => "precio_ageb"}})

      assert_push_event(lv, "capa_vivienda", %{activa: true, etiqueta: "Precio de oferta"})
      assert html =~ "por AGEB."
      assert html =~ "no es precio de cierre ni avalúo"
      assert html =~ "Toca una AGEB"
      assert html =~ "Sin dato: 1"
      assert html =~ "Precio estimado por rango"

      lv = montar_con_ubicacion(conn, precio.([]))
      lv |> element(".pestana[aria-controls=cinta-vivienda]") |> render_click()

      html =
        lv
        |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
        |> render_submit(%{vivienda_capa: %{"indicador" => "precio_ageb"}})

      assert html =~ "Todavía no hay precio de oferta por AGEB en esa zona."
    end

    test "quitar apaga el acetato y su ficha", %{conn: conn} do
      lv = montar_vivienda(conn)

      lv
      |> form("#vivienda_capa_form", vivienda_capa: %{"indicador" => "eic_alqui"})
      |> render_submit()

      render_hook(lv, "ficha_vivienda", %{"cvegeo" => "14039"})
      html = lv |> element("#cinta-vivienda button", "Quitar") |> render_click()

      assert_push_event(lv, "capa_vivienda", %{activa: false})
      refute html =~ ~s(id="ficha-vivienda")
    end

    test "sin mapo_core la cinta lo dice en vez de un formulario vacío", %{conn: conn} do
      lv =
        montar_con_ubicacion(conn, fn conn ->
          conn |> Plug.Conn.put_status(500) |> Req.Test.json(%{"detail" => "caído"})
        end)

      html = lv |> element(".pestana[aria-controls=cinta-vivienda]") |> render_click()

      assert html =~ "No se pudo leer la lista de indicadores"
    end
  end

  describe "enlace permanente y cómo citar" do
    defp stub_con_carga(extra) do
      stub_estados_y_municipio(fn conn ->
        case conn.request_path do
          "/fuentes/carga" -> Req.Test.json(conn, %{"cargada" => "2026-11-17"})
          _ -> extra.(conn)
        end
      end)
    end

    test "la URL reconstruye estado, municipio, acetato y cinta", %{conn: conn} do
      yo = self()

      stub_con_carga(fn conn ->
        assert conn.request_path == "/censo/choropleth"
        send(yo, {:censo, conn.query_string})
        Req.Test.json(conn, coleccion_con_una_feature())
      end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?ent=14&mun=039&censo=graproes&ver=coropleta")

      assert_receive {:censo, consulta}
      assert consulta =~ "indicador=graproes" and consulta =~ "zona=mun%3A14039"
      assert_push_event(lv, "zona_elegida", %{geojson: _})
      assert_push_event(lv, "capa_coropleta", %{activa: true})
      refute has_element?(lv, "#cinta-coropleta[hidden]")
      assert has_element?(lv, ".rotulo-titulo", "Guadalajara, Jalisco")
      assert has_element?(lv, "#coropleta_capa_form option[selected][value=graproes]")
    end

    test "parámetros raros caen al valor por defecto sin error", %{conn: conn} do
      # El catálogo de vivienda se pide para saber que "nada" no está en él.
      stub_con_carga(fn %{request_path: "/vivienda/catalogo"} = conn ->
        Req.Test.json(conn, %{"indicadores" => [], "segmentos" => [], "anios_sniiv" => []})
      end)

      {:ok, lv, _html} =
        live(
          conn,
          "/mapa?ent=99&mun=039&censo=x%27%3BDROP&viv=nada&alcance=a,b,c&piel=zzz&ver=propios&anio=1"
        )

      assert has_element?(lv, ".rotulo-titulo", "México")
      assert has_element?(lv, ".rotulo dd", "sin acetatos")
      refute render(lv) =~ "DROP"
    end

    test "un punto fuera de México o minutos de más no piden la isócrona", %{conn: conn} do
      stub_con_carga(fn _ -> raise "no debería llamarse" end)
      {:ok, lv, _html} = live(conn, "/mapa?alcance=40.7,-74.0,10")
      assert has_element?(lv, ".pestana[aria-controls=cinta-isocrona]", "en la charola")
      {:ok, lv, _html} = live(conn, "/mapa?alcance=20.67,-103.35,9999")
      assert has_element?(lv, ".pestana[aria-controls=cinta-isocrona]", "en la charola")
    end

    test "poner un acetato escribe la URL sin agregar historial", %{conn: conn} do
      stub_con_carga(fn conn -> Req.Test.json(conn, coleccion_con_una_feature()) end)
      {:ok, lv, _html} = live(conn, ~p"/mapa")

      elegir_zona(lv, "ent:14")
      assert_patch(lv, "/mapa?zona=ent:14")

      elegir_zona(lv, "mun:14039")
      assert_patch(lv, "/mapa?zona=mun:14039")

      lv
      |> form("#coropleta_capa_form", coropleta_capa: %{"indicador" => "pobtot"})
      |> render_submit()

      assert_patch(lv, "/mapa?zona=mun:14039&censo=pobtot")

      lv |> element("[phx-click='quitar_coropleta']") |> render_click()
      assert_patch(lv, "/mapa?zona=mun:14039")
    end

    test "los alcances guardan su punto y sus minutos; la cita lleva el censo si se contó", %{
      conn: conn
    } do
      stub_con_carga(fn conn ->
        case conn.request_path do
          "/isocronas/calcular" ->
            Req.Test.json(conn, %{"poligono" => %{}, "metodo" => "carretera_real"})

          "/isocronas/poblacion" ->
            Req.Test.json(conn, poblacion(2))
        end
      end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?alcance=20.67,-103.35,15;20.7,-103.4,30")

      refute_push_event(lv, "modo_isocrona", %{activo: true})
      assert_push_event(lv, "capa_isocrona", %{activa: true, isocronas: [_, _]})
      assert has_element?(lv, "#isocrona_capa_form input[value='30']")

      lv |> element("#citar-isocrona") |> render_click()
      assert has_element?(lv, "#cita-isocrona", "Colaboradores de OpenStreetMap")
      assert has_element?(lv, "#cita-isocrona", "15 min desde 20.67000, -103.35000; 30 min desde")
      assert has_element?(lv, "#cita-isocrona", "método carretera_real")
      assert has_element?(lv, "#cita-isocrona", "población dentro de cada alcance en auto")
    end

    test "la cita pone la fuente original primero, su versión y el enlace", %{conn: conn} do
      yo = self()

      stub_estados_y_municipio(fn
        %{request_path: "/fuentes/carga"} = conn ->
          send(yo, {:carga, conn.query_string})
          Req.Test.json(conn, %{"cargada" => "2026-11-17"})

        conn ->
          Req.Test.json(conn, coleccion_con_una_feature())
      end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?ent=14&censo=pobtot&ver=coropleta")

      lv |> element("#citar-coropleta") |> render_click()

      html = lv |> element("#cita-coropleta") |> render()
      assert html =~ "INEGI. (2021). Censo de Población y Vivienda 2020"

      assert html =~
               "Procesado por Mapo: Población total (personas) por AGEB, Jalisco; tabla cargada en Mapo el 2026-11-17."

      assert html =~ "@misc{inegi_censo2020_mapo_"
      assert html =~ "author = {{Instituto Nacional de Estadística y Geografía}}"
      assert html =~ "/mapa?zona=ent:14&amp;censo=pobtot&amp;ver=coropleta"
      assert_receive {:carga, consulta}
      assert consulta =~ "tabla=censo" and consulta =~ "cve_ent=14"

      # Otra vista ya no es lo que se citaba: la cita se cierra.
      lv |> element("[phx-click='quitar_coropleta']") |> render_click()
      refute has_element?(lv, "#cita-coropleta")
    end

    test "la sesión del equipo va en la barra pero no en el enlace de la cita", %{
      conn: conn,
      scope: scope
    } do
      team = Mapo.TeamsFixtures.team_fixture(scope, %{name: "Planeación"})
      sesion = Mapo.SesionesFixtures.sesion_fixture(scope, team, %{"nombre" => "Recorrido"})
      stub_con_carga(fn conn -> Req.Test.json(conn, coleccion_con_una_feature()) end)

      {:ok, lv, _html} = live(conn, ~p"/mapa?ent=14&municipios=1&sesion=#{sesion.id}")

      assert_push_event(lv, "capa_coloreado", %{activa: true})
      lv |> element(".pestana[aria-controls=cinta-coloreado]") |> render_click()
      lv |> element("#citar-coloreado") |> render_click()

      enlace = lv |> element("#cita-coloreado-enlace") |> render()
      assert enlace =~ "municipios=1"
      refute enlace =~ "sesion"
      assert has_element?(lv, "#cita-coloreado", "Marco Geoestadístico")
    end

    test "vivienda reconstruye indicador, año, segmento y ficha; la cita lleva las cuatro fuentes",
         %{conn: conn} do
      yo = self()

      stub_con_carga(fn conn ->
        case conn.request_path do
          "/vivienda/catalogo" ->
            Req.Test.json(conn, %{
              "indicadores" => [
                %{
                  "clave" => "sniiv_acciones",
                  "fuente" => "SNIIV",
                  "etiqueta" => "Créditos",
                  "unidad" => "acciones"
                }
              ],
              "segmentos" => ["Media"],
              "anios_sniiv" => [%{"anio" => 2025, "meses" => 12}]
            })

          "/vivienda/municipios" ->
            send(yo, {:vivienda, conn.query_string})

            Req.Test.json(conn, %{
              "type" => "FeatureCollection",
              "features" => [%{}],
              "indicador" => %{
                "clave" => "sniiv_acciones",
                "etiqueta" => "Créditos",
                "unidad" => "acciones"
              },
              "nivel" => "municipio",
              "anio" => 2025,
              "meses" => 12,
              "segmento" => "Media",
              "metodo" => "Suma de acciones."
            })

          "/vivienda/ficha" ->
            Req.Test.json(conn, %{"cve_mun" => "039", "nombre" => "Guadalajara"})
        end
      end)

      {:ok, lv, _html} =
        live(conn, ~p"/mapa?ent=14&viv=sniiv_acciones&anio=2025&seg=Media&ficha=039&ver=vivienda")

      assert_receive {:vivienda, consulta}
      assert consulta =~ "anio=2025" and consulta =~ "segmento=Media"
      assert has_element?(lv, "#ficha-vivienda", "Guadalajara")

      lv |> element("#citar-vivienda") |> render_click()
      html = lv |> element("#cita-vivienda") |> render()
      assert html =~ "Datos de 2025, segmento Media."
      assert html =~ "Índice SHF" and html =~ "Encuesta Intercensal 2025" and html =~ "ENVI"
      assert html =~ "ficha de vivienda de Guadalajara"
    end

    test "un año o segmento fuera del catálogo no llega a mapo_core", %{conn: conn} do
      yo = self()

      stub_con_carga(fn conn ->
        case conn.request_path do
          "/vivienda/catalogo" ->
            Req.Test.json(conn, %{
              "indicadores" => [
                %{
                  "clave" => "sniiv_acciones",
                  "fuente" => "SNIIV",
                  "etiqueta" => "C",
                  "unidad" => "a"
                }
              ],
              "segmentos" => ["Media"],
              "anios_sniiv" => [%{"anio" => 2025, "meses" => 12}]
            })

          "/vivienda/municipios" ->
            send(yo, {:vivienda, conn.query_string})
            Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
        end
      end)

      {:ok, _lv, _html} = live(conn, "/mapa?ent=14&viv=sniiv_acciones&anio=1900&seg=%27x")

      assert_receive {:vivienda, consulta}
      refute consulta =~ "anio" or consulta =~ "segmento"
    end
  end
end
