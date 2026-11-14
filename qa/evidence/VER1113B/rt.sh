#!/bin/bash
# run pytest in rev worktree with rev DB
source /home/claude/v1113b/env.sh
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/qa_v1113b_rev
export TEST_DATABASE_URL=$DATABASE_URL
cd ${WT:-/home/claude/v1113b/rev} && pytest -q -p no:cacheprovider -rfxX "$@" 2>&1 | tail -${TAILN:-25}
