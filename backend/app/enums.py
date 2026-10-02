from enum import StrEnum


class EventType(StrEnum):
    """Every kind of user behaviour we record.

    Shared by the database layer (models.py, CHECK constraint) and the API
    layer (schemas.py, request validation), so it lives in neither.

    Explicit feedback: the user tells us what they think (like, dislike).
    Implicit feedback: we infer interest from what they do (everything else).

    The log is append-only, so toggles are recorded as explicit reversal
    events (unsave, unlike) rather than by deleting the original event.
    """

    VIEW = "view"
    CLICK = "click"
    SAVE = "save"
    UNSAVE = "unsave"
    LIKE = "like"
    UNLIKE = "unlike"
    DISLIKE = "dislike"
    SEARCH = "search"
    COMPLETE = "complete"
    SKIP = "skip"
