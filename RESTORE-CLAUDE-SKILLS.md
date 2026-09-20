# Restore `.claude/skills`

The `.claude/skills` directory is currently in Windows "pending delete"
state — the running Claude Code session holds an open handle to it, so it
cannot be recreated until that session exits.

The files are safe in git. After closing this Claude Code session, run:

```powershell
cd D:\Projects\Netmonitor
git checkout c037f68 -- .claude
git status --short          # should be clean
```

That restores all four files:

```
.claude/skills/caveman.skill
.claude/skills/caveman/SKILL.md
.claude/skills/test-driven development/SKILL.md
.claude/skills/test-driven development/writing-good-tests.md
```

Then delete this file.

## Why they went missing

An early version of `src/netwatch/uninstall.py` resolved its target
directory with `Path(os.environ.get("NETWATCH_DATA_DIR") or "")` and then
tested that `Path` for truthiness. `Path("")` is `Path(".")`, which is
truthy, so with the variable unset it resolved to the working directory and
began deleting the project. It stopped on a permission error inside `.venv`.

Everything committed was recovered from git. `uninstall.py` now refuses any
target that is not an absolute path named `NetWatch` containing only known
app-data entries, re-checked immediately before the delete, and
`tests/test_uninstall.py` pins each of those conditions.
