defmodule MapoWeb.PerfilLive.IndexTest do
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

  defp perfil_con_demografia do
    %{
      "cve_ent" => "14",
      "cve_mun" => "039",
      "demografia" => %{
        "pobtot" => 1_500_000,
        "pobfem" => 800_000,
        "pobmas" => 700_000,
        "graproes" => 10.5,
        "pea" => 700_000,
        "pocupada" => 650_000,
        "pdesocup" => 50000,
        "tothog" => 400_000,
        "vivtot" => 420_000
      },
      "comercio" => %{
        "total_negocios" => 3200,
        "top_clases_actividad" => [["Comercio al por menor de abarrotes", 450]]
      },
      "consumo" => %{
        "n_hogares_muestra" => 12,
        "periodo" => "diario",
        "promedio_ponderado" => 476.23,
        "mediana" => 410.0
      },
      "seguridad" => %{
        "anio" => 2024,
        "total_delitos" => 320,
        "por_tipo" => [["Robo", 200], ["Homicidio", 20]]
      },
      "laboral" => %{
        "anio" => 2025,
        "trimestre" => "trim3",
        "tasa_desocupacion" => 2.49
      },
      "empleo_formal" => empleo_formal()
    }
  end

  defp empleo_formal(cambios \\ %{}) do
    Map.merge(
      %{
        "periodo" => "2024-12-31",
        "puestos" => 694_493,
        "permanentes" => 610_000,
        "eventuales" => 84_493,
        "salario_diario" => 612.4,
        "parte_rango_tope" => 2.8,
        "asegurados_sin_empleo" => 40_000,
        "por_division" => [
          %{"division" => "8", "nombre" => "Servicios para empresas", "puestos" => 250_000}
        ],
        "anual" => nil,
        "puestos_estado_sin_municipio" => 0
      },
      cambios
    )
  end

  test "shows a warning when mapo_core/Gaiarda is not reachable", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    {:ok, _lv, html} = live(conn, ~p"/perfil")

    assert html =~ "No se pudo cargar la lista de estados"
  end

  test "ver_perfil without a municipio shows a flash", %{conn: conn} do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    html =
      lv
      |> form("#perfil_form", perfil: %{"cve_ent" => "", "cve_mun" => ""})
      |> render_submit()

    assert html =~ "Selecciona un estado y un municipio"
  end

  defp ageb_feature do
    %{
      "type" => "Feature",
      "properties" => %{"cvegeo" => "1403900010010"},
      "geometry" => %{
        "type" => "Polygon",
        "coordinates" => [
          [[-103.35, 20.67], [-103.34, 20.67], [-103.34, 20.68], [-103.35, 20.67]]
        ]
      }
    }
  end

  defp stub_catalogo(perfil) do
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

        "/geo/agebs" ->
          Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [ageb_feature()]})

        "/perfil_zona" ->
          assert conn.params["cve_ent"] == "14"
          assert conn.params["cve_mun"] == "039"
          Req.Test.json(conn, perfil)
      end
    end)
  end

  test "ver_perfil puts the query in the URL and renders the five documents", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, _html} = live(conn, ~p"/perfil")

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => ""})
    |> render_change()

    lv
    |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => "039"})
    |> render_submit()

    assert_patch(lv, ~p"/perfil?cve_ent=14&cve_mun=039")
    html = render_async(lv)

    assert html =~ "Guadalajara, Jalisco"
    assert html =~ "1,500,000"
    assert html =~ "2.49 %"
    assert html =~ "694,493"
    assert html =~ "diciembre de 2024"
    assert html =~ "falta el mismo mes del año anterior"
    assert html =~ "Las demás clases"
    assert has_element?(lv, "[data-piel=demografia]")
    assert has_element?(lv, "[data-piel=laboral]")
    assert has_element?(lv, ".plano path")
  end

  test "opening /perfil with a query in the URL loads it directly", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")

    assert render_async(lv) =~ "Gasto de los hogares"
    assert has_element?(lv, "#perfil_form option[value='039'][selected]")
  end

  test "an unknown municipio in the URL shows a flash and no query", %{conn: conn} do
    stub_catalogo(perfil_con_demografia())

    {:ok, lv, html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=777")

    assert html =~ "Ese municipio no está en el catálogo."
    refute has_element?(lv, ".documentos")
  end

  test "each document says so when its source does not cover the municipio", %{conn: conn} do
    stub_catalogo(%{
      "demografia" => nil,
      "comercio" => %{"total_negocios" => 0, "top_clases_actividad" => []},
      "consumo" => nil,
      "seguridad" => nil,
      "laboral" => nil,
      "empleo_formal" => nil
    })

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
    html = render_async(lv)

    assert html =~ "El censo no tiene datos de este municipio."
    assert html =~ "El DENUE no registra negocios en este municipio."
    assert html =~ "La muestra de la ENIGH no llegó a este municipio."
    assert html =~ "No hay incidencia del SESNSP cargada para este municipio."
    assert html =~ "No hay datos de la ENOE cargados para este estado."
    assert html =~ "No hay datos del IMSS cargados para este estado."
  end

  test "the IMSS block gives the yearly change only when that month is loaded", %{conn: conn} do
    anual = %{"periodo" => "2023-12-31", "puestos" => 680_000, "variacion" => 2.13}

    stub_catalogo(%{
      perfil_con_demografia()
      | "empleo_formal" => empleo_formal(%{"anual" => anual})
    })

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
    html = render_async(lv)

    assert html =~ "2.13 % (desde diciembre de 2023)"
    refute html =~ "falta el mismo mes del año anterior"
  end

  test "a state the IMSS does not split by municipio says so", %{conn: conn} do
    sin_municipio = empleo_formal(%{"puestos" => 0, "puestos_estado_sin_municipio" => 3_479_354})
    stub_catalogo(%{perfil_con_demografia() | "empleo_formal" => sin_municipio})

    {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")

    assert render_async(lv) =~ "El IMSS no asigna municipio a 3,479,354 puestos"
  end

  describe "notas del equipo" do
    import Mapo.TeamsFixtures

    test "without a team, each document invites to create one", %{conn: conn} do
      stub_catalogo(perfil_con_demografia())
      {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
      render_async(lv)

      assert has_element?(lv, "[data-piel=comercio] .notas a[href='/teams/new']")
    end

    test "a note written on a document shows up there, and can be deleted", %{
      conn: conn,
      scope: scope
    } do
      team = team_fixture(scope)
      stub_catalogo(perfil_con_demografia())
      {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
      render_async(lv)

      lv
      |> form("[data-piel=comercio] .nota-forma", %{"texto" => "faltan papelerías"})
      |> render_submit()

      assert has_element?(lv, "[data-piel=comercio] .nota-texto", "faltan papelerías")
      refute has_element?(lv, "[data-piel=demografia] .nota-texto")
      assert [nota] = Mapo.Notas.list_notas(scope, team.id, "14", "039")
      assert nota.documento == "comercio"

      lv |> element("#nota-#{nota.id} .nota-borrar") |> render_click()
      refute has_element?(lv, "#nota-#{nota.id}")
    end

    test "with several teams, switching team shows that team's notes", %{
      conn: conn,
      scope: scope
    } do
      a = team_fixture(scope, %{name: "A"})
      b = team_fixture(scope, %{name: "B"})

      {:ok, _} =
        Mapo.Notas.create_nota(scope, b.id, %{
          "cve_ent" => "14",
          "cve_mun" => "039",
          "documento" => "seguridad",
          "texto" => "nota de B"
        })

      stub_catalogo(perfil_con_demografia())
      {:ok, lv, _html} = live(conn, ~p"/perfil?cve_ent=14&cve_mun=039")
      render_async(lv)
      refute render(lv) =~ "nota de B"

      lv
      |> form("#perfil_form", perfil: %{"cve_ent" => "14", "cve_mun" => "039", "equipo" => b.id})
      |> render_change()

      assert has_element?(lv, "[data-piel=seguridad] .nota-texto", "nota de B")
      assert a.id != b.id
    end
  end
end
