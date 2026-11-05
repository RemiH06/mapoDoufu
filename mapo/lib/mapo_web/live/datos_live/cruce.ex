defmodule MapoWeb.DatosLive.Cruce do
  @moduledoc """
  Cruce de una capa con fuentes públicas, por zona: la persona dice cómo se
  agrega cada columna, porque Mapo no sabe qué mide. El resultado se revisa
  aquí y, si sirve, se guarda como capa. Ver docs/producto/datos-propios.md.

  El cálculo vive en `mapo_core`, que recibe los renglones en la petición.
  Aquí se decide quién puede leer la capa.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.Capas
  alias Mapo.Limite
  alias Mapo.MapoCore
  alias Mapo.Teams

  # Cruzar 50 mil renglones cuesta CPU, y los minutos, llamadas a OSRM.
  @max_cruces 60
  @ventana_cruces 3600
  @filas_a_la_vista 20

  @agregaciones [
    {"No incluir", ""},
    {"Suma", "suma"},
    {"Promedio", "promedio"},
    {"Mediana", "mediana"}
  ]

  @impl true
  def render(assigns) do
    assigns =
      assign(assigns,
        agregaciones: @agregaciones,
        indicadores: MapoCore.indicadores_censo(),
        a_la_vista: @filas_a_la_vista
      )

    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" amplio?={true}>
      <div class="equipo">
        <section class="doc pegado" aria-labelledby="t-cruce">
          <header class="doc-cab">
            <h1 id="t-cruce">Cruzar {@capa.nombre}</h1>
            <span class="doc-tipo">{cifra(@capa.num_filas)} renglones</span>
          </header>

          <div class="doc-seccion">
            <p class="secundario">
              Cada cifra queda en su propia columna: Mapo no las pondera ni las junta en un puntaje.
            </p>

            <.form for={@form} id="cruce_form" phx-change="cambiar" phx-submit="cruzar">
              <.input
                :if={length(@niveles) > 1}
                field={@form[:nivel]}
                type="select"
                label="Agregar por"
                options={@niveles}
              />
              <.input :if={length(@niveles) == 1} field={@form[:nivel]} type="hidden" />

              <fieldset :if={@capa.numericas != []} class="cruce-grupo">
                <legend>Columnas de tu capa</legend>
                <p class="secundario">
                  Sumar sirve para ventas; para precios o edades, un promedio o una mediana. Los renglones por zona siempre se cuentan.
                </p>
                <.input
                  :for={{columna, i} <- Enum.with_index(@capa.numericas)}
                  type="select"
                  id={"agregacion_#{i}"}
                  name={"cruce[agregacion][#{i}]"}
                  label={columna}
                  value={@agregacion[to_string(i)] || ""}
                  options={@agregaciones}
                />
              </fieldset>

              <fieldset class="cruce-grupo">
                <legend>Censo 2020</legend>
                <input type="hidden" name="cruce[censo][]" value="" />
                <div class="cruce-censo">
                  <label :for={{clave, etiqueta} <- @indicadores}>
                    <input
                      type="checkbox"
                      name="cruce[censo][]"
                      value={clave}
                      checked={clave in @censo}
                    />
                    {etiqueta}
                  </label>
                </div>
              </fieldset>

              <.input
                field={@form[:denue]}
                type="select"
                label="Negocios de DENUE"
                options={@rubros}
              />
              <.input
                :if={minutos?(@form)}
                field={@form[:minutos]}
                type="checkbox"
                label="Minutos en auto al negocio más cercano del rubro"
              />

              <div class="doc-botones">
                <.button variant="primary" phx-disable-with="Cruzando...">Cruzar</.button>
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
              {cifra(@resultado["zonas_con_renglones"])} de {cifra(length(@resultado["filas"]))} zonas con renglones
            </span>
          </header>

          <div class="doc-seccion">
            <p :for={aviso <- @resultado["avisos"]} class="nota">{aviso}</p>

            <div class="tabla-muestra">
              <table>
                <caption class="sr-only">Primeras zonas del cruce</caption>
                <thead>
                  <tr>
                    <th scope="col">Clave</th>
                    <th :for={c <- @resultado["columnas"]} scope="col">{c}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr :for={fila <- Enum.take(@resultado["filas"], @a_la_vista)}>
                    <td>{fila["clave"]}</td>
                    <td :for={c <- @resultado["columnas"]}>{celda(fila["datos"][c])}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p :if={length(@resultado["filas"]) > @a_la_vista} class="secundario">
              Se ven las primeras {@a_la_vista} zonas. Guarda el cruce para verlas todas en el mapa o bajarlas en CSV.
            </p>

            <details class="cruce-metodo" open>
              <summary>Cómo se calculó</summary>
              <ul>
                <li :for={linea <- @resultado["metodo"]}>{linea}</li>
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

  @impl true
  def mount(%{"id" => id, "capa_id" => capa_id}, _session, socket) do
    scope = socket.assigns.current_scope
    team = Teams.get_team!(scope, id)

    case Capas.get_capa(scope, capa_id) do
      %{team_id: team_id} = capa when team_id == team.id ->
        if Capas.cruzable?(capa), do: montar(socket, team, capa), else: regresar(socket, team)

      _ ->
        regresar(socket, team)
    end
  end

  defp montar(socket, team, capa) do
    [{_, nivel} | _] = niveles = niveles(capa)

    {:ok,
     assign(socket,
       team: team,
       capa: capa,
       niveles: niveles,
       rubros: rubros(),
       form: to_form(%{"nivel" => nivel, "denue" => ""}, as: "cruce"),
       guardado: to_form(%{"nombre" => nombre_sugerido(capa)}, as: "guardado"),
       agregacion: %{},
       censo: ["pobtot"],
       resultado: nil
     )}
  end

  defp regresar(socket, team) do
    {:ok,
     socket
     |> put_flash(:error, "Esa capa no se puede cruzar.")
     |> push_navigate(to: ~p"/teams/#{team}/datos")}
  end

  defp niveles(%{tipo: "municipio"}), do: [{"Municipio", "municipio"}]
  defp niveles(_), do: [{"AGEB urbano", "ageb"}, {"Municipio", "municipio"}]

  defp nombre_sugerido(capa), do: String.slice("Cruce de #{capa.nombre}", 0, 120)

  defp rubros do
    fijos = [{"No incluir", ""}, {"Todos los negocios", "todos"}]

    case MapoCore.buscador_catalogo() do
      {:ok, %{"sectores" => sectores}} ->
        fijos ++
          Enum.map(sectores, fn s ->
            {s["nombre"], Enum.map(s["rubros"], &{&1["nombre"], &1["rubro"]})}
          end)

      _ ->
        fijos
    end
  end

  @impl true
  def handle_event("cambiar", %{"cruce" => params}, socket) do
    # Lo que está a la vista dejaría de ser lo que se ve en el formulario.
    {:noreply, socket |> recordar(params) |> assign(resultado: nil)}
  end

  def handle_event("cruzar", %{"cruce" => params}, socket) do
    socket = recordar(socket, params)
    scope = socket.assigns.current_scope

    if Limite.permitir?({:cruce, scope.user.id}, @max_cruces, @ventana_cruces) do
      {:noreply, cruzar(socket, params)}
    else
      {:noreply, put_flash(socket, :error, "Demasiados cruces en una hora. Espera un rato.")}
    end
  end

  def handle_event("guardar", %{"guardado" => %{"nombre" => nombre}}, socket) do
    %{capa: capa, team: team, resultado: resultado, current_scope: scope} = socket.assigns

    case resultado && Capas.crear_cruce(scope, capa, String.trim(nombre), resultado) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Cruce guardado como capa.")
         |> push_navigate(to: ~p"/teams/#{team}/datos")}

      nil ->
        {:noreply, socket}

      {:error, motivo} ->
        {:noreply, put_flash(socket, :error, mensaje(motivo))}
    end
  end

  defp recordar(socket, params) do
    assign(socket,
      form: to_form(params, as: "cruce"),
      agregacion: params["agregacion"] || %{},
      censo: Enum.reject(params["censo"] || [], &(&1 == ""))
    )
  end

  defp cruzar(socket, params) do
    %{capa: capa, censo: censo} = socket.assigns
    agregaciones = agregaciones(capa, params["agregacion"] || %{})

    solicitud = %{
      tipo: capa.tipo,
      nivel: params["nivel"],
      filas: Capas.filas_para_cruce(capa, Map.keys(agregaciones)),
      agregaciones: agregaciones,
      censo: censo,
      denue: if(params["denue"] != "", do: params["denue"]),
      minutos: minutos?(socket.assigns.form) and params["minutos"] == "true"
    }

    case MapoCore.cruce_calcular(solicitud) do
      {:ok, resultado} -> socket |> clear_flash() |> assign(resultado: resultado)
      {:error, motivo} -> put_flash(socket, :error, mensaje(motivo))
    end
  end

  # El formulario las nombra por posición: un nombre de columna viene del
  # archivo y puede traer corchetes.
  defp agregaciones(capa, elegidas) do
    capa.numericas
    |> Enum.with_index()
    |> Enum.flat_map(fn {columna, i} ->
      case elegidas[to_string(i)] do
        agregacion when agregacion in ~w(suma promedio mediana) -> [{columna, agregacion}]
        _ -> []
      end
    end)
    |> Map.new()
  end

  defp minutos?(form),
    do: form[:nivel].value == "ageb" and form[:denue].value not in ["", "todos", nil]

  defp celda(nil), do: "sin dato"
  defp celda(valor), do: cifra(valor)

  defp mensaje(:cuota), do: "El cruce ya no cabe en los 500 MB del equipo. Borra alguna capa."

  defp mensaje({:status, 422, %{"detail" => detalle}}) when is_binary(detalle), do: detalle

  defp mensaje(%Ecto.Changeset{}), do: "Revisa el nombre de la capa (máximo 120 caracteres)."
  defp mensaje(_), do: "mapo_core no está disponible ahorita mismo."
end
