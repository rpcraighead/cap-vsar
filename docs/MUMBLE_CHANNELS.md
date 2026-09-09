# Mumble channel structure

**The channels below already exist**, and (O-4) that is no longer just true
of ms01's hand-provisioned database - it's true of any deployment.
`services/exercise/app/mumble_channels.py` is the single source of truth for
this tree; `scripts/provision_mumble.py` creates it (and the Instructor/SET
ACL below) directly in `mumble-server.sqlite`, idempotently, and
`scripts/deploy.sh` runs it on every deploy. Mumble has no config-file
channel definition, so - same as when this was done by hand - it works by
writing to the database with the server stopped.

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
└── Instructor - SET            restricted - scenario control and adjudication
```

(The tree above previously said "Instructor / SET" here while the setup steps
below already said "Instructor - SET" - the real name in the database. That
inconsistency is what `mumble_channels.py` now exists to prevent.)

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

`scripts/provision_mumble.py` now handles the channel tree and the
Instructor/SET ACL (deny `Enter` for `@all`, grant it back to an `instructor`
group it also creates) on every deploy. What's left, and can't be automated
because it requires knowing who's actually connecting:

1. Register participants as they first connect (right-click user ->
   **Register**) so identities persist between sessions.
2. Add the real instructor accounts to the **instructor** group (right-click
   user -> **Add to group**) once they've registered. Until this is done, no
   one - instructor included - can enter Instructor - SET; the deny applies
   to everyone until someone is explicitly a member of the group carved out
   from it.
3. Connect as **SuperUser** (right-click server -> **Change username**, using
   the SuperUser password from `.env`) if you need to do either of the above,
   or to inspect/adjust the provisioned ACL by hand.

Participant-facing instructions are in `docs/CONNECT.md` - that is the document
to hand to aircrew and mission base staff.

## Discipline

Every transmission on this server begins and ends with
**"EXERCISE, EXERCISE, EXERCISE."** It costs two seconds and it is the habit
that keeps simulated traffic unmistakable.
