# As-Built — CAP V-SAR Infrastructure

**Deployed:** 2026-09-06
**Host:** ms01 (192.0.2.151), Docker Compose
**Repository:** `/srv/capvsar` on ms01

Service stack for the [[CONOPS-cap-vsar|CAP V-SAR]] trainer. Chosen over a new
Proxmox VM because ms01 already had 20 cores, 53 GB free RAM, 1.1 TB free disk
and Docker.

## Containers

| Container | Image | Port | Exposure |
|---|---|---|---|
| `capvsar-mumble` | `mumblevoip/mumble-server` | 64738 TCP+UDP | **Public** via router forward |
| `capvsar-exercise` | built from `services/exercise` | 8700 TCP | LAN and WireGuard only |

## Mumble — CAP mission voice net

Server password required, autoban after 10 attempts in 120 s. ATC is PilotEdge,
not this server; mission traffic stays here.

Channel structure, created directly in `mumble-server.sqlite`:

```
CAP V-SAR
├── Briefing Room
├── Mission Base
├── Mission Net PRIMARY
├── Mission Net ALTERNATE
├── Aircraft
│   ├── CAP-1 Intercom
│   ├── CAP-2 Intercom
│   └── CAP-3 Intercom
└── Instructor - SET
```

**Gotcha:** the `mumblevoip` image generates `/data/mumble_server_config.ini`
from `MUMBLE_CONFIG_*` environment variables on every start and **overwrites
any mounted config file**. A mounted config is silently discarded — this left
the server with no password while it was port-forwarded. Set everything in the
compose environment block.

Participant instructions: `docs/CONNECT.md` in the repository.

## Exercise console

FastAPI plus a browser front end. Three views on one backend:

| View | Path | Audience |
|---|---|---|
| Instructor console | `/` | Scenario control, effect toggles, reveal |
| Mission base | `/base` | Alert intake, status board, bearings, tasking |
| Debrief replay | `/debrief` | Track scrubbed against beacon truth, scoring |

**Beacon truth is withheld server-side** until an explicit reveal, so a trainee
opening the console cannot read the answer out of it.

`POST /api/positions` is the contract the sim reports through:
`{callsign, lat, lon, alt_ft, hdg_true}`. Keep it stable.

## Networking

- **WireGuard is on the router**, not on any host. GL-MT6000 (192.0.2.1)
  runs `wgserver` on UDP 51820, subnet 10.0.0.0/24, with peers ron-desktop .3,
  ron-mobile .4, cyberflight-wp .5 (GCP site-to-site). It terminates on its own
  WAN so it needs no port forward. **Never forward 51820 anywhere** — doing so
  hijacks the router tunnel and drops remote access and the GCP link.
- Router port forwards added: `capvsar-mumble-tcp` and `capvsar-mumble-udp`,
  64738 → 192.0.2.151. These are the only forwards on the router.
- Host firewall (ufw) on ms01 allows `192.0.2.0/24` unrestricted, because
  ms01 NFS-exports `/srv/fastnfs` to the lab and cainfra02 mounts it for
  HERMES_HOME. A default-deny without that rule takes Hermes down.
- Docker publishes container ports ahead of ufw's rules, so ufw does not filter
  published container ports. The router forward list is what controls public
  exposure.

## Simulator side

X-Plane 12 at `/home/ron/X-Plane 12` on the workstation (ron-MS-7B98).

- **XPPython3 v4.7.1** installed at `Resources/plugins/XPPython3` — bundles its
  own Python 3.12, so the system Python 3.14 is irrelevant.
- **`PI_capvsar_df.py`** at `Resources/plugins/PythonPlugins/` — the DF
  propagation engine. Publishes `cap/df/valid`, `bearing_rel`, `bearing_true`,
  `signal`, `distance_nm`, `in_cone`, `blocked`, `band`, and writable
  `cap/scenario/beacon_*`. Probes real terrain along the aircraft-to-beacon
  path for line of sight. Also acts as the sim bridge — a background thread
  polls the console and reports position, so no network call runs in the flight
  loop.

Geodesy validated against the FAA plate for the KCRQ ILS: KCRQ to ESCON gives
76.01° true and 10.40 nm against a charted 10.4 DME on the 065 radial.

**Blocked:** Air Manager is licensed software and is not installed, so the
Phase 0 exit criterion — a value from our plugin visibly moving a needle —
is undemonstrated. Instrument work targets the **Air Manager 4 API subset**
because spare AM4 licences exist; avoid `layer_add`, `scene_add` and the V5.2
shape functions.

## Repository

`/srv/capvsar` on ms01, branch `main`. Contains the compose stack, Mumble
config, the exercise console service, the XPPython3 plugin, the router and
firewall documentation, and the project documents under `docs/`.

Related: [[CONOPS-cap-vsar]], [[LAB]]
