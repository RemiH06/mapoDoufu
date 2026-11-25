defmodule MapoWeb.AccesibilidadLive.IndexTest do
  use MapoWeb.ConnCase, async: true

  import Phoenix.LiveViewTest
  import Mapo.ZonaFixtures

  alias MapoWeb.Cotejo

  setup :register_and_log_in_user

  # 1,000 personas: 400 a 5 min o menos, 700 a 20 o menos, 100 sin ruta.
  defp dentro, do: for(m <- 0..120, do: if(m < 5, do: 0, else: if(m < 20, do: 400, else: 700)))

  defp resultado(modo) do
    %{
      "zona" => %{
        "clave" => "mun:14061",
        "estados" => ["14"],
        "nombre" => "Mezquitic",
        "geojson" => %{
          "type" => "Polygon",
          "coordinates" => [[[-104, 22], [-104, 23], [-103, 23], [-104, 22]]]
        }
      },
      "modo" => modo,
      "max_minutos" => 120,
      "lugares" => 96,
      "agebs" => 4,
      "servicios" => [
        %{
          "clave" => "centro_salud",
          "titulo" => "Centro de salud",
          "grupo" => "POBTOT",
          "grupo_etiqueta" => "personas",
          "calculado" => true,
          "total" => 1000,
          "reservados" => 2,
          "sin_ruta" => 100,
          "dentro" => dentro(),
          "fuente" => "CLUES de la Secretaría de Salud (DGIS), corte 2026-10",
          "red" => "OSM, perfil foot.lua",
          "fecha" => "2026-11-22",
          "destinos_estado" => 623,
          "destinos_zona" => 12,
          "metodo" => "Minutos a pie por calle.",
          "solo_agebs" => false,
          "sin_calcular" => 0,
          "sin_calcular_lugares" => 0
        },
        %{
          "clave" => "primaria_publica",
          "titulo" => "Primaria pública",
          "grupo" => "P_6A11",
          "grupo_etiqueta" => "personas de 6 a 11 años",
          "calculado" => true,
          "total" => 1000,
          "reservados" => 0,
          "sin_ruta" => 100,
          "dentro" => dentro(),
          "fuente" => "DENUE de INEGI",
          "red" => "OSM, perfil foot.lua",
          "fecha" => "2026-11-22",
          "destinos_estado" => 2536,
          "destinos_zona" => 2,
          "metodo" => "Solo AGEB.",
          "solo_agebs" => true,
          "sin_calcular" => 2178,
          "sin_calcular_lugares" => 92
        },
        %{
          "clave" => "supermercado",
          "titulo" => "Supermercado",
          "grupo" => "POBTOT",
          "grupo_etiqueta" => "personas",
          "calculado" => false
        }
      ],
      "plano" => %{"type" => "FeatureCollection", "features" => []},
      "destinos" => %{"type" => "FeatureCollection", "features" => []}
    }
  end

  defp stub(fun) do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      responder_zona(conn) ||
        case conn.request_path do
          "/accesibilidad/zona" -> fun.(Plug.Conn.fetch_query_params(conn))
        end
    end)
  end

  defp responde(conn), do: Req.Test.json(conn, resultado(conn.query_params["modo"]))

  defp consultar(lv) do
    elegir_zona(lv, "mun:14061")
    render_async(lv)
  end

  test "resumen resta la gente sin ruta y lee el minuto del umbral" do
    s = %{"total" => 1000, "sin_ruta" => 100, "dentro" => dentro()}
    assert Cotejo.resumen(s, 15) == %{dentro: 400, fuera: 500, con_ruta: 900}
    assert Cotejo.resumen(s, 4) == %{dentro: 0, fuera: 900, con_ruta: 900}
    assert Cotejo.resumen(s, 500).dentro == 700
  end

  test "cada servicio por separado, con su grupo, su fuente y lo que falta", %{conn: conn} do
    stub(fn conn ->
      assert conn.query_params == %{"zona" => "mun:14061", "modo" => "pie"}
      responde(conn)
    end)

    {:ok, lv, html} = live(conn, ~p"/accesibilidad")
    assert html =~ "sin índice"

    html = consultar(lv)

    assert has_element?(lv, "#servicio-centro_salud .cerca", "500")
    assert html =~ "el 55.6 % de 900 con ruta"
    assert html =~ "a más de 15 minutos a pie"
    assert has_element?(lv, "#servicio-centro_salud .procedencia", "CLUES")
    assert html =~ "INEGI reserva el dato en 2 lugares"
    # Con menos de la mitad del grupo calculado no hay cifra (337 de 3,909 en Mezquitic).
    assert has_element?(
             lv,
             "#servicio-primaria_publica .cotejo-ficha[data-estado=rayada]",
             "parcial"
           )

    lv |> element("#ver-primaria_publica") |> render_click()
    assert has_element?(lv, "#servicio-primaria_publica", "personas de 6 a 11 años")

    assert has_element?(
             lv,
             "#servicio-primaria_publica",
             "92 lugares que no se calculan: localidades sin AGEB"
           )

    assert has_element?(lv, "#servicio-supermercado", "Todavía no se calcula a pie")
    refute html =~ "índice de"

    assert_push_event(lv, "zona", %{servicio: "centro_salud", umbral: 15})
    assert_patch(lv, "/accesibilidad?zona=mun:14061&modo=pie&umbral=15&servicio=centro_salud")
  end

  test "mover el umbral vuelve a restar sin consultar", %{conn: conn} do
    {:ok, cuenta} = Agent.start_link(fn -> 0 end)

    stub(fn conn ->
      Agent.update(cuenta, &(&1 + 1))
      responde(conn)
    end)

    {:ok, lv, _} = live(conn, ~p"/accesibilidad")
    consultar(lv)

    html =
      lv
      |> form("#accesibilidad_form", acc: %{umbral: "30"})
      |> render_change()

    assert html =~ "a más de 30 minutos a pie"
    assert has_element?(lv, "#servicio-centro_salud .cerca", "200")
    assert_push_event(lv, "estilo", %{servicio: "centro_salud", umbral: 30})
    assert Agent.get(cuenta, & &1) == 1

    # Un umbral fuera de rango no cambia nada.
    lv
    |> form("#accesibilidad_form", acc: %{umbral: "500"})
    |> render_change()

    assert render(lv) =~ "a más de 30 minutos"
  end

  describe "matriz" do
    defp metropoli do
      m = fn lugares, sin_calcular ->
        %{
          "lugares" => lugares,
          "total" => 100,
          "sin_ruta" => 0,
          "reservados" => 0,
          "sin_calcular" => sin_calcular,
          "dentro" => for(i <- 0..120, do: if(i < 20, do: 40, else: 100))
        }
      end

      resultado("pie")
      |> put_in(["zona", "municipios"], [
        %{"cvegeo" => "14039", "nombre" => "Guadalajara", "poblacion" => 100},
        %{"cvegeo" => "14051", "nombre" => "Juanacatlán", "poblacion" => 100}
      ])
      |> put_in(["zona", "poblacion"], 1000)
      |> update_in(["servicios"], fn [salud | resto] ->
        salud =
          Map.put(salud, "municipios", %{"14039" => m.(40, 0), "14051" => m.(0, 0)})

        [
          salud
          | Enum.map(resto, &if(&1["calculado"], do: Map.put(&1, "municipios", %{}), else: &1))
        ]
      end)
    end

    test "municipios por servicio, y el umbral los mueve sin consultar", %{conn: conn} do
      stub(fn conn -> Req.Test.json(conn, metropoli()) end)
      {:ok, lv, _} = live(conn, ~p"/accesibilidad")
      consultar(lv)

      assert has_element?(lv, "#vista-matriz[aria-pressed=true]")
      assert has_element?(lv, "#matriz-zona td[data-clase='4']", "56 %")
      assert has_element?(lv, "#matriz-14039 td[data-clase='4']", "60 %")
      assert has_element?(lv, "#matriz-14051 td[data-estado=rayada]", "sin calc.")
      assert has_element?(lv, "#matriz button[phx-value-clave=supermercado][disabled]")

      lv |> form("#accesibilidad_form", acc: %{umbral: "20"}) |> render_change()
      assert has_element?(lv, "#matriz-14039 td[data-clase='0']", "0 %")
    end

    test "una zona fija se sigue moviendo con el umbral y se suelta al cambiar de modo", %{
      conn: conn
    } do
      stub(fn conn ->
        if conn.query_params["zona"] == "mun:14061",
          do: responde(conn),
          else:
            Req.Test.json(
              conn,
              put_in(metropoli(), ["zona", "clave"], conn.query_params["zona"])
              |> put_in(["modo"], conn.query_params["modo"])
            )
      end)

      {:ok, lv, _} = live(conn, ~p"/accesibilidad")
      consultar(lv)
      lv |> element("#vista-matriz") |> render_click()
      lv |> element("#fijar") |> render_click()
      elegir_zona(lv, "zm:14.1.01")
      render_async(lv)

      fija = "#matriz tr[id^=matriz-fija]"
      assert has_element?(lv, "#{fija} td[data-clase='4']", "56 %")
      lv |> form("#accesibilidad_form", acc: %{umbral: "30"}) |> render_change()
      assert has_element?(lv, "#{fija} td[data-clase='3']", "22 %")

      lv |> form("#accesibilidad_form", acc: %{modo: "auto"}) |> render_change()
      render_async(lv)
      refute has_element?(lv, fija)
    end

    test "abrir en el mapa lleva el servicio, el modo y los minutos", %{conn: conn} do
      stub(&responde/1)
      {:ok, lv, _} = live(conn, ~p"/accesibilidad")
      consultar(lv)

      assert has_element?(
               lv,
               "#abrir-mapa[href='/mapa?zona=mun:14061&servicio=centro_salud&modo=pie&umbral=15&ver=servicios']"
             )
    end
  end

  test "cambiar el modo vuelve a consultar", %{conn: conn} do
    stub(&responde/1)
    {:ok, lv, _} = live(conn, ~p"/accesibilidad")
    consultar(lv)

    lv
    |> form("#accesibilidad_form", acc: %{modo: "auto"})
    |> render_change()

    assert render_async(lv) =~ "a más de 15 minutos en auto"
  end

  test "ver en el plano cambia el servicio pintado; uno sin calcular no", %{conn: conn} do
    stub(&responde/1)
    {:ok, lv, _} = live(conn, ~p"/accesibilidad")
    consultar(lv)

    render_click(lv, "ver", %{"clave" => "primaria_publica"})
    assert_push_event(lv, "estilo", %{servicio: "primaria_publica"})
    assert has_element?(lv, "#servicio-primaria_publica.activo")

    render_click(lv, "ver", %{"clave" => "supermercado"})
    assert has_element?(lv, "#servicio-primaria_publica.activo")
  end

  test "el enlace permanente reconstruye la vista y lo raro cae al valor inicial", %{conn: conn} do
    stub(&responde/1)

    {:ok, lv, _} =
      live(conn, ~p"/accesibilidad?ent=14&mun=061&modo=auto&umbral=45&servicio=primaria_publica")

    html = render_async(lv)
    assert html =~ "a más de 45 minutos en auto"
    assert has_element?(lv, "#servicio-primaria_publica.activo")

    {:ok, lv, _} = live(conn, ~p"/accesibilidad?ent=14&mun=999")
    refute render(lv) =~ "Mezquitic:"

    {:ok, lv, _} = live(conn, ~p"/accesibilidad?ent=14&mun=061&modo=bici&umbral=x")
    assert render_async(lv) =~ "a más de 15 minutos a pie"
  end

  test "cómo citar pone la fuente de los destinos, el censo y la red", %{conn: conn} do
    stub(&responde/1)
    {:ok, lv, _} = live(conn, ~p"/accesibilidad")
    consultar(lv)

    render_click(lv, "citar", %{"clave" => "centro_salud"})
    html = render(lv)
    assert html =~ "Catálogo de Clave Única de Establecimientos de Salud (CLUES)"
    assert html =~ "Censo de Población y Vivienda 2020"
    assert html =~ "OpenStreetMap"
    assert html =~ "personas a más de 15 minutos a pie, Mezquitic"
  end

  test "un error de mapo_core se dice", %{conn: conn} do
    stub(fn conn -> conn |> Plug.Conn.put_status(500) |> Req.Test.json(%{"detail" => "boom"}) end)
    {:ok, lv, _} = live(conn, ~p"/accesibilidad")
    assert consultar(lv) =~ "No se pudo consultar la zona"
  end
end
