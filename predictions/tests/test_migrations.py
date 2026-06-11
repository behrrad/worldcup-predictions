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


class ReslugLeaguesTests(TransactionTestCase):
    """0006 rewrites Persian league slugs to readable ASCII (and leaves ASCII
    slugs — e.g. ones customised by hand — exactly as they are)."""

    migrate_from = [("predictions", "0005_league_reveal_predictions")]
    migrate_to = [("predictions", "0006_reslug_leagues_to_latin")]
    head = [("predictions", "0006_reslug_leagues_to_latin")]

    def test_persian_slugs_rewritten_ascii_slugs_kept(self):
        from accounts.models import User

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)            # before the re-slug runs
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Competition = old_apps.get_model("predictions", "Competition")
        League = old_apps.get_model("predictions", "League")

        owner = User.objects.create_user(email="owner@test.com", password="pw")
        comp = Competition.objects.create(name="جام", slug="cup")
        # A Persian slug (what save() used to produce) — must be transliterated.
        League.objects.create(name="لیگ دوستان", slug="لیگ-دوستان", competition=comp,
                              owner_id=owner.id, invite_code="INVITE01")
        # An ASCII slug (English name or hand-edited) — must be left untouched.
        League.objects.create(name="My League", slug="custom-keep", competition=comp,
                              owner_id=owner.id, invite_code="INVITE02")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps

        League = new_apps.get_model("predictions", "League")
        self.assertEqual(League.objects.get(invite_code="INVITE01").slug, "lig-dustan")
        self.assertEqual(League.objects.get(invite_code="INVITE02").slug, "custom-keep")

    def test_colliding_slugs_get_suffixed_without_overwrite(self):
        from accounts.models import User

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Competition = old_apps.get_model("predictions", "Competition")
        League = old_apps.get_model("predictions", "League")

        owner = User.objects.create_user(email="owner@test.com", password="pw")
        comp = Competition.objects.create(name="جام", slug="cup")
        # An existing ASCII slug equal to what «لیگ دوستان» transliterates to — it
        # must be preserved, and the re-slugged leagues must route around it.
        League.objects.create(name="Keep Me", slug="lig-dustan", competition=comp,
                              owner_id=owner.id, invite_code="INVITE00")
        # Two Persian leagues whose names transliterate to the same base.
        League.objects.create(name="لیگ دوستان", slug="لیگ-دوستان", competition=comp,
                              owner_id=owner.id, invite_code="INVITE01")
        League.objects.create(name="لیگ دوستان", slug="لیگ-دوستان-2", competition=comp,
                              owner_id=owner.id, invite_code="INVITE02")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps

        League = new_apps.get_model("predictions", "League")
        slugs = {
            ic: League.objects.get(invite_code=ic).slug
            for ic in ("INVITE00", "INVITE01", "INVITE02")
        }
        self.assertEqual(slugs["INVITE00"], "lig-dustan")          # untouched
        self.assertEqual(len(set(slugs.values())), 3)              # all unique
        self.assertTrue(slugs["INVITE01"].startswith("lig-dustan-"))
        self.assertTrue(slugs["INVITE02"].startswith("lig-dustan-"))

    def tearDown(self):
        # Leave the schema at head for the rest of the suite.
        MigrationExecutor(connection).migrate(self.head)


class UnlockUntilKickoffTests(TransactionTestCase):
    """0007 moves leagues off the old 30-minute lock default to 0 (lock at
    kickoff) — but leaves deliberately customised lock windows alone."""

    migrate_from = [("predictions", "0006_reslug_leagues_to_latin")]
    migrate_to = [("predictions", "0007_alter_league_lock_minutes")]

    def test_old_default_rewritten_custom_values_kept(self):
        from accounts.models import User

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)            # before the unlock runs
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Competition = old_apps.get_model("predictions", "Competition")
        League = old_apps.get_model("predictions", "League")

        owner = User.objects.create_user(email="owner@test.com", password="pw")
        comp = Competition.objects.create(name="جام", slug="cup")
        League.objects.create(name="یک", slug="one", competition=comp,
                              owner_id=owner.id, invite_code="INVITE01",
                              export_key="EXPORT01", lock_minutes=30)
        League.objects.create(name="دو", slug="two", competition=comp,
                              owner_id=owner.id, invite_code="INVITE02",
                              export_key="EXPORT02", lock_minutes=60)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps

        League = new_apps.get_model("predictions", "League")
        self.assertEqual(League.objects.get(invite_code="INVITE01").lock_minutes, 0)
        self.assertEqual(League.objects.get(invite_code="INVITE02").lock_minutes, 60)

    def tearDown(self):
        # Leave the schema at the latest migration for the rest of the suite.
        MigrationExecutor(connection).migrate(self.migrate_to)
