# Router configuration - GL-MT6000 (OpenWrt) at 192.0.2.1

Two UDP forwards are all CAP V-SAR needs from the edge. **Nothing else should
be forwarded.** No web service, no Gitea, no Proxmox, no SSH.

| Service | Protocol / Port | Forward to | Why public |
|---|---|---|---|
| Mumble (mission voice net) | TCP **and** UDP 64738 | 192.0.2.151 | Base staff and aircrew join without a VPN client. Protected by a server password. |
| WireGuard | UDP 51820 | 192.0.2.151 | Everything that is not Mumble rides this tunnel. |

Mumble uses TCP for control and UDP for voice. Forward both or voice degrades
to TCP tunnelling and latency suffers.

## Steps (GL.iNet / OpenWrt UI)

1. Log in to `http://192.0.2.1`.
2. **Network -> Firewall -> Port Forwards** (GL.iNet: *Applications -> Port
   Forwarding*).
3. Add the three rules above (Mumble needs one TCP and one UDP entry).
4. Set the internal host to `192.0.2.151` and keep external = internal port.
5. Apply, then verify from off-network (phone on cellular):
   `nc -vz -u <public-ip> 51820` and open the Mumble client against
   `<public-ip>:64738`.

## Dynamic WAN address

The current WAN address is `203.0.113.10`. If it is not static, WireGuard
peers will break when it changes, because each peer config hard-codes the
endpoint.

Fix before handing configs out: point a hostname such as
`vpn.rpc-cyberflight.com` at the WAN address with DDNS (OpenWrt has a DDNS
package; GL.iNet ships its own DDNS service), then set `WG_SERVERURL` in
`.env` to that hostname and re-run `scripts/deploy.sh`. Peers regenerate with
the hostname instead of the raw address.

## Deliberately NOT exposed

| Service | Reach it via |
|---|---|
| Mission base web client | WireGuard |
| Scenario / tracking services | WireGuard |
| Gitea (192.0.2.121) | WireGuard |
| Proxmox nodes, NFS, Ollama | WireGuard, LAN only |
| SSH to any host | WireGuard, LAN only |
