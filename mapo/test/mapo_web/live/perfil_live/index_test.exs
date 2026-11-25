defmodule MapoWeb.PerfilLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest

  doctest MapoWeb.PerfilDocumentos, import: true

  setup :register_and_log_in_user

  @contorno %{
    "type" => "Polygon",
    "coordinates" => [[[-103.4, 20.6], [-103.3, 20.6], [-103.3, 20.7], [-103.4, 20.6]]]
  }

  defp zona(cambios \\ %{}) do
    Map.merge(
      %{
        "clave" => "mun:14039",
        "tipo" => "municipios",
        "nombre" => "Guadalajara",
        "detalle" => "Jalisco",
        "km2" => 151.0,
        "municipios" => [%{"cvegeo" => "14039", "nombre" => "Guadalajara"}],
        "estados" => ["14"],
        "geojson" => @contorno,
        "aviso" => nil
      },
      cambios
    )
  end

  defp colonia do
    zona(%{
      "clave" => "col:14039_0010",
      "tipo" => "colonia",
      "nombre" => "Americana",
      "detalle" => "Colonia · Guadalajara, Jalisco",
      "km2" => 1.43
    })
  end

  defp demografia(cambios \\ %{}) do
    Map.merge(
      %{
        "pobtot" => 1_500_000,
        "pobfem" => 800_000,
        "pobmas" => 700_000,
        "densidad" => 9_178.9,
        "graproes" => 10.5,
        "pea" => 700_000,
        "pocupada" => 650_000,
        "pdesocup" => 50_000,
        "tothog" => 400_000,
        "menores15_pct" => 19.6,
        "mayores60_pct" => 17.2,
        "nacidos_fuera_pct" => 11.5,
        "sin_salud_pct" => 27.0,
        "pea_pct" => 64.0,
        "piramide" => [
          %{"etiqueta" => "0 a 5", "anios" => 6, "F" => 60_000, "M" => 62_000},
          %{"etiqueta" => "60 o más", "anios" => 25, "F" => 150_000, "M" => 100_000}
        ],
        "reservados" => 0,
        "estimada" => false,
        "error_pct" => nil,
        "metodo" => "Censo 2020."
      },
      cambios
    )
  end

  defp empleo(cambios \\ %{}) do
    Map.merge(
      %{
        "periodo" => "2024-12-31",
        "puestos" => 694_493,
        "permanentes" => 610_000,
        "eventuales" => 84_493,
        "salario_diario" => 612.4,
        "parte_rango_tope" => 2.8,
        "por_division" => [
          %{"division" => "8", "nombre" => "Servicios para empresas", "puestos" => 250_000}
        ],
        "anual" => nil,
        "puestos_estado_sin_municipio" => 0
      },
      cambios
    )
  end

  defp servicio(clave, titulo, cambios) do
    Map.merge(
      %{
        "clave" => clave,
        "titulo" => titulo,
        "grupo_etiqueta" => "personas",
        "calculado" => true,
        "parcial" => false,
        "tramos" => [80, 15, 5],
        "con_ruta" => 100,
        "sin_ruta" => 0,
        "sin_calcular" => 0,
        "cerca_pct" => 80.0
      },
      cambios
    )
  end

  defp perfil(zona, cambios \\ %{}) do
    Map.merge(
      %{
        "zona" => Map.put(zona, "entera", zona["tipo"] in ~w(municipios metropoli estado)),
        "agebs" => 3,
        "localidades" => 1,
        "demografia" => demografia(),
        "rezago_social" => %{
          "grados" => [%{"grado" => "Bajo", "agebs" => 265, "personas" => 956_112}]
        },
        "vivienda" => %{
          "total" => 500_000,
          "habitadas" => 400_000,
          "deshabitadas" => 50_000,
          "temporales" => 9_000,
          "deshabitadas_pct" => 10.2,
          "ocupantes" => 3.46,
          "bienes" => [
            %{"clave" => "VPH_INTER", "etiqueta" => "Internet", "pct" => 77.7},
            %{"clave" => "VPH_PC", "etiqueta" => "Computadora", "pct" => nil}
          ],
          "precio" => %{
            "mediana" => 2_800_000.0,
            "bajo" => 570_000.0,
            "alto" => 43_000_000.0,
            "agebs" => 13,
            "agebs_zona" => 15
          },
          "tenencia" => [%{"nombre" => "Guadalajara", "propias" => 50.1, "rentadas" => 34.1}]
        },
        "servicios" => [
          servicio("centro_salud", "Centro de salud", %{}),
          servicio("primaria_publica", "Primaria pública", %{
            "parcial" => true,
            "cerca_pct" => nil,
            "con_ruta" => 337,
            "sin_calcular" => 3_572
          }),
          servicio("supermercado", "Supermercado", %{"sin_calcular" => 60}),
          %{
            "clave" => "parada_transporte",
            "titulo" => "Parada de transporte público",
            "grupo_etiqueta" => "personas",
            "calculado" => false
          }
        ],
        "comercio" => %{
          "total_negocios" => 3_200,
          "top_clases_actividad" => [["Comercio al por menor de abarrotes", 450]],
          "sectores" => [["Comercio al por menor", 2_000], ["Alojamiento y comida", 1_200]],
          "sin_sector" => 0,
          "estratos" => [["0 a 5 personas", 3_000], ["251 y más personas", 200]],
          "estados_sin_denue" => []
        },
        "economia" => %{
          "anio_datos" => 2023,
          "total" => %{
            "ue" => 89_635.0,
            "personal" => 631_859.0,
            "remuneraciones" => 74_677.3,
            "ingresos" => 786_162.1,
            "vacb" => 270_495.7
          },
          "sectores" => [
            %{"sector" => "46", "nombre" => "Comercio al por menor", "personal" => 145_871.0},
            %{"sector" => "55", "nombre" => "Corporativos", "personal" => nil}
          ],
          "reservados" => 1
        },
        "consumo" => %{
          "zona" => %{
            "n_hogares_muestra" => 12,
            "promedio_ponderado" => 476.23,
            "mediana" => 410.0
          },
          "estado" => %{
            "n_hogares_muestra" => 2_604,
            "promedio_ponderado" => 613.87,
            "mediana" => 490.56
          }
        },
        "seguridad" => %{
          "anio" => 2025,
          "meses" => 8,
          "total_delitos" => 320,
          "por_mil" => nil,
          "por_tipo" => [["Robo", 200], ["Homicidio", 20]],
          "serie" => [
            %{"anio" => 2024, "total" => 500, "meses" => 12},
            %{"anio" => 2025, "total" => 320, "meses" => 8}
          ]
        },
        "laboral" => %{"anio" => 2025, "trimestre" => "trim3", "tasa_desocupacion" => 2.49},
        "empleo_formal" => empleo(),
        "hacienda" => %{
          "anio" => 2023,
          "ultimo_publicado" => 2024,
          "total_ingresos" => 11_358_708_621.0,
          "total_egresos" => 11_358_708_621.0,
          "predial" => 1_548_431_223.0,
          "ingresos" => [["Participaciones federales", 5_178_362_442.0]],
          "egresos" => [["Servicios personales", 4_896_167_882.0]],
          "propios_pct" => 38.8,
          "transferencias_pct" => 60.5,
          "serie_propios" => [%{"anio" => 2023, "propios_pct" => 38.8}]
        },
        "planeacion" => %{
          "anio" => 2024,
          "principales" => [
            %{
              "nombre" => "Plan o programa de desarrollo urbano",
              "existio" => "sí",
              "vigencia" => "2045"
            },
            %{"nombre" => "Atlas de riesgos", "existio" => "no se sabe", "vigencia" => "NA"}
          ],
          "otros" => []
        },
        "plano" => %{
          "nivel" => "ageb",
          "type" => "FeatureCollection",
          "features" => [],
          "localidades" => []
        }
      },
      cambios
    )
  end

  defp variable(clave, area, cambios \\ %{}) do
    Map.merge(
      %{
        "clave" => clave,
        "area" => area,
        "etiqueta" => "Con internet",
        "unidad" => "%",
        "decimales" => 1,
        "log" => false,
        "valor" => 77.7,
        "banda" => %{
          "bajo" => 70.0,
          "alto" => 85.0,
          "p10" => 40.0,
          "p50" => 60.0,
          "p90" => 90.0,
          "min" => 10.0,
          "max" => 99.0,
          "comparadas" => 124
        }
      },
      cambios
    )
  end

  defp similares(cambios \\ %{}) do
    Map.merge(
      %{
        "motivo" => nil,
        "nivel" => "municipio",
        "nivel_nombre" => "municipios",
        "referencia" => %{
          "clave" => "mun:14039",
          "nombre" => "Guadalajara",
          "pobtot" => 1_500_000,
          "chica" => false
        },
        "areas" => [%{"clave" => "vivienda", "titulo" => "Vivienda"}],
        "comparadas" => 124,
        "estados" => ["Jalisco"],
        "min_poblacion" => nil,
        "calculado" => "2026-11-25",
        "fraccion" => 0.5,
        "variables" => [
          variable("internet", "vivienda"),
          variable("automovil", "vivienda", %{
            "etiqueta" => "Con automóvil",
            "valor" => nil,
            "banda" => nil
          })
        ],
        "resultados" => [
          %{
            "clave" => "mun:14120",
            "nombre" => "Zapopan",
            "detalle" => "Jalisco",
            "pobtot" => 1_476_491,
            "parecidas" => 1,
            "con_dato" => 1,
            "valores" => %{
              "internet" => %{"valor" => 81.2, "estado" => "parecida"},
              "automovil" => %{"valor" => 64.8, "estado" => "sin_dato"}
            }
          }
        ]
      },
      cambios
    )
  end

  defp stub(zonas, opciones \\ []) do
    prueba = self()
    por_clave = Map.new(zonas, &{&1["clave"], &1})

    Req.Test.stub(Mapo.MapoCore, fn conn ->
      case conn.request_path do
        "/zona/buscar" ->
          Req.Test.json(conn, %{
            "resultados" =>
              Enum.map(zonas, &(Map.take(&1, ~w(clave nombre detalle)) |> Map.put("tipo", "x"))),
            "aviso" => nil
          })

        "/zona/resolver" ->
          case por_clave[conn.params["clave"]] do
            nil ->
              conn
              |> Plug.Conn.put_status(404)
              |> Req.Test.json(%{"detail" => "nada"})

            z ->
              Req.Test.json(conn, z)
          end

        "/perfil_zona" ->
          send(prueba, {:perfil, conn.params["zona"]})

          case opciones[:perfil] do
            {status, detalle} ->
              conn |> Plug.Conn.put_status(status) |> Req.Test.json(%{"detail" => detalle})

            nil ->
              Req.Test.json(conn, perfil(por_clave[conn.params["zona"]]))

            cuerpo ->
              Req.Test.json(conn, cuerpo)
          end

        "/perfil_zona/similares" ->
          send(prueba, {:similares, conn.params})
          Req.Test.json(conn, opciones[:similares] || similares())
      end
    end)
  end

  defp abrir(conn, ruta) do
    {:ok, lv, _html} = live(conn, ruta)
    html = render_async(lv)
    {lv, html}
  end

  test "sin zona, invita a elegirla y no consulta", %{conn: conn} do
    stub([])
    {:ok, lv, html} = live(conn, ~p"/perfil")

    assert html =~ "Elige una zona"
    assert has_element?(lv, "#perfil-map[phx-hook=PerfilMapa]")
    refute has_element?(lv, "#documentos")
    refute_received {:perfil, _}
  end

  test "con mapo_core caído lo dice", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {_lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")
    assert html =~ "No se pudo consultar la zona"
  end

  test "elegir una zona la pone en la URL y pinta los ocho documentos", %{conn: conn} do
    stub([zona()])
    {:ok, lv, _html} = live(conn, ~p"/perfil")

    lv |> form("#zona-form", zona_q: %{q: "guada"}) |> render_change()
    lv |> form("#zona-form") |> render_submit()

    assert_patch(lv, "/perfil?zona=mun:14039")
    html = render_async(lv)

    assert_received {:perfil, "mun:14039"}
    assert_push_event(lv, "perfil_plano", %{zona: _, plano: %{"nivel" => "ageb"}})

    for {clave, _, _, _} <- MapoWeb.PerfilDocumentos.documentos(),
        do: assert(has_element?(lv, "#doc-#{clave} .notas"))

    assert html =~ "1,500,000"
    refute html =~ "≈"
    assert html =~ "2.49 %"
    assert html =~ "694,493"
    assert html =~ "diciembre de 2024"
    assert html =~ "falta el mismo mes del año anterior"
    assert has_element?(lv, "#ir-riesgos[href='/riesgos?zona=mun:14039']")
  end

  test "un enlace de antes de la 29h sigue abriendo", %{conn: conn} do
    stub([zona()])
    {lv, html} = abrir(conn, ~p"/perfil?cve_ent=14&cve_mun=039")

    assert_received {:perfil, "mun:14039"}
    assert html =~ "Gasto de los hogares"
    assert has_element?(lv, "h1", "Guadalajara")
  end

  test "una zona que no existe o es demasiado grande dice por qué", %{conn: conn} do
    stub([zona()])
    {_lv, html} = abrir(conn, ~p"/perfil?zona=mun:99999")
    assert html =~ "No hay nada cargado en Mapo con esa zona."

    stub([zona()], perfil: {422, "la zona mide 8,000 km²"})
    {lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")
    assert html =~ "la zona mide 8,000 km²"
    refute has_element?(lv, "#documentos")

    stub([zona()], perfil: {404, "nada"})
    {_lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")
    assert html =~ "Esa zona no toca nada cargado en Mapo."
  end

  test "una colonia va estimada y lo municipal dice que no es de ella", %{conn: conn} do
    estimada = %{"estimada" => true, "error_pct" => 13, "pobtot" => 3_973, "tothog" => 1_618}

    stub([colonia()],
      perfil: perfil(colonia(), %{"demografia" => demografia(estimada)})
    )

    {lv, html} = abrir(conn, ~p"/perfil?zona=col:14039_0010")

    assert html =~ "≈ 4,000"
    refute html =~ "3,973"
    assert has_element?(lv, "#perfil-estimada", "±13 %")
    assert has_element?(lv, "#doc-demografia .nivel", "De la zona")
    assert has_element?(lv, "#doc-seguridad .nivel.ajeno", "De Guadalajara entero, no de la zona")
    assert has_element?(lv, "#doc-laboral .nivel.ajeno")
  end

  test "con menos de 100 personas avisa que ninguna cifra es de fiar", %{conn: conn} do
    chica = %{"estimada" => true, "error_pct" => nil, "pobtot" => 40}
    stub([colonia()], perfil: perfil(colonia(), %{"demografia" => demografia(chica)}))

    {_lv, html} = abrir(conn, ~p"/perfil?zona=col:14039_0010")
    assert html =~ "ninguna cifra del censo es de fiar"
  end

  test "los servicios no confunden lo no calculado con lo lejos", %{conn: conn} do
    stub([zona()])
    {lv, _html} = abrir(conn, ~p"/perfil?zona=mun:14039")

    assert has_element?(lv, "#doc-servicios", "80.0 %")
    assert has_element?(lv, "#doc-servicios", "solo se calcula para 337 de 3,909")
    # 60 de 160 sin calcular: la cifra dice de cuánta gente es.
    assert has_element?(lv, "#doc-servicios", "calculado para 100 de 160")

    assert has_element?(
             lv,
             "#doc-servicios .falta",
             "Aquí no se calcula: parada de transporte público"
           )
  end

  test "cada documento dice cuando su fuente no cubre la zona", %{conn: conn} do
    stub([zona()],
      perfil:
        perfil(zona(), %{
          "demografia" => nil,
          "vivienda" => nil,
          "servicios" => [],
          "comercio" => nil,
          "economia" => nil,
          "consumo" => nil,
          "seguridad" => nil,
          "laboral" => nil,
          "empleo_formal" => nil,
          "hacienda" => nil,
          "planeacion" => nil,
          "rezago_social" => nil
        })
    )

    {_lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")

    assert html =~ "El censo no tiene datos de esta zona."
    assert html =~ "El censo no tiene viviendas de esta zona."
    assert html =~ "Los minutos a pie todavía no se calculan para este estado."
    assert html =~ "El DENUE de este estado no está cargado en Mapo."
    assert html =~ "La muestra de la ENIGH no llegó a Guadalajara."
    assert html =~ "No hay incidencia del SESNSP cargada para Guadalajara."
    assert html =~ "No hay datos de la ENOE cargados para este estado."
    assert html =~ "No hay datos del IMSS cargados para este estado."
    assert html =~ "No hay finanzas municipales cargadas."
  end

  test "lo reservado no es cero, y un año incompleto se dice", %{conn: conn} do
    stub([zona()])
    {lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")

    assert html =~ "631,859"
    refute html =~ "631,859.0"
    assert html =~ "Comercio al por menor (23.1 %)"
    assert html =~ "reservado"
    assert html =~ "INEGI reserva el personal de 1 sector"
    assert html =~ "11,358.7"
    assert html =~ "38.8 %"
    assert html =~ "El municipio no reportó 2024"
    assert html =~ "956,112 personas en 265 AGEB"
    assert html =~ "vigente hasta 2045"
    assert html =~ "no se sabe"
    assert html =~ "(8 meses)"
    assert has_element?(lv, "#doc-seguridad .columnas i.incompleto")
  end

  test "varios municipios se suman y cada hacienda lleva su año", %{conn: conn} do
    varios =
      zona(%{
        "clave" => "mun:14039,14120",
        "nombre" => "Guadalajara y Zapopan",
        "municipios" => [
          %{"cvegeo" => "14039", "nombre" => "Guadalajara"},
          %{"cvegeo" => "14120", "nombre" => "Zapopan"}
        ]
      })

    stub([varios],
      perfil:
        perfil(varios, %{
          "hacienda" => %{
            "varios" => true,
            "anio" => 2023,
            "municipios" => 2,
            "reportaron" => 1,
            "total_ingresos" => 1_000_000_000.0,
            "propios_pct" => 40.0,
            "predial" => 100_000_000.0,
            "tabla" => [
              %{
                "cvegeo" => "14039",
                "nombre" => "Guadalajara",
                "anio" => 2023,
                "total" => 1_000_000_000.0,
                "propios_pct" => 40.0
              },
              %{
                "cvegeo" => "14120",
                "nombre" => "Zapopan",
                "anio" => nil,
                "total" => nil,
                "propios_pct" => nil
              }
            ]
          },
          "planeacion" => %{
            "varios" => true,
            "anio" => 2024,
            "principales" => [%{"nombre" => "Atlas de riesgos", "n" => 2, "si" => 1}]
          },
          "empleo_formal" =>
            empleo(%{
              "anual" => %{"periodo" => "2023-12-31", "puestos" => 680_000, "variacion" => 2.13}
            })
        })
    )

    {lv, html} = abrir(conn, "/perfil?zona=mun:14039,14120")

    assert html =~ "Suma de los 2 municipios"
    assert html =~ "1 de 2 municipios"
    assert has_element?(lv, "#doc-hacienda", "no reportó")
    assert has_element?(lv, "#doc-hacienda", "1 de 2")
    assert html =~ "2.13 % (desde diciembre de 2023)"
  end

  test "un estado que el IMSS no reparte por municipio lo dice", %{conn: conn} do
    sin = empleo(%{"puestos" => 0, "puestos_estado_sin_municipio" => 3_479_354})
    stub([zona()], perfil: perfil(zona(), %{"empleo_formal" => sin}))

    {_lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")
    assert html =~ "El IMSS no asigna municipio a 3,479,354 puestos"
  end

  describe "zonas que se parecen" do
    test "buscar va en la URL, con las áreas y el margen, y da el desglose", %{conn: conn} do
      stub([zona()])
      {lv, _html} = abrir(conn, ~p"/perfil?zona=mun:14039")

      refute has_element?(lv, "#similares-resultado")

      lv
      |> form("#similares-form", sim: %{areas: ["vivienda"], margen: "muy_cerca"})
      |> render_submit()

      assert_patch(lv, "/perfil?zona=mun:14039&parecidas=vivienda&margen=muy_cerca")
      render_async(lv)

      assert_received {:similares,
                       %{"areas" => "vivienda", "margen" => "muy_cerca", "donde" => "todo"}}

      # Buscar no vuelve a pedir el perfil.
      assert_received {:perfil, _}
      refute_received {:perfil, _}

      assert has_element?(lv, "#sim-mun_14120", "1 de 1 se parecen")
      assert has_element?(lv, "#sim-mun_14120 .sim-enlace[href='/perfil?zona=mun:14120']")
      refute has_element?(lv, ".sim-desglose")

      lv |> element("#ver-mun_14120") |> render_click()
      assert has_element?(lv, ".sim-desglose .regla-ref")
      assert has_element?(lv, ".sim-desglose tr[data-estado=parecida]", "81.2")
      assert has_element?(lv, ".sim-desglose tr[data-estado=sin_dato]", "sin dato")

      refute render(lv) =~ ~r/similitud|calificación|% parecid/i
    end

    test "el enlace con parecidas abre con la búsqueda hecha; lo raro cae a lo normal", %{
      conn: conn
    } do
      stub([zona()])

      {lv, _html} =
        abrir(conn, "/perfil?zona=mun:14039&parecidas=vivienda,inventada&margen=xx&donde=yy")

      assert_received {:similares,
                       %{"areas" => "vivienda", "margen" => "cerca", "donde" => "todo"}}

      assert has_element?(lv, "#similares-form input[value=vivienda][checked]")
    end

    test "una colonia no ofrece seguridad ni hacienda, y sí dónde buscar", %{conn: conn} do
      stub([colonia()])
      {lv, _html} = abrir(conn, ~p"/perfil?zona=col:14039_0010")

      refute has_element?(lv, "#similares-form input[value=seguridad]")
      assert has_element?(lv, "#similares-form select[name='sim[donde]']")
    end

    test "cuando no hay con qué comparar, dice por qué", %{conn: conn} do
      stub([zona()], similares: %{"motivo" => "No hay otro estado", "resultados" => []})
      {lv, _html} = abrir(conn, "/perfil?zona=mun:14039&parecidas=todas&margen=cerca")

      assert has_element?(lv, "#similares-motivo", "No hay otro estado")
    end
  end

  describe "notas del equipo" do
    import Mapo.TeamsFixtures

    test "sin equipo, cada documento invita a crear uno", %{conn: conn} do
      stub([zona()])
      {lv, _html} = abrir(conn, ~p"/perfil?zona=mun:14039")

      assert has_element?(lv, "#doc-comercio .notas a[href='/teams/new']")
    end

    test "una nota escrita en un documento sale ahí y se puede borrar", %{
      conn: conn,
      scope: scope
    } do
      team = team_fixture(scope)
      stub([colonia()])
      {lv, _html} = abrir(conn, ~p"/perfil?zona=col:14039_0010")

      lv
      |> form("#doc-servicios .nota-forma", %{"texto" => "faltan paradas"})
      |> render_submit()

      assert has_element?(lv, "#doc-servicios .nota-texto", "faltan paradas")
      refute has_element?(lv, "#doc-demografia .nota-texto")
      assert [nota] = Mapo.Notas.list_notas(scope, team.id, "col:14039_0010")
      assert nota.documento == "servicios"

      lv |> element("#nota-#{nota.id} .nota-borrar") |> render_click()
      refute has_element?(lv, "#nota-#{nota.id}")
    end

    test "con varios equipos, cambiar de equipo trae sus notas", %{conn: conn, scope: scope} do
      _a = team_fixture(scope, %{name: "A"})
      b = team_fixture(scope, %{name: "B"})

      {:ok, _} =
        Mapo.Notas.create_nota(scope, b.id, %{
          "zona" => "mun:14039",
          "documento" => "seguridad",
          "texto" => "nota de B"
        })

      stub([zona()])
      {lv, html} = abrir(conn, ~p"/perfil?zona=mun:14039")
      refute html =~ "nota de B"

      lv |> form("#equipo-form", %{"equipo" => b.id}) |> render_change()
      assert has_element?(lv, "#doc-seguridad .nota-texto", "nota de B")
    end
  end
end
