"""Hide watchdog's harmless "Callback with id ... already exists for watch" warning.

A recursive inotify watch races itself whenever two nested folders appear at
once -- subscribing a series creates ``Series/`` and ``Series/v2018/`` in one
os.makedirs. Watching the new ``Series/`` already covers ``v2018/``, then the
separate "v2018 was created" event asks for the same watch again; watchdog
(7.x) skips the duplicate and emits a RuntimeWarning with a multi-kilobyte dump
of every watched folder. Nothing is lost and nothing is watched twice, so the
warning is filtered here, narrowly: only this message, only from watchdog's
inotify module. Any other watchdog warning still shows.

Imported for its side effect by core/file_watcher.py, the library watcher and
the one inotify user. monitor.py watches WATCH with the PollingObserver, which
never registers inotify watches and so cannot raise this.
"""

import warnings

DUPLICATE_WATCH_MESSAGE = r"Callback with id .* already exists for watch"


def install():
    warnings.filterwarnings(
        "ignore",
        message=DUPLICATE_WATCH_MESSAGE,
        category=RuntimeWarning,
        module=r"watchdog\.observers\.inotify",
    )


install()
