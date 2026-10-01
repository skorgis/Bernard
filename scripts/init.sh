#!/usr/bin/env bash
# Rename this template into a new project: updates pyproject.toml, ruff.toml,
# and the src/ package directory (plus any imports referencing it).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SRC_DIR="src"
PYPROJECT="pyproject.toml"
RUFF_TOML="ruff.toml"

mapfile -t pkg_dirs < <(find "$SRC_DIR" -mindepth 1 -maxdepth 1 -type d)
if [ "${#pkg_dirs[@]}" -ne 1 ]; then
    echo "Expected exactly one package directory under $SRC_DIR/, found ${#pkg_dirs[@]}." >&2
    exit 1
fi
old_pkg_path="${pkg_dirs[0]}"
old_pkg_name="$(basename "$old_pkg_path")"

read -rp "New project name (e.g. 'My Cool Project'): " project_name
if [ -z "$project_name" ]; then
    echo "Project name cannot be empty." >&2
    exit 1
fi
read -rp "Description (default: \"\"): " description
read -rp "Author name (default: \"\"): " author_name
read -rp "Author email (default: \"\"): " author_email

dist_name="$(echo "$project_name" | tr '[:upper:]' '[:lower:]' | tr -s ' _' '-' | tr -cd 'a-z0-9-')"
pkg_name="$(echo "$project_name" | tr '[:upper:]' '[:lower:]' | tr -s ' -' '_' | tr -cd 'a-z0-9_')"

if [ -z "$dist_name" ] || [ -z "$pkg_name" ]; then
    echo "Could not derive a valid name from '$project_name'." >&2
    exit 1
fi
if [[ "$pkg_name" =~ ^[0-9] ]]; then
    pkg_name="pkg_${pkg_name}"
fi

echo
echo "Project name:       $project_name"
echo "Distribution name:  $dist_name   (pyproject.toml [project].name)"
echo "Package name:       $pkg_name   (src/$pkg_name, import name)"
echo "Description:        $description"
echo "Author name:        $author_name"
echo "Author email:       $author_email"
echo
read -rp "Apply these changes? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo "==> Renaming $SRC_DIR/$old_pkg_name -> $SRC_DIR/$pkg_name"
if [ "$old_pkg_name" != "$pkg_name" ]; then
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git mv "$old_pkg_path" "$SRC_DIR/$pkg_name"
    else
        mv "$old_pkg_path" "$SRC_DIR/$pkg_name"
    fi
fi

echo "==> Updating $PYPROJECT"
sed -i \
    -e "s/^name = \".*\"/name = \"$dist_name\"/" \
    -e "s#packages = \\[\"src/$old_pkg_name\"\\]#packages = [\"src/$pkg_name\"]#" \
    "$PYPROJECT"

echo "==> Updating description and author in $PYPROJECT"
DESCRIPTION="$description" AUTHOR_NAME="$author_name" AUTHOR_EMAIL="$author_email" python3 - "$PYPROJECT" <<'PYEOF'
import os
import re
import sys


def escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


path = sys.argv[1]
text = open(path, encoding="utf-8").read()

description = escape(os.environ.get("DESCRIPTION", ""))
author_name = escape(os.environ.get("AUTHOR_NAME", ""))
author_email = escape(os.environ.get("AUTHOR_EMAIL", ""))

text = re.sub(
    r'^description = ".*"$',
    f'description = "{description}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
fields = []
if author_name:
    fields.append(f'name = "{author_name}"')
if author_email:
    fields.append(f'email = "{author_email}"')
author_entry = "{" + ",".join(fields) + "}" if fields else ""

text = re.sub(
    r"authors = \[\s*\{name = \"[^\"]*\"(?:,\s*email = \"[^\"]*\")?\}\s*\]",
    f"authors = [{author_entry}]" if author_entry else "authors = []",
    text,
    count=1,
)

open(path, "w", encoding="utf-8").write(text)
PYEOF

echo "==> Updating $RUFF_TOML"
sed -i "s/known-first-party = \\[\"$old_pkg_name\"\\]/known-first-party = [\"$pkg_name\"]/" "$RUFF_TOML"

echo "==> Updating references to '$old_pkg_name' in $SRC_DIR/ and tests/"
if [ "$old_pkg_name" != "$pkg_name" ]; then
    matches="$(grep -rl --include="*.py" -E "\\b${old_pkg_name}\\b" "$SRC_DIR" tests 2>/dev/null || true)"
    if [ -n "$matches" ]; then
        echo "$matches" | while read -r file; do
            sed -i "s/\\b${old_pkg_name}\\b/${pkg_name}/g" "$file"
        done
    fi
fi

echo
echo "Done. Review the changes (git status / git diff), then run:"
echo "  uv sync"
