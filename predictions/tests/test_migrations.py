"""Migration-level test for the export_key backfill.

Production already has leagues, and a unique field with only a *callable* default
would hand every existing row the same value at migrate time and collide. The
0004 migration instead adds the column unconstrained, backfills a unique key per
league, then enforces uniqueness — this test exercises exactly that path.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ExportKeyBackfillTests(TransactionTestCase):
    migrate_from = [("predictions", "0003_match_away_label_match_home_label_match_venue")]
    migrate_to = [("predictions", "0004_league_export_key")]

    def test_backfills_unique_keys_for_existing_leagues(self):
        from accounts.models import User  # real manager; accounts table is at head

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)            # roll back: no export_key yet
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Competition = old_apps.get_model("predictions", "Competition")
        League = old_apps.get_model("predictions", "League")

        owner = User.objects.create_user(email="owner@test.com", password="pw")
        comp = Competition.objects.create(name="جام", slug="cup")
        # owner_id (not owner): the real User isn't part of the historical app set.
        League.objects.create(name="یک", slug="one", competition=comp,
                              owner_id=owner.id, invite_code="INVITE01")
        League.objects.create(name="دو", slug="two", competition=comp,
                              owner_id=owner.id, invite_code="INVITE02")

        # Apply 0004: add column -> backfill -> enforce unique.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps

        League = new_apps.get_model("predictions", "League")
        keys = list(League.objects.values_list("export_key", flat=True))
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(keys), "every existing league must receive a key")
        self.assertEqual(len(set(keys)), 2, "backfilled keys must be unique")

    def tearDown(self):
        # Leave the schema at the latest migration for the rest of the suite.
        MigrationExecutor(connection).migrate(self.migrate_to)
