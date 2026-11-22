defmodule MapoWeb.Cita do
  @moduledoc """
  Cómo citar lo que se ve en Mapo (docs/producto/citar.md). La fuente original
  va primero: Mapo no se atribuye el dato, solo dice que lo procesó, con qué
  versión de la tabla y con qué enlace se reconstruye la vista.

  Cada referencia es de un catálogo cerrado. Un año o una liga que no se pudo
  comprobar no se inventa: el año queda "s. f." y la liga se omite.
  """
  use Phoenix.Component

  @inegi "Instituto Nacional de Estadística y Geografía"

  @referencias %{
    "censo" => %{
      clave: "inegi_censo2020",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: "2021",
      titulo:
        "Censo de Población y Vivienda 2020: principales resultados por AGEB y manzana urbana",
      url: "https://www.inegi.org.mx/programas/ccpv/2020/"
    },
    "marco" => %{
      clave: "inegi_marco",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: nil,
      titulo: "Marco Geoestadístico, servicio de catálogo y geometrías (wscatgeo v2)",
      url: "https://gaia.inegi.org.mx/wscatgeo/v2"
    },
    "denue" => %{
      clave: "inegi_denue",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: nil,
      titulo: "Directorio Estadístico Nacional de Unidades Económicas (DENUE), descarga masiva",
      url: "https://www.inegi.org.mx/contenidos/masiva/denue/"
    },
    "eic2025" => %{
      clave: "inegi_eic2025",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: "2026",
      titulo: "Encuesta Intercensal 2025: datos abiertos",
      url:
        "https://www.inegi.org.mx/contenidos/programas/eic/2025/datosabiertos/conjunto_de_datos_eic2025_105_csv.zip"
    },
    "envi" => %{
      clave: "inegi_envi2020",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: nil,
      titulo: "Encuesta Nacional de Vivienda (ENVI) 2020: datos abiertos",
      url:
        "https://www.inegi.org.mx/contenidos/programas/envi/2020/datosabiertos/conjunto_de_datos_envi_2020_csv.zip"
    },
    "sniiv" => %{
      clave: "sedatu_sniiv",
      autor: "SEDATU",
      autor_largo: "Secretaría de Desarrollo Agrario, Territorial y Urbano",
      anio: nil,
      titulo:
        "Sistema Nacional de Información e Indicadores de Vivienda (SNIIV): financiamientos para vivienda",
      url: "https://sniiv.sedatu.gob.mx/Reporte/Datos_abiertos"
    },
    "shf" => %{
      clave: "shf_ipv",
      autor: "Sociedad Hipotecaria Federal",
      autor_largo: "Sociedad Hipotecaria Federal",
      anio: nil,
      titulo: "Índice SHF de Precios de la Vivienda en México (consultado en el SNIIV)",
      url: "https://sniiv.sedatu.gob.mx/api/ShfPriceAPI/"
    },
    "iieg" => %{
      clave: "iieg_oferta",
      autor: "IIEG",
      autor_largo: "Instituto de Información Estadística y Geográfica de Jalisco",
      anio: "2024",
      titulo: "Sector inmobiliario: precios de oferta de vivienda, julio de 2024",
      url: "https://iieg.gob.mx/ns/?page_id=11967"
    },
    "osm" => %{
      clave: "osm",
      autor: "Colaboradores de OpenStreetMap",
      autor_largo: "Colaboradores de OpenStreetMap",
      anio: nil,
      titulo: "OpenStreetMap (ODbL), ruteado con OSRM",
      url: "https://www.openstreetmap.org/copyright"
    },
    "clues" => %{
      clave: "dgis_clues",
      autor: "DGIS, Secretaría de Salud",
      autor_largo: "Dirección General de Información en Salud, Secretaría de Salud",
      anio: nil,
      titulo: "Catálogo de Clave Única de Establecimientos de Salud (CLUES)",
      url: "http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html"
    },
    "renameca" => %{
      clave: "conagua_renameca",
      autor: "Conagua",
      autor_largo: "Comisión Nacional del Agua",
      anio: nil,
      titulo: "Red Nacional de Medición de la Calidad del Agua (RENAMECA)",
      url: nil
    },
    "repda" => %{
      clave: "conagua_repda",
      autor: "Conagua",
      autor_largo: "Comisión Nacional del Agua",
      anio: nil,
      titulo: "Registro Público de Derechos de Agua (REPDA): permisos de descarga",
      url: nil
    },
    "retc" => %{
      clave: "semarnat_retc",
      autor: "SEMARNAT",
      autor_largo: "Secretaría de Medio Ambiente y Recursos Naturales",
      anio: nil,
      titulo: "Registro de Emisiones y Transferencia de Contaminantes (RETC)",
      url: nil
    },
    "firms" => %{
      clave: "nasa_firms",
      autor: "NASA FIRMS",
      autor_largo: "NASA Fire Information for Resource Management System (LANCE, EOSDIS)",
      anio: nil,
      titulo: "Focos de calor VIIRS S-NPP 375 m",
      url: "https://firms.modaps.eosdis.nasa.gov/"
    },
    "acuiferos" => %{
      clave: "conagua_acuiferos",
      autor: "Conagua",
      autor_largo: "Comisión Nacional del Agua",
      anio: "2023",
      titulo:
        "Disponibilidad media anual de agua en los acuíferos (DOF del 9 de noviembre de 2023)",
      url: nil
    },
    "sequia" => %{
      clave: "smn_sequia",
      autor: "SMN, Conagua",
      autor_largo: "Servicio Meteorológico Nacional, Comisión Nacional del Agua",
      anio: nil,
      titulo: "Monitor de Sequía de México, municipios con sequía",
      url:
        "https://smn.conagua.gob.mx/es/climatologia/monitor-de-sequia/monitor-de-sequia-en-mexico"
    },
    "anp" => %{
      clave: "conanp_anp",
      autor: "CONANP",
      autor_largo: "Comisión Nacional de Áreas Naturales Protegidas",
      anio: nil,
      titulo:
        "Áreas naturales protegidas federales de México (copia de CONABIO, CC BY-NC 2.5 MX)",
      url: "http://geoportal.conabio.gob.mx/"
    },
    "uso_suelo" => %{
      clave: "inegi_usv",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: nil,
      titulo:
        "Uso del suelo y vegetación, escala 1:250 000, series VI y VII (copia de CONABIO, CC BY-NC 2.5 MX)",
      url: "http://geoportal.conabio.gob.mx/"
    },
    "siap" => %{
      clave: "siap_agricola",
      autor: "SIAP, SADER",
      autor_largo: "Servicio de Información Agroalimentaria y Pesquera",
      anio: nil,
      titulo: "Estadística de la producción agrícola por municipio",
      url: "https://nube.siap.gob.mx/cierreagricola/"
    },
    "defunciones" => %{
      clave: "inegi_edr",
      autor: "INEGI",
      autor_largo: @inegi,
      anio: nil,
      titulo: "Estadísticas de defunciones registradas",
      url: "https://www.inegi.org.mx/programas/edr/"
    }
  }

  @meses ~w(enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre)

  @doc "Las claves del catálogo."
  def fuentes, do: Map.keys(@referencias)

  @doc """
  Fecha de hoy en el centro de México (UTC−6, sin horario de verano desde
  2022). Sin base de zonas horarias: no hace falta para un día.
  """
  def hoy, do: DateTime.utc_now() |> DateTime.add(-6 * 3600) |> DateTime.to_date()

  @doc """
  Enlace absoluto a una ruta de Mapo, para que la cita sirva fuera de la app.
  """
  def enlace(ruta), do: MapoWeb.Endpoint.url() <> ruta

  @doc """
  Arma la cita de una fuente del catálogo. Opciones:

    * `:que`: lo que se ve en Mapo ("Viviendas rentadas por municipio, Jalisco").
    * `:datos`: fecha o periodo de los datos, si la fuente no lo dice en el título.
    * `:version`: versión de la tabla en Mapo o fecha en que se cargó.
    * `:enlace`: enlace permanente a la vista.
    * `:hoy`: fecha de consulta (por omisión, `hoy/0`).

  Regresa `%{clave, titulo, apa, bibtex}`; `nil` si la fuente no está en el
  catálogo.
  """
  def armar(fuente, opts \\ []) do
    case @referencias[fuente] do
      nil -> nil
      ref -> armar_ref(ref, Map.new(opts))
    end
  end

  defp armar_ref(ref, opts) do
    hoy = opts[:hoy] || hoy()
    anio = ref.anio || "s. f."

    procesado =
      [
        "Procesado por Mapo",
        opts[:que] && ": #{opts[:que]}",
        opts[:version] && "; #{opts[:version]}"
      ]
      |> Enum.reject(&(&1 in [nil, false]))
      |> Enum.join()

    apa =
      [
        "#{ref.autor}. (#{anio}). #{ref.titulo} [Conjunto de datos].",
        ref.url && ref.url,
        opts[:datos] && "Datos de #{opts[:datos]}.",
        procesado <> ".",
        consulta(hoy, opts[:enlace])
      ]
      |> Enum.reject(&(&1 in [nil, false]))
      |> Enum.join(" ")

    nota =
      [
        opts[:datos] && "Datos de #{opts[:datos]}.",
        procesado <> ".",
        ref.url && "Fuente original: #{ref.url}."
      ]
      |> Enum.reject(&(&1 in [nil, false]))
      |> Enum.join(" ")

    clave = "#{ref.clave}_mapo_#{Calendar.strftime(hoy, "%Y%m%d")}"

    campos =
      [
        {"author", "{#{tex(ref.autor_largo)}}"},
        {"title", "{#{tex(ref.titulo)}}"},
        {"year", if(ref.anio, do: ref.anio, else: "s. f.")},
        {"note", tex(nota)},
        opts[:enlace] && {"url", opts[:enlace]},
        {"urldate", Date.to_iso8601(hoy)}
      ]
      |> Enum.reject(&(&1 in [nil, false]))
      |> Enum.map_join(",\n", fn {k, v} -> "  #{k} = {#{v}}" end)

    %{
      clave: clave,
      titulo: ref.titulo,
      apa: apa,
      bibtex: "@misc{#{clave},\n#{campos}\n}"
    }
  end

  defp consulta(hoy, nil), do: "Consultado el #{fecha_larga(hoy)}."
  defp consulta(hoy, enlace), do: "Consultado el #{fecha_larga(hoy)} en #{enlace}"

  defp fecha_larga(%Date{day: d, month: m, year: a}),
    do: "#{d} de #{Enum.at(@meses, m - 1)} de #{a}"

  # Lo que LaTeX lee como orden. El texto viene de este catálogo y de los
  # catálogos de Mapo, pero un nombre de municipio o un filtro escrito pueden
  # traer cualquier cosa.
  defp tex(texto) do
    String.replace(texto, ~r/[\\{}&%$#_^~]/, fn
      "\\" -> "\\textbackslash{}"
      "^" -> "\\^{}"
      "~" -> "\\~{}"
      c -> "\\" <> c
    end)
  end

  @doc """
  Bloque "Cómo citar": una o varias referencias con su texto tipo APA y su
  BibTeX, cada una con botón de copiar, y el enlace permanente.
  """
  attr :id, :string, required: true
  attr :citas, :list, required: true
  attr :enlace, :string, default: nil

  def como_citar(assigns) do
    ~H"""
    <%!-- Al abrirse, el foco va al primer "Copiar": la cita queda a la vista
         aunque la cinta tenga que desplazarse, y sirve con teclado. --%>
    <div id={@id} class="cita" phx-mounted={Phoenix.LiveView.JS.focus_first()}>
      <p class="cita-aviso">
        Cita primero la fuente original: Mapo solo la procesó.
      </p>
      <div :for={{c, i} <- Enum.with_index(@citas)} class="cita-ref">
        <p :if={length(@citas) > 1} class="cita-de">{c.titulo}</p>
        <pre id={"#{@id}-apa-#{i}"} class="cita-texto">{c.apa}</pre>
        <div class="cita-botones">
          <button
            type="button"
            id={"#{@id}-copiar-apa-#{i}"}
            class="enlace"
            phx-hook=".Copiar"
            data-de={"#{@id}-apa-#{i}"}
          >
            Copiar
          </button>
          <button
            type="button"
            id={"#{@id}-copiar-bib-#{i}"}
            class="enlace"
            phx-hook=".Copiar"
            data-de={"#{@id}-bib-#{i}"}
          >
            Copiar BibTeX
          </button>
        </div>
        <details class="cita-bib" phx-mounted={Phoenix.LiveView.JS.ignore_attributes(["open"])}>
          <summary>BibTeX</summary>
          <pre id={"#{@id}-bib-#{i}"} class="cita-texto">{c.bibtex}</pre>
        </details>
      </div>
      <p :if={@enlace} class="cita-enlace">
        <span class="etiqueta">Enlace permanente</span>
        <a href={@enlace} id={"#{@id}-enlace"} class="enlace">{@enlace}</a>
        <button
          type="button"
          id={"#{@id}-copiar-enlace"}
          class="enlace"
          phx-hook=".Copiar"
          data-de={"#{@id}-enlace"}
        >
          Copiar
        </button>
      </p>
    </div>
    <script :type={Phoenix.LiveView.ColocatedHook} name=".Copiar">
      export default {
        mounted() {
          const original = this.el.textContent
          this.el.addEventListener("click", () => {
            const origen = document.getElementById(this.el.dataset.de)
            if (!origen) return
            const texto = origen.textContent.trim()
            const aviso = ok => {
              this.el.textContent = ok ? "Copiado" : "Selecciónalo y cópialo"
              setTimeout(() => { this.el.textContent = original }, 1600)
            }
            if (navigator.clipboard) {
              navigator.clipboard.writeText(texto).then(() => aviso(true), () => aviso(false))
            } else {
              aviso(false)
            }
          })
        }
      }
    </script>
    """
  end
end
