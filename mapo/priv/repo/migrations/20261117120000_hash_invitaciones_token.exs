defmodule Mapo.Repo.Migrations.HashInvitacionesToken do
  use Ecto.Migration

  # La columna `token` pasa a guardar el SHA-256 en hexadecimal, igual que
  # `Mapo.Teams.hash_token/1`. Los enlaces ya enviados siguen sirviendo.
  def up do
    execute "UPDATE invitaciones SET token = encode(sha256(convert_to(token, 'UTF8')), 'hex')"
  end

  # El hash no se revierte: al bajar, los enlaces pendientes dejan de servir
  # y basta con reenviarlos. No truena para no estorbar un regreso de versión.
  def down, do: :ok
end
