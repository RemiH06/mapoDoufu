defmodule MapoWeb.DatosLive.Distancia do
  @moduledoc """
  Distancia de cada renglón de una capa al más cercano de otra del mismo
  equipo. Se revisa aquí y, si sirve, se guarda como capa. El cálculo vive en
  `Mapo.Capas.Distancias`; ver docs/producto/datos-propios.md.
  """

  use MapoWeb, :live_view

  import MapoWeb.Cifras

  alias Mapo.Capas
  alias Mapo.Capas.Distancias
  alias Mapo.Limite
  alias Mapo.Teams

  # Medir 50 mil renglones contra 10 mil polígonos cuesta CPU de la base.
  @max_calculos 60
  @ventana 3600

  @impl true
  def render(assigns) do
    ~H"""
    <Layouts.app flash={@flash} current_scope={@current_scope} seccion="equipos" amplio?={true}>
      <div class="equipo">
        <section class="doc pegado" aria-labelledby="t-distancia">
          <header class="doc-cab">
            <h1 id="t-distancia">Distancia desde {@capa.nombre}</h1>
             <span class="doc-tipo">{cifra(@capa.num_filas)} renglones</span>
          </header>
          
          <div class="doc-seccion">
            <p class="secundario">
              De cada renglón al más cercano de otra capa, en metros. Cercanía no dice causa: escribe "a 240 m de", no "expuesto a".
            </p>
            
            <p :if={@destinos == []} class="nota">
              El equipo no tiene otra capa de puntos o geometrías contra la cual medir.
            </p>
            
            <.form
              :if={@destinos != []}
              for={@form}
              id="distancia_form"
              phx-change="cambiar"
              phx-submit="medir"
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
                  ejemplo="educación"
                />
              </fieldset>
              
              <fieldset class="cruce-grupo">
                <legend>Hasta</legend>
                 <.input field={@form[:destino]} type="select" label="Capa" options={@destinos} />
                <.input
                  field={@form[:etiqueta_destino]}
                  type="select"
                  label="Columna que nombra al más cercano"
                  options={@destino.columnas}
                />
                <.condiciones
                  form={@form}
                  lado="destino"
                  columnas={@destino.columnas}
                  ejemplo="AGRICULTURA"
                />
              </fieldset>
              
              <.input
                field={@form[:radio]}
                type="number"
                min="1"
                max="100000"
                label="Contar además los que estén a esta distancia o menos (metros, opcional)"
              />
              <div class="doc-botones">
                <.button variant="primary" phx-disable-with="Midiendo...">Medir</.button>
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
              <%= if @resultado.a_menos do %>
                {cifra(@resultado.a_menos)} de {cifra(@resultado.total)} a {@opciones.radio} m o menos
              <% else %>
                {cifra(@resultado.total)} renglones medidos
              <% end %>
            </span>
          </header>
          
          <div class="doc-seccion">
            <div class="tabla-muestra">
              <table>
                <caption class="sr-only">Los renglones más cercanos</caption>
                
                <thead>
                  <tr>
                    <th scope="col">{@opciones.etiqueta_origen}</th>
                    
                    <th scope="col">Metros</th>
                    
                    <th :if={@opciones.etiqueta_destino} scope="col">
                      Más cercano ({@opciones.etiqueta_destino})
                    </th>
                    
                    <th :if={@opciones.radio} scope="col">A {@opciones.radio} m o menos</th>
                  </tr>
                </thead>
                
                <tbody>
                  <tr :for={fila <- @resultado.filas}>
                    <td>{fila.nombre || "sin dato"}</td>
                    
                    <td>{celda(fila.metros)}</td>
                    
                    <td :if={@opciones.etiqueta_destino}>{fila.cercano || "sin dato"}</td>
                    
                    <td :if={@opciones.radio}>{cifra(fila.cuantos)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            
            <p :if={@resultado.total > length(@resultado.filas)} class="secundario">
              Se ven los {length(@resultado.filas)} más cercanos. Guarda la capa para ver todos en el mapa o bajarlos en CSV.
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

  attr :form, :any, required: true
  attr :lado, :string, required: true
  attr :columnas, :list, required: true
  attr :ejemplo, :string, required: true

  # Dos condiciones que se cumplen las dos; una barra separa alternativas
  # dentro de una ("039|120").
  defp condiciones(assigns) do
    ~H"""
    <p class="secundario">
      Solo los renglones que cumplan, sin importar mayúsculas ni acentos. Para aceptar varios textos, sepáralos con una barra: 039|120.
    </p>

    <div :for={i <- 0..1} class="distancia-condicion">
      <.input
        type="select"
        id={"#{@lado}_columna_#{i}"}
        name={"distancia[filtro_#{@lado}][#{i}][columna]"}
        label={if i == 0, do: "Donde la columna", else: "y donde la columna"}
        value={condicion(@form, @lado, i, "columna")}
        options={[{"(cualquiera)", ""} | @columnas]}
      />
      <.input
        type="text"
        id={"#{@lado}_texto_#{i}"}
        name={"distancia[filtro_#{@lado}][#{i}][texto]"}
        label="contiene"
        value={condicion(@form, @lado, i, "texto")}
        placeholder={if i == 0, do: @ejemplo}
      />
    </div>
    """
  end

  defp condicion(form, lado, i, campo),
    do: get_in(form.params, ["filtro_#{lado}", to_string(i), campo]) || ""

  @impl true
  def mount(%{"id" => id, "capa_id" => capa_id}, _session, socket) do
    scope = socket.assigns.current_scope
    team = Teams.get_team!(scope, id)

    case Capas.get_capa(scope, capa_id) do
      %{team_id: team_id} = capa when team_id == team.id ->
        if Distancias.medible?(capa), do: montar(socket, team, capa), else: regresar(socket, team)

      _ ->
        regresar(socket, team)
    end
  end

  defp montar(socket, team, capa) do
    candidatas =
      socket.assigns.current_scope
      |> Capas.list_capas(team.id)
      |> Enum.filter(&(Distancias.medible?(&1) and &1.id != capa.id))

    destino = List.first(candidatas)

    params = %{
      "etiqueta_origen" => etiqueta(capa),
      "destino" => destino && to_string(destino.id),
      "etiqueta_destino" => destino && etiqueta(destino),
      "radio" => ""
    }

    {:ok,
     assign(socket,
       team: team,
       capa: capa,
       candidatas: candidatas,
       destinos: Enum.map(candidatas, &{&1.nombre, to_string(&1.id)}),
       destino: destino,
       form: to_form(params, as: "distancia"),
       guardado: to_form(%{"nombre" => ""}, as: "guardado"),
       opciones: nil,
       resultado: nil
     )}
  end

  defp regresar(socket, team) do
    {:ok,
     socket
     |> put_flash(:error, "Desde esa capa no se puede medir.")
     |> push_navigate(to: ~p"/teams/#{team}/datos")}
  end

  # Una columna que parezca nombre; si no, la primera.
  defp etiqueta(capa) do
    Enum.find(capa.columnas, List.first(capa.columnas), fn c ->
      String.downcase(c) =~ ~r/nombre|^nom_|^name|descrip|titulo/
    end)
  end

  @impl true
  def handle_event("cambiar", %{"distancia" => params}, socket) do
    destino = Enum.find(socket.assigns.candidatas, &(to_string(&1.id) == params["destino"]))

    # Al cambiar de destino, sus columnas son otras.
    params =
      if destino && destino != socket.assigns.destino,
        do:
          params
          |> Map.put("etiqueta_destino", etiqueta(destino))
          |> Map.delete("filtro_destino"),
        else: params

    {:noreply,
     assign(socket,
       form: to_form(params, as: "distancia"),
       destino: destino || socket.assigns.destino,
       resultado: nil
     )}
  end

  def handle_event("medir", %{"distancia" => params}, socket) do
    scope = socket.assigns.current_scope

    if Limite.permitir?({:distancia, scope.user.id}, @max_calculos, @ventana) do
      {:noreply, medir(assign(socket, form: to_form(params, as: "distancia")), params)}
    else
      {:noreply, put_flash(socket, :error, "Demasiadas mediciones en una hora. Espera un rato.")}
    end
  end

  def handle_event("guardar", %{"guardado" => %{"nombre" => nombre}}, socket) do
    %{capa: capa, team: team, resultado: resultado, opciones: opciones, current_scope: scope} =
      socket.assigns

    case resultado && Distancias.guardar(scope, capa, opciones, String.trim(nombre), resultado) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Distancias guardadas como capa.")
         |> push_navigate(to: ~p"/teams/#{team}/datos")}

      nil ->
        {:noreply, socket}

      {:error, motivo} ->
        {:noreply, put_flash(socket, :error, mensaje(motivo))}
    end
  end

  defp medir(socket, params) do
    %{capa: capa, destino: destino} = socket.assigns

    with {:ok, radio} <- radio(params["radio"]) do
      opciones = %{
        destino: destino,
        etiqueta_origen: columna(params["etiqueta_origen"], capa),
        etiqueta_destino: columna(params["etiqueta_destino"], destino),
        filtro_origen: filtros(params["filtro_origen"], capa),
        filtro_destino: filtros(params["filtro_destino"], destino),
        radio: radio
      }

      case Distancias.calcular(capa, opciones) do
        {:ok, resultado} ->
          socket
          |> clear_flash()
          |> assign(
            opciones: opciones,
            resultado: resultado,
            guardado: to_form(%{"nombre" => nombre_sugerido(capa, destino)}, as: "guardado")
          )

        {:error, mensaje} ->
          put_flash(socket, :error, mensaje)
      end
    else
      {:error, mensaje} -> put_flash(socket, :error, mensaje)
    end
  end

  # Lo que llega del navegador solo vale si es una columna de la capa.
  defp columna(nombre, capa), do: if(nombre in capa.columnas, do: nombre)

  defp filtros(condiciones, capa) when is_map(condiciones) do
    for i <- ["0", "1"],
        %{"columna" => col, "texto" => texto} <- [condiciones[i]],
        columna(col, capa) && String.trim(texto) != "",
        do: {col, String.trim(texto)}
  end

  defp filtros(_, _), do: []

  defp radio(texto) do
    case Integer.parse(String.trim(texto || "")) do
      :error -> {:ok, nil}
      {n, ""} when n >= 1 and n <= 100_000 -> {:ok, n}
      _ -> {:error, "El radio va de 1 a 100,000 metros, en número entero."}
    end
  end

  defp nombre_sugerido(capa, destino),
    do: String.slice("#{capa.nombre} a #{destino.nombre}", 0, 120)

  defp celda(nil), do: "sin dato"
  defp celda(valor), do: cifra(valor)

  defp mensaje(:cuota), do: "El resultado ya no cabe en los 500 MB del equipo. Borra alguna capa."
  defp mensaje(%Ecto.Changeset{}), do: "Revisa el nombre de la capa (máximo 120 caracteres)."
  defp mensaje(_), do: "No se pudo guardar."
end
