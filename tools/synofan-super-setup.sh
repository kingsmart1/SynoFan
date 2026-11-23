#!/bin/sh
# One-time root setup for the SynoFan Synology package.
#
# DSM 7 refuses root privileges to unsigned third-party packages, so SynoFan
# runs its daemon and lifecycle scripts as the package user (sc-synofan).  The
# privileged bits (writing /sys/class/hwmon/*/pwm*, stopping the RR fancontrol
# supervisor, writing the nginx bridge) are done through a sudo helper,
# /usr/local/sbin/synofan-super, which this script installs once.
#
# Usage: run as root (an admin account via `sudo sh tools/synofan-super-setup.sh`).
set -e

SUPER=/usr/local/sbin/synofan-super
USER=sc-synofan

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo sh $0" >&2
    exit 1
fi

cat > "$SUPER" <<'EOF'
#!/bin/sh
# SynoFan privilege helper: execute its arguments as root.
# Allowed only for sc-synofan via the matching /etc/sudoers entry.
exec "$@"
EOF
chmod 755 "$SUPER"

LINE="$USER ALL=(root) NOPASSWD: $SUPER"
if ! grep -qF "$LINE" /etc/sudoers; then
    printf '\n%s\n' "$LINE" >> /etc/sudoers
    echo "added sudoers entry: $LINE"
else
    echo "sudoers entry already present"
fi

ls -la "$SUPER"
echo "done"
