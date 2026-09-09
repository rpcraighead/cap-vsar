THREE MODELS, ONE CODEBASE
How CAP V-SAR got built by Claude, Codex, and Gemini sharing the same brain

People ask how much of CAP V-SAR is "AI-written," as if that's a single
number. The more interesting answer is that it wasn't built by one AI at
all — it was built by three different coding assistants, working the same
project without a human relaying context between them by hand, and the thing
that made that possible wasn't any of the models themselves. It was a shared
knowledge base and a shared habit of writing everything down.

THREE ASSISTANTS, NOT ONE

Claude Code and OpenAI Codex both run as extensions inside VS Code, sitting
next to the actual project files. Gemini runs in Google's Antigravity IDE,
a separate editor built around the same kind of agentic workflow. Different
front ends, different vendors, none of them aware the others exist by
default. Left alone, that's a recipe for three divergent versions of the
truth — each tool making locally reasonable decisions that quietly
contradict each other three files away.

What ties them together instead is that none of them work from their own
private notes. They all read from, and write back to, the same two things:
a shared knowledge base, and a shared changelog checked into the project
itself.

RAGD: ONE KNOWLEDGE BASE, MANY CONSUMERS

The knowledge base is a small self-hosted service called `ragd` — a vector
database (Qdrant under the hood) that holds the project's notes, decisions,
manuals, and prior build logs, indexed once. Retrieval is *hybrid*: a dense
embedding search for meaning ("what did we decide about wing shadowing")
alongside a sparse keyword search for exact terms ("cap/df/rx_open"), merged
into one ranked result. Right now the main vault holds just under 20,000
indexed chunks.

The important design decision isn't the vector math, it's that there's only
one of these. Before `ragd`, there were three separate, overlapping retrieval
setups — because three tools each defaulted to bringing their own. That meant
three ingestion pipelines and three slightly different answers to the same
question. Collapsing that into one indexed corpus, exposed over a standard
interface (MCP), means every assistant is quoting from the same source of
truth instead of three private, drifting copies of it. Adding a new
consumer — a different tool, a different session — is a config change, not a
new pipeline.

Just as important is what tells each assistant to actually *use* it. A
standing project file (`CLAUDE.md`, and its equivalent for the other tools)
is loaded into every session automatically and says, in effect: this corpus
is the primary reference, search it before answering, cite what you used,
and its contents outrank your own training data on anything it covers.
Without that instruction, a model will happily answer an infrastructure or
implementation question from generic knowledge instead of this project's
actual, specific history — and generic knowledge is exactly what doesn't
know that this project's wing-null loss cap is 24 dB, or why.

THE HANDOFF: HOW WORK ACTUALLY MOVED BETWEEN MODELS

`ragd` is the long-memory layer — durable facts and past decisions. The
moment-to-moment coordination happened somewhere much lower-tech: a
`CHANGELOG.md` at the root of the repository that every session, human or AI,
is expected to read before touching anything and update before finishing.

Here's what that looked like on one real piece of work. Gemini, in
Antigravity, built out the Mission Observer instrument panel — a full Air
Manager layout wiring a G1000 MFD, an audio panel, and both DF units
together — and logged what it had built and why.

Claude picked that panel up cold in a later session, with no memory of
Gemini's reasoning beyond what was written down, and did what a human
reviewer does with someone else's pull request: read the log for context,
then checked the actual artifact against Air Manager's own licensing rules
and against the sandbox's runtime log. That review caught two real defects —
a license-tier mismatch that would have made Air Manager treat
locally-authored content as paid marketplace content, and a reentrancy bug
where a debounced redraw callback could re-enter Air Manager's rendering
engine and crash it. Both got fixed, both got verified independently (a
small `ctypes` harness against the real Lua runtime, since the GUI itself
wasn't available to test against), and both got written back into the same
changelog Gemini had started. Codex, meanwhile, was working a completely
different part of the same tree under the same convention — DF propagation,
in this case — without needing to know any of that had happened.

None of these three tools can see inside each other's context window or
their intermediate mistakes. They have no direct channel to each other. The
changelog and the corpus are what stand in for that: every claim either one
writes down is something the *next* reader — AI or human — can independently
verify against the actual code and the actual runtime, not just take on
faith. That is an old idea (the same reason a well-run engineering team
writes things down instead of relying on tribal knowledge) applied to a new
kind of team.

THE FORCE MULTIPLIER IS THE LOOP, NOT THE MODEL

None of this replaces a human in the loop — it changes what the human is
for. Across this project that's meant flying the simulator, listening to
whether a DF null actually happens on the correct wing, checking a faceplate
against the manual it's supposed to match, noticing when something is
technically working but wrong in a way no test would catch. That feedback
goes back into the same changelog and the same corpus the models already
read from, which is what makes it compound instead of evaporating at the end
of a session.

That's the actual force multiplier: not three models instead of one, but a
tester and engineer's judgment amplified across three independent workers
that all start from the same ground truth and hand off through a record
anyone — human included — can audit. One assistant with a good memory is
useful. Three assistants that read each other's homework, and a human who
keeps them honest against the real airplane, is a different order of
throughput.

TRY IT YOURSELF

None of this needs exotic infrastructure. The floor is a markdown changelog
in the repo that every session is expected to read first and correct in
place when it's wrong — that alone catches most silent divergence. `ragd` is
the upgrade once there's enough institutional knowledge that no single
changelog can hold it: one indexed corpus, one retrieval interface, as many
consumers as you have tools.

---
*Built with Claude Code, Codex, and Gemini working the same codebase, grounded
against the same corpus. Lab documented at rpc-cyberflight.com.*
