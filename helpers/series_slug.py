"""The series page URL slug: ``series-name-vVOLUME-ID``."""
import re


def generate_series_slug(series_name, metron_id, volume=None):
    """
    Generate a URL-friendly slug for a series or issue page.
    Format: series-name-vVOLUME-ID (e.g., amazing-spider-man-v1-4984)

    The metron_id is a series_id or issue_id depending on the route:
    - For issue_view: issue_id (resolves to series_id then redirects)
    - For series_view: series_id (used directly)
    """

    # Ensure we have a valid ID
    if not metron_id:
        return None

    if not series_name:
        return str(metron_id)

    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = str(series_name).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")

    # Add volume if provided
    if volume:
        slug = f"{slug}-v{volume}"

    # Always append ID for reliable lookup
    slug = f"{slug}-{metron_id}"

    return slug
