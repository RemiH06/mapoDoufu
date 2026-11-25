defmodule MapoWeb.RiesgosLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.ZonaFixtures

  setup :register_and_log_in_user

  defp grupos(pob) do
    %{
      "POBTOT" => %{"etiqueta" => "personas", "valor" => pob, "reservados" => 0},
      "P_0A2" => %{"etiqueta" => "de 0 a 2 años", "valor" => 30, "reservados" => 4},
      "P_60YMAS" => %{"etiqueta" => "de 60 años o más", "valor" => 90, "reservados" => 0}
    }
  end

  defp gente(personas, total, corto) do
    %{
      "personas" => personas,
      "total" => total,
      "pct" => personas * 100 / total,
      "cuenta" => 1,
      "detalle" => "#{corto} en rojo",
      "corto" => corto,
      "sin_medicion" => false
    }
  end

  defp categoria(clave, texto) do
    %{
      "categoria" => clave,
      "texto" => texto,
      "severa" => 15,
      "cortes" => 119,
      "detalle" => "15 de 119 en D2+",
      "corto" => "15 de 119"
    }
  end

  # Dos municipios: uno con sitios de la red y otro sin medición, y con sequía distinta.
  defp metropoli do
    base = resultado(%{"tipo" => "metropoli", "clave" => "zm:14.1.01"})

    base
    |> put_in(["zona", "municipios"], [
      %{"cvegeo" => "14039", "nombre" => "Guadalajara", "poblacion" => 1_385_629},
      %{"cvegeo" => "14051", "nombre" => "Juanacatlán", "poblacion" => 30_855}
    ])
    |> update_in(["bloques"], fn [agua, sequia] ->
      [
        put_in(agua, ["medida", "municipios"], %{
          "14039" => gente(554_252, 1_385_629, "1 de 2"),
          "14051" => %{"sin_medicion" => true, "pct" => 0.0, "total" => 30_855}
        }),
        put_in(sequia, ["medida"], %{
          "tipo" => "categoria",
          "zona" => %{"categoria" => nil, "rango" => ["sin", "D2"], "detalle" => nil},
          "municipios" => %{
            "14039" => categoria("sin", "sin anomalía"),
            "14051" => categoria("D2", "sequía severa")
          }
        })
      ]
    end)
  end

  defp resultado(zona) do
    %{
      "zona" =>
        Map.merge(zona, %{
          "geojson" => %{
            "type" => "Polygon",
            "coordinates" => [[[-104, 19], [-104, 20], [-103, 20], [-104, 19]]]
          },
          "km2" => 705.1,
          "limites" => %{"type" => "FeatureCollection", "features" => []},
          "municipios" => [
            %{
              "cvegeo" => "14015",
              "cve_ent" => "14",
              "cve_mun" => "015",
              "nombre" => "Autlán de Navarro",
              "poblacion" => 64_931
            }
          ]
        }),
      "cerca_m" => 1000,
      "poblacion" => %{
        "agebs" => 33,
        "localidades" => 139,
        "grupos" => grupos(64_931),
        "urbanas_por_punto" => 1,
        "pob_urbanas_por_punto" => 12_500
      },
      "metodo_poblacion" => "AGEB urbanos y localidades del ITER.",
      "bloques" => [
        %{
          "clave" => "agua_superficial",
          "titulo" => "Calidad del agua superficial",
          "fuente" => "Conagua, RENAMECA",
          "fecha_dato" => "2012 a 2025",
          "nivel" => "punto (sitio de monitoreo)",
          "metodo" => "Semáforo de Conagua tal cual.",
          "hechos" => ["1 sitio dentro de la zona: 1 en rojo."],
          "poblacion_cerca" =>
            Map.put(
              %{"agebs" => 2, "localidades" => 1, "grupos" => grupos(1_575)},
              "frase",
              "viven a menos de 1,000 m de un sitio en rojo"
            ),
          "capa" => %{
            "type" => "FeatureCollection",
            "features" => [
              %{
                "type" => "Feature",
                "geometry" => %{"type" => "Point", "coordinates" => [-104.3, 19.7]},
                "properties" => %{"semaforo" => "ROJO"}
              }
            ]
          },
          "medida" => %{
            "tipo" => "gente",
            "zona" => gente(1_575, 64_931, "1 de 1"),
            "municipios" => %{"14015" => gente(1_575, 64_931, "1 de 1")}
          }
        },
        %{
          "clave" => "sequia",
          "titulo" => "Sequía",
          "fuente" => "SMN, Monitor de Sequía",
          "fecha_dato" => "2003 a 2026-10-31",
          "nivel" => "municipio",
          "metodo" => "Categoría del Monitor.",
          "hechos" => ["Autlán de Navarro: anormalmente seco al 2026-10-31."],
          "poblacion_cerca" => nil,
          "capa" => nil,
          "medida" => %{
            "tipo" => "categoria",
            "zona" => categoria("D0", "anormalmente seco"),
            "municipios" => %{"14015" => categoria("D0", "anormalmente seco")}
          }
        }
      ]
    }
  end

  defp stub(fun) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      responder_zona(conn) ||
        case conn.request_path do
          "/riesgos/zona" -> fun.(conn)
        end
    end)
  end

  defp sin_consulta, do: stub(fn _ -> raise "no debería consultar" end)

  defp autlan(conn),
    do: Req.Test.json(conn, resultado(%{"tipo" => "municipios", "cvegeos" => ["14015"]}))

  test "mounts with the zone selector", %{conn: conn} do
    sin_consulta()
    {:ok, _lv, html} = live(conn, ~p"/riesgos")

    assert html =~ "Riesgos de la zona"
    assert html =~ "Estado, municipio, metrópoli, colonia o CP"
    assert html =~ "sin índice"
  end

  test "elegir una zona consulta de una vez, con la clave de la zona", %{conn: conn} do
    stub(fn conn ->
      conn = Plug.Conn.fetch_query_params(conn)
      assert conn.query_params == %{"zona" => "mun:14015", "cerca_m" => "1000"}
      autlan(conn)
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    elegir_zona(lv, "Autlán")
    html = render_async(lv)

    assert html =~ "Riesgos de Autlán de Navarro"
    assert html =~ "Quién vive en Autlán de Navarro"
    assert html =~ "64,931"
    # En la lista, cada peligro con su cifra y su clase; el detalle, al abrirlo.
    assert has_element?(lv, "#bloque-agua_superficial .cotejo-ficha[data-clase='1']", "2.4 %")
    assert has_element?(lv, "#bloque-sequia .cotejo-ficha[data-color='D0']", "D0")
    refute has_element?(lv, "#bloque-agua_superficial .procedencia")

    html = lv |> element("#ver-poblacion") |> render_click()
    assert html =~ "en 4 de los 172"
    assert html =~ "12,500 personas son de 1 localidad urbana que cuenta entera por su punto"
    # La población no tiene capa: el plano se queda con todas.
    assert_push_event(lv, "solo", %{clave: nil})

    lv |> element("#ver-agua_superficial") |> render_click()
    assert_push_event(lv, "solo", %{clave: "agua_superficial"})
    assert_patch(lv, "/riesgos?zona=mun:14015&cerca=1000&peligro=agua_superficial")
    assert has_element?(lv, "#bloque-agua_superficial .procedencia", "Conagua, RENAMECA")

    assert has_element?(
             lv,
             "#bloque-agua_superficial .cerca",
             "1,575 personas de la zona viven a menos de 1,000 m"
           )

    lv |> element("#ver-sequia") |> render_click()
    assert has_element?(lv, "#bloque-sequia .metodo", "Categoría del Monitor")
    refute html =~ "expuest"

    assert_push_event(lv, "zona_elegida", %{geojson: _})
    assert_push_event(lv, "zona", %{capas: [%{clave: "agua_superficial"}], solo: nil})

    # Elegirlo otra vez los regresa todos.
    lv |> element("#ver-sequia") |> render_click()
    refute has_element?(lv, "#bloque-sequia .metodo")

    # Una clave que no es de un bloque no hace nada.
    render_click(lv, "ver", %{"clave" => "inventada"})
    refute has_element?(lv, ".cotejo-renglon.abierto")
  end

  describe "matriz y mapas" do
    test "varios municipios abren en matriz, cada celda con su clase y su cifra", %{conn: conn} do
      stub(fn conn -> Req.Test.json(conn, metropoli()) end)
      {:ok, lv, _} = live(conn, "/riesgos?zona=zm:14.1.01&cerca=1000")
      render_async(lv)

      assert has_element?(lv, "#vista-matriz[aria-pressed=true]")
      assert has_element?(lv, "#matriz-zona .cotejo-zona", "toda la zona")
      assert has_element?(lv, "#matriz-14039 td[data-clase='3']", "40 %")
      assert has_element?(lv, "#matriz-14039 td[data-clase='3']", "1 de 2")
      # Sin sitios de la red no hay medición: no es 0 %.
      assert has_element?(lv, "#matriz-14051 td[data-estado=rayada]", "sin red")
      assert has_element?(lv, "#matriz-14051 td[data-color=D2]", "D2")
      assert has_element?(lv, "#matriz-zona td[data-estado=plana]", "hasta D2")
      assert has_element?(lv, "#matriz-14039 .cotejo-gente", "1.4 M")

      lv |> element("#matriz button[phx-value-clave=sequia]") |> render_click()
      assert has_element?(lv, "#detalle h2", "Sequía")
      assert_push_event(lv, "solo", %{clave: "sequia"})
      assert_patch(lv, "/riesgos?zona=zm:14.1.01&cerca=1000&peligro=sequia")
    end

    test "los mapas chicos van en la URL y cada uno lleva su peligro al plano", %{conn: conn} do
      stub(&autlan/1)
      {:ok, lv, _} = live(conn, "/riesgos?zona=mun:14015&cerca=1000&vista=mapas")
      render_async(lv)

      assert has_element?(lv, "#mapas-chicos:not([hidden]) canvas[data-clave=agua_superficial]")
      lv |> element("#mapa-agua_superficial") |> render_click()
      assert_push_event(lv, "solo", %{clave: "agua_superficial"})
      assert has_element?(lv, "#mapa-agua_superficial.activa")

      lv |> element("#vista-lista") |> render_click()
      assert has_element?(lv, "#mapas-chicos[hidden]")
      assert_patch(lv, "/riesgos?zona=mun:14015&cerca=1000&peligro=agua_superficial")
    end

    test "una zona se deja fija para compararla con la siguiente", %{conn: conn} do
      stub(fn conn ->
        conn = Plug.Conn.fetch_query_params(conn)

        if conn.query_params["zona"] == "mun:14015",
          do: Req.Test.json(conn, resultado(%{"tipo" => "municipios", "clave" => "mun:14015"})),
          else: Req.Test.json(conn, metropoli())
      end)

      {:ok, lv, _} = live(conn, "/riesgos?zona=mun:14015&cerca=1000&vista=matriz")
      render_async(lv)
      lv |> element("#fijar") |> render_click()
      assert has_element?(lv, "#fijar[disabled]")
      # Fija y consultada: un solo renglón, no dos.
      refute has_element?(lv, "#matriz .cotejo-quitar")

      elegir_zona(lv, "zm:14.1.01")
      render_async(lv)
      assert has_element?(lv, "#matriz tr .cotejo-zona", "Autlán de Navarro")
      assert has_element?(lv, "#matriz-14039")

      lv |> element("#matriz .cotejo-quitar") |> render_click()
      refute has_element?(lv, "#matriz tr .cotejo-zona", "Autlán de Navarro")
    end

    test "otra cercanía vuelve a consultar y suelta las fijas", %{conn: conn} do
      yo = self()

      stub(fn conn ->
        conn = Plug.Conn.fetch_query_params(conn)
        send(yo, {:cerca, conn.query_params["cerca_m"]})

        Req.Test.json(
          conn,
          Map.put(
            resultado(%{"tipo" => "municipios", "clave" => "mun:14015"}),
            "cerca_m",
            String.to_integer(conn.query_params["cerca_m"])
          )
        )
      end)

      {:ok, lv, _} = live(conn, "/riesgos?zona=mun:14015&cerca=1000&vista=matriz")
      render_async(lv)
      assert_receive {:cerca, "1000"}

      lv |> element("#fijar") |> render_click()
      lv |> element("#ajustar") |> render_click()
      lv |> form("#riesgos_form", riesgos: %{cerca_m: "500"}) |> render_change()
      assert_receive {:cerca, "500"}
      render_async(lv)
      refute has_element?(lv, "#fijar[disabled]")
    end

    test "abrir en el mapa lleva la zona y el peligro elegido", %{conn: conn} do
      stub(&autlan/1)
      {:ok, lv, _} = live(conn, "/riesgos?zona=mun:14015&cerca=500")
      render_async(lv)

      assert has_element?(
               lv,
               "#abrir-mapa[href='/mapa?zona=mun:14015&riesgos=agua_superficial,agua_subterranea,descargas,retc,fuego&cerca=500&ver=riesgos']"
             )

      lv |> element("#ver-sequia") |> render_click()
      assert has_element?(lv, "#abrir-mapa[href*='riesgos=sequia&']")
    end
  end

  test "una colonia o un dibujo se consultan igual", %{conn: conn} do
    yo = self()

    stub(fn conn ->
      conn = Plug.Conn.fetch_query_params(conn)
      send(yo, {:zona, conn.query_params["zona"]})
      Req.Test.json(conn, resultado(%{"tipo" => "colonia"}))
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    elegir_zona(lv, "col:14098_0135")
    assert_receive {:zona, "col:14098_0135"}
    assert render_async(lv) =~ "Quién vive en Lopez Cotilla"

    # El plano manda los vértices al cerrar el dibujo.
    lv |> element("#zona-cambiar") |> render_click()
    lv |> element("#zona-dibujar") |> render_click()
    assert_push_event(lv, "dibujar_zona", %{destino: "#zona"})

    lv
    |> with_target("#zona")
    |> render_hook("poligono", %{"vertices" => [[-103.4, 20.6], [-103.3, 20.6], [-103.3, 20.7]]})

    assert_receive {:zona, "pol:-103.4,20.6;-103.3,20.6;-103.3,20.7"}
  end

  test "un dibujo que no sirve se dice y no consulta", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")

    html =
      lv |> with_target("#zona") |> render_hook("poligono", %{"vertices" => [[-103.4, 20.6]]})

    assert html =~ "Ese dibujo no sirve"

    html =
      lv
      |> with_target("#zona")
      |> render_hook("poligono", %{"vertices" => [["x", 1], [1, 2], [3, 4]]})

    assert html =~ "Ese dibujo no sirve"
  end

  test "a circle needs a point and sends lon, lat and radio in meters", %{conn: conn} do
    stub(fn conn ->
      conn = Plug.Conn.fetch_query_params(conn)
      assert %{"zona" => "cir:-104.3,19.7,2500", "cerca_m" => "500"} = conn.query_params

      Req.Test.json(
        conn,
        resultado(%{"tipo" => "circulo", "lon" => -104.3, "lat" => 19.7, "radio_m" => 2500})
      )
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    lv |> element("#modo-circulo") |> render_click()

    html =
      lv |> form("#riesgos_form", riesgos: %{radio_km: "2.5"}) |> render_submit()

    assert html =~ "Toca el plano para poner el centro"

    render_hook(lv, "punto", %{"lat" => 19.7, "lon" => -104.3})
    assert_push_event(lv, "previa", %{lat: 19.7, lon: -104.3})

    lv
    |> form("#riesgos_form", riesgos: %{radio_km: "2.5", cerca_m: "500"})
    |> render_submit()

    assert render_async(lv) =~ "Quién vive en el círculo de 2.5 km"
  end

  test "a radius out of range or an unknown distance is not sent", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")
    render_hook(lv, "punto", %{"lat" => 19.7, "lon" => -104.3})

    html = lv |> form("#riesgos_form", riesgos: %{radio_km: "80"}) |> render_submit()
    assert html =~ "El radio va de 0.1 a 25 km"

    html =
      render_submit(lv, "consultar", %{
        "riesgos" => %{"radio_km" => "2", "cerca_m" => "999"}
      })

    assert html =~ "Elige qué tan cerca contar"
  end

  test "sin zona el botón lo pide", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")

    assert lv |> form("#riesgos_form", riesgos: %{cerca_m: "1000"}) |> render_submit() =~
             "Elige una zona"
  end

  test "points that are not numbers are ignored", %{conn: conn} do
    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")

    render_hook(lv, "punto", %{"lat" => "x", "lon" => nil})
    refute render(lv) =~ "Centro en"
  end

  test "an error from mapo_core is said, not hidden", %{conn: conn} do
    stub(fn conn -> conn |> Plug.Conn.put_status(500) |> Req.Test.json(%{"detail" => "boom"}) end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    elegir_zona(lv, "Autlán")

    assert render_async(lv) =~ "No se pudo consultar la zona"
  end

  test "una zona muy grande dice por qué", %{conn: conn} do
    stub(fn conn ->
      conn
      |> Plug.Conn.put_status(422)
      |> Req.Test.json(%{"detail" => "la zona mide 78,601 km² y aquí se calcula hasta 5,000 km²"})
    end)

    {:ok, lv, _} = live(conn, ~p"/riesgos")
    elegir_zona(lv, "Jalisco")

    assert render_async(lv) =~ "La zona no sirve: la zona mide 78,601 km²"
  end

  test "la zona guardada abre la vista sin consultar sola", %{conn: conn} do
    stub(&autlan/1)
    {:ok, lv, _} = live(conn, ~p"/riesgos")
    elegir_zona(lv, "Autlán")
    render_async(lv)

    lv |> element("#zona-guardar") |> render_click()
    assert has_element?(lv, "#zona-olvidar", "Es tu zona")

    sin_consulta()
    {:ok, lv, _} = live(conn, ~p"/riesgos")
    assert has_element?(lv, "#zona .zona-nombre", "Autlán de Navarro")
    assert_push_event(lv, "zona_elegida", %{geojson: _})
    refute render(lv) =~ "Quién vive"

    lv |> element("#zona-olvidar") |> render_click()
    assert has_element?(lv, "#zona-guardar")
  end

  describe "enlace permanente y cómo citar" do
    test "consultar escribe la zona en la URL", %{conn: conn} do
      stub(&autlan/1)
      {:ok, lv, _} = live(conn, ~p"/riesgos")
      lv |> form("#riesgos_form", riesgos: %{cerca_m: "500"}) |> render_change()
      elegir_zona(lv, "Autlán")

      render_async(lv)
      assert_patch(lv, "/riesgos?zona=mun:14015&cerca=500")
    end

    test "abrir el enlace vuelve a consultar la misma zona", %{conn: conn} do
      yo = self()

      stub(fn conn ->
        conn = Plug.Conn.fetch_query_params(conn)
        send(yo, {:zona, conn.query_params})

        Req.Test.json(
          conn,
          resultado(%{"tipo" => "circulo", "lon" => -104.3, "lat" => 19.7, "radio_m" => 2500})
        )
      end)

      {:ok, lv, _} = live(conn, "/riesgos?zona=cir:-104.3,19.7,2500&cerca=250")

      assert_receive {:zona, %{"zona" => "cir:-104.3,19.7,2500", "cerca_m" => "250"}}
      assert render_async(lv) =~ "Quién vive en el círculo de 2.5 km"

      assert has_element?(
               lv,
               "#riesgos_form select[name='riesgos[cerca_m]'] option[selected][value='250']"
             )
    end

    test "los enlaces de antes de la zona común siguen abriendo", %{conn: conn} do
      yo = self()

      stub(fn conn ->
        conn = Plug.Conn.fetch_query_params(conn)
        send(yo, {:zona, conn.query_params["zona"]})
        autlan(conn)
      end)

      {:ok, lv, _} = live(conn, "/riesgos?modo=municipio&ent=14&mun=015&cerca=1000")
      assert_receive {:zona, "mun:14015"}
      assert render_async(lv) =~ "Quién vive en Autlán de Navarro"

      {:ok, _lv, _} = live(conn, "/riesgos?modo=circulo&lat=19.7&lon=-104.3&radio=2.5&cerca=250")
      assert_receive {:zona, "cir:-104.3,19.7,2500"}
    end

    test "una zona rara en la URL deja la hoja vacía sin consultar", %{conn: conn} do
      sin_consulta()

      for url <- [
            "/riesgos?modo=municipio&ent=14&mun=999",
            "/riesgos?modo=municipio&ent=99&mun=015",
            "/riesgos?zona=mun:99999",
            "/riesgos?zona=cir:abc,19.7,2000",
            "/riesgos?modo=circulo&lat=abc&lon=-104&radio=2",
            "/riesgos?modo=circulo&lat=19.7&lon=-104.3&radio=900",
            "/riesgos?modo=municipio&ent=14&mun=015&cerca=7"
          ] do
        {:ok, lv, html} = live(conn, url)
        refute html =~ "Quién vive"
        refute render(lv) =~ "Quién vive"
      end
    end

    test "cada bloque cita su fuente con la fecha del dato y el enlace", %{conn: conn} do
      stub(&autlan/1)
      {:ok, lv, _} = live(conn, "/riesgos?zona=mun:14015&cerca=1000")
      render_async(lv)

      lv |> element("#ver-sequia") |> render_click()
      lv |> element("#citar-sequia") |> render_click()
      html = lv |> element("#cita-sequia") |> render()
      assert html =~ "SMN, Conagua. (s. f.). Monitor de Sequía de México"
      assert html =~ "Datos de 2003 a 2026-10-31."
      assert html =~ "Procesado por Mapo: Sequía, Autlán de Navarro, por municipio."
      assert html =~ "/riesgos?zona=mun:14015&amp;cerca=1000&amp;peligro=sequia"

      lv |> element("#ver-agua_superficial") |> render_click()
      lv |> element("#citar-agua_superficial") |> render_click()
      refute has_element?(lv, "#cita-sequia")
      assert has_element?(lv, "#cita-agua_superficial", "RENAMECA")

      lv |> element("#ver-poblacion") |> render_click()
      lv |> element("#citar-poblacion") |> render_click()
      assert has_element?(lv, "#cita-poblacion", "Censo de Población y Vivienda 2020")

      # Una clave que no es de un bloque no tumba la vista.
      render_click(lv, "citar", %{"clave" => "inventada"})
      assert has_element?(lv, "#cita-poblacion")
    end
  end
end
