#!/usr/bin/env bash
# Helpers sourced by scripts/deploy.sh. Kept separate so tests/test_deploy_lib.py
# can run them in a scratch directory without Docker or sudo.
#
# All of these work relative to the current directory, which deploy.sh sets to
# the repository root (where docker-compose.yml and .env live).

# env_get KEY [FILE]  -> print KEY's value from FILE (default .env), or nothing.
#
# deploy.sh used to `source .env`, which is a shell parser, not compose's: a
# value containing $, #, backticks or spaces was expanded or mangled before
# the script looked at it, and a stray line could run as code. This reads one
# key with grep and never evaluates anything. Last assignment wins, as in
# compose. Surrounding single or double quotes are removed; an unquoted value
# loses a trailing " # comment". No variable expansion is performed.
env_get() {
  local key=$1 file=${2:-.env} line val
  [ -f "$file" ] || return 0
  line=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" | tail -n 1) || true
  [ -n "$line" ] || return 0
  val=${line#*=}
  val=${val#"${val%%[![:space:]]*}"}                       # trim leading space
  if [[ $val =~ ^\"(.*)\"[[:space:]]*(#.*)?$ ]]; then
    val=${BASH_REMATCH[1]}
  elif [[ $val =~ ^\'(.*)\'[[:space:]]*(#.*)?$ ]]; then
    val=${BASH_REMATCH[1]}
  else
    val=$(printf '%s' "$val" | sed -E 's/[[:space:]]+#.*$//; s/[[:space:]]+$//')
  fi
  printf '%s' "$val"
}

# cfg KEY  -> the shell environment wins over .env, exactly as in compose.
cfg() {
  local v=${!1:-}
  if [ -z "$v" ]; then v=$(env_get "$1"); fi
  printf '%s' "$v"
}

# O2-7: where bind-mounted runtime state lives. Default is this checkout.
state_dir() {
  local s; s=$(cfg CAPVSAR_STATE_DIR)
  printf '%s' "${s:-.}"
}

board_repo_path()  { local v; v=$(cfg CAPVSAR_BOARD_REPO);        printf '%s' "${v:-$(state_dir)/services/board/repo}"; }
board_key_path()   { local v; v=$(cfg CAPVSAR_BOARD_SSH_KEY);     printf '%s' "${v:-./services/board/secrets/id_ed25519}"; }
board_known_path() { local v; v=$(cfg CAPVSAR_BOARD_KNOWN_HOSTS); printf '%s' "${v:-./services/board/secrets/known_hosts}"; }

# prepare_host_paths: create every directory compose bind-mounts, and the one
# FILE mount the flight planner needs. Never creates the board's key or
# known_hosts: Docker turns a missing FILE mount into a DIRECTORY, so those are
# only mounted when board_configured says they are real files.
prepare_host_paths() {
  local s; s=$(state_dir)
  mkdir -p "$s/mumble/data"
  mkdir -p "$s/services/exercise/data"             # exercise.db lives here
  mkdir -p "$s/services/exercise/radio-public"     # CA cert served at /radio-ca.crt
  mkdir -p "$s/services/flightplanner/data/charts" # cached chart tiles
  # An empty file is a valid SQLite database; init_database() creates the schema.
  [ -e "$s/services/flightplanner/data/aviation_data.db" ] \
    || : > "$s/services/flightplanner/data/aviation_data.db"
  # The board's clone target and secrets directory exist so the README's
  # `git clone` and `ssh-keygen -f` have somewhere to write. Directories only.
  local repo key known
  repo=$(board_repo_path); key=$(board_key_path); known=$(board_known_path)
  mkdir -p "$repo"
  [ -d "$(dirname "$key")" ]   || { mkdir -p "$(dirname "$key")";   chmod 700 "$(dirname "$key")"; }
  [ -d "$(dirname "$known")" ] || mkdir -p "$(dirname "$known")"
}

# board_configured: succeed (and print nothing) only when the board's one-time
# setup (services/board/README.md) is complete. Otherwise print why on stdout
# and fail, so deploy.sh can skip the board instead of starting a container that
# cannot sync or, worse, letting Docker create directories in place of files.
board_configured() {
  local repo key known missing=()
  repo=$(board_repo_path); key=$(board_key_path); known=$(board_known_path)
  [ -e "$repo/.git" ] || missing+=("a git clone at $repo")
  for f in "$key" "$known"; do
    if [ -d "$f" ]; then
      missing+=("$f is a DIRECTORY (Docker made it); rmdir it and redo the README setup")
    elif [ ! -s "$f" ]; then
      missing+=("a non-empty file at $f")
    fi
  done
  [ ${#missing[@]} = 0 ] && return 0
  local IFS=';'
  echo "board not configured, skipping: needs ${missing[*]}"
  return 1
}
