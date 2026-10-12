#!/usr/bin/env bash
# Rootless Debian 13 bootstrap. APT verifies signed indexes and package hashes.
set -euo pipefail
if command -v libreoffice >/dev/null 2>&1; then
  libreoffice --headless --version
  exit 0
fi
TOOLS_ROOT=${STOCK_TOOLS_ROOT:-/workspace/tools}
if [[ -x "$TOOLS_ROOT/bin/libreoffice" ]]; then
  "$TOOLS_ROOT/bin/libreoffice" --headless --version
  exit 0
fi
. /etc/os-release
if [[ "$ID" != debian || "$VERSION_ID" != 13 ]]; then
  echo 'Install LibreOffice Writer using the system package manager on this OS.' >&2
  exit 1
fi
mkdir -p "$TOOLS_ROOT/apt/archives/partial" "$TOOLS_ROOT/apt/lists/partial" "$TOOLS_ROOT/apt/empty" "$TOOLS_ROOT/libreoffice" "$TOOLS_ROOT/bin"
cat > "$TOOLS_ROOT/apt/sources.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://security.debian.org/debian-security trixie-security main
SOURCES
cat > "$TOOLS_ROOT/apt/apt.conf" <<CONF
Dir::Etc::parts "$TOOLS_ROOT/apt/empty";
Dir::Etc::main "$TOOLS_ROOT/apt/empty.conf";
Dir::Etc::sourcelist "$TOOLS_ROOT/apt/sources.list";
Dir::Etc::sourceparts "$TOOLS_ROOT/apt/empty";
Dir::State::lists "$TOOLS_ROOT/apt/lists";
Dir::Cache::archives "$TOOLS_ROOT/apt/archives";
Debug::NoLocking "true";
APT::Sandbox::User "$(id -un)";
CONF
APT_CONFIG="$TOOLS_ROOT/apt/apt.conf" /usr/bin/apt-get update
APT_CONFIG="$TOOLS_ROOT/apt/apt.conf" /usr/bin/apt-get --download-only --no-install-recommends -y install libreoffice-writer fonts-crosextra-carlito
for pkg in "$TOOLS_ROOT"/apt/archives/*.deb; do
  dpkg-deb -x "$pkg" "$TOOLS_ROOT/libreoffice"
done
# Relocate only extracted configuration symlinks, never system files.
python3 - "$TOOLS_ROOT" <<'PY'
import sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()/ 'libreoffice'
for p in root.rglob('*'):
    if p.is_symlink() and p.readlink().is_absolute():
        target=root/str(p.readlink()).lstrip('/')
        p.unlink(); p.symlink_to(target)
registry=root/'etc/libreoffice/registry/main.xcd'
registry.parent.mkdir(parents=True, exist_ok=True)
registry.write_bytes((root/'usr/lib/libreoffice/share/.registry/main.xcd').read_bytes())
PY
cat > "$TOOLS_ROOT/fonts.conf" <<CONF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>$TOOLS_ROOT/libreoffice/usr/share/fonts</dir>
  <cachedir>$TOOLS_ROOT/cache/fontconfig</cachedir>
  <alias><family>Calibri</family><prefer><family>Carlito</family></prefer></alias>
</fontconfig>
CONF
cat > "$TOOLS_ROOT/bin/libreoffice" <<WRAPPER
#!/bin/sh
export LD_LIBRARY_PATH="$TOOLS_ROOT/libreoffice/usr/lib/libreoffice/program:$TOOLS_ROOT/libreoffice/usr/lib/x86_64-linux-gnu\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export XDG_CACHE_HOME="$TOOLS_ROOT/cache"
export FONTCONFIG_FILE="$TOOLS_ROOT/fonts.conf"
exec "$TOOLS_ROOT/libreoffice/usr/lib/libreoffice/program/soffice" -env:BRAND_BASE_DIR=file://$TOOLS_ROOT/libreoffice/usr/lib/libreoffice "\$@"
WRAPPER
chmod +x "$TOOLS_ROOT/bin/libreoffice"
"$TOOLS_ROOT/bin/libreoffice" --headless --version
