defmodule Mapo.Repo.Migrations.AddLapizYDetalle do
  use Ecto.Migration

  # El lápiz (color de sus marcas) es de la persona dentro de un equipo. Se
  # guarda, en vez de salir de su lugar en la lista, para que no cambie cuando
  # alguien más entra o sale. Los equipos de antes se numeran por antigüedad.
  def change do
    alter table(:team_memberships) do
      add :lapiz, :integer, null: false, default: 1
    end

    execute(
      """
      UPDATE team_memberships m SET lapiz = (n.lugar - 1) % 6 + 1
      FROM (SELECT id, row_number() OVER (PARTITION BY team_id ORDER BY id) AS lugar
            FROM team_memberships) n
      WHERE n.id = m.id
      """,
      ""
    )

    # `texto` es la etiqueta corta del plano; `detalle`, la nota larga de la ficha.
    alter table(:anotaciones) do
      add :detalle, :text, null: false, default: ""
    end
  end
end
