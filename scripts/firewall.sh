#!/usr/bin/env bash
# CAP V-SAR host firewall for ms01.
#
# READ THIS BEFORE RUNNING:
#   ms01 exports NFS (/srv/fastnfs) to 192.0.2.0/24 and other lab hosts
#   depend on it - cainfra02 mounts it for HERMES_HOME. This ruleset allows
#   the entire LAN unrestricted, so those services keep working. It only
#   restricts traffic arriving from outside the LAN.
#
#   IMPORTANT CAVEAT: Docker publishes container ports by inserting its own
#   iptables rules ahead of ufw's, so ufw does NOT filter published container
#   ports (Mumble 64738, WireGuard 51820). What actually controls public
#   exposure is the router forward list in infra/ROUTER.md. This ruleset
#   protects the HOST services - SSH, NFS, Ollama, and anything on 8080.
set -euo pipefail

echo "==> allowing LAN (preserves NFS, Ollama, SSH for lab hosts)"
sudo ufw allow from 192.0.2.0/24 comment 'lab LAN - full access'

echo "==> allowing WireGuard peer subnet"
sudo ufw allow from 10.0.0.0/24 comment 'WireGuard peers via router wgserver'

echo "==> allowing the one intended public service"
sudo ufw allow 64738/tcp comment 'CAP V-SAR Mumble'
sudo ufw allow 64738/udp comment 'CAP V-SAR Mumble'
# No 51820 rule: WireGuard runs on the router, not this host.

echo "==> default policy"
sudo ufw default deny incoming
sudo ufw default allow outgoing

echo
echo "Rules staged. Review them, then enable with:"
echo "    sudo ufw --force enable"
echo
sudo ufw show added
