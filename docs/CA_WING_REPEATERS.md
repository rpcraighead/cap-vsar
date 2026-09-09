# California Wing repeater reference

Gathered 2026-09-08 from public radio-monitoring sources, **not** a CAP-published
list. Treat the national pair convention as solid; treat individual site
PL/NAC values as "probably right, worth confirming" — RadioReference's data
comes from hobbyist monitoring, not a CAP release, and there is an open forum
thread from people still chasing down accurate post-narrowband-transition
values for California. CAP's own site-by-site frequency list lives behind
member eServices access, not publicly.

| File / Source | What it is |
|---|---|
| [RadioReference — Civil Air Patrol (California)](https://www.radioreference.com/db/aid/1191) | Site table below, transcribed from here |
| [RadioReference Wiki — Civil Air Patrol](https://wiki.radioreference.com/index.php/Civil_Air_Patrol) | National repeater pair / PL / NAC conventions |
| [RadioReference Forums — CA narrowband transition search request](https://forums.radioreference.com/threads/california-civil-air-patrol-narrowband-transition-repeater-frequencies-search-request.161152/) | Evidence the CA list isn't fully nailed down even by hobbyists |
| [CAP National HQ — Communications Program](https://www.gocivilairpatrol.com/programs/emergency-services/radio) | Confirms scale (500+ VHF repeaters, dual analog/P25) but no site data |
| [California Wing — Locations](https://cawg.cap.gov/locations) | Wing unit locations, not repeater sites specifically |

## National repeater pair convention

CAP repeaters nationwide use one of two standard TX/RX pairs, dual-mode
(analog FM with a PL/CTCSS tone, or P25 digital using a NAC in place of the
tone on the same pair):

| Pair | Repeater TX | Repeater RX (input) |
|---|---|---|
| Primary | 148.1250 MHz | 143.5500 MHz |
| Secondary | 148.1500 MHz | 143.7000 MHz |

## California Wing sites

| Site | Location | Freq (MHz) | PL (analog) | NAC (P25) |
|---|---|---|---|---|
| R02 | Mt. Diablo (primary) | 148.150 | 162.2 | 656 |
| R39 | Mt. Diablo (secondary) | 148.125 | 162.2 | 656 |
| R08 | Mt. Tamalpais | 148.150 | 67.0 | 29E |
| R09 | Mt. Vaca | 148.125 | 156.7 | 61F |
| R14 | Ward Peak / Lake Tahoe | 148.150 | 146.2 | 68F |
| R16 | (location not listed) | 148.150 | 136.5 | 555 |
| R26 | Mt. St. Helena | 148.150 | 146.2 | 5B6 |
| R12 | Blue Ridge | 148.150 | 173.8 | 6CA |
| R14 | Saddle Peak | 148.150 | 167.9 | 68F |
| R20 | Mt. Palomar | 148.150 | 141.3 | 585 |
| R24 | Onyx (primary) | 148.150 | 127.3 | 4F9 |
| R61 | Onyx (secondary) | 148.125 | 127.3 | 4F9 |
| R28 | Oat Mountain | 148.150 | 156.7 | 61F |
| R35 | Palm Springs | 148.125 | 97.4 | 3CE |
| R62 | Santiago Peak (primary) | 148.150 | 186.2 | 746 |
| R59 | Santiago Peak (secondary) | 148.125 | 186.2 | 746 |

Note the two "R14" entries (Ward Peak/Lake Tahoe and Saddle Peak) share a
site number in the source table — either a numbering collision in Northern
vs. Southern California sub-lists, or a transcription issue upstream. Not
resolved here.

Not currently wired into any instrument or scenario — `cap-fm-tdfm-136b`
doesn't reference specific repeater sites today. This is reference material
for whenever the CAP mission net simulation wants real CA Wing channel names
instead of generic training frequencies.
