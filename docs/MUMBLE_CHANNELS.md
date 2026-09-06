# Mumble channel structure

**The channels below already exist** - they were inserted into the server
database at deploy time. Mumble has no config-file channel definition, so they
were created by writing to `mumble-server.sqlite` with the server stopped.

The one thing still to do by hand is the ACL on the instructor channel, in
step 4 below.

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

## Remaining setup

1. Connect as **SuperUser** (right-click server -> **Change username**), using
   the SuperUser password from `.env`.
2. On **Instructor - SET**, right-click -> **Edit** -> **ACL**: deny `Enter`
   for `@all`, then grant it to the instructor accounts or a group containing
   them. Until this is done the channel is visible to everyone.
3. Register participants as they first connect (right-click user ->
   **Register**) so identities persist between sessions.

Participant-facing instructions are in `docs/CONNECT.md` - that is the document
to hand to aircrew and mission base staff.

## Discipline

Every transmission on this server begins and ends with
**"EXERCISE, EXERCISE, EXERCISE."** It costs two seconds and it is the habit
that keeps simulated traffic unmistakable.
