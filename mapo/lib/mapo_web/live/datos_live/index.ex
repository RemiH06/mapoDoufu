defmodule MapoWeb.DatosLive.Index do
  @moduledoc """
  Datos propios de un equipo: subir un archivo, decir dónde está cada renglón
  y guardarlo como capa para `/mapa`. Ver docs/producto/datos-propios.md.

  El archivo vive solo en la memoria de este proceso entre "Leer" y "Guardar":
  nunca se escribe en disco ni se guarda el original, solo los renglones
  ubicados. Quien lo interpreta es `mapo_core`.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.Capas
  alias Mapo.Limite
  alias Mapo.MapoCore
  alias Mapo.Teams

  @partes ~w(ent mun loc ageb)

  # Interpretar un archivo grande cuesta CPU de la máquina: sin esto, una sola
  # cuenta podría tenerla ocupada subiendo el mismo archivo una y otra vez.
  @max_lecturas 30
  @ventana_lecturas 3600

  @tipos [
    {"Coordenadas (latitud y longitud)", "puntos"},
    {"Clave de municipio (5 dígitos)", "municipio"},
    {"Clave de AGEB (13 caracteres)", "ageb"}
  ]

  # LiveView solo acepta extensiones que conoce la tabla de tipos MIME, y
  # `.gpkg` no está: el navegador filtra con esta lista y `mapo_core` decide.
  @aceptados ".csv,.xlsx,.geojson,.json,.zip,.gpkg,.tif,.tiff"

  @impl true
  def render(assigns) do
    assigns = assign(assigns, tipos: @tipos, aceptados: @aceptados)

    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" amplio?={true}>
      <div class="equipo">
        <section class="doc pegado" aria-labelledby="t-datos">
          <header class="doc-cab">
            <h1 id="t-datos">Datos de {@team.name}</h1>
            <span class="doc-tipo">{megas(@uso)} de {megas(Capas.max_bytes_equipo())}</span>
          </header>

          <div class="doc-seccion">
            <p :if={@capas == []} class="nota">
              Todavía no hay capas. Sube un archivo y aparece como acetato en el mapa.
            </p>

            <ul :if={@capas != []} class="lista-doc">
              <li :for={c <- @capas} class="lista-fila">
                <span>
                  <b>{c.nombre}</b>
                  <span class="secundario capa-detalle">
                    {detalle(c)}
                  </span>
                </span>
                <span class="lista-fin">
                  <.link navigate={~p"/mapa?#{[capa: c.id]}"} class="boton chico-doc">
                    Ver en el mapa
                  </.link>
                  <.button
                    :if={Capas.puede_borrar?(@current_scope, c)}
                    phx-click="borrar"
                    phx-value-id={c.id}
                    data-confirm={"¿Borrar la capa #{c.nombre}?"}
                    class="boton chico-doc borrar"
                  >
                    Borrar
                  </.button>
                </span>
              </li>
            </ul>

            <p><.link navigate={~p"/teams/#{@team}"}>Volver al equipo</.link></p>
          </div>
        </section>

        <section class="doc pegado" aria-labelledby="t-subir">
          <header class="doc-cab">
            <h2 id="t-subir">Subir un archivo</h2>
            <span class="doc-tipo">Tabla, vectorial o ráster · hasta 50 MB</span>
          </header>

          <div class="doc-seccion">
            <p class="nota">
              Mapo todavía es una demostración. No subas datos personales ni confidenciales, como nombres, teléfonos o datos de clientes.
            </p>
            <p class="secundario">
              La capa la ve solo tu equipo, pero quien administra esta instalación puede llegar a leerla, y los respaldos la conservan unos días después de borrarla.
            </p>

            <p class="secundario">
              CSV, XLSX, GeoJSON, shapefile en ZIP, GeoPackage o GeoTIFF.
            </p>

            <.form
              :if={is_nil(@archivo)}
              for={%{}}
              as={:subida}
              id="subir_form"
              phx-drop-target={@uploads.archivo.ref}
              phx-change="validar"
              phx-submit="leer"
              class="subida"
            >
              <.live_file_input upload={@uploads.archivo} accept={@aceptados} />
              <p :for={e <- upload_errors(@uploads.archivo)} class="nota">{error_subida(e)}</p>
              <div :for={entrada <- @uploads.archivo.entries}>
                <p class="secundario">{entrada.client_name}: {entrada.progress}%</p>
                <p :for={e <- upload_errors(@uploads.archivo, entrada)} class="nota">
                  {error_subida(e)}
                </p>
              </div>
              <.button
                variant="primary"
                phx-disable-with="Leyendo..."
                disabled={@uploads.archivo.entries == []}
              >
                Leer archivo
              </.button>
            </.form>

            <div :if={@archivo} class="subida">
              <p><b>{@archivo.nombre}</b>{descripcion(@archivo.lectura)}</p>
              <p :for={aviso <- @archivo.lectura["avisos"]} class="nota">{aviso}</p>

              <div :if={@archivo.lectura["columnas"] != []} class="tabla-muestra">
                <table>
                  <caption class="sr-only">Primeros renglones del archivo</caption>
                  <thead>
                    <tr>
                      <th :for={c <- @archivo.lectura["columnas"]} scope="col">{c}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr :for={fila <- @archivo.lectura["muestra"]}>
                      <td :for={celda <- fila}>{celda}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <.form for={@form} id="capa_form" phx-change="ubicacion" phx-submit="guardar">
                <.input field={@form[:nombre]} type="text" label="Nombre de la capa" required />
                <.input :if={fijo?(@archivo)} field={@form[:tipo]} type="hidden" />
                <p :if={fijo?(@archivo)} class="secundario">
                  Trae su propia ubicación: se dibuja tal cual en el plano.
                </p>
                <.input
                  :if={not fijo?(@archivo)}
                  field={@form[:tipo]}
                  type="select"
                  label="Cómo se ubica cada renglón"
                  options={@tipos}
                />
                <.columna
                  :for={{campo, etiqueta} <- campos(@form)}
                  campo={@form[campo]}
                  etiqueta={etiqueta}
                  columnas={@archivo.lectura["columnas"]}
                />
                <.input
                  :if={zona?(@form)}
                  field={@form[:partes]}
                  type="checkbox"
                  label="La clave viene en varias columnas"
                />
                <div class="doc-botones">
                  <.button variant="primary" phx-disable-with="Guardando...">Guardar capa</.button>
                  <.button type="button" phx-click="descartar" class="boton">Descartar</.button>
                </div>
              </.form>
            </div>
          </div>
        </section>
      </div>
    </Layouts.app>
    """
  end

  attr :campo, Phoenix.HTML.FormField, required: true
  attr :etiqueta, :string, required: true
  attr :columnas, :list, required: true

  defp columna(assigns) do
    ~H"""
    <.input
      field={@campo}
      type="select"
      label={@etiqueta}
      options={@columnas}
      prompt="Elige una columna"
      required
    />
    """
  end

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    team = Teams.get_team!(socket.assigns.current_scope, id)

    {:ok,
     socket
     |> assign(team: team, archivo: nil, form: to_form(%{}, as: "capa"))
     |> recargar()
     |> allow_upload(:archivo,
       accept: :any,
       max_entries: 1,
       max_file_size: Capas.max_bytes_archivo()
     )}
  end

  @impl true
  def handle_event("validar", _params, socket), do: {:noreply, socket}

  def handle_event("leer", _params, socket) do
    scope = socket.assigns.current_scope

    if Limite.permitir?({:datos, scope.user.id}, @max_lecturas, @ventana_lecturas) do
      {:noreply, leer(socket)}
    else
      {:noreply, put_flash(socket, :error, "Demasiados archivos en una hora. Espera un rato.")}
    end
  end

  def handle_event("ubicacion", %{"capa" => params}, socket),
    do: {:noreply, assign(socket, form: to_form(params, as: "capa"))}

  def handle_event("descartar", _params, socket),
    do: {:noreply, assign(socket, archivo: nil, form: to_form(%{}, as: "capa"))}

  def handle_event("guardar", %{"capa" => params}, socket) do
    %{nombre: nombre, contenido: contenido, formato: formato} = socket.assigns.archivo

    socket =
      with {:ok, ubicados} <- MapoCore.datos_ubicar(contenido, formato, ubicacion(params)),
           :ok <- alguno_ubicado(ubicados),
           {:ok, capa} <- guardar(socket, params, nombre, byte_size(contenido), ubicados) do
        socket
        |> assign(archivo: nil, form: to_form(%{}, as: "capa"))
        |> recargar()
        |> put_flash(:info, resumen(capa, ubicados))
      else
        {:error, motivo} -> put_flash(socket, :error, mensaje(motivo))
      end

    {:noreply, socket}
  end

  def handle_event("borrar", %{"id" => id}, socket) do
    scope = socket.assigns.current_scope
    capa = Capas.get_capa(scope, id)

    if capa && capa.team_id == socket.assigns.team.id && Capas.puede_borrar?(scope, capa) do
      {:ok, _} = Capas.delete_capa(scope, capa)
      {:noreply, recargar(socket)}
    else
      {:noreply, put_flash(socket, :error, "Esa capa no se puede borrar.")}
    end
  end

  defp leer(socket) do
    [{nombre, contenido}] =
      consume_uploaded_entries(socket, :archivo, fn %{path: path}, entrada ->
        {:ok, {entrada.client_name, File.read!(path)}}
      end)

    formato = nombre |> Path.extname() |> String.trim_leading(".") |> String.downcase()

    with true <- Capas.cabe?(socket.assigns.team.id, byte_size(contenido)) || {:error, :cuota},
         {:ok, lectura} <- MapoCore.datos_leer(contenido, formato) do
      assign(socket,
        archivo: %{nombre: nombre, contenido: contenido, formato: formato, lectura: lectura},
        form: to_form(valores_iniciales(nombre, lectura["sugerencia"]), as: "capa")
      )
    else
      {:error, motivo} -> put_flash(socket, :error, mensaje(motivo))
    end
  end

  defp valores_iniciales(nombre, sugerencia) do
    base = %{"nombre" => Path.rootname(nombre), "tipo" => "puntos"}

    case sugerencia do
      %{"partes" => partes, "tipo" => tipo} ->
        partes = Enum.zip(@partes, partes) |> Map.new()
        base |> Map.merge(partes) |> Map.merge(%{"tipo" => tipo, "partes" => "true"})

      nil ->
        base

      sugerencia ->
        Map.merge(base, sugerencia)
    end
  end

  defp fijo?(%{lectura: %{"sugerencia" => %{"tipo" => tipo}}}), do: tipo in ~w(vector raster)
  defp fijo?(_), do: false

  defp zona?(form), do: form[:tipo].value in ~w(municipio ageb)
  defp partida?(form), do: form[:partes].value in ["true", true]

  defp campos(form) do
    cond do
      form[:tipo].value == "puntos" ->
        [lat: "Columna de latitud", lon: "Columna de longitud"]

      not zona?(form) ->
        []

      not partida?(form) ->
        [clave: "Columna de la clave"]

      form[:tipo].value == "municipio" ->
        [ent: "Columna del estado", mun: "Columna del municipio"]

      true ->
        [
          ent: "Columna del estado",
          mun: "Columna del municipio",
          loc: "Columna de la localidad",
          ageb: "Columna del AGEB"
        ]
    end
  end

  defp ubicacion(%{"tipo" => "puntos", "lat" => lat, "lon" => lon}),
    do: [tipo: "puntos", lat: lat, lon: lon]

  defp ubicacion(%{"tipo" => tipo}) when tipo in ~w(vector raster), do: [tipo: tipo]

  defp ubicacion(%{"tipo" => tipo, "partes" => "true"} = params) do
    columnas = if tipo == "municipio", do: ~w(ent mun), else: @partes
    [{:tipo, tipo} | Enum.map(columnas, &{:clave, params[&1]})]
  end

  defp ubicacion(%{"tipo" => tipo, "clave" => clave}), do: [tipo: tipo, clave: clave]

  defp alguno_ubicado(%{"raster" => _}), do: :ok

  defp alguno_ubicado(%{"filas" => [], "descartes" => descartes}),
    do: {:error, {:nada_ubicado, descartes}}

  defp alguno_ubicado(_), do: :ok

  defp guardar(socket, params, archivo, bytes, ubicados) do
    attrs = %{
      nombre: String.trim(params["nombre"]),
      archivo: archivo,
      tamano_bytes: bytes,
      tipo: ubicados["tipo"],
      columnas: ubicados["columnas"],
      numericas: ubicados["numericas"],
      num_filas: length(ubicados["filas"]),
      num_descartadas: ubicados["num_filas"] - length(ubicados["filas"]),
      repetidas: ubicados["repetidas"]
    }

    Capas.crear_capa(
      socket.assigns.current_scope,
      socket.assigns.team.id,
      attrs,
      ubicados["filas"],
      imagen(ubicados["raster"])
    )
  end

  defp imagen(nil), do: nil

  defp imagen(raster) do
    %{
      png: Base.decode64!(raster["png"]),
      oeste: raster["oeste"],
      sur: raster["sur"],
      este: raster["este"],
      norte: raster["norte"],
      limites: raster["limites"]
    }
  end

  defp recargar(socket) do
    team_id = socket.assigns.team.id

    assign(socket,
      capas: Capas.list_capas(socket.assigns.current_scope, team_id),
      uso: Capas.uso_equipo(team_id)
    )
  end

  defp resumen(%{tipo: "raster"}, _), do: "Capa guardada."

  defp resumen(capa, %{"descartes" => descartes}) do
    base = "Capa guardada: #{cifra(capa.num_filas)} renglones en el mapa."

    case texto_descartes(descartes) do
      "" -> base
      texto -> "#{base} Sin ubicar: #{texto}."
    end
  end

  defp texto_descartes(descartes) do
    [
      {"sin_dato", "sin dato de ubicación"},
      {"no_es_numero", "coordenada que no es número"},
      {"fuera_de_mexico", "fuera de México (¿longitud sin signo negativo?)"},
      {"clave_invalida", "clave con otra forma"},
      {"clave_desconocida", "clave que no está en el marco cargado"}
    ]
    |> Enum.filter(fn {clave, _} -> (descartes[clave] || 0) > 0 end)
    |> Enum.map_join(", ", fn {clave, texto} -> "#{cifra(descartes[clave])} #{texto}" end)
  end

  defp mensaje({:nada_ubicado, descartes}),
    do: "No se ubicó ningún renglón: #{texto_descartes(descartes)}."

  defp mensaje(:cuota), do: "Ese archivo ya no cabe en los 500 MB del equipo. Borra alguna capa."

  defp mensaje({:status, status, %{"detail" => detalle}})
       when status in [413, 422] and is_binary(detalle),
       do: detalle

  defp mensaje(%Ecto.Changeset{}), do: "Revisa el nombre de la capa (máximo 120 caracteres)."
  defp mensaje(_), do: "mapo_core no está disponible ahorita mismo."

  defp error_subida(:too_large), do: "El archivo pasa de 50 MB."
  defp error_subida(:too_many_files), do: "Sube un archivo a la vez."
  defp error_subida(_), do: "No se pudo subir el archivo."

  defp descripcion(%{"raster" => %{"ancho" => ancho, "alto" => alto}}),
    do: ": #{cifra(ancho)} × #{cifra(alto)} píxeles."

  defp descripcion(%{"num_filas" => n}), do: ": #{cifra(n)} renglones."

  defp detalle(%{tipo: "raster"} = capa), do: "ráster · #{megas(capa.tamano_bytes)}"

  defp detalle(capa) do
    total = capa.num_filas + capa.num_descartadas

    "#{cifra(capa.num_filas)} de #{cifra(total)} renglones · #{etiqueta(capa.tipo)} · #{megas(capa.tamano_bytes)}"
  end

  defp etiqueta("puntos"), do: "puntos"
  defp etiqueta("municipio"), do: "por municipio"
  defp etiqueta("ageb"), do: "por AGEB"
  defp etiqueta("vector"), do: "geometrías"

  defp megas(bytes) when bytes > 0 and bytes < 100 * 1024, do: "menos de 0.1 MB"
  defp megas(bytes), do: "#{cifra(bytes / (1024 * 1024))} MB"
end
