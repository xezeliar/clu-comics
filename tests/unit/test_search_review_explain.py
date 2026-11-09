"""explain_decision / is_borderline (models/getcomics.py) and the sweep wiring."""

import ast
import os

from models.getcomics import (
    ACCEPT_THRESHOLD, BORDERLINE_MARGIN, ComicScore, explain_decision, is_borderline,
)

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app.py")


def test_accept_names_the_issue():
    cs = ComicScore(score=80, series_match=True, issue_matched=True)
    assert explain_decision(cs, "ACCEPT", "5") == "series matches and issue #5 is named"


def test_arc_page_rejected():
    cs = ComicScore(score=45, series_match=True, sub_series_type="arc")
    assert explain_decision(cs, "REJECT", "5") == "arc page, not this series"


def test_never_names_issue():
    cs = ComicScore(score=20, series_match=True)
    assert explain_decision(cs, "REJECT", "5") == "never names issue #5"


def test_range_pack_rejected_when_single_found():
    cs = ComicScore(score=39, series_match=True, range_contains_target=True)
    assert explain_decision(cs, "REJECT", "5") == "range pack, better single issue found"


def test_fallback_and_different_series():
    cs = ComicScore(score=39, series_match=True, range_contains_target=True)
    assert "range pack containing #5" in explain_decision(cs, "FALLBACK", "5")
    assert explain_decision(ComicScore(), "REJECT", "5") == "different series"


def test_partial_object_does_not_raise():
    assert explain_decision(object(), "REJECT", "1") == "different series"


def test_borderline():
    assert is_borderline("FALLBACK", 99)
    assert is_borderline("ACCEPT", ACCEPT_THRESHOLD)
    assert not is_borderline("ACCEPT", ACCEPT_THRESHOLD + BORDERLINE_MARGIN)


def _func():
    tree = ast.parse(open(APP, encoding="utf-8").read())
    return next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "scheduled_getcomics_download")


def test_sweep_wiring():
    src = ast.get_source_segment(open(APP, encoding="utf-8").read(), _func())
    # hold is never applied to a scoped run
    assert 'get_bool("REVIEW_BEFORE_DOWNLOAD") and only_series_id is None' in src
    assert "is_borderline(" in src and "explain_decision(" in src
    assert src.count("return_detail=True") == 2
    assert "record_search_attempt(" in src
    # a held pick must not reach the fallback sources or the queue
    assert 'attempt_outcome != "waiting"' in src
    hold = src.index('attempt_outcome = "waiting"')
    assert hold < src.index("download_queue.put(task)")
    # per-item logging stays DEBUG
    assert "Held {series_name}" in src
    held = src[src.rindex("app_logger.", 0, src.index("Held {series_name}")):src.index("Held {series_name}")]
    assert held.startswith("app_logger.debug")
