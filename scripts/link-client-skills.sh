#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/link-client-skills.sh [options]

Symlink client skills from clients/**/skills/<skill-name> into .agents/skills.

Options:
  --target DIR   Target skills directory. Defaults to .agents/skills.
  --force        Replace existing symlinks that point somewhere else.
  --dry-run      Print actions without changing the filesystem.
  -h, --help     Show this help text.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
clients_dir="$repo_root/clients"
target_dir="$repo_root/.agents/skills"
force=0
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      if [[ $# -lt 2 ]]; then
        echo "error: --target requires a directory" >&2
        exit 2
      fi
      target_dir="$2"
      if [[ "$target_dir" != /* ]]; then
        target_dir="$repo_root/$target_dir"
      fi
      shift 2
      ;;
    --force)
      force=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$clients_dir" ]]; then
  echo "error: clients directory not found: $clients_dir" >&2
  exit 1
fi

run() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'dry-run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

relative_path() {
  python3 - "$1" "$2" <<'PY'
import os
import sys

print(os.path.relpath(sys.argv[1], start=sys.argv[2]))
PY
}

if [[ "$dry_run" -eq 1 ]]; then
  echo "dry-run: mkdir -p $(printf '%q' "$target_dir")"
else
  mkdir -p "$target_dir"
fi

linked=0
skipped=0
conflicts=0

while IFS= read -r skills_dir; do
  while IFS= read -r skill_dir; do
    skill_name="$(basename "$skill_dir")"
    link_path="$target_dir/$skill_name"
    link_target="$(relative_path "$skill_dir" "$target_dir")"

    if [[ -L "$link_path" ]]; then
      existing_target="$(readlink "$link_path")"
      if [[ "$existing_target" == "$link_target" ]]; then
        echo "skip: $link_path already points to $link_target"
        skipped=$((skipped + 1))
        continue
      fi

      if [[ "$force" -eq 1 ]]; then
        run rm "$link_path"
      else
        echo "conflict: $link_path points to $existing_target; use --force to replace it" >&2
        conflicts=$((conflicts + 1))
        continue
      fi
    elif [[ -e "$link_path" ]]; then
      echo "conflict: $link_path already exists and is not a symlink" >&2
      conflicts=$((conflicts + 1))
      continue
    fi

    run ln -s "$link_target" "$link_path"
    echo "linked: $link_path -> $link_target"
    linked=$((linked + 1))
  done < <(find "$skills_dir" -mindepth 1 -maxdepth 1 -type d -print | sort)
done < <(find "$clients_dir" -type d -name skills -print | sort)

echo "done: linked=$linked skipped=$skipped conflicts=$conflicts target=$target_dir"

if [[ "$conflicts" -gt 0 ]]; then
  exit 1
fi
