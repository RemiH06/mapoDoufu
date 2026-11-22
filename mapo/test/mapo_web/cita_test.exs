defmodule MapoWeb.CitaTest do
  use ExUnit.Case, async: true

  alias MapoWeb.Cita

  @hoy ~D[2026-11-21]

  test "la fuente original va primero y Mapo solo como quien la procesó" do
    c =
      Cita.armar("iieg",
        que: "Precio de oferta por AGEB, Jalisco",
        datos: "julio de 2024",
        version: "tabla v2",
        enlace: "https://mapo.remlam.dev/mapa?ent=14",
        hoy: @hoy
      )

    assert c.apa ==
             "IIEG. (2024). Sector inmobiliario: precios de oferta de vivienda, julio de 2024 " <>
               "[Conjunto de datos]. https://iieg.gob.mx/ns/?page_id=11967 Datos de julio de 2024. " <>
               "Procesado por Mapo: Precio de oferta por AGEB, Jalisco; tabla v2. " <>
               "Consultado el 21 de noviembre de 2026 en https://mapo.remlam.dev/mapa?ent=14"

    assert c.bibtex =~ "@misc{iieg_oferta_mapo_20261121,"
    assert c.bibtex =~ "author = {{Instituto de Información Estadística y Geográfica de Jalisco}}"
    assert c.bibtex =~ "url = {https://mapo.remlam.dev/mapa?ent=14}"
    assert c.bibtex =~ "urldate = {2026-11-21}"
  end

  test "sin año comprobado no se inventa uno, y sin liga no se pone" do
    c = Cita.armar("repda", hoy: @hoy)

    assert c.apa ==
             "Conagua. (s. f.). Registro Público de Derechos de Agua (REPDA): permisos de descarga " <>
               "[Conjunto de datos]. Procesado por Mapo. Consultado el 21 de noviembre de 2026."

    assert c.bibtex =~ "year = {s. f.}"
    refute c.bibtex =~ "url ="
  end

  test "lo que LaTeX lee como orden se escapa en el BibTeX" do
    c = Cita.armar("denue", que: ~S(giro "50% & más_#1" {x} \ ~^), hoy: @hoy)

    assert c.bibtex =~ ~S(50\% \& más\_\#1" \{x\} \textbackslash{} \~{}\^{})
  end

  test "un GTFS se cita con su productor, su página y su licencia tal como la declara" do
    feed = %{
      "feed" => "jal-setran",
      "titulo" => "Jalisco",
      "productor" => "SETRAN",
      "pagina" => "https://mobilitydatabase.org/feeds/gtfs/mdb-3632",
      "licencia" => nil
    }

    c = Cita.gtfs(feed, datos: "frecuencias del 2026-11-25", hoy: @hoy)

    assert c.apa ==
             "SETRAN. (s. f.). GTFS de transporte público: Jalisco (sin licencia declarada) " <>
               "[Conjunto de datos]. https://mobilitydatabase.org/feeds/gtfs/mdb-3632 " <>
               "Datos de frecuencias del 2026-11-25. Procesado por Mapo. " <>
               "Consultado el 21 de noviembre de 2026."

    assert c.clave == "gtfs_jal_setran_mapo_20261121"
    assert Cita.gtfs(%{feed | "licencia" => "CC-BY-4.0"}, hoy: @hoy).titulo =~ "(CC BY 4.0)"
  end

  test "una fuente fuera del catálogo no da cita" do
    assert Cita.armar("wikipedia") == nil
  end

  test "cada referencia tiene autor, título y clave" do
    for f <- Cita.fuentes() do
      c = Cita.armar(f, hoy: @hoy)
      assert c.apa =~ "[Conjunto de datos]"
      assert c.clave =~ ~r/^[a-z0-9_]+_mapo_20261121$/
    end
  end
end
