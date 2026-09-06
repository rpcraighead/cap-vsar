# Joining the CAP V-SAR mission voice net

For aircrew, mission base staff and instructors. Five minutes, once.

---

## 1. Install a Mumble client

| Platform | Client |
|---|---|
| Windows / macOS / Linux | **Mumble** — mumble.info (use this for a sim station) |
| Android | **Mumla** (Play Store) |
| iOS | **Mumble** (App Store) |

A desktop client is strongly preferred at a sim station. Phone clients are fine
for mission base staff who are only talking and watching a map.

## 2. Connect

| Field | Value |
|---|---|
| Address | `203.0.113.10` — or `192.0.2.151` if you are on the lab network |
| Port | `64738` |
| Username | Your CAP name or callsign, e.g. `Craighead` or `CAP-1-MO` |
| Password | Ask the exercise controller — the server requires one |

Mumble calls the server password a "server password", not a user password. You
do not need an account to connect; you need the server password.

The client will warn that the server certificate is self-signed. Accept it. It
is a certificate the server generated itself, not a sign of a problem.

## 3. Set push-to-talk — do this before your first exercise

**Configure > Settings > Audio Input > Transmit: Push To Talk**, then bind a
key. Voice activation on a shared mission net is unusable; every keyboard
click and cough goes out over the net.

If you also fly with **PilotEdge**, you now have two radios and you need two
separate keys:

| Net | Application | Suggested key |
|---|---|---|
| ATC | PilotEdge | your existing PilotEdge PTT |
| CAP mission net | Mumble | a different key — e.g. a spare yoke button |

This is the point, not an inconvenience. It is how the real aircraft works:
one radio to ATC, one to mission base, and a crew that has to manage both.

Also worth setting:

- **Audio Output > Positional Audio: off.** It is for games; on a radio net it
  makes people sound off to one side.
- **Audio Input > run the Audio Wizard** once. It sets input levels properly.
- If Mumble and PilotEdge fight over your headset, set Mumble's output to a
  different device, or use PilotEdge on your headset and Mumble on speakers.

## 4. Find your channel

```
CAP V-SAR
├── Briefing Room            gather here before the sortie
├── Mission Base             IC / AOBD / MRO internal coordination
├── Mission Net PRIMARY      base <-> aircrew. The working channel.
├── Mission Net ALTERNATE    overflow, or a second simultaneous sortie
├── Aircraft
│   ├── CAP-1 Intercom       crew-internal, aircraft 1
│   ├── CAP-2 Intercom
│   └── CAP-3 Intercom
└── Instructor - SET         scenario control and adjudication
```

**Where you sit:**

- **Mission base staff** — Mission Base for internal chat, Mission Net PRIMARY
  when working the aircrew.
- **Aircrew** — your aircraft's Intercom channel. The Mission Observer moves to
  Mission Net PRIMARY to make a report, then comes back. Or stays in Intercom
  and uses Shout (below).
- **Instructor / SET** — Instructor channel, and drop into others to listen.

You only hear the channel you are in. That is deliberate: it is what makes crew
coordination a skill rather than a group call.

**Shout** lets you transmit into another channel without leaving yours — right
click a channel > **Shout to this channel**, and bind it to a second key. An MO
can then work the mission net without leaving the crew intercom. Closest thing
to a real radio panel.

## 5. Get registered

Ask the exercise controller to **register** you after your first connection
(they right-click your name > Register). Registration ties your name to your
client certificate, so you keep the same identity every session and nobody else
can take your callsign.

---

## Radio discipline

**Every transmission begins and ends with "EXERCISE, EXERCISE, EXERCISE."**

It costs two seconds and it is the habit that keeps simulated traffic
unmistakable for the real thing. Practise it here so it is automatic.

**Mission traffic stays on the mission net.** Bearings, beacon reports, position
reports, tasking — all of it belongs here, never on the PilotEdge ATC
frequency. That is both realistic and a courtesy to the live controllers, who
are volunteers working real traffic for everyone else on the network.

**Nothing on this server is a real distress communication.** No part of CAP
V-SAR transmits on any real radio, and no simulated beacon is ever radiated.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Wrong server password" | Get the current one from the exercise controller; it changes if the server is rebuilt |
| Connects, nobody hears you | You are almost certainly not holding PTT, or PTT is bound to a key your sim has grabbed. Try a keyboard key first. |
| You hear nobody | Check you are in the same channel. You only hear your own channel. |
| Certificate warning every time | Accept and tick to remember; the server uses a self-signed certificate |
| Robotic or dropping audio | Settings > Audio Input, lower quality to ~40 kb/s; the server allows up to 72 kb/s but a poor uplink will not sustain it |
| Works on LAN, not from home | The server is reachable at the public address on 64738 TCP **and** UDP; a restrictive corporate or hotel network may block UDP, which degrades voice to TCP |
