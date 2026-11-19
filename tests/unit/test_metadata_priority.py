import pytest
from core.metadata_priority import should_skip_tagged

SCENE = "Scraped metadata from ComicVine [CVDB1026557]."
CLU_CV = "Metadata from ComicVine. Issue ID: 5"
METRON = "Metadata from Metron"


@pytest.mark.parametrize("notes,provider,order,skip", [
    ("", "comicvine", ["comicvine", "metron"], False),            # untagged
    (SCENE, "metron", ["metron", "comicvine"], False),            # higher priority retags
    (SCENE, "comicvine", ["metron", "comicvine"], True),          # lower priority leaves it
    (SCENE, "comicvine", ["comicvine", "metron"], True),          # equal rank leaves it
    (SCENE, "metron", ["comicvine", "metron"], True),             # CV outranks Metron
    (CLU_CV, "metron", ["metron", "comicvine"], False),
    (CLU_CV, "comicvine_sqlite", ["comicvine", "comicvine_sqlite"], True),  # same source
    (METRON, "comicvine", ["metron", "comicvine"], True),
    (METRON, "comicvine", ["comicvine", "metron"], False),        # CV outranks Metron: retag
    ("Metadata entered manually in CLU", "metron", ["metron"], True),
    ("Metadata from Grand Comic Database (GCD).", "metron", ["metron"], True),  # not in order
    ("hand written", "metron", ["metron"], True),                 # unrecognised
])
def test_should_skip_tagged(notes, provider, order, skip):
    assert should_skip_tagged(notes, provider, order) is skip
