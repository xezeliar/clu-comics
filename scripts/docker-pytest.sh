#!/bin/sh
# Run pytest inside the CLU image the way upstream CI does (used by `make test`).
#
# As a normal user, not root: root ignores read-only file modes, which one test
# relies on. And with no /data folder: the image ships an empty /data, which
# makes CLU add a default library the tests do not expect.
#
# The repo is mounted at /work. Dependencies are installed first, so a merge
# that added a package still runs against an image built before it.
set -eu

mkdir -p /tmp/cfg && chmod 777 /tmp/cfg
pip install -q -r requirements.txt -r requirements-test.txt 2>&1 | tail -n 1
rmdir /data 2>/dev/null || true
HOME=/tmp PYTHONDONTWRITEBYTECODE=1 exec gosu 1000:1000 python -m pytest -q -p no:cacheprovider "$@"
