defmodule Mapo.TeamsTest do
  use Mapo.DataCase

  alias Mapo.Teams

  describe "teams" do
    alias Mapo.Teams.Team

    import Mapo.AccountsFixtures, only: [user_scope_fixture: 0]
    import Mapo.TeamsFixtures

    @invalid_attrs %{name: nil}

    test "list_teams/1 returns only teams the scoped user belongs to" do
      scope = user_scope_fixture()
      other_scope = user_scope_fixture()
      team = team_fixture(scope)
      other_team = team_fixture(other_scope)
      assert Teams.list_teams(scope) == [team]
      assert Teams.list_teams(other_scope) == [other_team]
    end

    test "get_team!/2 returns the team with given id" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      other_scope = user_scope_fixture()
      assert Teams.get_team!(scope, team.id) == team
      assert_raise Ecto.NoResultsError, fn -> Teams.get_team!(other_scope, team.id) end
    end

    test "create_team/2 with valid data creates a team and makes the scoped user its owner" do
      valid_attrs = %{name: "some name"}
      scope = user_scope_fixture()

      assert {:ok, %Team{} = team} = Teams.create_team(scope, valid_attrs)
      assert team.name == "some name"
      assert Teams.role_in_team(scope, team.id) == :owner
    end

    test "create_team/2 with invalid data returns error changeset" do
      scope = user_scope_fixture()
      assert {:error, %Ecto.Changeset{}} = Teams.create_team(scope, @invalid_attrs)
    end

    test "update_team/3 with valid data updates the team" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      update_attrs = %{name: "some updated name"}

      assert {:ok, %Team{} = team} = Teams.update_team(scope, team, update_attrs)
      assert team.name == "some updated name"
    end

    test "update_team/3 with a scope that is not a member raises" do
      scope = user_scope_fixture()
      other_scope = user_scope_fixture()
      team = team_fixture(scope)

      assert_raise MatchError, fn ->
        Teams.update_team(other_scope, team, %{})
      end
    end

    test "update_team/3 with invalid data returns error changeset" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      assert {:error, %Ecto.Changeset{}} = Teams.update_team(scope, team, @invalid_attrs)
      assert team == Teams.get_team!(scope, team.id)
    end

    test "delete_team/2 deletes the team" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      assert {:ok, %Team{}} = Teams.delete_team(scope, team)
      assert_raise Ecto.NoResultsError, fn -> Teams.get_team!(scope, team.id) end
    end

    test "delete_team/2 with a scope that is not owner raises" do
      scope = user_scope_fixture()
      other_scope = user_scope_fixture()
      team = team_fixture(scope)
      assert_raise MatchError, fn -> Teams.delete_team(other_scope, team) end
    end

    test "change_team/2 returns a team changeset" do
      scope = user_scope_fixture()
      team = team_fixture(scope)
      assert %Ecto.Changeset{} = Teams.change_team(scope, team)
    end
  end

  describe "team_memberships" do
    alias Mapo.Teams.Membership

    import Mapo.AccountsFixtures, only: [user_scope_fixture: 0, user_fixture: 0]
    import Mapo.TeamsFixtures

    @invalid_attrs %{role: nil, team_id: nil, user_id: nil}

    test "list_team_memberships/0 returns all team_memberships" do
      membership = membership_fixture()
      assert Teams.list_team_memberships() |> Enum.map(& &1.id) |> Enum.member?(membership.id)
    end

    test "get_membership!/1 returns the membership with given id" do
      membership = membership_fixture()
      assert Teams.get_membership!(membership.id) == membership
    end

    test "create_membership/1 with valid data creates a membership" do
      team = team_fixture(user_scope_fixture())
      user = user_fixture()
      valid_attrs = %{role: :owner, team_id: team.id, user_id: user.id}

      assert {:ok, %Membership{} = membership} = Teams.create_membership(valid_attrs)
      assert membership.role == :owner
    end

    test "create_membership/1 with invalid data returns error changeset" do
      assert {:error, %Ecto.Changeset{}} = Teams.create_membership(@invalid_attrs)
    end

    test "create_membership/1 twice for the same team/user violates the unique constraint" do
      team = team_fixture(user_scope_fixture())
      user = user_fixture()
      attrs = %{role: :member, team_id: team.id, user_id: user.id}

      assert {:ok, %Membership{}} = Teams.create_membership(attrs)
      assert {:error, changeset} = Teams.create_membership(attrs)
      assert "has already been taken" in errors_on(changeset).team_id
    end

    test "update_membership/2 with valid data updates the membership" do
      membership = membership_fixture()
      update_attrs = %{role: :admin}

      assert {:ok, %Membership{} = membership} = Teams.update_membership(membership, update_attrs)
      assert membership.role == :admin
    end

    test "update_membership/2 with invalid data returns error changeset" do
      membership = membership_fixture()
      assert {:error, %Ecto.Changeset{}} = Teams.update_membership(membership, @invalid_attrs)
      assert membership == Teams.get_membership!(membership.id)
    end

    test "delete_membership/1 deletes the membership" do
      membership = membership_fixture()
      assert {:ok, %Membership{}} = Teams.delete_membership(membership)
      assert_raise Ecto.NoResultsError, fn -> Teams.get_membership!(membership.id) end
    end

    test "change_membership/1 returns a membership changeset" do
      membership = membership_fixture()
      assert %Ecto.Changeset{} = Teams.change_membership(membership)
    end
  end
end
