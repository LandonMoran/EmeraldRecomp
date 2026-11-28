# Playtest evidence

Everything in this directory is harness code and the runs it produced. The
**status** those runs support lives in one place: [`docs/PLAYABILITY_AUDIT.md`](../../docs/PLAYABILITY_AUDIT.md).
The harness itself (TCP commands, drivers, what still needs a device) is
documented in [`docs/PLAYTEST.md`](../../docs/PLAYTEST.md) and, for the gym and
environment puzzles, [`docs/PUZZLE_PLAYTEST.md`](../../docs/PUZZLE_PLAYTEST.md).

## How a transcript is produced

A run is **one harness process, one append-mode transcript**. The driver opens
the emulator over TCP (port 19892), loads a checkpoint, and drives the pad with
held directions; every line it records is either its own note (`[tag] ...`) or a
line the **game actually printed**, taken from the accessibility speech ring and
stamped with the utterance's frame (`[tag f143613] Door two steps south-east. ...`).

Two rules make the transcripts quotable as evidence:

- **The ring outlives a checkpoint load and its frame stamps restart**, so a
  session is given a monotonic `seq` floor at start-up; anything logged before
  the run began can never be quoted as this session's speech.
- **Nothing is inferred.** A claim of "the player bought five balls" is backed by
  a pocket read (`[(0, 4, 5)] (carrying 5)`, raw bytes quoted), not by a hope
  that the menu presses landed.

## The transcripts the audit quotes

| Transcript | What it proves |
| --- | --- |
| [`reports/travel-walk.txt`](reports/travel-walk.txt) | Route 101 ↔ Oldale Town walked both ways; `New area. Oldale Town.` / `New area. Route 101.` at the border |
| [`reports/catch-final.txt`](reports/catch-final.txt) | Catching, end to end in one session: five balls bought, counter exited, Route 116 reached, `A used POKé BALL!`, `Gotcha! POOCHYENA was caught!`, the Pokédex lines, and the pocket re-read 5 → 4 |
| [`reports/catch-party.txt`](reports/catch-party.txt) | The same run with the party read afterwards: `party count 1` → `party count 2`, the caught level 8 Pokémon in slot 1 beside the starter |
| [`reports/catch-pokeball.txt`](reports/catch-pokeball.txt) | The party dump taken straight after the first catch (three slots, third a level 3 Poochyena) |
| [`reports/travel-route-cues.txt`](reports/travel-route-cues.txt) | Travel by name: `Route 116 east.` before the crossing, `New area. Route 116.` after it; doors that say what they lead to; the sign cue and its text |
| [`reports/target-cue.txt`](reports/target-cue.txt) | The navigation-target cue: arm a tile, step onto it, `You have arrived.` |
| [`reports/cues-closeout.txt`](reports/cues-closeout.txt) | The `sign`, `item`, `target` and `ok` cue rows with the spoken line each one accompanies |
| [`reports/bag-items.txt`](reports/bag-items.txt) | Bag pockets and contents by name (`TMs and HMs. TM03, 1 of 7, 1 in the bag.`) |
| [`reports/cues.txt`](reports/cues.txt) | The raw `cue: <name> (<asset>) + speak: <line>` log the cue layer writes |
| [`reports/shop-catch.txt`](reports/shop-catch.txt) | Shopping and the first catch attempt, before the counter-exit fix |
| [`reports/rustboro-walk.txt`](reports/rustboro-walk.txt), [`reports/dewford-walk.txt`](reports/dewford-walk.txt), [`reports/fortree-walk.txt`](reports/fortree-walk.txt), [`reports/petalburg-walk.txt`](reports/petalburg-walk.txt) | The walk-and-fight gym runs: trainers, leaders, badges and TMs |
| [`reports/mauville-four-plates.txt`](reports/mauville-four-plates.txt), [`reports/mauville-wattson.txt`](reports/mauville-wattson.txt) | Mauville's four plates pressed in one visit, then Wattson beaten |
| [`reports/lavaridge-full-walk.txt`](reports/lavaridge-full-walk.txt), [`reports/lavaridge-flannery.txt`](reports/lavaridge-flannery.txt) | Lavaridge's pits, vents and ledges, then Flannery |
| [`reports/sootopolis-leader.txt`](reports/sootopolis-leader.txt), [`reports/mossdeep-leader.txt`](reports/mossdeep-leader.txt), [`reports/mossdeep-walk.txt`](reports/mossdeep-walk.txt) | The two water gyms' leaders, and the statue walk that stops short of a solution |

Newer transcripts keep the frame stamps the speech ring reported; older ones
were written before the `seq` floor existed, which is called out in the audit
wherever it matters.

## The drivers

| Script | What it does |
| --- | --- |
| [`catch_final.py`](catch_final.py) | Walk to the Mart, buy, leave the counter, reach grass, throw from the bag, catch, read the party back |
| [`travel_cues.py`](travel_cues.py) | The travel row and the sign / item / target / ok cue rows in one session |
| [`pad.py`](pad.py) | The TCP pad: input, scenes, nav, speech (`flush_speech` logs every new utterance once) |
| [`navwalk.py`](navwalk.py) | Walk loop with refused-edge learning, pad and battle guards |
| [`maps.py`](maps.py) | `map.bin` blocks, collision, object tiles, path finding |
| [`party.py`](party.py) | Reads `gPlayerParty` slot by slot; boosts stats for test parties and never the level byte |
| [`mossdeep_solve.py`](mossdeep_solve.py) | The Mossdeep statue model and search (see the audit for where it stops) |
| [`sootopolis_refight.py`](sootopolis_refight.py) | Re-fights Juan on the healed party so the badge, TM and Pokénav lines land in the transcript (the first capture wrote no speech) |
| [`checkpoints.py`](checkpoints.py) | Save-state checkpoints (`checkpoints/*.json` + `.state`) used to start runs near a puzzle |

The rest are older one-mechanic runners kept because the audit's gym rows were
produced with them.
