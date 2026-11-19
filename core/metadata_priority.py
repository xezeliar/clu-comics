"""Library provider priority for auto-tagging a file that already has metadata.

A file tagged by a provider is left alone unless a provider the library ranks
*higher* is about to tag it. Equal or lower rank, a provider outside the
library's order, manual tags and unrecognised Notes all keep the file.
"""
from core.comicinfo import has_trusted_notes, provider_from_notes

SUPPORTED = ('metron', 'comicvine', 'comicvine_sqlite')


def move_metadata_order(path):
    """Provider order for auto-metadata on ``path``'s library (legacy default if unset)."""
    from helpers.library import get_library_for_path
    from core.database import get_library_providers
    lib = get_library_for_path(path)
    if lib and lib.get('id'):
        order = [p['provider_type'] for p in get_library_providers(lib['id'])
                 if p.get('enabled', True) and p['provider_type'] in SUPPORTED]
        if order:
            return order
    return ['metron', 'comicvine']


def _rank(order, provider):
    # ComicVine's API and local DB are one source of data: either slot counts.
    group = ('comicvine', 'comicvine_sqlite') if provider.startswith('comicvine') else (provider,)
    return next((i for i, p in enumerate(order) if p in group), None)


def should_skip_tagged(notes, provider, order):
    """True when ``provider`` must not re-tag a file whose ComicInfo Notes are ``notes``."""
    if not has_trusted_notes(notes):
        return False
    existing = provider_from_notes(notes)
    if not existing or existing == 'manual':
        return True
    have, want = _rank(order, existing), _rank(order, provider)
    if have is None or want is None:
        return True
    return want >= have
