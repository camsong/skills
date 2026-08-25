#!/usr/bin/env bash
# Print every skill in the repo as "name<TAB>description" (from SKILL.md frontmatter).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find "$REPO/skills" -name SKILL.md | sort | while IFS= read -r skill_md; do
  name=$(basename "$(dirname "$skill_md")")
  # Frontmatter description may wrap; take everything up to the next key or the
  # closing ---, then squeeze whitespace onto one line.
  desc=$(awk '
    /^---$/ { fm++; if (fm == 2) exit; next }
    fm == 1 && /^description:/ { sub(/^description:[[:space:]]*/, ""); grab = 1; print; next }
    fm == 1 && grab && /^[a-zA-Z_-]+:/ { grab = 0 }
    fm == 1 && grab { print }
  ' "$skill_md" | tr '\n' ' ' | sed 's/  */ /g; s/^ //; s/ $//')
  printf '%s\t%s\n' "$name" "$desc"
done
