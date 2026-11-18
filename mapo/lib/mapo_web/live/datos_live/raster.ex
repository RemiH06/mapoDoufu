defmodule MapoWeb.DatosLive.Raster do
  @moduledoc """
  Valor de un ráster del equipo en cada renglón de una capa: el del píxel en el
  punto, o un resumen en una zona. Se revisa aquí y, si sirve, se guarda como
  capa. El cálculo vive en `Mapo.Capas.Muestreo`; ver docs/producto/datos-propios.md.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras
  import MapoWeb.DatosLive.Derivada

  alias Mapo.Capas
  alias Mapo.Capas.Muestreo
  alias Mapo.Limite
  alias Mapo.Teams

  # Comparte el tope con la distancia: los dos cuestan CPU de la base.
  @max_calculos 60
  @ventana 3600

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" amplio?={true}>
      <div class="equipo">
        <section class="doc pegado" aria-labelledby="t-raster">
          <header class="doc-cab">
            <h1 id="t-raster">Ráster en {@capa.nombre}</h1>
            <span class="doc-tipo">{cifra(@capa.num_filas)} renglones</span>
          </header>

          <div class="doc-seccion">
            <p class="secundario">
              El valor de un ráster del equipo en cada renglón: el del píxel donde cae un punto, o un resumen de los píxeles alrededor o adentro. Los valores salen con la escala del archivo.
            </p>

            <p :if={@rasters == []} class="nota">
              El equipo no tiene ningún ráster con valores. Sube un GeoTIFF; los que se subieron antes de noviembre de 2026 hay que subirlos otra vez.
            </p>

            <.form
              :if={@rasters != []}
              for={@form}
              id="raster_form"
              phx-change="cambiar"
              phx-submit="calcular"
            >
              <fieldset class="cruce-grupo">
                <legend>Desde {@capa.nombre}</legend>

                <.input
                  field={@form[:etiqueta_origen]}
                  type="select"
                  label="Columna que nombra cada renglón"
                  options={@capa.columnas}
                />
                <.condiciones
                  form={@form}
                  lado="origen"
                  columnas={@capa.columnas}
                  fechas={@capa.fechas}
                  ejemplo="educación"
                />
              </fieldset>

              <fieldset class="cruce-grupo">
                <legend>Ráster</legend>
                <.input field={@form[:raster]} type="select" label="Capa" options={@rasters} />
                <.input
                  field={@form[:radio]}
                  type="number"
                  min="1"
                  max="100000"
                  label={etiqueta_radio(@capa)}
                />
                <.input
                  field={@form[:valores]}
                  type="text"
                  label="Además, qué parte tiene estos valores (opcional)"
                  placeholder="40"
                />
                <p class="secundario">
                  Para clases como las de WorldCover: 40 es cultivo, 50 construido. Separa varios con una barra: 10|20.
                </p>
              </fieldset>

              <div class="doc-botones">
                <.button variant="primary" phx-disable-with="Calculando...">Calcular</.button>
                <.link navigate={~p"/teams/#{@team}/datos"} class="boton">Volver a los datos</.link>
              </div>
            </.form>
          </div>
        </section>

        <section
          :if={@resultado}
          class="doc pegado cruce-resultado"
          aria-labelledby="t-resultado"
          tabindex="-1"
          phx-mounted={JS.focus()}
        >
          <header class="doc-cab">
            <h2 id="t-resultado">Resultado</h2>

            <span class="doc-tipo">
              {cifra(@resultado.total - @resultado.sin_dato)} de {cifra(@resultado.total)} con valor
            </span>
          </header>

          <div class="doc-seccion">
            <div class="tabla-muestra">
              <table>
                <caption class="sr-only">Los renglones con valor más alto</caption>

                <thead>
                  <tr>
                    <th scope="col">{@opciones.etiqueta_origen}</th>

                    <th :for={c <- @resultado.columnas} scope="col">{c}</th>
                  </tr>
                </thead>

                <tbody>
                  <tr :for={fila <- @resultado.filas}>
                    <td>{fila.nombre || "sin dato"}</td>

                    <td :for={v <- fila.valores}>{celda(v)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p :if={@resultado.total > length(@resultado.filas)} class="secundario">
              Se ven los {length(@resultado.filas)} de valor más alto. Guarda la capa para ver todos en el mapa o bajarlos en CSV.
            </p>

            <details class="cruce-metodo" open>
              <summary>Cómo se calculó</summary>

              <ul>
                <li :for={linea <- @resultado.metodo}>{linea}</li>
              </ul>
            </details>

            <.form for={@guardado} id="guardar_form" phx-submit="guardar">
              <.input field={@guardado[:nombre]} type="text" label="Nombre de la capa" required />
              <div class="doc-botones">
                <.button variant="primary" phx-disable-with="Guardando...">Guardar como capa</.button>
              </div>
            </.form>
          </div>
        </section>
      </div>
    </Layouts.app>
    """
  end

  defp etiqueta_radio(%{tipo: "puntos"}),
    do: "Radio en metros (opcional; sin radio, el valor del píxel en el punto)"

  defp etiqueta_radio(_),
    do: "Radio en metros (opcional; sin radio, los píxeles dentro de cada polígono)"

  @impl true
  def mount(%{"id" => id, "capa_id" => capa_id}, _session, socket) do
    scope = socket.assigns.current_scope
    team = Teams.get_team!(scope, id)

    case Capas.get_capa(scope, capa_id) do
      %{team_id: team_id} = capa when team_id == team.id ->
        if Muestreo.muestreable?(capa),
          do: montar(socket, team, capa),
          else: regresar(socket, team)

      _ ->
        regresar(socket, team)
    end
  end

  defp montar(socket, team, capa) do
    rasters =
      socket.assigns.current_scope
      |> Capas.list_capas(team.id)
      |> Enum.filter(&(&1.tipo == "raster"))
      |> Enum.filter(&Capas.raster_con_valores?/1)

    params = %{
      "etiqueta_origen" => etiqueta(capa),
      "raster" => rasters |> List.first() |> then(&(&1 && to_string(&1.id))),
      "radio" => "",
      "valores" => ""
    }

    {:ok,
     assign(socket,
       team: team,
       capa: capa,
       candidatas: rasters,
       rasters: Enum.map(rasters, &{&1.nombre, to_string(&1.id)}),
       form: to_form(params, as: "raster"),
       guardado: to_form(%{"nombre" => ""}, as: "guardado"),
       opciones: nil,
       resultado: nil
     )}
  end

  defp regresar(socket, team) do
    {:ok,
     socket
     |> put_flash(:error, "Desde esa capa no se puede leer un ráster.")
     |> push_navigate(to: ~p"/teams/#{team}/datos")}
  end

  @impl true
  def handle_event("cambiar", %{"raster" => params}, socket),
    do: {:noreply, assign(socket, form: to_form(params, as: "raster"), resultado: nil)}

  def handle_event("calcular", %{"raster" => params}, socket) do
    scope = socket.assigns.current_scope

    if Limite.permitir?({:distancia, scope.user.id}, @max_calculos, @ventana) do
      {:noreply, calcular(assign(socket, form: to_form(params, as: "raster")), params)}
    else
      {:noreply, put_flash(socket, :error, "Demasiados cálculos en una hora. Espera un rato.")}
    end
  end

  def handle_event("guardar", %{"guardado" => %{"nombre" => nombre}}, socket) do
    %{capa: capa, team: team, resultado: resultado, opciones: opciones, current_scope: scope} =
      socket.assigns

    case resultado && Muestreo.guardar(scope, capa, opciones, String.trim(nombre), resultado) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Valores guardados como capa.")
         |> push_navigate(to: ~p"/teams/#{team}/datos")}

      nil ->
        {:noreply, socket}

      {:error, motivo} ->
        {:noreply, put_flash(socket, :error, mensaje(motivo))}
    end
  end

  defp calcular(socket, params) do
    %{capa: capa, candidatas: candidatas} = socket.assigns
    raster = Enum.find(candidatas, &(to_string(&1.id) == params["raster"]))

    with {:ok, radio} <- radio(params["radio"]),
         {:ok, filtro_origen} <- condiciones_de(params, "origen", capa) do
      opciones = %{
        raster: raster,
        radio: radio,
        valores: params["valores"],
        etiqueta_origen: columna(params["etiqueta_origen"], capa),
        filtro_origen: filtro_origen
      }

      case Muestreo.calcular(capa, opciones) do
        {:ok, resultado} ->
          nombre = String.slice("#{raster.nombre} en #{capa.nombre}", 0, 120)

          socket
          |> clear_flash()
          |> assign(
            opciones: opciones,
            resultado: resultado,
            guardado: to_form(%{"nombre" => nombre}, as: "guardado")
          )

        {:error, mensaje} ->
          put_flash(socket, :error, mensaje)
      end
    else
      {:error, mensaje} -> put_flash(socket, :error, mensaje)
    end
  end

  defp celda(nil), do: "sin dato"
  defp celda(valor), do: cifra(valor)
end
