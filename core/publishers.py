"""House colours for the publisher dot.

A fixed table: a publisher not listed gets no dot, never a hashed colour.
The colour is identity only; the name always sits beside the dot.
"""
import re

PUBLISHER_COLORS = {
    "dc": "#0476f2",
    "marvel": "#ec1d24",
    "image": "#111111",
    "dark horse": "#7b1e1e",
    "idw": "#0b3d91",
    "boom": "#f26522",
    "dynamite": "#fcb515",
    "oni": "#009b5a",
    "titan": "#00a3a1",
    "valiant": "#c8102e",
    "archie": "#f7c600",
    "vault": "#6a2c91",
    "mad cave": "#e8590c",
    "ahoy": "#0d98ba",
}

_SUFFIXES = {"comics", "publishing", "entertainment", "studios", "press"}


def publisher_color(name):
    """The house colour for a publisher name, or None."""
    words = re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return PUBLISHER_COLORS.get(" ".join(words))
