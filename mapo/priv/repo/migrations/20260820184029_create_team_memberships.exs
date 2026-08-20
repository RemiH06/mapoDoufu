defmodule Mapo.Repo.Migrations.CreateTeamMemberships do
  use Ecto.Migration

  def change do
    create table(:team_memberships) do
      add :role, :string, null: false
      add :team_id, references(:teams, on_delete: :delete_all), null: false
      add :user_id, references(:users, on_delete: :delete_all), null: false

      timestamps(type: :utc_datetime)
    end

    create index(:team_memberships, [:user_id])
    create unique_index(:team_memberships, [:team_id, :user_id])
  end
end
