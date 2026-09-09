# V-SAR Google Cloud cost estimate

Prepared 2026-09-09 for the hybrid architecture in `WEB_HOSTING_AND_IDENTITY_PLAN.md`, Section 3a. USD, planning estimate, not a quote. No resources provisioned.

**Deferred option:** the owner chose to stage the pilot in the existing lab. These cloud costs are not required for that stage; see `LAB_HOSTED_DEPLOYMENT_PLAN.md` for the active plan and incremental lab costs.

## Summary

| Measure | Budget |
|---|---:|
| Standing monthly platform cost | $140–$170 |
| Additional usage for five days, 25 participants, 8 hours/day | $25–$55 |
| Entire month's bill with that one exercise | $165–$225 |
| Five-day cost allocation including 120 hours of standing infrastructure | approximately $50–$85 |
| Allocated exercise cost per participant | approximately $2.00–$3.40 |

The five-day allocation is an accounting measure, not the monthly invoice if services remain available all month. Use $225/month as a working budget for one event with these assumptions; it is not a spending cap or capacity guarantee.

## Assumptions

- `us-central1` (Iowa) reference rates and mostly North American participants; region and international egress can change prices. Choose latency/region after testing.
- On-demand pricing, 730 hours/month, no promotional credits, committed-use discounts, or assumed unused free tiers.
- 25 signed-in participants and conservatively up to 25 simultaneous browser radio listeners, for 40 active exercise hours across five days. One effective incoming audio stream per listener; simultaneous multiple-net streams increase traffic proportionally.
- Existing radio PCM format, 48 kHz mono 16-bit; typical modeled received-audio duty cycle 25–50%, with a 20% allowance for framing/transport/estimation error. This is an estimate, not measured traffic. No continuous video, streamed X-Plane, or voice recording.
- One always-on `e2-standard-2` VM (2 vCPU/8 GiB) for authentik server/worker and Mumble/browser bridge. Load-test 25 sessions; increase CPU if needed. The current 16-session default must be deliberately raised after testing.
- One Cloud SQL Enterprise PostgreSQL instance, single zone, 1 vCPU/3.75 GiB, with separate identity/application databases and credentials; 20 GiB SSD. No HA replica. This is initial sizing, not a performance guarantee.
- One external Application Load Balancer; private VM with one Cloud NAT address; Direct VPC egress for required Cloud Run private traffic rather than a provisioned Serverless VPC Access connector. Internet browser audio traverses the load balancer, not Cloud NAT; NAT is for the private VM's outbound dependencies.
- Cloud Run minimum instances zero outside exercises. No separate permanently running staging stack, Cloud Armor subscription, Redis/Memorystore, commercial identity license, or premium support.

## Monthly standing costs

| Item | Calculation or allowance | USD/month |
|---|---|---:|
| Compute Engine identity/radio VM | 730 × $0.06701142/hour | $48.92 |
| Cloud SQL CPU and memory | 730 × ($0.0413 + 3.75 × $0.007)/hour | $49.31 |
| Persistent disks | SQL: 20 GiB × $0.17; VM: 30 GiB balanced disk × approximately $0.10 | $6.40 |
| External Application Load Balancer | One forwarding-rule price group, 730 × $0.025/hour | $18.25 |
| Cloud NAT standing charges | One VM and one NAT IP, 730 × ($0.0014 + $0.005)/hour | $4.67 |
| Database backups, object storage, images | Small retained footprint; budgeting allowance | $3–$7 |
| Secrets, light monitoring/logging, idle maintenance/build activity | Budgeting allowance, not a quoted SKU bundle | $2–$8 |
| DNS/domain amortization | Budgeting allowance; existing domain could reduce this | $1–$3 |
| Transactional mail | Existing suitable relay to modest paid mail allowance | $0–$15 |
| **Calculated range** | | **$134–$161** |
| **Rounded operating budget** | Allows minor usage and estimation variation | **$140–$170** |

VM rates: [Compute Engine](https://cloud.google.com/products/compute/pricing/general-purpose). SQL CPU, memory and SSD rates: [Cloud SQL](https://cloud.google.com/sql/pricing). VM disk rates: [Persistent disks](https://cloud.google.com/compute/disks-image-pricing). Load balancer forwarding and traffic rates: [VPC pricing](https://cloud.google.com/vpc/pricing). NAT rates: [Cloud NAT](https://cloud.google.com/nat/pricing).

These are reference list-rate calculations. The main SQL pricing page was too large for the browser fetch, so its indexed official rate tables and the official Cloud SQL product pricing summary were used. Reconfirm the exact selected SKU, edition and region in the Google pricing calculator before provisioning.

## Five-day exercise usage

| Variable item | Basis | Additional USD |
|---|---|---:|
| Cloud Run web/API/planner compute and requests | Conservative two-service allowance: each 1–2 vCPU/1 GiB active for all 40 hours | $8–$15 |
| Browser radio internet egress | 97–193 GiB modeled outgoing audio × $0.12/GiB | $12–$23 |
| Maps, charts, pages and telemetry internet egress | 10–30 GiB allowance × $0.12/GiB | $1–$4 |
| Load balancer traffic processing and minor network overhead | Includes incoming PTT audio and outgoing streams; assumes modest cross-zone/private traffic | $2–$5 |
| Extra artifacts, logs, email/maintenance activity | Incremental usage allowance | $2–$5 |
| **Total** | | **$25–$52** |
| **Rounded additional exercise budget** | | **$25–$55** |

Cloud Run request-based active rates used: $0.000024/vCPU-second and $0.0000025/GiB-second. Two services × 144,000 seconds × (1 CPU + 1 GiB at these rates) = $7.63; 2 CPUs each = $14.54. CPU is shared across concurrent requests; there is not one server per participant. Actual autoscaled/request-driven consumption may be lower. Free-tier discounts, if available on the billing account, reduce the bill but are not relied upon. [Cloud Run pricing](https://cloud.google.com/run/pricing)

Network reference: Premium Tier North America initial paid tier $0.12/GiB, plus load balancer processing $0.008/GiB inbound and $0.008/GiB outbound. Apply internet egress once; do not add it again as a second load-balancer egress charge. VM private outbound NAT processing is separate at $0.045/GiB and should be small for login/mail dependencies; it is not charged on browser traffic delivered through the load balancer. [Network pricing](https://cloud.google.com/vpc/pricing), [NAT pricing](https://cloud.google.com/nat/pricing)

### Radio sensitivity

Formula: `25 listeners × 40 hours × 3600 × 48000 samples/sec × 2 bytes × duty cycle × 1.20 / 2^30` gives outgoing GiB. Multiplication already includes fan-out to the listeners; do not multiply by participant count again.

| Average received-audio duty cycle | Outgoing radio GiB | Internet egress alone |
|---|---:|---:|
| 10%: quiet nets | 38.6 | $4.63 |
| 25%: moderate use | 96.6 | $11.59 |
| 50%: busy nets | 193.1 | $23.17 |
| 100%: continuous audio | 386.2 | $46.35 |

Continuous audio raises the additional exercise budget to roughly $60–$80 for the same 40 hours. If “five days” means 24-hour operations (120 active hours), use roughly $75–$165 additional usage at the same 25–50% duty cycle. Standing costs do not triple; only activity-related costs scale this way. Multiple simultaneous streams per participant, excessive silence transmission, overseas participants or heavy chart downloads can increase these figures.

## Costs outside this estimate

- Development, migration, system administration and participant support.
- X-Plane, Air Manager, PilotEdge, CalTopo subscriptions and any paid weather/chart APIs or content licensing.
- Cloud SQL HA/read replicas, a second always-on VM, managed Redis, Cloud Armor, extended log retention, and a permanent staging environment.
- Dedicated VM health/capacity upgrade: moving from e2-standard-2 to e2-standard-4 adds about $49/month if kept all month, or about $8 for 120 hours. Schedule any VM resize outside live sessions.
- Statewide or national deployment, video conferencing/streaming, and a cloud-hosted flight simulator.

Authenticator-app codes have no per-message delivery cost; the identity software fee is zero under the proposed Open Source setup. Mail still depends on the selected relay and allowance. Upstream social-account consent and application setup are not per-participant VM charges.

## Before booking an exercise

Run a 25-session staging load test, measure CPU/memory and audio bytes over one hour, verify whether silent periods send data, and extrapolate using the table above. Confirm Cloud Run instance/concurrency limits and SQL connection pools. Set billing alerts at $150, $200 and $250 for the pilot month; alerts notify and are not hard caps. Monitor hourly during the initial exercise, with explicit service quotas and a manual incident response rather than an automatic shutdown during training.
