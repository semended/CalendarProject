from typing import Optional

from app.models import User

PRIVACY_FIELDS = ("email", "bio", "position", "company", "workplace")
PRIVACY_CHOICES = ("public", "authed", "self")


def is_visible(target: User, viewer: Optional[User], field: str) -> bool:
    level = getattr(target, f"privacy_{field}", None) or "authed"
    if viewer is not None and viewer.id == target.id:
        return True
    if level == "public":
        return True
    if level == "authed":
        return viewer is not None
    return False
