"""Undo toast after a delete. Asserts on the assets as text (no JS runner here)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_toast_supports_an_action():
    js = read("static", "js", "clu-toast.js")
    assert "opts.action" in js and "clu-toast-action" in js


def test_delete_offers_undo_by_trash_name():
    js = read("static", "js", "clu-delete.js")
    assert "CLU.offerUndoDelete" in js and "/api/trash/restore" in js
