#!/usr/bin/env bash
# Move the Linux apx host to one exact commit of main. bootstrap.sh runs this when APX_SHA is set; it can also run alone (as root):
#   sudo APX_SHA=<full sha> bash deploy/linux/release.sh            # then re-run bootstrap.sh so the rules are rendered from the new release
#   DRY_RUN=1 APX_SHA=<full sha> bash deploy/linux/release.sh       # prints the steps, changes nothing
# In order, stopping at the first refusal, and touching `current` only in the last step:
#   1. fetch main into the bootstrap clone ($SHARED/autopilot) and refuse a sha that is not on origin/main (code only comes from main);
#      move that clone's main and HEAD to it, so the updater clone, which fetches from it, can see the commit
#   2. fetch it into the updater clone ($SHARED/updater, made if missing) and check it is on main there too
#   3. build $SHARED/releases/<sha> in a staging dir and rename it into place, or reuse an existing one; either way refuse unless its
#      HEAD is the sha and its tree is clean. A wrong existing dir is reported, never repaired or removed.
#   4. check the updater out at the sha
#   5. switch `current` atomically (a temp link, then mv -T) only to a release that exists and verified; record the old target as
#      `previous` and print the one-command rollback
# Every git and link step runs as APX_USER (default apx), which owns the shared tree. Knobs: APX_SHA (required), SHARED, APX_USER, DRY_RUN.
set -euo pipefail

SHARED="${SHARED:-/srv/apx}"
WANT_SHA="${APX_SHA:-}"
APX_USER="${APX_USER:-apx}"
DRY_RUN="${DRY_RUN:-0}"
CLONE="$SHARED/autopilot"
UPDATER="$SHARED/updater"
MAIN=refs/remotes/origin/main
FETCH=(fetch -q origin "+refs/heads/main:$MAIN")

say() { printf '%s\n' "$*"; }
die() { say "REFUSED: $*"; exit 1; }
as_apx() {
  if [ "$(id -un)" = "$APX_USER" ]; then "$@"; return; fi
  setpriv --reuid="$(id -u "$APX_USER")" --regid="$(id -g "$APX_USER")" --init-groups \
    env HOME="$(getent passwd "$APX_USER" | cut -d: -f6)" "$@"
}

[[ "$WANT_SHA" =~ ^[0-9a-f]{40}$ ]] || die "APX_SHA must be a full 40-character lowercase commit id"
TARGET="releases/$WANT_SHA"

if [ "$DRY_RUN" = 1 ]; then
  for s in "git -C $CLONE ${FETCH[*]}" "git -C $CLONE merge-base --is-ancestor $WANT_SHA $MAIN (refuse if not)" \
    "git -C $CLONE checkout -q --detach $WANT_SHA; git -C $CLONE branch -f main $MAIN" \
    "git -C $UPDATER ${FETCH[*]} (clone it from $CLONE if missing); the same merge-base check" \
    "build $SHARED/$TARGET in a staging dir unless it exists; refuse unless rev-parse HEAD = $WANT_SHA and the tree is clean" \
    "git -C $UPDATER checkout -q --detach $WANT_SHA" \
    "ln -sfn $TARGET $SHARED/.current.new; mv -T $SHARED/.current.new $SHARED/current; record the old target as $SHARED/previous"; do
    say "DRY-RUN (as $APX_USER): $s"
  done
  exit 0
fi

[ -d "$CLONE/.git" ] || die "$CLONE is not a git clone (run bootstrap.sh first)"
if [ -e "$SHARED/current" ] && ! [ -L "$SHARED/current" ]; then die "$SHARED/current exists but is not a symlink; move it aside by hand"; fi

on_main() { as_apx git -C "$1" merge-base --is-ancestor "$WANT_SHA" "$MAIN" 2>/dev/null || die "$WANT_SHA is not on origin/main in $1; nothing changed"; }

# 1. the bootstrap clone
as_apx git -C "$CLONE" "${FETCH[@]}"
on_main "$CLONE"
as_apx git -C "$CLONE" checkout -q --detach "$WANT_SHA"
as_apx git -C "$CLONE" branch -f main "$MAIN"

# 2. the updater clone
if [ -d "$UPDATER/.git" ]; then as_apx git -C "$UPDATER" "${FETCH[@]}"; else as_apx git clone -q --no-hardlinks "$CLONE" "$UPDATER"; fi
on_main "$UPDATER"

# 3. the release, built aside and renamed into place, then verified whatever its origin
verify() { # dir
  [ -d "$1/.git" ] || die "$1 is not a git checkout; current untouched. Move it aside and run again"
  local head
  head="$(as_apx git -C "$1" rev-parse HEAD 2>/dev/null || true)"
  [ "$head" = "$WANT_SHA" ] || die "$1 has HEAD ${head:-unreadable}, not $WANT_SHA; current untouched. Move it aside and run again"
  [ -z "$(as_apx git -C "$1" status --porcelain --untracked-files=no)" ] || die "$1 has local changes; current untouched"
}
stage=""
cleanup() { if [ -n "$stage" ] && [ -d "$stage" ]; then as_apx rm -rf -- "$stage"; fi; as_apx rm -f -- "$SHARED/.current.new" "$SHARED/.previous.new"; }
trap cleanup EXIT
as_apx mkdir -p "$SHARED/releases"
if ! [ -e "$SHARED/$TARGET" ]; then
  stage="$SHARED/releases/.stage-$WANT_SHA.$$"
  as_apx git clone -q --no-hardlinks "$CLONE" "$stage"
  as_apx git -C "$stage" checkout -q --detach "$WANT_SHA"
  verify "$stage"
  as_apx mv -T "$stage" "$SHARED/$TARGET"
  stage=""
fi
verify "$SHARED/$TARGET"
# the sandbox accounts read this code but must never write it, whatever umask apx has
as_apx chmod -R go-w,go+rX "$SHARED/$TARGET"
say "release: $SHARED/$TARGET verified at $WANT_SHA"

# 4. the updater
as_apx git -C "$UPDATER" checkout -q --detach "$WANT_SHA"
as_apx chmod -R go-w,go+rX "$UPDATER"

# 5. the switch
old=""
[ -L "$SHARED/current" ] && old="$(readlink "$SHARED/current")"
if [ "$old" = "$TARGET" ]; then
  say "current already points at $TARGET; left as it is"
  exit 0
fi
relink() { # target name: replace $SHARED/name with a link to target in one rename
  as_apx ln -sfn "$1" "$SHARED/.$2.new"
  as_apx mv -T "$SHARED/.$2.new" "$SHARED/$2"
}
relink "$TARGET" current
if ! [ -d "$SHARED/current/" ]; then # cannot happen after the checks above; if it does, put the old link back
  if [ -n "$old" ]; then relink "$old" current; fi
  die "current did not resolve after the switch; restored ${old:-nothing}"
fi
say "current: $TARGET (was ${old:-unset})"
case "$old" in /*) old_dir="$old" ;; *) old_dir="$SHARED/$old" ;; esac
if [ -n "$old" ] && [ -d "$old_dir/" ]; then
  relink "$old" previous
  say "previous: $old"
  say "rollback, one command (the old sha is on main too; this also re-renders the rules from it):"
  say "  sudo APX_SHA=${old##*/} ADMIN_USER=<you> bash deploy/linux/bootstrap.sh"
  say "or, links only:  sudo -u $APX_USER sh -c 'ln -sfn $old $SHARED/.current.new && mv -T $SHARED/.current.new $SHARED/current'"
elif [ -n "$old" ]; then
  say "the old target $old did not exist, so there is no rollback target"
fi
