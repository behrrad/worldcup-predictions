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
    if len(teams) != 48:
        errors.append(f"باید ۴۸ تیم باشد، اما {len(teams)} تیم وجود دارد.")
    if not all(codes) or len(set(codes)) != len(codes):
        errors.append("کد تیم‌ها باید یکتا و غیرخالی باشد.")
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
            # Full clean slate — this also removes any predictions/scores via cascade.
            comp.matches.all().delete()
            self.stdout.write(self.style.WARNING("داده‌های قبلی این تورنمنت پاک شد."))

        # UPSERT teams by code (don't delete-and-recreate): this keeps each Team's
        # identity, so knockout matches an admin has already filled in keep pointing
        # at the right team across reloads. Teams that left the tournament (a code no
        # longer in the file) are pruned afterwards.
        team_map = {}
        for t in data["teams"]:
            team, _ = Team.objects.update_or_create(
                competition=comp, code=t["code"],
                defaults={
                    "name_fa": t.get("name_fa") or t["name_en"],
                    "name_en": t.get("name_en", ""),
                    "flag_emoji": t.get("flag") or "",
                    "group": t.get("group") or "",
                },
            )
            team_map[t["code"]] = team
        comp.teams.exclude(code__in=team_map).delete()

        # Matches are UPSERTED by match_number, so existing match rows — and the
        # predictions, scores, and entered results attached to them — survive.
        # Teams are only (re)assigned from the file when it actually names them, so
        # a reload never wipes admin-filled knockout participants (the JSON has no
        # home_code/away_code for undecided knockout slots).
        n_group = n_knockout = n_cleared = 0
        for m in sorted(data["matches"], key=lambda x: x["match_number"]):
            kickoff = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
            hc, ac = m.get("home_code"), m.get("away_code")
            defaults = {"stage": m["stage"], "kickoff": kickoff}
            if hc:
                defaults["home_team"] = team_map.get(hc)
            if ac:
                defaults["away_team"] = team_map.get(ac)

            existing = (
                Match.objects.filter(competition=comp, match_number=m["match_number"])
                .select_related("home_team", "away_team").first()
            )
            # If this match number now points at a *different* fixture than what's
            # stored (e.g. migrating an old placeholder schedule to the real one),
            # any predictions/scores on the row were about other teams — drop them
            # so they aren't silently reattached to the wrong fixture. Unchanged
            # fixtures keep their predictions (the whole point of the upsert).
            if existing and (
                (hc and existing.home_team and existing.home_team.code != hc)
                or (ac and existing.away_team and existing.away_team.code != ac)
            ):
                Prediction.objects.filter(match=existing).delete()
                MatchScore.objects.filter(match=existing).delete()
                n_cleared += 1

            Match.objects.update_or_create(
                competition=comp, match_number=m["match_number"], defaults=defaults,
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
