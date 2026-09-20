"""Platform-specific public profile lookup modules."""

from social_osint_lookup.platforms import instagram, tiktok, x

PLATFORMS = {
    "tiktok": tiktok,
    "instagram": instagram,
    "x": x,
    "twitter": x,  # alias
}

__all__ = ["PLATFORMS", "tiktok", "instagram", "x"]
