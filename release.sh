#!/usr/bin/env bash
# release.sh — tag a release and trigger the GitHub CI package build.
#
# What it does, in one command:
#   1. validates the version and that the tag doesn't already exist,
#   2. bumps `version` in pyproject.toml and commits it (unless --no-bump),
#   3. pushes the current branch to the remote,
#   4. creates an annotated tag v<version> and pushes it.
#
# Pushing the tag triggers .github/workflows/release-packages.yml, which builds
# the deb/rpm/archlinux packages + Python sdist and publishes a GitHub Release.
# A pre-release version (e.g. 1.5.0-rc1) is published as a GitHub *prerelease*.
#
# Usage:
#   ./release.sh <version> [options]
#
#   <version>            e.g. 1.5.0  or  v1.5.0  or  1.5.0-rc1
#
# Options:
#   --remote <name>      git remote to push to (default: origin)
#   --no-bump            don't touch pyproject.toml (tag the current commit as-is)
#   --allow-dirty        don't refuse to release with uncommitted changes
#   -m, --message <msg>  annotated-tag message (default: "Release v<version>")
#   --watch              after pushing, follow the CI run (requires gh)
#   -n, --dry-run        print what would happen, make no changes
#   -h, --help           show this help
#
# Requires: git. (--watch additionally needs the GitHub CLI `gh`, authenticated.)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REMOTE="origin"
ALLOW_DIRTY=0
BUMP=1
WATCH=0
DRY_RUN=0
TAG_MSG=""
VERSION_ARG=""
PYPROJECT="$SCRIPT_DIR/pyproject.toml"

usage() { sed -n '2,42p' "$0" | sed 's/^# \{0,1\}//'; }

# ── argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)        REMOTE="${2:?--remote needs a value}"; shift 2 ;;
    --no-bump)       BUMP=0; shift ;;
    --allow-dirty)   ALLOW_DIRTY=1; shift ;;
    -m|--message)    TAG_MSG="${2:?--message needs a value}"; shift 2 ;;
    --watch)         WATCH=1; shift ;;
    -n|--dry-run)    DRY_RUN=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    -*)              echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -n "$VERSION_ARG" ]]; then
        echo "Unexpected extra argument: $1" >&2; exit 2
      fi
      VERSION_ARG="$1"; shift ;;
  esac
done

err() { echo "error: $*" >&2; exit 1; }
run() { if [[ "$DRY_RUN" == 1 ]]; then echo "DRY-RUN: $*"; else "$@"; fi; }

[[ -n "$VERSION_ARG" ]] || { echo "error: <version> is required" >&2; usage; exit 2; }

# Normalize: accept "1.5.0" or "v1.5.0"; tag is always v-prefixed.
VERSION="${VERSION_ARG#v}"
TAG="v${VERSION}"

# Validate SemVer-ish (X.Y.Z with optional -prerelease and +build metadata).
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  err "version '$VERSION' is not SemVer-like (expected e.g. 1.5.0 or 1.5.0-rc1)"
fi

# Must be inside the repo.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || err "not a git repository"

# Remote must exist.
git remote get-url "$REMOTE" >/dev/null 2>&1 || err "remote '$REMOTE' not found"

# Refuse a dirty tree unless explicitly allowed.
if [[ "$ALLOW_DIRTY" != 1 ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    err "working tree has uncommitted changes (commit them or pass --allow-dirty)"
  fi
fi

# Tag must not already exist locally or on the remote.
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  err "tag $TAG already exists locally"
fi
if [[ "$DRY_RUN" != 1 ]]; then
  if git ls-remote --tags "$REMOTE" "refs/tags/$TAG" | grep -q "$TAG"; then
    err "tag $TAG already exists on remote '$REMOTE'"
  fi
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ -n "$TAG_MSG" ]] || TAG_MSG="Release $TAG"

echo "▶ Releasing $TAG"
echo "  branch : $BRANCH"
echo "  remote : $REMOTE"
echo "  commit : $(git rev-parse --short HEAD)"
[[ "$VERSION" == *-* ]] && echo "  note   : pre-release suffix → will publish as a GitHub prerelease"

# Bump pyproject.toml's version and commit it so the tagged commit records the
# released version (CI also overwrites it during the build, but this keeps the
# repository's committed state in sync). The inline comment is preserved.
if [[ "$BUMP" == 1 ]]; then
  [[ -f "$PYPROJECT" ]] || err "pyproject.toml not found at $PYPROJECT"
  CUR_VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]*)".*/\1/p' "$PYPROJECT" | head -n1)"
  if [[ "$CUR_VERSION" == "$VERSION" ]]; then
    echo "  bump   : pyproject.toml already at $VERSION (nothing to commit)"
  else
    echo "  bump   : pyproject.toml $CUR_VERSION → $VERSION"
    if [[ "$DRY_RUN" == 1 ]]; then
      echo "DRY-RUN: update version in pyproject.toml and commit"
    else
      sed -i -E "s|^(version[[:space:]]*=[[:space:]]*)\"[^\"]*\"|\1\"$VERSION\"|" "$PYPROJECT"
      git add "$PYPROJECT"
      git commit -m "chore(release): $TAG" -- "$PYPROJECT"
    fi
  fi
fi

# Push branch first so the tagged commit is reachable on the remote.
run git push "$REMOTE" "$BRANCH"

# Create + push the annotated tag → triggers the Release packages workflow.
run git tag -a "$TAG" -m "$TAG_MSG"
run git push "$REMOTE" "$TAG"

echo "✅ Pushed $TAG. GitHub CI 'Release packages' will build & publish it."

if [[ "$WATCH" == 1 ]]; then
  if command -v gh >/dev/null 2>&1; then
    echo "⏳ Waiting for the workflow run to appear…"
    # Give GitHub a moment to register the workflow run for the new tag.
    sleep 5
    RUN_ID="$(gh run list --workflow release-packages.yml --limit 1 \
      --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
    if [[ -n "${RUN_ID:-}" ]]; then
      gh run watch "$RUN_ID" --exit-status || true
    else
      echo "  (could not locate the run; check: gh run list --workflow release-packages.yml)"
    fi
  else
    echo "  --watch requested but 'gh' is not installed; skipping."
  fi
fi

if command -v gh >/dev/null 2>&1; then
  echo "ℹ View runs:  gh run list --workflow release-packages.yml"
fi
