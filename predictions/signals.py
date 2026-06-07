from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Match
from .scoring import recompute_match_scores


@receiver(post_save, sender=Match, dispatch_uid="recompute_scores_on_match_save")
def recompute_on_match_save(sender, instance, **kwargs):
    """When a match result is entered or changed, recompute everyone's score."""
    recompute_match_scores(instance)
