defmodule MapoWeb.Cotejo do
  @moduledoc """
  Lo que comparten `/riesgos` y `/accesibilidad` para leerse de un vistazo: el
  catálogo de peligros y de servicios (nombre corto, ícono), la celda (clase y
  cifra) y la matriz de zonas por columnas.

  La clase dice qué parte de la gente (o del área) y usa cortes fijos, los
  mismos en todas las columnas y en las dos vistas: no depende de con qué se
  compara. Cada columna se lee sola; nunca se suman ni se promedian entre sí.
  Ver docs/producto/vista-riesgos.md y docs/producto/accesibilidad.md.
  """

  use Phoenix.Component

  import MapoWeb.Cifras
  import MapoWeb.Iconos, only: [icono: 1]

  alias MapoWeb.Cita
  alias MapoWeb.Iconos

  # Los peligros de la matriz, con las claves de mapo_core/riesgos.py: nombre corto
  # y qué cuenta el segundo renglón de sus celdas.
  @peligros [
    {"agua_superficial", "Agua superf.", "sitios en rojo"},
    {"agua_subterranea", "Agua subt.", "sitios en rojo"},
    {"descargas", "Descargas", "permisos"},
    {"retc", "Emisiones", "reportaron"},
    {"fuego", "Fuego", "focos del año"},
    {"acuifero", "Acuífero", "sin agua"},
    {"sequia", "Sequía", "cortes en D2+"}
  ]
  # Se dibujan, pero no son un peligro con clase: van de contexto.
  @contexto ~w(anp uso_suelo agricultura defunciones)
  @dibujables Enum.map(@peligros, &elem(&1, 0)) ++ ["anp"]

  @titulos_peligro %{
    "agua_superficial" => "Calidad del agua superficial",
    "agua_subterranea" => "Calidad del agua subterránea",
    "descargas" => "Descargas con permiso",
    "retc" => "Establecimientos del RETC",
    "fuego" => "Focos de calor",
    "acuifero" => "Agua subterránea disponible",
    "sequia" => "Sequía",
    "anp" => "Áreas naturales protegidas"
  }

  # Los servicios, con las claves de mapo_core/accesibilidad.py, en su orden. El
  # tercero dice si solo va a pie.
  @servicios [
    {"centro_salud", "C. de salud", "Centro de salud", false},
    {"umf_imss", "IMSS", "Clínica del IMSS", false},
    {"hospital_publico", "Hospital", "Hospital público", false},
    {"preescolar_publico", "Preescolar", "Preescolar pública", false},
    {"primaria_publica", "Primaria", "Primaria pública", false},
    {"secundaria_publica", "Secundaria", "Secundaria pública", false},
    {"media_superior_publica", "Bachillerato", "Bachillerato público", false},
    {"supermercado", "Súper", "Supermercado", false},
    {"transporte_masivo", "Estación", "Estación de transporte masivo", true},
    {"parada_transporte", "Parada", "Parada de transporte público", true},
    {"parada_frecuente", "Parada 15 min", "Parada con paso cada 15 minutos o menos", true}
  ]

  @doc "Las columnas de la matriz de peligros: `{clave, nombre corto, unidad}`."
  def peligros, do: @peligros

  def contexto, do: @contexto

  # La tinta de cada peligro en el plano y lo que dice su color (variables de
  # assets/css/cotejo.css). `true`: se dibuja hueco.
  @tintas %{
    "descargas" => "--p-descargas",
    "retc" => "--p-retc",
    "fuego" => "--p-fuego",
    "acuifero" => "--p-agua-sin",
    "anp" => "--p-anp"
  }
  @semaforo [
    ["--r-rojo", "rojo", false],
    ["--r-amarillo", "amarillo", false],
    ["--r-verde", "verde", true],
    ["--text2", "sin semáforo", false]
  ]
  @sequia [
    ["--msm-sin", "sin anomalía", false],
    ["--msm-d0", "D0 seco", false],
    ["--msm-d1", "D1 moderada", false],
    ["--msm-d2", "D2 severa", false],
    ["--msm-d3", "D3 extrema", false],
    ["--msm-d4", "D4 excepcional", false]
  ]
  @colores %{
    "agua_superficial" => @semaforo,
    "agua_subterranea" => @semaforo,
    "acuifero" => [
      ["--p-agua-sin", "sin agua disponible", false],
      ["--p-agua-con", "con agua disponible", false]
    ],
    "sequia" => @sequia
  }

  @doc "La tinta de un peligro, como variable de CSS."
  def tinta(clave), do: Map.get(@tintas, clave, "--text2")

  @doc "Qué dice cada color de los peligros dados, sin repetir: `[variable, texto, hueco]`."
  def colores(claves), do: claves |> Enum.flat_map(&Map.get(@colores, &1, [])) |> Enum.uniq()

  @doc "Íconos, tintas y colores en JSON, para que el plano dibuje los mismos."
  def plano_json,
    do: Jason.encode!(%{iconos: Iconos.trazos(), tintas: @tintas, colores: @colores})

  @doc "Los peligros con algo que dibujar: `{clave, título}`."
  def dibujables, do: for(c <- @dibujables, do: {c, @titulos_peligro[c]})

  def dibujable?(clave), do: clave in @dibujables

  @doc "Los servicios que se calculan en un modo: `{clave, corto, título}`."
  def servicios(modo),
    do:
      for(
        {c, corto, titulo, solo_pie} <- @servicios,
        modo == "pie" or not solo_pie,
        do: {c, corto, titulo}
      )

  ## Celdas

  @cortes [0, 5, 20, 50]
  @rangos ["0 %", "hasta 5 %", "5 a 20 %", "20 a 50 %", "más de 50 %"]

  def rangos, do: @rangos

  @doc """
  La clase de un porcentaje, de 0 a 4: nadie, hasta 5 %, hasta 20 %, hasta la
  mitad y más de la mitad.

      iex> Enum.map([0, 0.0, 0.01, 5, 5.1, 20, 50, 50.1, 100], &MapoWeb.Cotejo.clase/1)
      [0, 0, 1, 1, 2, 2, 3, 4, 4]
  """
  def clase(nil), do: nil
  def clase(pct), do: Enum.count(@cortes, &(pct > &1))

  @doc """
  Un porcentaje como cabe en una celda.

      iex> Enum.map([0, 0.02, 4.26, 9.97, 59.5, 99.96, 100.0], &MapoWeb.Cotejo.pct/1)
      ["0 %", "<0.1 %", "4.3 %", "10 %", "60 %", "99.9 %", "100 %"]
  """
  def pct(v) when v == 0, do: "0 %"
  def pct(v) when v < 0.05, do: "<0.1 %"
  def pct(v) when v < 9.95, do: "#{cifra(v / 1, 1)} %"
  # Casi todo no es todo.
  def pct(v) when v >= 99.5 and v < 100, do: "#{Float.floor(v / 1, 1)} %"
  def pct(v), do: "#{round(v)} %"

  @doc "La celda de un peligro, de su medida en mapo_core (la zona o un municipio)."
  def celda_peligro(tipo, medida, cerca_m)

  def celda_peligro(_tipo, nil, _cerca), do: sin("sin dato", "Sin dato")

  def celda_peligro("gente", %{"sin_medicion" => true}, cerca),
    do:
      sin(
        "sin red",
        "Ningún sitio de la red de monitoreo dentro ni a menos de #{metros(cerca)}: no hay medición"
      )

  def celda_peligro("gente", %{"pct" => nil, "total" => 0} = m, _cerca),
    do: %{
      sin("sin gente", "Nadie vive ahí: no hay porcentaje")
      | detalle: m["detalle"],
        corto: m["corto"]
    }

  def celda_peligro("gente", %{"pct" => nil} = m, _cerca),
    do: %{
      sin("sin dato", "INEGI reserva la población de esos lugares")
      | detalle: m["detalle"],
        corto: m["corto"]
    }

  def celda_peligro("gente", m, cerca) do
    %{
      clase: clase(m["pct"]),
      cifra: pct(m["pct"]),
      detalle: m["detalle"],
      corto: m["corto"],
      color: nil,
      titulo:
        "#{cifra(m["pct"] / 1, 2)} %: #{cifra(m["personas"])} de #{cifra(m["total"])} personas a #{metros(cerca)} o menos; #{m["detalle"]}"
    }
  end

  def celda_peligro("area", %{"pct" => nil}, _cerca),
    do: sin("sin dato", "Ningún acuífero cargado")

  def celda_peligro("area", m, _cerca) do
    %{
      clase: clase(m["pct"]),
      cifra: pct(m["pct"]),
      detalle: m["detalle"],
      corto: m["corto"],
      color: nil,
      titulo:
        "#{cifra(m["pct"] / 1, 1)} % del área sobre acuíferos sin disponibilidad (#{m["detalle"]})"
    }
  end

  def celda_peligro("categoria", %{"categoria" => nil, "rango" => [a, b]}, _cerca) do
    cifra = if a == "sin", do: "hasta #{b}", else: "#{a} a #{b}"
    %{sin(cifra, "Sus municipios están en categorías distintas") | estado: "plana"}
  end

  def celda_peligro("categoria", %{"categoria" => nil}, _cerca), do: sin("sin dato", "Sin dato")

  def celda_peligro("categoria", m, _cerca) do
    %{
      clase: nil,
      cifra: if(m["categoria"] == "sin", do: "sin anomalía", else: m["categoria"]),
      detalle: m["detalle"],
      corto: m["corto"],
      color: m["categoria"],
      titulo:
        "#{m["texto"]} en el último corte; #{m["severa"]} de #{m["cortes"]} cortes de los últimos 5 años en sequía severa o peor"
    }
    |> Map.put(:estado, "categoria")
  end

  @doc """
  La celda de un servicio: qué parte de su grupo queda a más de `umbral`
  minutos. `c` es la curva (`total`, `sin_ruta`, `dentro`) de la zona o de un
  municipio; la gente sin ruta no cuenta ni cerca ni lejos.
  """
  def celda_servicio(c, umbral, grupo)

  def celda_servicio(nil, _umbral, _grupo), do: sin("sin calc.", "Aquí no se calcula")

  def celda_servicio(%{"lugares" => 0}, _umbral, _grupo),
    do: sin("sin calc.", "Aquí no se calcula")

  def celda_servicio(c, umbral, grupo) do
    r = resumen(c, umbral)
    sin_calcular = c["sin_calcular"] || 0

    cond do
      # Con menos de la mitad del grupo calculado, la cifra engaña: en Mezquitic,
      # 0 % lejos de la primaria eran 337 de 3,909 (las localidades no se calculan).
      sin_calcular > c["total"] ->
        sin(
          "parcial",
          "Solo se calcula para #{cifra(c["total"])} de #{cifra(c["total"] + sin_calcular)} #{grupo}"
        )

      r.con_ruta == 0 ->
        sin("sin gente", "Nadie de este grupo con ruta por calle")

      true ->
        pct = r.fuera * 100 / r.con_ruta

        %{
          clase: clase(pct),
          cifra: pct(pct),
          detalle: corta(r.fuera),
          corto: corta(r.fuera),
          color: nil,
          titulo:
            "#{cifra(pct, 1)} %: #{cifra(r.fuera)} de #{cifra(r.con_ruta)} #{grupo} a más de #{umbral} minutos"
        }
    end
  end

  @doc """
  Lo que se lee de un servicio con el umbral elegido: `dentro[m]` es la gente a
  m minutos o menos, y la gente sin ruta no cuenta ni cerca ni lejos.
  """
  def resumen(c, umbral) do
    dentro = Enum.at(c["dentro"], min(umbral, length(c["dentro"]) - 1))
    con_ruta = c["total"] - c["sin_ruta"]
    %{dentro: dentro, fuera: con_ruta - dentro, con_ruta: con_ruta}
  end

  @doc """
  Una cantidad que cabe en una celda.

      iex> Enum.map([0, 950, 1234, 45_600, 1_385_629], &MapoWeb.Cotejo.corta/1)
      ["0", "950", "1.2 mil", "46 mil", "1.4 M"]
  """
  def corta(n) when n < 1000, do: "#{n}"
  def corta(n) when n < 9_950, do: "#{cifra(n / 1000, 1)} mil"
  def corta(n) when n < 999_500, do: "#{round(n / 1000)} mil"
  def corta(n), do: "#{cifra(n / 1_000_000, 1)} M"

  defp sin(cifra, titulo),
    do: %{
      clase: nil,
      cifra: cifra,
      detalle: nil,
      corto: nil,
      color: nil,
      titulo: titulo,
      estado: "rayada"
    }

  defp metros(m) when m >= 1000, do: "#{cifra(m / 1000, 0)} km"
  defp metros(m), do: "#{m} m"

  defp estado(%{estado: e}), do: e
  defp estado(_celda), do: "valor"

  ## Componentes

  attr :vista, :string, required: true

  @doc "El cambio entre lista, matriz y mapas chicos."
  def vistas(assigns) do
    ~H"""
    <div class="cotejo-vistas" role="group" aria-label="Cómo verlo">
      <button
        :for={{v, texto} <- [{"lista", "Lista"}, {"matriz", "Matriz"}, {"mapas", "Mapas"}]}
        type="button"
        id={"vista-#{v}"}
        class="chico"
        phx-click="vista"
        phx-value-vista={v}
        aria-pressed={to_string(@vista == v)}
      >
        {texto}
      </button>
    </div>
    """
  end

  attr :celda, :map, required: true
  attr :class, :any, default: nil

  @doc "La cifra con su clase, suelta (en la lista y en los mapas chicos)."
  def ficha(assigns) do
    ~H"""
    <span
      class={["cotejo-ficha", @class]}
      data-clase={@celda.clase}
      data-color={@celda.color}
      data-estado={estado(@celda)}
      title={@celda.titulo}
    >
      <b class="num">{@celda.cifra}</b> <small :if={@celda.detalle}>{@celda.detalle}</small>
    </span>
    """
  end

  attr :id, :string, required: true
  attr :titulo, :string, required: true, doc: "el caption, para lectores de pantalla"
  attr :columnas, :list, required: true, doc: "`%{clave, corto, titulo, inactiva}`"
  attr :filas, :list, required: true, doc: "`%{id, nombre, nota, gente, celdas, fija}`"
  attr :activa, :string, default: nil

  @doc "Zonas por columnas: cada celda con su clase y su cifra."
  def matriz(assigns) do
    ~H"""
    <div class="cotejo-matriz" tabindex="0" role="region" aria-label={@titulo}>
      <table id={@id}>
        <caption class="sr-only">{@titulo}</caption>

        <thead>
          <tr>
            <th scope="col" class="cotejo-zona">Zona</th>

            <th scope="col" class="cotejo-gente">Gente</th>

            <th :for={c <- @columnas} scope="col" class={@activa == c.clave && "activa"}>
              <button
                type="button"
                phx-click="ver"
                phx-value-clave={c.clave}
                aria-pressed={to_string(@activa == c.clave)}
                aria-label={"Ver #{c.titulo}"}
                title={c.titulo}
                disabled={Map.get(c, :inactiva, false)}
              >
                <.icono nombre={c.clave} /> <span>{c.corto}</span>
                <small :if={Map.get(c, :unidad)}>{c.unidad}</small>
              </button>
            </th>
          </tr>
        </thead>

        <tbody>
          <tr :for={f <- @filas} id={"#{@id}-#{f.id}"} class={f.id == "zona" && "total"}>
            <th scope="row" class="cotejo-zona">
              {f.nombre}
              <small :if={f.nota}>{f.nota}</small>
              <button
                :if={Map.get(f, :fija)}
                type="button"
                class="cotejo-quitar"
                phx-click="soltar"
                phx-value-clave={f.fija}
                aria-label={"Quitar #{f.nombre} de la matriz"}
              >
                ×
              </button>
            </th>

            <td class="cotejo-gente num" title={f.gente && "#{cifra(f.gente)} personas"}>
              {if f.gente, do: corta(f.gente), else: "sin dato"}
            </td>

            <td
              :for={c <- @columnas}
              data-clase={f.celdas[c.clave].clase}
              data-color={f.celdas[c.clave].color}
              data-estado={estado(f.celdas[c.clave])}
              class={@activa == c.clave && "activa"}
              title={f.celdas[c.clave].titulo}
            >
              <b class="num">{f.celdas[c.clave].cifra}</b>
              <small :if={f.celdas[c.clave].corto}>{f.celdas[c.clave].corto}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    """
  end

  attr :que, :string, required: true, doc: "qué mide el porcentaje"
  attr :sequia, :boolean, default: false
  attr :sin, :string, default: nil, doc: "qué dice la celda rayada"

  def leyenda(assigns) do
    assigns = assign(assigns, rangos: Enum.with_index(@rangos))

    ~H"""
    <div class="cotejo-leyenda">
      <p>{@que}</p>

      <ul>
        <li :for={{rango, i} <- @rangos}>
          <span class="cotejo-muestra" data-clase={i} aria-hidden="true"></span> {rango}
        </li>

        <li :if={@sin}>
          <span class="cotejo-muestra" data-estado="rayada" aria-hidden="true"></span> {@sin}
        </li>
      </ul>

      <p :if={@sequia}>Sequía: categoría del Monitor en el último corte</p>

      <ul :if={@sequia}>
        <li :for={
          {c, t} <- [
            {"sin", "sin anomalía"},
            {"D0", "D0 seco"},
            {"D1", "D1 moderada"},
            {"D2", "D2 severa"},
            {"D3", "D3 extrema"},
            {"D4", "D4 excepcional"}
          ]
        }>
          <span class="cotejo-muestra" data-color={c} aria-hidden="true"></span> {t}
        </li>
      </ul>
    </div>
    """
  end

  attr :columnas, :list, required: true
  attr :celdas, :map, required: true, doc: "la celda de la zona entera, por columna"
  attr :activa, :string, default: nil
  attr :oculta, :boolean, required: true
  attr :tipo, :string, required: true, doc: "peligros | servicios"

  @doc """
  Un mapa chico por columna, todos con el mismo recuadro. El hook los dibuja con
  lo mismo que manda al plano; cada uno es un botón que lo lleva al plano grande.
  """
  def mapas(assigns) do
    ~H"""
    <div
      id="mapas-chicos"
      class="cotejo-mapas"
      phx-hook="MapasChicos"
      data-tipo={@tipo}
      hidden={@oculta}
    >
      <button
        :for={c <- @columnas}
        type="button"
        id={"mapa-#{c.clave}"}
        class={["cotejo-mapa", @activa == c.clave && "activa"]}
        phx-click="ver"
        phx-value-clave={c.clave}
        aria-pressed={to_string(@activa == c.clave)}
        disabled={Map.get(c, :inactiva, false)}
      >
        <span class="cotejo-mapa-titulo">
          <.icono nombre={c.clave} /> {c.titulo}
        </span>
        <span id={"lienzo-#{c.clave}"} class="cotejo-lienzo" phx-update="ignore">
          <canvas data-clave={c.clave} aria-hidden="true"></canvas>
        </span>
        <.ficha :if={@celdas[c.clave]} celda={@celdas[c.clave]} />
      </button>
    </div>
    """
  end

  ## Cómo citar

  # Cada bloque de mapo_core/riesgos.py con su referencia (docs/producto/citar.md).
  @fuente_bloque %{
    "poblacion" => "censo",
    "agua_superficial" => "renameca",
    "agua_subterranea" => "renameca",
    "descargas" => "repda",
    "retc" => "retc",
    "fuego" => "firms",
    "acuifero" => "acuiferos",
    "sequia" => "sequia",
    "anp" => "anp",
    "uso_suelo" => "uso_suelo",
    "agricultura" => "siap",
    "defunciones" => "defunciones"
  }

  def fuente_peligro(clave), do: @fuente_bloque[clave]

  # De dónde salen los destinos de cada servicio.
  @fuente_destinos %{
    "centro_salud" => "clues",
    "umf_imss" => "clues",
    "hospital_publico" => "clues",
    "transporte_masivo" => "osm"
  }

  @frase_modo %{"pie" => "a pie", "auto" => "en auto"}

  @doc "Las referencias de un servicio: sus destinos, la gente y la red."
  def citas_servicio(resultado, clave, umbral, enlace) do
    s = Enum.find(resultado["servicios"], &(&1["clave"] == clave))
    modo = @frase_modo[resultado["modo"]]
    lugar = resultado["zona"]["nombre"]
    version = "calculado el #{s["fecha"]}"

    que = "#{s["titulo"]}: #{s["grupo_etiqueta"]} a más de #{umbral} minutos #{modo}, #{lugar}"

    destinos =
      case s["feeds"] do
        [_ | _] = feeds ->
          for f <- feeds,
              do:
                Cita.gtfs(f,
                  que: que,
                  datos: "frecuencias del #{f["fecha_ref"]}",
                  version: version,
                  enlace: enlace
                )

        _ ->
          [
            Cita.armar(@fuente_destinos[clave] || "denue",
              que: que,
              version: version,
              enlace: enlace
            )
          ]
      end

    destinos ++
      [
        Cita.armar("censo",
          que: "#{s["grupo_etiqueta"]} por AGEB urbano y localidad, #{lugar}",
          datos: "2020",
          enlace: enlace
        ),
        Cita.armar("osm",
          que: "minutos #{modo} por calle; #{s["red"]}",
          version: version,
          enlace: enlace
        )
      ]
  end
end
