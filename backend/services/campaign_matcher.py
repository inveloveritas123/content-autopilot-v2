import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def match_item_to_campaigns(
    analysis: dict,
    campaigns: list[dict],
    threshold: float = 0.1,
) -> Optional[uuid.UUID]:
    """
    Match a source item's analysis against active campaigns.
    Returns the campaign ID of the best match, or None.

    campaigns: list of dicts with 'id', 'keywords', 'name'
    """
    if not analysis or not campaigns:
        return None

    # Build item keyword set from tags + key_points words
    item_tags = set(t.lower() for t in analysis.get("tags", []))
    key_point_words = set()
    for kp in analysis.get("key_points", []):
        for word in kp.lower().split():
            if len(word) > 3:
                key_point_words.add(word)

    item_keywords = item_tags | key_point_words

    best_match_id = None
    best_score = 0.0

    for campaign in campaigns:
        campaign_keywords = set(k.lower() for k in campaign.get("keywords", []))
        if not campaign_keywords:
            continue

        score = jaccard_similarity(item_keywords, campaign_keywords)
        if score > best_score and score >= threshold:
            best_score = score
            best_match_id = campaign["id"]

    if best_match_id:
        logger.info(f"Matched to campaign {best_match_id} with score {best_score:.2f}")

    return best_match_id
