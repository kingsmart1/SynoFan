#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 LiuFudi
#
# Build the Synology .spk for the NiuFan Synology port (SynoFan).
#
# Output:  dist/synofan-noarch-<version>-<release>.spk
#
# The upstream `package/` tree is not modified: this script stages a copy,
# injects the Synology-only pieces (self-auth guard, login overlay, desktop
# shell, nginx bridge config written at runtime) and packs them.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HERE/package/app"
VERSION="2.2.5"
RELEASE="4"
PKG="synofan"
ARCH="x86_64"
BASE_URL="/webman/3rdparty/synofan"

DIST="$HERE/dist"
BUILD="$HERE/.build"
STAGE="$BUILD/synofan"
TARGET="$STAGE/target"

rm -rf "$STAGE" && mkdir -p "$TARGET/ui" "$TARGET/server" "$STAGE/conf" "$STAGE/scripts" "$DIST"

command -v sips >/dev/null 2>&1 || { echo "build-spk: sips not found (macOS)" >&2; exit 1; }

# 1. upstream server + ui ---------------------------------------------------
cp -a "$APP/server/." "$TARGET/server/"
cp -a "$APP/ui/." "$TARGET/ui/"

# 2. Synology-only runtime pieces ------------------------------------------
cp "$HERE/spk/dsm/synoauth.py" "$TARGET/server/synoauth.py"
cp "$HERE/spk/dsm/dsm-auth.js" "$TARGET/ui/dsm-auth.js"
cp "$HERE/spk/nginx.conf" "$TARGET/nginx.conf"

# 3. DSM desktop shell ------------------------------------------------------
cp "$HERE/spk/ui/config" "$TARGET/ui/config"
cp "$HERE/spk/ui/synofan.js" "$TARGET/ui/synofan.js"
cp "$HERE/spk/ui/application.cfg" "$TARGET/ui/application.cfg"
mkdir -p "$TARGET/ui/images"
for s in 16 24 32 48 64 72 256; do
    sips -s format png -z "$s" "$s" "$HERE/package/ICON_256.PNG" \
        --out "$TARGET/ui/images/synofan-$s.png" >/dev/null
done
# the in-app icon the UI itself references
cp "$TARGET/ui/images/synofan-64.png" "$TARGET/ui/images/icon_64.png" 2>/dev/null || true
cp "$TARGET/ui/images/synofan-256.png" "$TARGET/ui/images/icon_256.png" 2>/dev/null || true

# 4. rewrite the web UI base path and load the login overlay ---------------
sed -i '' "s|__FC_BASE__|$BASE_URL/|g" "$TARGET/ui/index.html"
sed -i '' "s|</body>|<script src=\"$BASE_URL/dsm-auth.js\"></script>\n</body>|" "$TARGET/ui/index.html"

# 5. purge bytecode so it never ships --------------------------------------
find "$TARGET" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$TARGET" -name '*.py[co]' -delete 2>/dev/null || true

# 6. package.tgz (contents land in /var/packages/synofan/target/) ----------
( cd "$TARGET" && COPYFILE_DISABLE=1 tar --uid 0 --gid 0 --format ustar \
    -czf "$STAGE/package.tgz" . )

# 7. icons + scripts --------------------------------------------------------
sips -s format png -z 72 72 "$HERE/package/ICON_256.PNG" \
    --out "$STAGE/PACKAGE_ICON.PNG" >/dev/null
sips -s format png -z 256 256 "$HERE/package/ICON_256.PNG" \
    --out "$STAGE/PACKAGE_ICON_256.PNG" >/dev/null
cp -a "$HERE/spk/conf/." "$STAGE/conf/"

# 8. INFO -------------------------------------------------------------------
CHECKSUM="$(md5 -q "$STAGE/package.tgz")"
ICON_B64="$(openssl base64 -A -in "$STAGE/PACKAGE_ICON.PNG")"
ICON256_B64="$(openssl base64 -A -in "$STAGE/PACKAGE_ICON_256.PNG")"
cat > "$STAGE/INFO" <<EOF
package="synofan"
version="$VERSION-$RELEASE"
arch="$ARCH"
displayname="SynoFan"
description="基于 NiuFan 的群晖风扇调速套件：按温度曲线控制 SuperIO 风扇，支持 CPU/硬盘/显卡多温度源、每路独立曲线与失效保护。网页经 DSM 桌面入口访问，独立密码登录。"
maintainer="kingsmart"
maintainer_url="https://github.com/kingsmart1/SynoFan"
distributor="kingsmart"
distributor_url="https://github.com/kingsmart1/SynoFan"
os_min_ver="7.0-40000"
helpurl="https://github.com/kingsmart1/SynoFan"
ctl_stop="yes"
dsmuidir="ui"
dsmappname="SynoFan.Application"
support_conf_folder="yes"
package_icon="$ICON_B64"
package_icon_256="$ICON256_B64"
checksum="$CHECKSUM"
EOF

# 9. scripts ----------------------------------------------------------------
cp -a "$HERE/spk/scripts/." "$STAGE/scripts/"
chmod 755 "$STAGE/scripts/"*

# 9. assemble the spk -------------------------------------------------------
ARTIFACT="$DIST/synofan-$ARCH-$VERSION-$RELEASE.spk"
rm -f "$ARTIFACT"
( cd "$STAGE" && COPYFILE_DISABLE=1 tar --uid 0 --gid 0 \
    -cf "$ARTIFACT" INFO PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG package.tgz conf scripts )

echo "build-spk: $ARTIFACT"
ls -la "$ARTIFACT"
tar -tf "$ARTIFACT"
