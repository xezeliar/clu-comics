#!/bin/sh
# Merge the author's latest main (the "upstream" remote) into develop.
#
#   make sync-upstream            fetch + merge into develop
#   make sync-upstream test       ...then run the test suite
#
# Stops without touching anything when the tree has uncommitted changes or a
# merge is already in progress. On conflicts it leaves the merge open and
# lists the files, so you can fix them or run `git merge --abort`.
# It never pushes.
set -eu

BRANCH="${BRANCH:-develop}"
REMOTE="${UPSTREAM:-upstream}"

cd "$(git rev-parse --show-toplevel)"

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "No '$REMOTE' remote. Add it with:"
    echo "  git remote add upstream https://github.com/allaboutduncan/clu-comics"
    exit 1
fi

if [ -e "$(git rev-parse --git-dir)/MERGE_HEAD" ]; then
    echo "A merge is already in progress. Finish it (git commit) or undo it (git merge --abort) first."
    exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "You have uncommitted changes:"
    git status --short --untracked-files=no
    echo "Commit or stash them first."
    exit 1
fi

current="$(git branch --show-current)"
if [ "$current" != "$BRANCH" ]; then
    echo "Switching from $current to $BRANCH."
    git checkout -q "$BRANCH"
fi

echo "Fetching $REMOTE..."
git fetch -q "$REMOTE"

incoming="$(git rev-list --count "HEAD..$REMOTE/main")"
if [ "$incoming" -eq 0 ]; then
    echo "$BRANCH already has everything from $REMOTE/main."
    exit 0
fi

echo "$incoming new commit(s) from $REMOTE/main:"
git log --oneline --no-decorate "HEAD..$REMOTE/main" | head -n 20
if [ "$incoming" -gt 20 ]; then
    echo "  ... and $((incoming - 20)) more"
fi
echo

upstream_version() {
    sed -n 's/^__version__ = "\(.*\)"$/\1/p' core/version.py | head -n 1
}
old_version="$(upstream_version)"

if git merge --no-edit "$REMOTE/main"; then
    echo
    echo "Merged $REMOTE/main into $BRANCH."
    new_version="$(upstream_version)"
    if [ "$new_version" != "$old_version" ]; then
        echo "Upstream version: $old_version -> $new_version"
    fi
    echo "Next: make test, then make up (and push $BRANCH when you're happy)."
else
    echo
    echo "The merge stopped on conflicts in:"
    git diff --name-only --diff-filter=U | sed 's/^/  /'
    echo
    echo "Fix those files, then:  git add <files>  and  git commit"
    echo "Or undo the merge:      git merge --abort"
    exit 1
fi
