"""Simple keyword extraction from title + description without LLM."""
import re
from collections import Counter

# German + English stopwords (compact set)
STOPWORDS = {
    "der", "die", "das", "ein", "eine", "und", "oder", "aber", "in", "im", "an", "am",
    "auf", "aus", "bei", "bis", "mit", "nach", "von", "vor", "zu", "zum", "zur",
    "ist", "sind", "war", "hat", "haben", "wird", "werden", "kann", "wie", "was",
    "wir", "ihr", "sie", "ich", "du", "er", "es", "den", "dem", "des", "nicht",
    "auch", "noch", "nur", "schon", "sehr", "mehr", "wenn", "dass", "dann", "denn",
    "ueber", "unter", "fuer", "gegen", "ohne", "durch", "um", "ob", "als", "so",
    "diese", "dieser", "dieses", "jetzt", "hier", "da", "doch", "mal", "neue",
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "is", "are", "was", "has", "have", "will", "can", "how", "what", "why", "who",
    "with", "from", "by", "this", "that", "your", "you", "we", "it", "its", "my",
    "not", "all", "new", "get", "just", "about", "more", "than", "most", "every",
    "video", "videos", "kanal", "channel", "episode", "folge", "teil", "part",
}


def extract_keywords(title: str, description: str = "", max_keywords: int = 10) -> list[str]:
    """Extract keywords from title and description using frequency analysis."""
    text = f"{title} {title} {description}"  # Title weighted 2x
    # Remove URLs, special chars, numbers-only tokens
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^\w\säöüÄÖÜß#]", " ", text)

    words = text.lower().split()
    # Filter: min length 3, not stopword, not pure number
    filtered = [w for w in words if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()]

    # Count frequency
    counts = Counter(filtered)

    # Extract hashtags from description separately
    hashtags = re.findall(r"#(\w{3,})", description)

    # Combine: hashtags first, then by frequency
    seen = set()
    result = []
    for tag in hashtags:
        tag_lower = tag.lower()
        if tag_lower not in seen and tag_lower not in STOPWORDS:
            result.append(tag_lower)
            seen.add(tag_lower)

    for word, _ in counts.most_common(max_keywords * 2):
        if word not in seen:
            result.append(word)
            seen.add(word)
        if len(result) >= max_keywords:
            break

    return result[:max_keywords]
