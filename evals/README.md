# evals

Scores `/check` and `/check-iterate` against small fixture diffs with planted
bugs, so a change to a skill or agent is kept because it measured no worse, not
because it read better.

```
python3 evals/run.py --self-test                                   # fixtures only, no model calls
python3 evals/run.py --skill check --ref main --ref WORKTREE        # A/B this checkout against main
python3 evals/run.py --skill check-iterate --cases off-by-one,clean-slugify --reps 1
```

`--ref` takes any git ref, or `WORKTREE` for the `.claude/` in this checkout,
uncommitted edits included. Results land in `evals/results/<skill>-<timestamp>/`
(gitignored): `summary.md`, `results.json`, and per run the transcript, the plan
file, and the graded record.

## How a run works

1. A fresh git repo per run: `base/` committed as `main` together with the
   `.claude/` from the ref under test, then `head/` committed on a branch. The
   skills are on `main`, so they never show in the diff being reviewed.
2. `claude -p "/check --auto"` (or `/check-iterate --max-loops 3`) in that repo,
   with `--setting-sources project` and this session's linked directories
   scrubbed from the environment, so the child sees only the ref's skills. Bash
   is allowed: the skills chain git commands that a prefix rule does not match,
   and each run has a throwaway repo to act in.
3. Grading:
   - **`/check`**: every finding bullet in the plan body is matched against the
     planted bugs by file and line (±3). A bug is *found* when any finding hits
     it. *Unmatched* counts findings that hit no planted bug. It undercounts,
     because line proximity is all it checks. On the clean cases, every finding
     is a false positive or a nit.
   - **`/check-iterate`**: the bug's probe has to pass afterwards (*fixed*), every
     guard probe has to still pass, and the fixture's own suite has to stay
     green.
   - Cost, wall time, turns, and top-level subagent spawns come from the
     transcript. A run that timed out, errored, or hit a permission denial is
     marked ⚠ instead of being scored as a quiet miss.

Run each configuration at least twice (`--reps 2` is the default). A
regression that shows in one run of two is still a regression.

## Fixtures

Each `fixtures/<case>/` holds `base/`, `head/`, `case.json`, and `probes/`.
Probes are standalone scripts, run from the repo root, that exit 0 on pass.
They stay outside the repo under review, so the reviewer never sees them.

| case | planted bug |
| --- | --- |
| `sql-injection` | prefix search interpolates input into SQL |
| `path-traversal` | read path joined without the guard the write path has |
| `secret-logged` | failed-login log line includes the password |
| `changed-default` | default unit changes; a caller outside the diff relied on the old one |
| `test-edited-to-match` | units change, test edited to match, caller outside the diff not updated |
| `swallowed-error` | bare `except` turns a documented error into silent defaults |
| `off-by-one` | 1-based pages, 0-based offset |
| `mutable-default` | mutable default argument leaks state between calls |
| `missing-none-guard` | dereferences a value documented as possibly `None` |
| `clean-truncate`, `clean-slugify` | none: measures false positives |

`case.json` locates each bug by a substring of its line (`contains`), not a
line number, so editing a fixture cannot leave the grader pointing at the wrong
line. A bug can list several acceptable locations, such as the changed
signature and the caller that did not adapt.

### Adding a case

1. `base/` and `head/` as full trees, with `tests/` that pass on each
   (`python3 -m unittest discover -s tests`). Standard library only.
2. A probe per bug that fails on `head` and passes once the bug is fixed, plus
   guard probes for behaviour any fix must keep.
3. `python3 evals/run.py --self-test`. It fails if a probe cannot detect its
   bug, a guard fails on `head`, a suite is red, or a `contains` string is not
   unique in its file.

Keep fixtures small and do not leave comments that point at the bug: a case
the reviewer can solve by grepping for a hint measures nothing.
