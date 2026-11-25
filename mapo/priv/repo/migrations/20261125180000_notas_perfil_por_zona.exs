defmodule Mapo.Repo.Migrations.NotasPerfilPorZona do
  use Ecto.Migration

  # Las notas pasan de un municipio a cualquier zona de la zona común (29h).
  # `cve_ent` y `cve_mun` se quedan, ya sin uso, para poder regresar a la
  # versión anterior; por eso dejan de ser obligatorias y no se borran. Sin
  # índice nuevo: un dibujo mide hasta 6,000 letras y no cabe en un btree; el
  # de `team_id` (primera columna del que ya hay) basta.
  def up do
    alter table(:notas_perfil) do
      add :zona, :text
      modify :cve_ent, :string, size: 2, null: true
      modify :cve_mun, :string, size: 3, null: true
    end

    execute "UPDATE notas_perfil SET zona = 'mun:' || cve_ent || cve_mun"
  end

  def down do
    execute "DELETE FROM notas_perfil WHERE cve_ent IS NULL OR cve_mun IS NULL"

    alter table(:notas_perfil) do
      remove :zona
      modify :cve_ent, :string, size: 2, null: false
      modify :cve_mun, :string, size: 3, null: false
    end
  end
end
