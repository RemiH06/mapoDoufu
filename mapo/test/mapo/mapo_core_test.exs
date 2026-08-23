defmodule Mapo.MapoCoreTest do
  use ExUnit.Case, async: true

  alias Mapo.MapoCore

  test "estados/0 pega a /gaiarda/estados" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/estados"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    assert {:ok, %{"type" => "FeatureCollection"}} = MapoCore.estados()
  end

  test "municipios/1 manda cve_ent como query param" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/municipios"
      assert conn.params["cve_ent"] == "14"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    assert {:ok, _} = MapoCore.municipios("14")
  end

  test "coropleta_censo_poblacion/3 manda indicador y cve_ent, sin cve_mun por defecto" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/gaiarda/choropleth/censo_poblacion"
      assert conn.params["indicador"] == "pobtot"
      assert conn.params["cve_ent"] == "14"
      refute Map.has_key?(conn.params, "cve_mun")
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    assert {:ok, _} = MapoCore.coropleta_censo_poblacion("pobtot", "14")
  end

  test "coropleta_censo_poblacion/3 incluye cve_mun cuando se da" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.params["cve_mun"] == "039"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => []})
    end)

    assert {:ok, _} = MapoCore.coropleta_censo_poblacion("pobtot", "14", "039")
  end

  test "voronoi_denue/3 manda cve_ent y cve_mun, sin clase_actividad por defecto" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/voronoi/denue"
      assert conn.params["cve_ent"] == "14"
      assert conn.params["cve_mun"] == "039"
      refute Map.has_key?(conn.params, "clase_actividad")
      Req.Test.json(conn, %{"celdas" => %{"type" => "FeatureCollection", "features" => []}, "metodo" => "recortado_a_limite"})
    end)

    assert {:ok, %{"metodo" => "recortado_a_limite"}} = MapoCore.voronoi_denue("14", "039")
  end

  test "voronoi_denue/3 incluye clase_actividad cuando se da" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.params["clase_actividad"] == "papeleria"
      Req.Test.json(conn, %{"celdas" => %{"type" => "FeatureCollection", "features" => []}, "metodo" => "recortado_a_limite"})
    end)

    assert {:ok, _} = MapoCore.voronoi_denue("14", "039", "papeleria")
  end

  test "coloreado_municipios/1 manda cve_ent" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      assert conn.request_path == "/coloreado/municipios"
      assert conn.params["cve_ent"] == "14"
      Req.Test.json(conn, %{"type" => "FeatureCollection", "features" => [], "num_colores" => 0})
    end)

    assert {:ok, %{"num_colores" => 0}} = MapoCore.coloreado_municipios("14")
  end

  test "regresa {:error, _} si mapo_core responde un status distinto de 200" do
    Req.Test.stub(Mapo.MapoCore, fn conn ->
      Plug.Conn.send_resp(conn, 502, Jason.encode!(%{"error" => "no disponible"}))
    end)

    assert {:error, {:status, 502, _}} = MapoCore.estados()
  end

  test "indicadores_censo/0 solo trae pares {codigo, etiqueta}" do
    for {codigo, etiqueta} <- MapoCore.indicadores_censo() do
      assert is_binary(codigo)
      assert is_binary(etiqueta)
    end
  end
end
