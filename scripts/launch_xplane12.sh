#!/usr/bin/env bash
set -euo pipefail

# X-Plane refuses to run when launched from a Snap-hosted editor or terminal.
# Preserve the host desktop search paths before removing the inherited Snap
# runtime variables.
host_xdg_data_dirs=${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-/usr/local/share:/usr/share}
host_xdg_config_dirs=${XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG:-/etc/xdg}

unset SNAP SNAP_ARCH SNAP_COMMON SNAP_CONTEXT SNAP_COOKIE SNAP_DATA SNAP_EUID
unset SNAP_INSTANCE_NAME SNAP_LAUNCHER_ARCH_TRIPLET SNAP_LIBRARY_PATH SNAP_NAME
unset SNAP_REAL_HOME SNAP_REVISION SNAP_UID SNAP_USER_COMMON SNAP_USER_DATA SNAP_VERSION
unset GTK_PATH GIO_MODULE_DIR GIO_LAUNCHED_DESKTOP_FILE GIO_LAUNCHED_DESKTOP_FILE_PID
unset XDG_DATA_DIRS_VSCODE_SNAP_ORIG XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG
unset LD_PRELOAD LD_LIBRARY_PATH
export XDG_DATA_DIRS="$host_xdg_data_dirs"
export XDG_CONFIG_DIRS="$host_xdg_config_dirs"

xplane_dir=${XPLANE12_DIR:-/home/ron/X-Plane 12}
xplane_binary="$xplane_dir/X-Plane-x86_64"

if [[ ! -x "$xplane_binary" ]]; then
    printf 'X-Plane executable not found: %s\n' "$xplane_binary" >&2
    exit 66
fi

loaded_driver=''
if [[ -r /proc/driver/nvidia/version ]]; then
    loaded_driver=$(sed -nE 's/.*Module for [^ ]+[[:space:]]+([0-9.]+).*/\1/p' /proc/driver/nvidia/version)
fi
installed_driver=$(modinfo -F version nvidia 2>/dev/null || true)

if [[ -n "$loaded_driver" && -n "$installed_driver" && "$loaded_driver" != "$installed_driver" ]]; then
    printf 'X-Plane cannot start: loaded NVIDIA module %s does not match installed driver %s.\n' \
        "$loaded_driver" "$installed_driver" >&2
    printf 'Reboot the host, then run this launcher again.\n' >&2
    exit 78
fi

if [[ ${1:-} == '--check' ]]; then
    printf 'X-Plane launch environment is clean; NVIDIA driver %s is ready.\n' \
        "${loaded_driver:-unknown}"
    exit 0
fi

# X-Plane renames its process to "Main Thread" while loading. Checking the
# process name can miss a running simulator and start a second memory-heavy
# instance. Resolve /proc executables instead, including during modal loading.
running_pid=$(python3 - "$xplane_binary" <<'PY'
from pathlib import Path
import sys
binary = Path(sys.argv[1]).resolve()
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    try:
        if (process / 'exe').resolve(strict=True) == binary:
            print(process.name)
    except (OSError, RuntimeError):
        pass
PY
)
if [[ -n "$running_pid" ]]; then
    printf 'X-Plane is already running (PID %s); refusing a second instance.\n' "$running_pid" >&2
    exit 75
fi

cd "$xplane_dir"
exec "$xplane_binary" "$@"
