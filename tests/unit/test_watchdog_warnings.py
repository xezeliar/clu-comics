"""core/watchdog_warnings.py hides one harmless watchdog warning, and only that one."""
import pathlib
import warnings

from core import watchdog_warnings

ROOT = pathlib.Path(__file__).resolve().parents[2]

DUPLICATE = ("Callback with id '133161626168896' already exists for watch "
             "<bound method Watch.short_str of Watch(wd=95, ...)>")


def _emit(message, module="watchdog.observers.inotify", category=RuntimeWarning):
    warnings.warn_explicit(message, category, "inotify.py", 365, module=module)


def _shown(message, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        watchdog_warnings.install()
        _emit(message, **kwargs)
    return [str(w.message) for w in caught]


def test_duplicate_watch_warning_is_hidden():
    assert _shown(DUPLICATE) == []


def test_other_watchdog_warnings_still_show():
    assert _shown("inotify watch limit reached") == ["inotify watch limit reached"]


def test_the_same_text_from_elsewhere_still_shows():
    assert _shown(DUPLICATE, module="core.something") == [DUPLICATE]


def test_only_runtime_warnings_are_filtered():
    assert _shown(DUPLICATE, category=UserWarning) == [DUPLICATE]


def test_the_library_watcher_installs_it():
    src = (ROOT / "core" / "file_watcher.py").read_text(encoding="utf-8")
    assert "import core.watchdog_warnings" in src
