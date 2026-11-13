"""Apply one named mutation (exact string replacement, must match exactly `count` times) to a worktree.
usage: python3 -I mutate.py <worktree> <spec.json> <name>"""
import json, sys, os
wt, spec, name = sys.argv[1:4]
m = json.load(open(spec))[name]
for path, old, new, *rest in m["edits"]:
    n = rest[0] if rest else 1
    p = os.path.join(wt, path)
    s = open(p, encoding="utf-8").read()
    c = s.count(old)
    if c != n:
        sys.exit(f"MUTATION-ERROR {name}: {path} expected {n} match(es), found {c}: {old!r}")
    open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("applied", name)
