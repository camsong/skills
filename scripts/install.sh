#!/usr/bin/env bash
# Install the skills in this repo into your agent's skill directory.
#
# Usage:
#   scripts/install.sh                      # symlink every skill into every detected target
#   scripts/install.sh --copy               # copy instead of symlink (no repo dependency)
#   scripts/install.sh --target ~/.claude/skills
#   scripts/install.sh youdao-wordbook      # install only the named skill(s)
#   scripts/install.sh --list               # show what would be installed, then exit
#
# Symlink is the default: `git pull` then updates every installed skill at once.
# Use --copy when you want a frozen snapshot you can edit in place.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$REPO/skills"

# Known agent skill directories. A target is used if it already exists, or if
# the user names it explicitly with --target.
CANDIDATE_TARGETS=(
  "$HOME/.claude/skills"   # Claude Code
  "$HOME/.agents/skills"   # Codex and other Agent Skills compatible harnesses
)

MODE="link"
LIST_ONLY=0
TARGETS=()
WANTED=()

while [ $# -gt 0 ]; do
  case "$1" in
    --copy)   MODE="copy"; shift ;;
    --link)   MODE="link"; shift ;;
    --list)   LIST_ONLY=1; shift ;;
    --target) TARGETS+=("${2:?--target needs a path}"); shift 2 ;;
    --target=*) TARGETS+=("${1#*=}"); shift ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "error: unknown option $1" >&2; exit 2 ;;
    *)  WANTED+=("$1"); shift ;;
  esac
done

# --- which skills -------------------------------------------------------
names=()
while IFS= read -r skill_md; do
  names+=("$(basename "$(dirname "$skill_md")")")
done < <(find "$SKILLS_DIR" -name SKILL.md | sort)

if [ ${#WANTED[@]} -gt 0 ]; then
  selected=()
  for want in "${WANTED[@]}"; do
    found=0
    for name in "${names[@]}"; do
      [ "$name" = "$want" ] && { selected+=("$name"); found=1; }
    done
    [ $found -eq 1 ] || { echo "error: no skill named '$want' (see --list)" >&2; exit 2; }
  done
  names=("${selected[@]}")
fi

if [ ${#names[@]} -eq 0 ]; then
  echo "error: no SKILL.md found under $SKILLS_DIR" >&2
  exit 1
fi

if [ $LIST_ONLY -eq 1 ]; then
  printf '%s\n' "${names[@]}"
  exit 0
fi

# --- where to put them --------------------------------------------------
if [ ${#TARGETS[@]} -eq 0 ]; then
  for candidate in "${CANDIDATE_TARGETS[@]}"; do
    [ -d "$candidate" ] && TARGETS+=("$candidate")
  done
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "error: no agent skill directory found." >&2
  echo "Looked for: ${CANDIDATE_TARGETS[*]}" >&2
  echo "Pass one explicitly, e.g. --target ~/.claude/skills" >&2
  exit 1
fi

# --- install ------------------------------------------------------------
for target in "${TARGETS[@]}"; do
  # A target that is itself a symlink into this repo would make us write the
  # per-skill links back into the working copy. Refuse rather than pollute it.
  if [ -L "$target" ]; then
    resolved="$(cd "$target" && pwd -P)"
    case "$resolved" in
      "$REPO"|"$REPO"/*)
        echo "error: $target resolves into this repo ($resolved); remove it and re-run" >&2
        exit 1 ;;
    esac
  fi

  mkdir -p "$target"

  for name in "${names[@]}"; do
    src="$SKILLS_DIR/$name"
    dest="$target/$name"

    if [ -e "$dest" ] || [ -L "$dest" ]; then
      rm -rf "$dest"
    fi

    if [ "$MODE" = "copy" ]; then
      cp -R "$src" "$dest"
      echo "copied  $name -> $dest"
    else
      ln -sfn "$src" "$dest"
      echo "linked  $name -> $dest"
    fi
  done
done
