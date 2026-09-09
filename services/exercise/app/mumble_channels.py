"""
Single source of truth for the CAP V-SAR Mumble channel tree (O-4).

Both scripts/provision_mumble.py (creates the channels and the Instructor/SET
ACL in mumble-server.sqlite) and radio.py (the browser net selector, which
looks channels up client-side by exact name via find_by_tree) read this, so
the two can no longer drift apart the way radio.py's own hardcoded four-name
copy could. Names here are the *actual* names already live in ms01's
mumble-server.sqlite, confirmed by inspecting it directly - notably
"Instructor - SET", not the "Instructor / SET" docs/MUMBLE_CHANNELS.md used
to say, which was itself a small drift this file also corrects.

See docs/MUMBLE_CHANNELS.md for the why. This file is the what.
"""
from __future__ import annotations

INSTRUCTOR_CHANNEL = "Instructor - SET"

TREE = {
    "name": "CAP V-SAR",
    "children": [
        {"name": "Briefing Room", "net": {"id": "briefing", "label": "BRIEFING"}},
        {"name": "Mission Base", "net": {"id": "base", "label": "MISSION BASE"}},
        {"name": "Mission Net PRIMARY", "net": {"id": "primary", "label": "PRIMARY"}},
        {"name": "Mission Net ALTERNATE", "net": {"id": "alternate", "label": "ALTERNATE"}},
        {"name": "Aircraft", "children": [
            {"name": "CAP-1 Intercom"},
            {"name": "CAP-2 Intercom"},
            {"name": "CAP-3 Intercom"},
        ]},
        {"name": INSTRUCTOR_CHANNEL},  # restricted; deliberately not a "net" - never offered to the browser radio
    ],
}


def browser_nets() -> list[dict]:
    """The subset of the tree radio.py exposes to the browser radio console -
    everything tagged "net". Order matches the tuple's declaration order,
    which is also the order the console lists them in."""
    result = []

    def walk(node):
        if "net" in node:
            result.append({"id": node["net"]["id"], "label": node["net"]["label"], "name": node["name"]})
        for child in node.get("children", []):
            walk(child)

    walk(TREE)
    return result


def walk_tree(node=None, parent_path: tuple[str, ...] = ()):
    """Yield (name, parent_path) for every node under the root, depth-first,
    root excluded - what a provisioner needs to create each channel under
    the right parent. parent_path is the chain of names above this node,
    root itself implicit and never included."""
    node = node or TREE
    for child in node.get("children", []):
        yield child["name"], parent_path
        yield from walk_tree(child, parent_path + (child["name"],))
