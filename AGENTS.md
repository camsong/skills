# Working on this repo

A collection of portable agent skills. Every skill here must run unchanged
under Claude Code, Codex, Cursor, and anything else that reads the Agent
Skills format.

## Layout

```
skills/<skill-name>/
  SKILL.md          required; frontmatter + instructions
  scripts/          executables the skill calls
  references/       long docs the skill reads on demand
  agents/           optional per-harness metadata (e.g. openai.yaml)
scripts/            repo tooling (install, list)
.claude-plugin/     Claude Code plugin + marketplace manifests
```

## SKILL.md rules

- Frontmatter has exactly two required keys, `name` and `description`.
  `name` must equal the directory name, lowercase with hyphens.
- `description` is the whole routing signal: say what the skill does **and**
  when to reach for it, including the phrases a user would actually type.
  Name what it is *not* for when a neighbouring skill overlaps.
- Keep SKILL.md under roughly 500 lines. Anything longer moves into
  `references/` and gets linked, so it is read only when needed.
- Write instructions for an agent, not a reader: imperative, concrete,
  with the exact commands to run.

## Portability rules

These are the ones that break silently, so check them on every change.

1. **No hardcoded harness paths.** Never write
   `~/.claude/skills/<name>/script.sh`. Refer to "this skill's directory",
   which every harness injects, and have scripts resolve their own location
   with `$(dirname "${BASH_SOURCE[0]}")`.
2. **Cross-skill references resolve relatively first.** A skill that calls a
   sibling skill looks for `../<sibling>` next to itself before falling back
   to the known harness directories.
3. **No absolute paths to a home directory.** Use `$HOME` or accept a path
   argument.
4. **Scripts declare their own dependencies.** Python scripts either use only
   the standard library or carry a PEP 723 header and run through `uv`. No
   repo-level install step, no venv to create.
5. **Scripts are executable** (`chmod +x`) and print errors to stderr with a
   documented exit code.

## Privacy rules

This repo is public. Nothing personal goes in, ever.

- No credentials, cookies, tokens, or API keys, in any file, including
  examples. Example values are obviously fake (`DICT_SESS=...`).
- No exported personal data: wordbook contents, transcripts, notes.
- No real names, emails, employer names, or absolute paths containing a
  username.
- Skills that touch credentials cache them **outside** the repo working tree
  or under a path covered by `.gitignore`, written `0600`.

Before committing, run:

```bash
git diff --cached | grep -niE 'DICT_SESS=[A-Za-z0-9]|/Users/|@gmail|@[a-z]+\.(com|cn)' 
```

and confirm every hit is a placeholder.

## Adding a skill

1. Create `skills/<name>/SKILL.md`.
2. Add it to the `skills` array in `.claude-plugin/plugin.json`.
3. Add a row to the table in `README.md`.
4. `scripts/install.sh --list` should show it.
