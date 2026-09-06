# Mumble channel structure

Channels are created once, by hand, after first start. Mumble has no
config-file channel definition, so this is a five-minute setup with the
Mumble desktop client connected as **SuperUser** (password in `.env`).

```
CAP V-SAR                       (root)
├── Briefing Room               everyone gathers here pre-sortie
├── Mission Base                IC / AOBD / MRO internal coordination
├── Mission Net PRIMARY         base <-> aircrew. The working channel.
├── Mission Net ALTERNATE       overflow, or a second simultaneous sortie
├── Aircraft
│   ├── CAP-1 Intercom          crew-internal for aircraft 1
│   ├── CAP-2 Intercom
│   └── CAP-3 Intercom
└── Instructor / SET            restricted - scenario control and adjudication
```

## Why this shape

The design in the implementation plan calls for one channel per simulated
frequency plus a per-aircraft intercom. **Mission Net PRIMARY** is the
frequency base and aircrew share; the **Intercom** channels are what a crew
talks on among themselves without cluttering the net - which is exactly the
split in the real aircraft.

**ATC is not here.** Air traffic control is PilotEdge, on a separate
application with its own audio device and push-to-talk. Two radios, two PTT
keys, as in the aeroplane. Keeping mission traffic off the ATC frequency is
both realistic and a courtesy to the controllers.

## Setup steps

1. Connect with the Mumble client to `192.0.2.151:64738`, server password
   from `.env`.
2. Log in as SuperUser: right-click the server -> **Change username** to
   `SuperUser`, use the SuperUser password from `.env`.
3. Right-click the root channel -> **Add** for each channel above.
4. On **Instructor / SET**, set ACL to deny `Enter` for `@all` and grant it to
   a group containing the instructor accounts.
5. Register the regular participants (right-click user -> **Register**) so they
   keep identities between sessions.

## Discipline

Every transmission on this server begins and ends with
**"EXERCISE, EXERCISE, EXERCISE."** It costs two seconds and it is the habit
that keeps simulated traffic unmistakable.
