defmodule MapoWeb.BuscadorLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  setup :register_and_log_in_user

  @catalogo %{
    "intenciones" => [
      %{
        "intencion" => "donde_poner",
        "nombre" => "Dónde poner",
        "huecos" => ["rubro", "municipios"]
      },
      %{"intencion" => "cuantos", "nombre" => "Contar", "huecos" => ["rubro", "municipios"]},
      %{
        "intencion" => "cuantos_cerca",
        "nombre" => "Contar cerca",
        "huecos" => ["rubro", "punto", "minutos"]
      },
      %{"intencion" => "perfil", "nombre" => "Perfil", "huecos" => ["municipio"]}
    ],
    "sectores" => [
      %{
        "sector" => "otros_comercios_al_menudeo",
        "nombre" => "Otros comercios",
        "rubros" => [%{"rubro" => "floreria", "nombre" => "Florería"}]
      }
    ],
    "edades" => [%{"edad" => "p_18a24", "nombre" => "18 a 24 años"}],
    "indicadores_zonas" => [
      %{"indicador" => "pobtot", "nombre" => "Población total"},
      %{"indicador" => "p_60ymas", "nombre" => "Población de 60 años o más"}
    ]
  }

  @plantilla_vacia %{
    "intencion" => nil,
    "rubro" => nil,
    "sector" => nil,
    "municipios" => [],
    "minutos" => nil,
    "edad" => nil,
    "solo_publicos" => false,
    "lat" => nil,
    "lon" => nil
  }

  defp feature(props), do: %{"type" => "Feature", "properties" => props, "geometry" => %{}}

  defp interpretacion(cambios, extra \\ %{}) do
    Map.merge(
      %{
        "plantilla" => Map.merge(@plantilla_vacia, cambios),
        "faltan" => [],
        "avisos" => [],
        "reconocidos" => []
      },
      extra
    )
  end

  defp resultado_donde_poner do
    %{
      "intencion" => "donde_poner",
      "capas" => %{
        "coropleta" => %{
          "geojson" => %{
            "type" => "FeatureCollection",
            "features" => [
              feature(%{"valor_choropleth" => 10}),
              feature(%{"valor_choropleth" => nil})
            ]
          },
          "indicador" => "pobtot",
          "etiqueta" => "Población total"
        },
        "voronoi" => %{"celdas" => %{"type" => "FeatureCollection", "features" => []}}
      },
      "cifras" => %{
        "que" => "Florería",
        "municipios" => [
          %{
            "cve_mun" => "120",
            "nombre" => "Zapopan",
            "negocios" => 305,
            "poblacion" => 1_476_491,
            "habitantes_por_negocio" => 4841
          }
        ],
        "total_negocios" => 305,
        "total_poblacion" => 1_476_491,
        "habitantes_por_negocio" => 4841,
        "formula" => "habitantes por negocio = población total ÷ negocios del rubro"
      },
      "avisos" => []
    }
  end

  defp zonas(cambios \\ %{}) do
    Map.merge(
      %{
        "indicador" => "pobtot",
        "etiqueta" => "Población total",
        "metodo" => "carretera_real",
        "criterios" => %{"minimo" => 2598, "minutos" => 2, "orden" => "indicador"},
        "total" => 540,
        "total_candidatas" => 1,
        "descartes" => %{"sin_dato" => 11, "por_indicador" => 264, "por_minutos" => 273},
        "filas" => [
          %{
            "cvegeo" => "1412000010001",
            "ageb" => "0001",
            "municipio" => "Zapopan",
            "lat" => 20.7,
            "lon" => -103.4,
            "valor" => 6240,
            "minutos" => 7.2
          }
        ],
        "cvegeos" => ["1412000010001"],
        "avisos" => []
      },
      cambios
    )
  end

  defp resolver_donde_poner(conn, opts \\ []) do
    plantilla = %{"intencion" => "donde_poner", "rubro" => "floreria", "municipios" => ["120"]}
    stub([interpretar: interpretacion(plantilla), resolver: resultado_donde_poner()] ++ opts)

    {:ok, view, _html} = live(conn, ~p"/buscador?q=florería en Zapopan")
    view |> form("#plantilla_form") |> render_submit()
    render_async(view)
    view
  end

  # Responde por ruta; `interpretar`, `resolver` y `zonas` cambian por test.
  defp stub(opts \\ []) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/geo/estados" ->
          Req.Test.json(conn, %{
            "features" => [feature(%{"cvegeo" => "14", "nomgeo" => "Jalisco"})]
          })

        "/geo/municipios" ->
          Req.Test.json(conn, %{
            "features" => [
              feature(%{"cve_mun" => "120", "nomgeo" => "Zapopan"}),
              feature(%{"cve_mun" => "039", "nomgeo" => "Guadalajara"})
            ]
          })

        "/buscador/catalogo" ->
          Req.Test.json(conn, @catalogo)

        "/buscador/interpretar" ->
          Req.Test.json(conn, opts[:interpretar] || interpretacion(%{}))

        "/buscador/zonas" ->
          {:ok, cuerpo, conn} = Plug.Conn.read_body(conn)
          if opts[:espia], do: send(opts[:espia], {:zonas, Jason.decode!(cuerpo)})

          case opts[:zonas] do
            {:status, status, respuesta} ->
              conn
              |> Plug.Conn.put_resp_content_type("application/json")
              |> Plug.Conn.send_resp(status, Jason.encode!(respuesta))

            respuesta ->
              Req.Test.json(conn, respuesta || zonas())
          end

        "/buscador/resolver" ->
          {:ok, cuerpo, conn} = Plug.Conn.read_body(conn)
          if opts[:espia], do: send(opts[:espia], {:resolver, Jason.decode!(cuerpo)})

          case opts[:resolver] do
            {:status, status, respuesta} ->
              conn
              |> Plug.Conn.put_resp_content_type("application/json")
              |> Plug.Conn.send_resp(status, Jason.encode!(respuesta))

            respuesta ->
              Req.Test.json(conn, respuesta)
          end
      end
    end)
  end

  defp pregunta(lv, texto) do
    lv |> form("#pregunta_form", pregunta: %{texto: texto}) |> render_submit()
    render(lv)
  end

  test "sin pregunta ofrece ejemplos y Resolver va apagado", %{conn: conn} do
    stub()
    {:ok, lv, html} = live(conn, ~p"/buscador")

    assert html =~ "¿Cuántas farmacias hay a 10 minutos de aquí?"
    assert has_element?(lv, "#plantilla_form button[disabled]", "Resolver")
  end

  test "sin mapo_core avisa y no truena", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, &Plug.Conn.send_resp(&1, 502, "{}"))
    {:ok, _lv, html} = live(conn, ~p"/buscador")

    assert html =~ "mapo_core no responde"
  end

  test "la pregunta llena la plantilla, va a la URL y dice lo que entendió", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(
          %{"intencion" => "donde_poner", "rubro" => "floreria", "municipios" => ["120"]},
          %{
            "reconocidos" => [
              %{
                "fragmento" => "floreria",
                "tipo" => "rubro",
                "clave" => "floreria",
                "nombre" => "Florería"
              }
            ]
          }
        )
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    html = pregunta(lv, "¿Dónde pongo una florería en Zapopan?")

    assert_patch(lv, ~p"/buscador?#{[q: "¿Dónde pongo una florería en Zapopan?"]}")
    assert html =~ "Entendí:"
    assert has_element?(lv, ~s(select[name="plantilla[que]"] option[selected]), "Florería")
    assert has_element?(lv, ".recorte", "Zapopan")
    refute has_element?(lv, "#plantilla_form button[disabled]")
  end

  test "con ?q= en la URL interpreta al abrir", %{conn: conn} do
    stub(interpretar: interpretacion(%{"intencion" => "perfil", "municipios" => ["120"]}))
    {:ok, lv, _html} = live(conn, ~p"/buscador?#{[q: "¿Cómo es Zapopan?"]}")

    assert has_element?(lv, ~s(select[name="plantilla[municipio]"] option[selected]), "Zapopan")
  end

  test "los avisos del analizador se muestran y el hueco vacío se pide", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "donde_poner"}, %{
          "avisos" => ["Reconocí varios rubros (Papelería, Florería); elige uno."]
        })
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    html = pregunta(lv, "papelería o florería")

    assert html =~ "Reconocí varios rubros"
    assert html =~ "Falta: el rubro, al menos un municipio."
    assert has_element?(lv, "#plantilla_form button[disabled]")
  end

  test "la plantilla se llena a mano y se resuelve con lo elegido", %{conn: conn} do
    stub(resolver: resultado_donde_poner(), espia: self())
    {:ok, lv, _html} = live(conn, ~p"/buscador")

    lv |> element("#plantilla_form") |> render_change(%{plantilla: %{intencion: "donde_poner"}})

    lv
    |> element("#plantilla_form")
    |> render_change(%{plantilla: %{que: "rubro:floreria", agregar: "120"}})

    lv
    |> element("#plantilla_form")
    |> render_change(%{plantilla: %{municipios: ["120"], agregar: "039"}})

    assert has_element?(lv, ".recorte", "Guadalajara")

    lv |> element("#plantilla_form") |> render_submit()
    html = render_async(lv)

    assert_receive {:resolver, %{"cve_ent" => "14", "plantilla" => plantilla}}
    assert plantilla["rubro"] == "floreria"
    assert plantilla["municipios"] == ["120", "039"]

    assert html =~ "4,841"
    assert html =~ "población total ÷ negocios del rubro"
    assert_push_event(lv, "capa_coropleta", %{activa: true, cortes: [10, 10, 10, 10]})
    assert_push_event(lv, "capa_voronoi", %{activa: true})
    assert_push_event(lv, "capa_puntos", %{activa: false})
    assert_push_event(lv, "piel", %{piel: "comercio"})
  end

  test "quitar un municipio apaga Resolver si era el único", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "cuantos", "rubro" => "floreria", "municipios" => ["120"]})
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "florerías en Zapopan")

    lv |> element(~s(button[phx-value-cve="120"])) |> render_click()

    refute has_element?(lv, ".recorte button")
    assert has_element?(lv, "#plantilla_form button[disabled]")
  end

  test "un municipio ajeno al estado no entra a la plantilla", %{conn: conn} do
    stub()
    {:ok, lv, _html} = live(conn, ~p"/buscador")

    lv |> element("#plantilla_form") |> render_change(%{plantilla: %{intencion: "cuantos"}})
    lv |> element("#plantilla_form") |> render_change(%{plantilla: %{agregar: "999"}})

    refute has_element?(lv, ".recorte")
  end

  test "cambiar de estado vacía los municipios de la plantilla", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "cuantos", "rubro" => "floreria", "municipios" => ["120"]})
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "florerías en Zapopan")

    lv |> element("#estado_form") |> render_change(%{cve_ent: "14"})

    refute has_element?(lv, ".recorte button")
  end

  test "cuantos_cerca toma el punto del clic en el plano", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "cuantos_cerca", "rubro" => "floreria", "minutos" => 10}),
      resolver: %{
        "intencion" => "cuantos_cerca",
        "capas" => %{
          "isocrona" => %{"poligono" => %{}, "metodo" => "osrm_real"},
          "puntos" => [%{"lat" => 20.6, "lon" => -103.3, "nombre" => "Flores"}]
        },
        "cifras" => %{
          "que" => "Florería",
          "total_negocios" => 1,
          "minutos" => 10,
          "metodo" => "osrm_real"
        },
        "avisos" => ["Solo cuentan los negocios que traen ubicación en DENUE."]
      },
      espia: self()
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    html = pregunta(lv, "florerías a 10 minutos de aquí")

    assert_push_event(lv, "modo_isocrona", %{activo: true})
    assert html =~ "Falta: el punto de partida."

    render_hook(lv, "click_mapa", %{"lat" => 20.6767, "lon" => -103.3475})
    assert_push_event(lv, "centrar", %{zoom: 12})

    lv |> element("#plantilla_form") |> render_submit()
    html = render_async(lv)

    assert_receive {:resolver, %{"plantilla" => %{"lat" => 20.6767, "lon" => -103.3475}}}
    assert html =~ "por carretera real (OSRM)"
    assert html =~ "Solo cuentan los negocios"
    assert_push_event(lv, "capa_isocrona", %{"activa" => true, "metodo" => "osrm_real"})
    assert_push_event(lv, "capa_puntos", %{activa: true})
    assert_push_event(lv, "piel", %{piel: "movilidad"})
  end

  test "el clic en el plano no hace nada fuera de cuantos_cerca", %{conn: conn} do
    stub(interpretar: interpretacion(%{"intencion" => "cuantos", "rubro" => "floreria"}))
    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "cuántas florerías")

    render_hook(lv, "click_mapa", %{"lat" => 20.0, "lon" => -103.0})

    refute_push_event(lv, "centrar", %{})
  end

  test "si el navegador niega la ubicación se dice", %{conn: conn} do
    stub()
    {:ok, lv, _html} = live(conn, ~p"/buscador")

    assert render_hook(lv, "ubicacion_fallida", %{}) =~ "El navegador no dio la ubicación"
  end

  test "perfil lleva a /perfil del municipio", %{conn: conn} do
    stub(
      interpretar: interpretacion(%{"intencion" => "perfil", "municipios" => ["120"]}),
      resolver: %{"intencion" => "perfil", "perfil" => %{"cve_ent" => "14", "cve_mun" => "120"}}
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "¿Cómo es Zapopan?")

    lv |> element("#plantilla_form") |> render_submit()

    assert_redirect(lv, ~p"/perfil?#{[cve_ent: "14", cve_mun: "120"]}", 1000)
  end

  test "el 422 de mapo_core se muestra con su mensaje", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "cuantos", "rubro" => "floreria", "municipios" => ["120"]}),
      resolver:
        {:status, 422, %{"detail" => %{"mensaje" => "Algún municipio no está en la base."}}}
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "florerías en Zapopan")

    lv |> element("#plantilla_form") |> render_submit()

    assert render_async(lv) =~ "Algún municipio no está en la base."
  end

  test "si mapo_core cae al resolver se dice", %{conn: conn} do
    stub(
      interpretar:
        interpretacion(%{"intencion" => "cuantos", "rubro" => "floreria", "municipios" => ["120"]}),
      resolver: {:status, 500, %{}}
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "florerías en Zapopan")

    lv |> element("#plantilla_form") |> render_submit()

    assert render_async(lv) =~ "mapo_core no está disponible"
  end

  test "una respuesta sin dato dice sin dato, no cero", %{conn: conn} do
    resultado =
      resultado_donde_poner()
      |> put_in(["cifras", "municipios"], [
        %{
          "cve_mun" => "120",
          "nombre" => "Zapopan",
          "negocios" => 0,
          "poblacion" => nil,
          "habitantes_por_negocio" => nil
        }
      ])

    stub(
      interpretar:
        interpretacion(%{
          "intencion" => "donde_poner",
          "rubro" => "floreria",
          "municipios" => ["120"]
        }),
      resolver: resultado
    )

    {:ok, lv, _html} = live(conn, ~p"/buscador")
    pregunta(lv, "florerías en Zapopan")

    lv |> element("#plantilla_form") |> render_submit()

    assert render_async(lv) =~ "sin dato"
  end

  describe "zonas candidatas" do
    test "van con sus criterios, lo que quedó fuera y sin puntaje", %{conn: conn} do
      view = resolver_donde_poner(conn)
      html = render_async(view)

      assert html =~ "Zonas candidatas"
      assert html =~ "de 540 AGEB cumplen"
      assert html =~ "Zapopan · 0001"
      assert html =~ "264 por el indicador"
      assert html =~ "273 por los minutos"
      assert html =~ "11"
      assert has_element?(view, ~s(input[name="criterios[minimo]"][value="2598"]))
      assert has_element?(view, ~s(input[name="criterios[minutos]"][value="2"]))
      assert_push_event(view, "capa_zonas", %{activa: true, cvegeos: ["1412000010001"]})
      refute html =~ "puntaje"
    end

    test "mover un criterio vuelve a pedirlas con lo elegido", %{conn: conn} do
      view = resolver_donde_poner(conn, espia: self())
      assert_receive {:zonas, %{"minimo" => nil, "minutos" => nil}}
      render_async(view)

      view
      |> form("#criterios_form", criterios: %{minimo: "4000", minutos: "5", orden: "minutos"})
      |> render_change()

      assert_receive {:zonas, %{"minimo" => 4000, "minutos" => 5, "orden" => "minutos"}}
    end

    test "cambiar de indicador regresa el mínimo a su mediana", %{conn: conn} do
      view = resolver_donde_poner(conn, espia: self())
      assert_receive {:zonas, _}
      render_async(view)

      view |> form("#criterios_form", criterios: %{indicador: "p_60ymas"}) |> render_change()

      assert_receive {:zonas, %{"indicador" => "p_60ymas", "minimo" => nil, "minutos" => 2}}
    end

    test "el límite de AGEB se muestra sin tirar la respuesta", %{conn: conn} do
      view =
        resolver_donde_poner(conn,
          zonas: {:status, 422, %{"detail" => %{"mensaje" => "Elige menos municipios."}}}
        )

      html = render_async(view)
      assert html =~ "Elige menos municipios."
      assert html =~ "Florería"
    end

    test "sin mapo_core avisa sin tirar la respuesta", %{conn: conn} do
      view = resolver_donde_poner(conn, zonas: {:status, 502, %{}})

      html = render_async(view)
      assert html =~ "No se pudieron calcular las zonas candidatas."
      assert html =~ "305"
    end

    test "sin negocios en el estado no pide minutos", %{conn: conn} do
      vacia =
        zonas(%{
          "metodo" => "sin_negocios",
          "criterios" => %{"minimo" => 100, "minutos" => nil, "orden" => "indicador"},
          "avisos" => ["No hay negocios del rubro."]
        })

      view = resolver_donde_poner(conn, zonas: vacia)
      html = render_async(view)

      assert html =~ "cumplen el criterio"
      assert html =~ "No hay negocios del rubro."
      refute has_element?(view, ~s(input[name="criterios[minutos]"]))
    end

    test "ver una zona dibuja su isócrona con los minutos del criterio", %{conn: conn} do
      view = resolver_donde_poner(conn)
      render_async(view)
      prueba = self()

      Req.Test.stub(Mapo.MapoCore, fn conn ->
        {:ok, cuerpo, conn} = Plug.Conn.read_body(conn)

        if conn.request_path == "/buscador/zonas" do
          Req.Test.json(conn, zonas())
        else
          send(prueba, {:cerca, Jason.decode!(cuerpo)})

          Req.Test.json(conn, %{
            "intencion" => "cuantos_cerca",
            "capas" => %{
              "isocrona" => %{"poligono" => %{}, "metodo" => "osrm_real"},
              "puntos" => []
            },
            "cifras" => %{"total_negocios" => 0, "metodo" => "osrm_real"},
            "avisos" => []
          })
        end
      end)

      view |> element("button", "Ver") |> render_click()
      html = render_async(view)

      assert_receive {:cerca, %{"plantilla" => %{"intencion" => "cuantos_cerca", "minutos" => 2}}}
      assert html =~ "0 negocios a 2 minutos en auto de 0001"

      assert_push_event(view, "capa_isocrona", %{
        "activa" => true,
        "origen" => %{"lat" => 20.7, "lon" => -103.4}
      })

      view |> form("#criterios_form", criterios: %{minutos: "3"}) |> render_change()

      refute render(view) =~ "minutos en auto de 0001"
      assert_push_event(view, "capa_isocrona", %{activa: false})
    end
  end
end
