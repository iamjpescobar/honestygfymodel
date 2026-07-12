"""
Player headshots via MLB's public image CDN. No API key required —
this is the same URL pattern MLB.com itself uses for player photos,
keyed by the MLBAM player ID your roster/statcast engines already track.
"""


def get_headshot_url(mlbam_id) -> str:
    """
    Returns MLB's official headshot CDN URL for a given MLBAM player ID.
    Falls back gracefully — MLB's CDN itself returns a generic silhouette
    image for unknown/invalid IDs rather than a broken image, so no local
    fallback image is needed here.
    """
    if not mlbam_id:
        return ""
    return f"https://img.mlbstatic.com/mlb-photos/image/upload/w_180,q_100/v1/people/{mlbam_id}/headshot/67/current"
