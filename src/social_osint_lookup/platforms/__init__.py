"""Platform-specific public profile lookup modules."""

from social_osint_lookup.platforms import facebook, instagram, tiktok

PLATFORMS = {
    "tiktok": tiktok,
    "instagram": instagram,
    "facebook": facebook,
}

__all__ = ["PLATFORMS", "tiktok", "instagram", "facebook"]
