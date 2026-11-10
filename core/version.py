"""
Version information for Comic Library Utilities (CLU)
"""

__version__ = "7.2"

# How CLU identifies itself to metadata providers that ask clients not to
# pretend to be a browser (Metron, MangaDex, MangaUpdates, Bedetheque,
# AniList). Providers fronted by a Cloudflare bot check that 403s non-browser
# agents (ComicVine, comics.org) use models.providers.base's
# DEFAULT_PROVIDER_USER_AGENT instead.
CLU_USER_AGENT = f"CLU/{__version__}"


# ---------------------------------------------------------------------------
# Fork build label (xezeliar/clu-comics).
#
# Upstream bumps __version__ at the top of this file; leave that line exactly
# as upstream has it, so their release bumps merge cleanly. The label is a
# PEP 440 local version ("7.1+xez.1"): it still sorts below upstream's next
# release, so the update check in app.py keeps announcing it. It is applied
# after CLU_USER_AGENT on purpose -- providers keep seeing plain "CLU/7.1".
# Raise the number when publishing a new build of the fork.
FORK_LABEL = "xez.1"
UPSTREAM_VERSION = __version__
__version__ = f"{UPSTREAM_VERSION}+{FORK_LABEL}"
