defmodule MapoWeb.ZonaSelector do
  @moduledoc """
  Selector de zona común (sesión 29b, docs/producto/zona.md): el mismo en todas
  las vistas. Se escribe un estado, municipio, metrópoli, colonia o código
  postal y se elige de las sugerencias (Enter toma la primera); un municipio
  elegido puede sumar otros, y "Dibujar en el plano" pasa el plano a modo
  dibujo (`assets/js/zona_plano.js`).

  La zona vive en la vista, no aquí: al elegir, el componente la resuelve con
  mapo_core y le manda `{:zona_elegida, zona}` a la vista, que la guarda y se
  la regresa en `zona`. `zona` es el mapa de `/zona/resolver` (clave, nombre,
  detalle, geojson, municipios...) o `nil`.
  """

  use MapoWeb, :live_component

  alias Mapo.Accounts
  alias Mapo.MapoCore

  @max_vertices 200

  @tipos %{
    "estado" => "Estado",
    "municipios" => "Municipios",
    "municipio" => "Municipio",
    "metropoli" => "Metrópoli",
    "cp" => "Código postal",
    "colonia" => "Colonia",
    "poligono" => "Dibujo",
    "circulo" => "Círculo"
  }

  @impl true
  def mount(socket) do
    {:ok,
     assign(socket,
       q: "",
       resultados: [],
       aviso: nil,
       error: nil,
       editando: false,
       sumando: false,
       dibujando: false,
       resolviendo: false
     )}
  end

  @impl true
  def update(assigns, socket) do
    {:ok,
     socket
     |> assign(assigns)
     |> assign_new(:etiqueta, fn -> "Zona" end)
     |> assign_new(:dibujar?, fn -> true end)
     |> assign_new(:scope, fn -> nil end)
     |> assign_new(:guardada, fn ->
       case assigns[:scope] do
         %{user: %{zona_operacion: clave}} -> clave
         _ -> nil
       end
     end)}
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div id={@id} class="zona-selector">
      <div :if={@zona && !@editando} class="zona-elegida">
        <p class="zona-tipo">{@etiqueta} · {tipo(@zona)}</p>
        <p class="zona-nombre">{@zona["nombre"]}</p>
        <p :if={@zona["detalle"] not in [nil, ""]} class="secundario">{@zona["detalle"]}</p>
        <p :if={@zona["aviso"]} class="aviso">{@zona["aviso"]}</p>

        <ul :if={varios_municipios?(@zona)} class="zona-chips" aria-label="Municipios de la zona">
          <li :for={m <- @zona["municipios"]}>
            {m["nombre"]}
            <button
              type="button"
              class="chico"
              phx-click="quitar_municipio"
              phx-value-cvegeo={m["cvegeo"]}
              phx-target={@myself}
              aria-label={"Quitar #{m["nombre"]}"}
            >
              ×
            </button>
          </li>
        </ul>

        <div class="botones">
          <button
            type="button"
            id={"#{@id}-cambiar"}
            class="chico"
            phx-click="editar"
            phx-target={@myself}
          >
            Cambiar
          </button>
          <button
            :if={@zona["tipo"] == "municipios"}
            type="button"
            id={"#{@id}-sumar"}
            class="chico"
            phx-click="sumar"
            phx-target={@myself}
          >
            Sumar un municipio
          </button>
          <button
            :if={@scope && @guardada != @zona["clave"]}
            type="button"
            id={"#{@id}-guardar"}
            class="chico"
            phx-click="guardar"
            phx-target={@myself}
          >
            Que sea mi zona
          </button>
          <button
            :if={@scope && @guardada == @zona["clave"]}
            type="button"
            id={"#{@id}-olvidar"}
            class="chico"
            phx-click="olvidar"
            phx-target={@myself}
            title="Las vistas abren con ella cuando el enlace no trae zona"
          >
            Es tu zona · Dejar de usarla
          </button>
        </div>
      </div>

      <.form
        :if={!@zona || @editando}
        for={to_form(%{"q" => @q}, as: :zona_q)}
        id={"#{@id}-form"}
        phx-change="buscar"
        phx-submit="elegir_primera"
        phx-target={@myself}
      >
        <.input
          field={to_form(%{"q" => @q}, as: :zona_q)[:q]}
          id={"#{@id}-q"}
          type="search"
          label={if @sumando, do: "Sumar un municipio", else: @etiqueta}
          placeholder="Estado, municipio, metrópoli, colonia o CP"
          autocomplete="off"
          phx-debounce="250"
          aria-describedby={"#{@id}-estado"}
        />
        <p id={"#{@id}-estado"} class="sr-only" aria-live="polite">{estado_lista(@resultados, @q)}</p>

        <ul :if={@resultados != []} id={"#{@id}-lista"} class="zona-sugerencias">
          <li :for={r <- @resultados}>
            <button
              type="button"
              id={"#{@id}-r-#{r["clave"] |> String.replace(~r/[^\w]/, "_")}"}
              phx-click="elegir"
              phx-value-clave={r["clave"]}
              phx-target={@myself}
            >
              <span class="zona-nombre">{r["nombre"]}</span>
              <span class="secundario">{r["detalle"]}</span>
            </button>
          </li>
        </ul>
        <p :if={@aviso} class="secundario">{@aviso}</p>
        <p
          :if={@resultados == [] and is_nil(@aviso) and String.length(String.trim(@q)) >= 2}
          class="secundario"
        >
          Nada con «{@q}» entre lo cargado en Mapo.
        </p>

        <div class="botones">
          <button
            :if={@dibujar? and !@sumando}
            type="button"
            id={"#{@id}-dibujar"}
            class="chico"
            phx-click={if @dibujando, do: "cancelar_dibujo", else: "dibujar"}
            phx-target={@myself}
            aria-pressed={to_string(@dibujando)}
          >
            {if @dibujando, do: "Dejar de dibujar", else: "Dibujar en el plano"}
          </button>
          <button
            :if={@zona}
            type="button"
            id={"#{@id}-cancelar"}
            class="chico"
            phx-click="cancelar"
            phx-target={@myself}
          >
            Cancelar
          </button>
        </div>
      </.form>

      <p :if={@dibujando} class="secundario" role="status">
        Toca el plano para poner los vértices; toca el primero o haz doble clic para cerrar.
      </p>
      <p :if={@resolviendo} class="secundario" role="status">Buscando la zona...</p>
      <p :if={@error} class="aviso" role="alert">{@error}</p>
    </div>
    """
  end

  @impl true
  def handle_event("buscar", %{"zona_q" => %{"q" => q}}, socket) when is_binary(q) do
    q = String.slice(q, 0, 80)

    if String.length(String.trim(q)) < 2 do
      {:noreply, assign(socket, q: q, resultados: [], aviso: nil)}
    else
      case MapoCore.zona_buscar(q) do
        {:ok, %{"resultados" => resultados} = r} ->
          resultados =
            if socket.assigns.sumando, do: solo_municipios(resultados), else: resultados

          {:noreply, assign(socket, q: q, resultados: resultados, aviso: r["aviso"], error: nil)}

        {:error, _} ->
          {:noreply,
           assign(socket, q: q, resultados: [], error: "No se pudo buscar. Inténtalo de nuevo.")}
      end
    end
  end

  def handle_event("elegir_primera", _params, %{assigns: %{resultados: [r | _]}} = socket),
    do: {:noreply, elegir(socket, r["clave"])}

  def handle_event("elegir_primera", _params, socket), do: {:noreply, socket}

  def handle_event("elegir", %{"clave" => clave}, socket) when is_binary(clave) do
    if Enum.any?(socket.assigns.resultados, &(&1["clave"] == clave)),
      do: {:noreply, elegir(socket, clave)},
      else: {:noreply, socket}
  end

  def handle_event("quitar_municipio", %{"cvegeo" => cvegeo}, socket) do
    restantes = for m <- socket.assigns.zona["municipios"], m["cvegeo"] != cvegeo, do: m["cvegeo"]

    if restantes == [],
      do: {:noreply, socket},
      else: {:noreply, elegir(socket, "mun:" <> Enum.join(restantes, ","))}
  end

  def handle_event(
        "guardar",
        _params,
        %{assigns: %{scope: scope, zona: %{"clave" => clave}}} = socket
      )
      when not is_nil(scope),
      do: {:noreply, guardar(socket, clave)}

  def handle_event("olvidar", _params, %{assigns: %{scope: scope}} = socket)
      when not is_nil(scope),
      do: {:noreply, guardar(socket, nil)}

  def handle_event(evento, _params, socket) when evento in ~w(guardar olvidar),
    do: {:noreply, socket}

  def handle_event("editar", _params, socket),
    do: {:noreply, assign(socket, editando: true, sumando: false, error: nil)}

  def handle_event("sumar", _params, socket),
    do:
      {:noreply, assign(socket, editando: true, sumando: true, q: "", resultados: [], error: nil)}

  def handle_event("cancelar", _params, socket),
    do:
      {:noreply,
       socket
       |> dejar_de_dibujar()
       |> assign(editando: false, sumando: false, q: "", resultados: [])}

  def handle_event("dibujar", _params, socket) do
    {:noreply,
     socket
     |> assign(dibujando: true, error: nil)
     |> push_event("dibujar_zona", %{destino: "##{socket.assigns.id}"})}
  end

  def handle_event("cancelar_dibujo", _params, socket),
    do: {:noreply, dejar_de_dibujar(socket)}

  # Lo manda el plano al cerrar el polígono (zona_plano.js).
  def handle_event("poligono", %{"vertices" => vertices}, socket) do
    socket = assign(socket, dibujando: false)

    case clave_de_poligono(vertices) do
      {:ok, clave} ->
        {:noreply, elegir(socket, clave)}

      :error ->
        {:noreply, assign(socket, error: "Ese dibujo no sirve: dibuja de 3 a 200 vértices.")}
    end
  end

  def handle_event("poligono", _params, socket), do: {:noreply, assign(socket, dibujando: false)}

  defp dejar_de_dibujar(%{assigns: %{dibujando: true}} = socket),
    do: socket |> assign(dibujando: false) |> push_event("cancelar_dibujo_zona", %{})

  defp dejar_de_dibujar(socket), do: socket

  defp elegir(socket, clave) do
    clave = if socket.assigns.sumando, do: sumar(socket.assigns.zona, clave), else: clave

    case resolver(clave) do
      {:ok, zona} ->
        send(self(), {:zona_elegida, zona})

        socket
        |> assign(editando: false, sumando: false, q: "", resultados: [], aviso: nil, error: nil)
        |> push_event("zona_elegida", %{geojson: zona["geojson"]})

      {:error, mensaje} ->
        assign(socket, error: mensaje)
    end
  end

  defp sumar(%{"tipo" => "municipios", "municipios" => ms}, "mun:" <> nuevos),
    do: "mun:" <> Enum.join(Enum.map(ms, & &1["cvegeo"]) ++ [nuevos], ",")

  defp sumar(_zona, clave), do: clave

  @doc """
  Resuelve una clave de zona con mapo_core: `{:ok, zona}` o `{:error, mensaje}`
  ya para mostrar. La usan las vistas al abrir un enlace con `zona=`.
  """
  def resolver(clave) when is_binary(clave) and byte_size(clave) <= 6_000 do
    case MapoCore.zona_resolver(clave) do
      {:ok, zona} ->
        {:ok, zona}

      {:error, {:status, 422, %{"detail" => d}}} when is_binary(d) ->
        {:error, "Esa zona no sirve: #{d}."}

      {:error, {:status, 404, _}} ->
        {:error, "No hay nada cargado en Mapo con esa zona."}

      {:error, _} ->
        {:error, "No se pudo consultar la zona. Inténtalo de nuevo en un momento."}
    end
  end

  def resolver(_clave), do: {:error, "Esa zona no sirve."}

  defp guardar(socket, clave) do
    case Accounts.update_user_zona(socket.assigns.scope, clave) do
      {:ok, _user} -> assign(socket, guardada: clave, error: nil)
      {:error, _changeset} -> assign(socket, error: "No se pudo guardar tu zona.")
    end
  end

  @doc """
  La zona en la que opera quien abre la vista, ya resuelta, o `nil` si no
  guardó una (o si ya no se puede resolver). Las vistas la usan cuando el
  enlace no trae zona.
  """
  def zona_inicial(%{user: %{zona_operacion: clave}}) when is_binary(clave) do
    case resolver(clave) do
      {:ok, zona} -> zona
      {:error, _} -> nil
    end
  end

  def zona_inicial(_scope), do: nil

  @doc "Pone la zona guardada en una vista que todavía no tiene zona, y la manda al plano."
  def con_zona_inicial(%{assigns: %{zona: nil, current_scope: scope}} = socket) do
    case zona_inicial(scope) do
      nil ->
        socket

      zona ->
        socket
        |> Phoenix.Component.assign(zona: zona)
        |> push_event("zona_elegida", %{geojson: zona["geojson"]})
    end
  end

  def con_zona_inicial(socket), do: socket

  @doc """
  Query string de un enlace permanente con la clave de zona legible
  (`zona=mun:14039,14120`, no `mun%3A14039%2C14120`): los dos puntos, la coma y
  el punto y coma son válidos en una query (RFC 3986) y Plug solo parte en `&`.
  """
  def query(params) do
    Enum.map_join(params, "&", fn {k, v} ->
      "#{k}=" <> URI.encode(to_string(v), &(URI.char_unreserved?(&1) or &1 in ~c":,;"))
    end)
  end

  @doc "Clave `pol:` de una lista de vértices `[lon, lat]` que manda el plano, o `:error`."
  def clave_de_poligono(vertices)
      when is_list(vertices) and length(vertices) in 3..@max_vertices do
    pares =
      for v <- vertices do
        case v do
          [lon, lat] when is_number(lon) and is_number(lat) -> "#{numero(lon)},#{numero(lat)}"
          _ -> nil
        end
      end

    if Enum.any?(pares, &is_nil/1), do: :error, else: {:ok, "pol:" <> Enum.join(pares, ";")}
  end

  def clave_de_poligono(_vertices), do: :error

  defp numero(x), do: x |> Kernel.*(1.0) |> Float.round(5) |> Float.to_string()

  @doc "Etiqueta del tipo de una zona resuelta."
  def tipo(%{"tipo" => "municipios", "municipios" => [_]}), do: @tipos["municipio"]
  def tipo(%{"tipo" => t}), do: Map.get(@tipos, t, "Zona")

  defp varios_municipios?(%{"tipo" => "municipios", "municipios" => [_, _ | _]}), do: true
  defp varios_municipios?(_zona), do: false

  defp solo_municipios(resultados), do: Enum.filter(resultados, &(&1["tipo"] == "municipio"))

  defp estado_lista([], _q), do: ""
  defp estado_lista([_], _q), do: "1 sugerencia"
  defp estado_lista(rs, _q), do: "#{length(rs)} sugerencias"
end
