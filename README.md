# CAP V-SAR - lab infrastructure

Civil Air Patrol Virtual Search and Rescue trainer. This repository holds the
service stack, the simulator plugins, and the project documents.

**Status:** infrastructure only. No simulator code exists yet - Phase 0 of the
implementation plan has not started.

## Layout

```
docker-compose.yml     Mumble + WireGuard service stack
.env.example           copy to .env and fill in (never commit .env)
mumble/                voice server config template
scripts/               deploy, firewall, peer handout
infra/ROUTER.md        the two port forwards this needs, and nothing more
docs/                  plan, CONOPS, channel structure, CONNECT.md for participants
sim/xppython3/         Phase 1: the DF propagation engine plugin
sim/airmanager/        Phase 2-3: Becker 517, RT-600, MO COM panel
services/scenario/     Phase 4: beacon truth service
services/tracking/     Phase 4: position aggregation, CalTopo relay
services/missionbase/  Phase 5: mission base web client
```

## Host

Runs on **ms01** (192.0.2.151) under Docker Compose. Chosen over a new
Proxmox VM because it has 20 cores, 53 GB free RAM and 1.1 TB free disk, and
already runs Docker. It also serves NFS to the lab - see the warning in
`scripts/firewall.sh` before touching the firewall.

## Deploy

```bash
cp .env.example .env      # fill in secrets
./scripts/deploy.sh
```

## Exposure model

One thing faces the internet, by explicit router forward:

- **Mumble** (64738 TCP+UDP) - so non-technical mission base staff can join a
  voice net without installing a VPN client. Server password required.

Everything else rides the **WireGuard server already running on the
GL-MT6000** (`wgserver`, UDP 51820, 10.0.0.0/24). It terminates on the
router's own WAN and needs no forward. Participants get a peer there; see
`infra/ROUTER.md`.

Do not run a second WireGuard on this host. An earlier draft did, and
forwarding 51820 to it would have hijacked the router tunnel, dropping remote
access and the GCP site-to-site link.

Nothing web-facing is public.

## Documents

The implementation plan, concept brief and summary live in `docs/`. The plan is
the authority on what this is for; this README only covers how to run it.
