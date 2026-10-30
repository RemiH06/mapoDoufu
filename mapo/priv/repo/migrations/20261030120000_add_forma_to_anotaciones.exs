defmodule Mapo.Repo.Migrations.AddFormaToAnotaciones do
  use Ecto.Migration

  # Las marcas dejan de ser solo puntos. `geom` ya es geometría genérica, así
  # que una forma nueva (un trazo libre sería un LineString) no pide otra
  # columna: `forma` dice cómo dibujarla y `radio_m` solo lo usa el círculo,
  # que se guarda como su centro para conservar el radio exacto.
  def change do
    alter table(:anotaciones) do
      add :forma, :string, null: false, default: "punto"
      add :radio_m, :float
    end
  end
end
