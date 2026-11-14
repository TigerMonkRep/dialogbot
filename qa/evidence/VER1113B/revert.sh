#!/bin/bash
# usage: revert.sh "<diffspec>" <pathspec...>   diffspec e.g. "A^ A" or "M^1 M"
set -u
R=/home/claude/v1113b/rev
cd $R && git checkout -q -f 39a886fe84d12ad261fd1afb27a9aa52e2df431e && git clean -qfd
spec=$1; shift
git diff $spec -- "$@" > /tmp/v1113b-rev.patch
echo "patch lines: $(wc -l < /tmp/v1113b-rev.patch)"
git apply -R -3 /tmp/v1113b-rev.patch 2>&1 | tail -5
git status --short | head -30
