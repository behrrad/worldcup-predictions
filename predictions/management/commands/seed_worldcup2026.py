"""
Seed the World Cup 2026 competition with the **real, official schedule**.

The data lives in `predictions/data/worldcup2026.json` (48 teams in their real
groups A–L and all 104 matches — 72 group + 32 knockout — with exact kickoff
times in UTC). The whole file is validated *before* any database write, so a bad
file can never leave the data half-loaded. Matches are upserted by match number,
so existing predictions, scores and entered results survive a reload.
"""
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from predictions import seed_data as sd
from predictions.models import Competition, Match, MatchScore, Prediction, Team

DATA_PATH = Path(settings.BASE_DIR) / "predictions" / "data" / "worldcup2026.json"
VALID_STAGES = {"GROUP", "R32", "R16", "QF", "SF", "TP", "F"}
EXPECTED_STAGE_COUNTS = {
    "GROUP": 72, "R32": 16, "R16": 8, "QF": 4, "SF": 2, "TP": 1, "F": 1,
}


def _validate(data):
    """Return a list of problems. Empty list ⇒ the file is safe to load."""
    errors = []
    teams = data.get("teams") or []
    matches = data.get("matches") or []

    codes = [t.get("code") for t in teams]
    # name_fa is the team's unique key (see Team.unique_team_per_competition), so
    # the loader upserts on it — names must be unique and non-empty too.
    names = [(t.get("name_fa") or t.get("name_en")) for t in teams]
    if len(teams) != 48:
        errors.append(f"باید ۴۸ تیم باشد، اما {len(teams)} تیم وجود دارد.")
    if not all(codes) or len(set(codes)) != len(codes):
        errors.append("کد تیم‌ها باید یکتا و غیرخالی باشد.")
    if not all(names) or len(set(names)) != len(names):
        errors.append("نام تیم‌ها باید یکتا و غیرخالی باشد.")
    code_set = set(codes)

    nums = [m.get("match_number") for m in matches]
    expected_total = sum(EXPECTED_STAGE_COUNTS.values())
    if not all(isinstance(n, int) for n in nums) or len(set(nums)) != len(nums):
        errors.append("شمارهٔ بازی‌ها باید عدد و یکتا باشد.")
    elif set(nums) != set(range(1, expected_total + 1)):
        # Require the exact 1..N set: otherwise an upsert would add the listed
        # numbers while leaving omitted old matches behind as stale fixtures.
        errors.append(f"شماره‌های بازی باید دقیقاً ۱ تا {expected_total} باشند.")
    stage_counts = Counter(m.get("stage") for m in matches)
    if dict(stage_counts) != EXPECTED_STAGE_COUNTS:
        errors.append(f"تعداد بازی‌های هر مرحله نادرست است: {dict(stage_counts)}")

    for m in matches:
        n = m.get("match_number")
        if m.get("stage") not in VALID_STAGES:
            errors.append(f"بازی {n}: مرحلهٔ نامعتبر «{m.get('stage')}».")
        try:
            datetime.fromisoformat((m.get("kickoff_utc") or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            errors.append(f"بازی {n}: زمان شروع نامعتبر است.")
        # Any team code the file names (group or knockout) must be a real team.
        for code in (m.get("home_code"), m.get("away_code")):
            if code is not None and code not in code_set:
                errors.append(f"بازی {n}: کد تیم نامعتبر «{code}».")
        # Group matches must name both teams (knockout slots may be undecided).
        if m.get("stage") == "GROUP":
            if m.get("home_code") not in code_set or m.get("away_code") not in code_set:
                errors.append(f"بازی گروهی {n}: تیم میزبان/میهمان نامعتبر است.")
    return errors


class Command(BaseCommand):
    help = (
        "بارگذاری برنامهٔ واقعی جام جهانی ۲۰۲۶ (تیم‌ها، گروه‌ها و زمان دقیق هر ۱۰۴ بازی). "
        "ابتدا کل فایل اعتبارسنجی می‌شود؛ سپس بازی‌ها بر اساس شمارهٔ بازی به‌روزرسانی "
        "می‌شوند تا پیش‌بینی‌ها، امتیازها و نتایج ثبت‌شده حفظ شوند."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", default=str(DATA_PATH),
            help="مسیر فایل JSON برنامه (پیش‌فرض: داده‌های همراه پروژه).",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help="حذف کامل تیم‌ها و بازی‌های قبلی این تورنمنت پیش از بارگذاری "
                 "(پیش‌بینی‌ها و نتایج پاک می‌شوند). بدون این گزینه، داده‌ها حفظ می‌شوند.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"فایل داده پیدا نشد: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"فایل JSON نامعتبر است: {exc}")

        # Validate EVERYTHING before any database write — so a bad file can never
        # leave the data half-loaded.
        errors = _validate(data)
        if errors:
            raise CommandError(
                "داده نامعتبر است؛ هیچ تغییری اعمال نشد:\n- " + "\n- ".join(errors[:25])
            )

        comp, _ = Competition.objects.get_or_create(
            slug=sd.WC2026_SLUG, defaults={"name": sd.WC2026_NAME, "is_active": True}
        )
        comp.name = sd.WC2026_NAME
        start = data.get("competition", {}).get("start_date")
        if start:
            comp.start_date = date.fromisoformat(start)
        comp.save()

        if options["reset"]:
            # Full clean slate — cascade removes predictions/scores; teams too so a
            # corrupted team row can't collide with the fresh upsert.
            comp.matches.all().delete()
            comp.teams.all().delete()
            self.stdout.write(self.style.WARNING("داده‌های قبلی این تورنمنت پاک شد."))

        # Snapshot each existing match's team codes BEFORE any team change, so a
        # fixture change is detected against the *real* old pairing even when an
        # old team is about to be pruned (its FK would otherwise be NULLed first).
        old_fixture = {
            mn: (h, a) for mn, h, a in comp.matches.values_list(
                "match_number", "home_team__code", "away_team__code"
            )
        }

        # UPSERT teams by name_fa — their unique key (see Team.Meta) — so each
        # Team keeps its identity (and any knockout FK pointing at it) across
        # reloads. Upserting by the unique key also avoids inserting a duplicate
        # name. Teams no longer in the file are pruned afterwards.
        team_map = {}        # code -> Team (for assigning matches)
        names_seen = set()
        for t in data["teams"]:
            name_fa = t.get("name_fa") or t["name_en"]
            names_seen.add(name_fa)
            team, _ = Team.objects.update_or_create(
                competition=comp, name_fa=name_fa,
                defaults={
                    "name_en": t.get("name_en", ""),
                    "code": t["code"],
                    "flag_emoji": t.get("flag") or "",
                    "group": t.get("group") or "",
                },
            )
            team_map[t["code"]] = team
        comp.teams.exclude(name_fa__in=names_seen).delete()

        # Matches are UPSERTED by match_number, so existing rows — and the
        # predictions, scores, and entered results attached to them — survive.
        # Teams are only (re)assigned from the file when it actually names them, so
        # a reload never wipes admin-filled knockout participants (the JSON has no
        # home_code/away_code for undecided knockout slots).
        n_group = n_knockout = n_cleared = 0
        for m in sorted(data["matches"], key=lambda x: x["match_number"]):
            mn = m["match_number"]
            kickoff = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
            hc, ac = m.get("home_code"), m.get("away_code")
            defaults = {"stage": m["stage"], "kickoff": kickoff}
            if hc:
                defaults["home_team"] = team_map.get(hc)
            if ac:
                defaults["away_team"] = team_map.get(ac)

            # Treat the fixture as changed when the file repoints this match number
            # at a different pairing OR a previously-assigned team has been pruned
            # (its code is gone from the new schedule). In either case the old
            # predictions/scores/result were about other teams — drop them so they
            # aren't reattached to the wrong (or now-empty) fixture. Unchanged
            # fixtures keep everything (the whole point of the upsert).
            old = old_fixture.get(mn)
            fixture_changed = old is not None and (
                (hc and old[0] != hc) or (ac and old[1] != ac)
                or (old[0] and old[0] not in team_map)
                or (old[1] and old[1] not in team_map)
            )
            if fixture_changed:
                Prediction.objects.filter(match__competition=comp, match__match_number=mn).delete()
                MatchScore.objects.filter(match__competition=comp, match__match_number=mn).delete()
                defaults["home_score"] = None
                defaults["away_score"] = None
                n_cleared += 1

            Match.objects.update_or_create(
                competition=comp, match_number=mn, defaults=defaults,
            )
            if m["stage"] == "GROUP":
                n_group += 1
            else:
                n_knockout += 1

        if n_cleared:
            self.stdout.write(self.style.WARNING(
                f"{n_cleared} بازی فیکسچرشان تغییر کرد؛ پیش‌بینی‌ها و امتیازهای قدیمیِ "
                f"آن بازی‌ها پاک شد."
            ))
        self.stdout.write(self.style.SUCCESS(
            f"«{comp.name}» با برنامهٔ واقعی بارگذاری شد: {len(team_map)} تیم، "
            f"{n_group} بازی گروهی و {n_knockout} بازی مرحلهٔ حذفی (با زمان دقیق). "
            f"پیش‌بینی‌ها و نتایج بازی‌های بدون تغییر حفظ شدند."
        ))
