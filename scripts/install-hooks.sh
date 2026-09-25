#!/usr/bin/env bash
# Install SkillGraph git hooks into .git/hooks/.
#
# Idempotent: re-running is safe.
# Use after cloning the repo or whenever hooks/pre-commit changes.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SOURCE_DIR="$REPO_ROOT/scripts/hooks"

for hook in "$SOURCE_DIR"/*; do
    name="$(basename "$hook")"
    target="$HOOKS_DIR/$name"
    cp "$hook" "$target"
    chmod +x "$target"
    echo "Installed: $target"
done

echo ""
echo "Git hooks installed. To verify:"
echo "  ls -la $HOOKS_DIR/pre-commit"
echo ""
echo "Bypass for emergency: git commit --no-verify"
echo "Bypass tests only (doc-only commits): HOOK_SKIP_TESTS=1 git commit"
