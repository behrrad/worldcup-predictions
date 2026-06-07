import json
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from predictions import seed_data as sd
from predictions.models import Competition, Match, Team

DATA_PATH = Path(settings.BASE_DIR) / "predictions" / "data" / "worldcup2026.json"
VALID_STAGES = {"GROUP", "R32", "R16", "QF", "SF", "TP", "F"}


class Command(BaseCommand):
    help = (
        "بارگذاری برنامهٔ واقعی جام جهانی ۲۰۲۶ از فایل predictions/data/worldcup2026.json "
        "(تیم‌ها، گروه‌ها و زمان دقیق همهٔ ۱۰۴ بازی). داده‌های قبلی این تورنمنت جایگزین می‌شود."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not DATA_PATH.exists():
            self.stderr.write(self.style.ERROR(f"فایل داده پیدا نشد: {DATA_PATH}"))
            return

        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

        comp, _ = Competition.objects.get_or_create(
            slug=sd.WC2026_SLUG, defaults={"name": sd.WC2026_NAME, "is_active": True}
        )
        comp.name = sd.WC2026_NAME
        start = data.get("competition", {}).get("start_date")
        if start:
            comp.start_date = date.fromisoformat(start)
        comp.save()

        # Replace any existing teams/matches for this competition (leagues are kept).
        comp.matches.all().delete()
        comp.teams.all().delete()

        teams = {}
        for t in data["teams"]:
            team = Team.objects.create(
                competition=comp,
                name_fa=t.get("name_fa") or t.get("name_en", ""),
                name_en=t.get("name_en", ""),
                code=t.get("code") or "",
                flag_emoji=t.get("flag") or "",
                group=t.get("group") or "",
            )
            if t.get("code"):
                teams[t["code"]] = team

        n_group = n_knockout = 0
        for m in sorted(data["matches"], key=lambda x: x["match_number"]):
            stage = m["stage"]
            kickoff_raw = m.get("kickoff_utc")
            if stage not in VALID_STAGES or not kickoff_raw:
                continue
            kickoff = datetime.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
            Match.objects.create(
                competition=comp,
                match_number=m["match_number"],
                stage=stage,
                home_team=teams.get(m.get("home_code")) if m.get("home_code") else None,
                away_team=teams.get(m.get("away_code")) if m.get("away_code") else None,
                kickoff=kickoff,
            )
            if stage == "GROUP":
                n_group += 1
            else:
                n_knockout += 1

        self.stdout.write(self.style.SUCCESS(
            f"«{comp.name}» با برنامهٔ واقعی بارگذاری شد: {len(teams)} تیم، "
            f"{n_group} بازی گروهی و {n_knockout} بازی مرحلهٔ حذفی (با زمان دقیق)."
        ))
