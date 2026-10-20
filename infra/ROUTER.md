# Router - GL-MT6000 (OpenWrt 21.02) at 192.0.2.1

WAN `eth1`, public address `203.0.113.10`. Root SSH with key auth.

## WireGuard is ALREADY on the router - do not run a second one

The router terminates WireGuard itself on the WAN interface:

- interface `wgserver`, **UDP 51820**, tunnel subnet `10.0.0.0/24`, router `10.0.0.1`
- config in `/etc/config/wireguard_server` (uci), peers as `@peers[n]`
- live peers: `ron-desktop` 10.0.0.3, `ron-mobile` 10.0.0.4,
  `cyberflight-wp` 10.0.0.5 (GCP site-to-site), plus 10.0.0.2

Because the router listens on its own WAN, **no port forward is needed for
WireGuard**, and there is currently no forward for it.

> **An earlier draft of this file said to forward UDP 51820 to ms01 for a
> second WireGuard server. That was wrong and would have hijacked the router
> tunnel, dropping remote access and the GCP site-to-site link. The ms01
> WireGuard container has been removed.**

## The only forward CAP V-SAR needs

> **Checked 2026-10-19.** A second, complete stack (Mumble, exercise, radio-https, planner containers, all healthy, with the
> nine-channel tree from `docs/MUMBLE_CHANNELS.md` provisioned) is running on the Linux workstation, which is a different host
> from ms01. ms01 (192.0.2.151) also still answers on TCP 64738. The forward below targets ms01. This file does not record
> whether the router's live forward was changed, and it was not queried (no router access from the workstation). If the
> workstation becomes the host, repoint `dest_ip` on both redirects to the workstation's address and re-test from cellular.

| Service | Protocol / Port | To | Why public |
|---|---|---|---|
| Mumble | TCP **and** UDP 64738 | 192.0.2.151 | So base staff and aircrew join the voice net without a VPN client. Server password required. |

Mumble uses TCP for control and UDP for voice. Forward both, or voice falls
back to TCP tunnelling and latency suffers.

```sh
# on the router, as root
uci add firewall redirect
uci set firewall.@redirect[-1].name=capvsar-mumble-tcp
uci set firewall.@redirect[-1].src=wan
uci set firewall.@redirect[-1].src_dport=64738
uci set firewall.@redirect[-1].dest=lan
uci set firewall.@redirect[-1].dest_ip=192.0.2.151
uci set firewall.@redirect[-1].dest_port=64738
uci set firewall.@redirect[-1].proto=tcp
uci set firewall.@redirect[-1].target=DNAT

uci add firewall redirect
uci set firewall.@redirect[-1].name=capvsar-mumble-udp
uci set firewall.@redirect[-1].src=wan
uci set firewall.@redirect[-1].src_dport=64738
uci set firewall.@redirect[-1].dest=lan
uci set firewall.@redirect[-1].dest_ip=192.0.2.151
uci set firewall.@redirect[-1].dest_port=64738
uci set firewall.@redirect[-1].proto=udp
uci set firewall.@redirect[-1].target=DNAT

uci commit firewall && /etc/init.d/firewall reload
```

Verify from off-network (phone on cellular), pointing a Mumble client at
`203.0.113.10:64738`.

## Adding CAP V-SAR participants to the VPN

Everything except Mumble rides the existing router tunnel. Add one peer per
person, in the 10.0.0.10+ range to stay clear of the existing peers.

Participant web traffic uses only `https://192.0.2.151/` on TCP 443 over the
LAN or tunnel. Caddy routes `/planner/` to the planner and all other paths to
the exercise service. Caddy publishes exactly three listeners on the host, and
**none of them is forwarded by the router** (see `docker-compose.yml` and
`services/exercise/Caddyfile`):

| Port | Purpose |
|---|---|
| 80 | Plaintext, but serves only `/radio-ca.crt` (CA bootstrap for new devices); everything else is a 308 to HTTPS. |
| 443 | The participant front door: exercise console, browser radio, plugin API, `/planner/`. |
| 8443 | The engineering listener: the agent coordination board only. LAN/WireGuard only. |

The exercise console (8700), planner (8080) and board (8770) ports are
container-internal and are not published on the host.

Easiest path is the GL.iNet UI: **VPN -> WireGuard Server -> Add Client**,
which generates the keypair and shows a QR code for the phone app.

From the shell, additively and without reloading the interface (so existing
tunnels including the GCP link are never dropped):

```sh
NAME=capvsar-instructor; IP=10.0.0.10
PRIV=$(wg genkey); PUB=$(echo "$PRIV" | wg pubkey); PSK=$(wg genpsk)
uci add wireguard_server peers
uci set wireguard_server.@peers[-1].name="$NAME"
uci set wireguard_server.@peers[-1].client_ip="$IP"
uci set wireguard_server.@peers[-1].public_key="$PUB"
uci set wireguard_server.@peers[-1].private_key="$PRIV"
uci set wireguard_server.@peers[-1].presharedkey="$PSK"
uci commit wireguard_server
echo "$PSK" > /tmp/psk.$$
wg set wgserver peer "$PUB" preshared-key /tmp/psk.$$ allowed-ips "$IP/32"
rm -f /tmp/psk.$$
```

Suggested allocation: instructor 10.0.0.10, IC .11, AOBD .12, MRO .13,
MP1 .14, MO1 .15, MS1 .16, spare .17.

## Dynamic WAN address

`203.0.113.10` is the current WAN address. If it is not static, set up DDNS
(GL.iNet ships one; OpenWrt has the `ddns-scripts` package) and give
participants a hostname such as `vpn.rpc-cyberflight.com` rather than the raw
address, so peer configs survive a lease change.

## Deliberately NOT exposed

Mission base client, scenario and tracking services, Gitea, Proxmox, NFS,
Ollama, SSH. All of these are reachable over the WireGuard tunnel only.
