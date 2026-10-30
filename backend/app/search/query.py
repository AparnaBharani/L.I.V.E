"""Turn a natural-language query into a typed, inspectable structure.

Traditional NLP on purpose: normalisation, regular expressions and small lexicons. Each
result can be traced to the phrase that produced it, runs in microseconds, needs no model
and cannot invent a constraint the text does not contain. Anything not recognised stays
in `text` for retrieval, so the safe failure is "no filter", never a wrong filter.

Budget, duration and difficulty become hard filters. Category is only a hint, because
"something relaxing" suggests wellness without ruling out a quiet walk.
"""

import re
from dataclasses import dataclass, field

# Assumptions for vague words. Costs are whole rupees, durations are minutes.
CHEAP_MAX_COST = 500
QUICK_MAX_MINUTES = 60
SHORT_MAX_MINUTES = 90
COUPLE_OF_HOURS_MINUTES = 150
AFTERNOON_MINUTES = 300
FULL_DAY_MINUTES = 720

CATEGORY_WORDS = {
    "outdoors": ("outdoor", "outdoors", "outside", "nature", "hike", "hiking", "trek", "trekking",
                 "trail", "camping", "camp", "birdwatching", "stargazing", "waterfall", "beach", "forest"),
    "adventure": ("adventure", "adventurous", "adrenaline", "thrill", "thrilling", "extreme",
                  "rafting", "climbing", "paragliding", "kayaking", "zipline", "caving"),
    "creative": ("creative", "art", "arts", "artistic", "craft", "crafts", "pottery", "ceramics",
                 "paint", "painting", "drawing", "illustration", "photography", "writing", "make"),
    "social": ("social", "friends", "people", "group", "party", "together", "strangers", "community",
               "neighbours", "dancing", "volunteer", "volunteering"),
    "learning": ("learn", "learning", "study", "course", "skill", "skills", "coding", "programming",
                 "language", "history", "finance", "museum"),
    "wellness": ("wellness", "relax", "relaxing", "relaxation", "calm", "calming", "peaceful", "yoga",
                 "meditation", "meditate", "mindfulness", "stress", "breathing", "pilates", "unwind"),
}

DIFFICULTY_PHRASES = {
    "beginner": r"beginners?|beginner[- ]friendly|easy|simple|intro|introductory|first[- ]time(?:rs?)?"
                r"|never (?:done|tried)(?: \w+)?|no experience|for novices?|novices?",
    "intermediate": r"intermediate|moderate|moderately difficult",
    "advanced": r"advanced|challenging|expert|experts|hard|difficult|tough|demanding",
}

STOPWORDS = frozenset("""
    a about activity activities all am an and any are around at be best can could day do doing
    experience experiences for from get give good have help i id ideas im in into is it just like
    looking me maybe my need of on one or please recommend show so some something somewhere soon
    suggest that the then thing things this time to today tomorrow tonight try trying up very want
    wanna was we weekend what where which with would you your
""".split())

WORD_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
NUMBER = r"\d+(?:\.\d+)?|a|an|one|two|three|four|five|six"
UNDER = r"under|below|less than|within|up to|upto|at most|no more than|max(?:imum)?(?: of)?|not more than"
CURRENCY = r"(?:₹|rs\.?|inr)"


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    text: str = ""                                  # what is left to search for
    categories: tuple[str, ...] = ()                # soft hint
    max_cost: int | None = None                     # hard filter
    max_duration_minutes: int | None = None         # hard filter
    difficulty: str | None = None                   # hard filter
    matched: tuple[str, ...] = field(default=())    # the phrases that set a constraint

    @property
    def has_filters(self) -> bool:
        return self.max_cost is not None or self.max_duration_minutes is not None or self.difficulty is not None


def _number(value: str) -> float:
    return float(WORD_NUMBERS.get(value, value))


def _consume(pattern: str, text: str) -> tuple[re.Match | None, str]:
    """First match of pattern, and the text with that match blanked out."""
    match = re.search(pattern, text)
    return match, text if match is None else text[: match.start()] + " " + text[match.end():]


def _extract_duration(text: str) -> tuple[int | None, str, str | None]:
    # "at least 2 hours" is a minimum, which the filters can't express: drop it, set nothing.
    text = re.sub(rf"\b(?:at least|over|more than|longer than)\s+(?:{NUMBER})\s*(?:hours?|hrs?|minutes?|mins?|days?)\b", " ", text)

    for pattern, minutes in (
        (r"\b(?:half an hour|half hour)\b", 30),
        (r"\b(?:a )?couple (?:of )?hours\b", COUPLE_OF_HOURS_MINUTES),
        (r"\b(?:half a day|half[- ]day)\b", AFTERNOON_MINUTES),
        (r"\b(?:full[- ]day|all day|whole day|entire day)\b", FULL_DAY_MINUTES),
        (r"\b(?:an|one|the|this|for an|single) afternoon\b", AFTERNOON_MINUTES),
    ):
        match, rest = _consume(pattern, text)
        if match:
            return minutes, rest, match.group()

    match, rest = _consume(rf"\b(?:(?:{UNDER})\s+)?({NUMBER})\s*(hours?|hrs?|h|minutes?|mins?|m|days?)\b", text)
    if match:
        unit = match.group(2)
        scale = 1440 if unit.startswith("d") else 60 if unit.startswith("h") else 1
        return round(_number(match.group(1)) * scale), rest, match.group()

    for pattern, minutes in ((r"\bquick(?:ly)?\b", QUICK_MAX_MINUTES), (r"\bshort\b", SHORT_MAX_MINUTES)):
        match, rest = _consume(pattern, text)
        if match:
            return minutes, rest, match.group()
    return None, text, None


def _extract_cost(text: str) -> tuple[int | None, str, str | None]:
    def amount(match: re.Match) -> int:
        digits, thousands = match.group(1).replace(",", ""), match.group(2)
        return round(float(digits) * (1000 if thousands else 1))

    value = r"(\d[\d,]*(?:\.\d+)?)\s*(k)?"
    for pattern in (
        rf"(?:{UNDER}|budget(?: of| is)?|for)\s*{CURRENCY}?\s*{value}\s*(?:rupees?|rs|inr)?\b(?!\s*(?:people|friends|persons?))",
        rf"{CURRENCY}\s*{value}\b(?:\s*budget)?",
        rf"\b{value}\s*(?:rupees?|rs|inr)\b",
    ):
        match, rest = _consume(pattern, text)
        if match:
            return amount(match), rest, match.group().strip()

    match, rest = _consume(r"\b(?:free of cost|for free|no cost|free)\b(?!\s+(?:time|day|evening|afternoon|weekend|morning))", text)
    if match:
        return 0, rest, match.group()
    match, rest = _consume(
        r"\b(?:cheap(?:ly)?|inexpensive|affordable|budget[- ]friendly|low[- ]cost|"
        r"(?:not|isn'?t|isnt|nothing)(?: too| very| that)? (?:expensive|costly|pricey))\b", text)
    if match:
        return CHEAP_MAX_COST, rest, match.group()
    return None, text, None


def _extract_difficulty(text: str) -> tuple[str | None, str, str | None]:
    for level, phrases in DIFFICULTY_PHRASES.items():
        match, rest = _consume(rf"\b(?:{phrases})\b", text)
        if match:
            return level, rest, match.group()
    return None, text, None


def parse_query(raw: str) -> ParsedQuery:
    text = " ".join(raw.lower().split())
    max_duration, text, duration_phrase = _extract_duration(text)
    max_cost, text, cost_phrase = _extract_cost(text)
    difficulty, text, difficulty_phrase = _extract_difficulty(text)

    tokens = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?|\d+", text)
    categories = tuple(c for c, words in CATEGORY_WORDS.items() if any(t in words for t in tokens))
    # Category words stay in the text: they are useful search terms as well as hints.
    remaining = [t for t in tokens if t.replace("'", "") not in STOPWORDS]

    return ParsedQuery(
        raw=raw,
        text=" ".join(remaining),
        categories=categories,
        max_cost=max_cost,
        max_duration_minutes=max_duration,
        difficulty=difficulty,
        matched=tuple(p for p in (duration_phrase, cost_phrase, difficulty_phrase) if p),
    )
