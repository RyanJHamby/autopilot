#!/usr/bin/env bash
# Emergency egress lockdown for the apx accounts. bootstrap.sh installs this as /usr/local/sbin/apx-lockdown (root:root 755), so in an
# incident you run the root-owned copy, never one under /srv/apx (which the apx account owns):
#   sudo apx-lockdown on        # cut ALL outbound traffic (IPv4 and IPv6, loopback included, open connections too) for the four accounts
#   sudo apx-lockdown off       # back to the normal allowlist
#   sudo apx-lockdown status    # on, off, or INCONSISTENT; exits 1 unless the flag and the live set agree
# It changes exactly two things: the members of the `lockdown` set in table inet apx (nft add element / flush set), and the flag file
# APX_LOCKDOWN_DIR/lockdown.nft that the rendered rules include, so a reload of apx-nft re-applies it. It never deletes, flushes or reloads
# the table, and it never touches any other account: it refuses uid 0 and the admin who ran it, and the table only matches local output
# from these uids, so inbound SSH and everyone else's traffic are unaffected. It does not stop apx: pair it with
#   sudo systemctl disable --now apx.timer apx-updater.timer
# APX_LOCKDOWN_DIR, APX_LOCKDOWN_ACCOUNTS and APX_NFT_FILE exist for the tests; on the host leave them unset.
set -euo pipefail

DIR="${APX_LOCKDOWN_DIR:-/etc/apx-lockdown}"
ACCOUNTS="${APX_LOCKDOWN_ACCOUNTS:-apx apx-ci apx-agent apx-dns}"
NFT_FILE="${APX_NFT_FILE:-/etc/apx/apx.nft}"
FLAG="$DIR/lockdown.nft"

say() { printf '%s\n' "$*"; }
die() { say "apx-lockdown: $*" >&2; exit 1; }
usage() { say "usage: apx-lockdown on|off|status"; exit 2; }

[ $# = 1 ] || usage
case "$1" in on | off | status) ;; *) usage ;; esac
[ "$(id -u)" != 0 ] && die "run as root (sudo apx-lockdown $1)"
command -v nft >/dev/null 2>&1 || die "nft not found"

admin_uid=""
[ -z "${SUDO_USER:-}" ] || admin_uid="$(id -u "$SUDO_USER" 2>/dev/null || true)"

uids() { # the numeric uids of ACCOUNTS, comma separated; refuses root and the admin, warns about a missing account
  local out="" a uid
  for a in $ACCOUNTS; do
    if ! uid="$(id -u "$a" 2>/dev/null)"; then say "warning: no account $a here; skipping it" >&2; continue; fi
    if [ "$uid" = 0 ] || [ "$uid" = "$admin_uid" ]; then die "refusing to lock $a (uid $uid): that is root or the admin running this"; fi
    out="${out:+$out, }$uid"
  done
  [ -n "$out" ] || die "none of the accounts ($ACCOUNTS) exist; nothing to lock"
  printf '%s' "$out"
}

has_set() { nft list set inet apx lockdown >/dev/null 2>&1; }
live() { # current members of the live set, comma separated (empty when off)
  nft list set inet apx lockdown 2>/dev/null | tr -d '\n\t' | sed -n 's/.*elements = { \([^}]*\) }.*/\1/p'
}
check_include() {
  if [ -f "$NFT_FILE" ] && ! grep -qF "include \"$DIR/*.nft\"" "$NFT_FILE"; then
    say "warning: $NFT_FILE does not include $DIR, so a reload of apx-nft would drop the lockdown; re-run bootstrap.sh"
  fi
}

cmd_on() {
  local list tmp
  list="$(uids)"
  install -d -m 700 -o root -g root "$DIR"
  chmod 700 "$DIR"
  tmp="$(mktemp "$DIR/.lockdown.XXXXXX")"
  printf '# written by apx-lockdown on %s; remove with: apx-lockdown off\nadd element inet apx lockdown { %s }\n' "$(date -u +%FT%TZ)" "$list" >"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$FLAG"
  say "flag written: $FLAG (a reload or restart of apx-nft keeps the lockdown)"
  if ! has_set; then
    say "LIVE CHANGE NOT MADE: table inet apx has no lockdown set (not loaded, or rules from before the lockdown)."
    say "Run: systemctl restart apx-nft   (it loads the rules with the flag), or re-run bootstrap.sh if the rules are old."
    exit 1
  fi
  nft add element inet apx lockdown "{ $list }"
  check_include
  say "lockdown: on for uids { $(live) }. Their packets are dropped, open connections included."
  say "apx itself keeps running until you also run: systemctl disable --now apx.timer apx-updater.timer"
}

cmd_off() {
  rm -f "$FLAG"
  say "flag removed: $FLAG"
  has_set || die "table inet apx has no lockdown set; nothing live to undo"
  nft flush set inet apx lockdown
  say "lockdown: off (the normal allowlist applies again). Check it with: bash deploy/linux/egress-probe.sh"
}

cmd_status() {
  local members flag=0
  [ -f "$FLAG" ] && flag=1
  has_set || { say "lockdown: INCONSISTENT (table inet apx or its lockdown set is not loaded; flag present: $flag)"; exit 1; }
  members="$(live)"
  check_include
  if [ "$flag" = 1 ] && [ -n "$members" ]; then say "lockdown: on (flag $FLAG, live uids { $members })"
  elif [ "$flag" = 0 ] && [ -z "$members" ]; then say "lockdown: off"
  else say "lockdown: INCONSISTENT (flag present: $flag, live uids: { ${members:-none} }); run on or off again"; exit 1
  fi
}

"cmd_$1"
