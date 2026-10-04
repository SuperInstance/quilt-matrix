# quilt-matrix — the external mind

A spreadsheet-viewable neural network of relational weights that model cells
ask questions into, bounce around, and sonify. Part of the SuperInstance
quilt-growing sprint (Wave-69+).

## The thesis

Stop letting a giant model *feel* an answer internally and then rationalize
it after the fact. Instead:

- **The parameters live OUTSIDE the agent** — `matrix/nodes.csv` and
  `matrix/edges.csv` are the only real memory. Open them in any spreadsheet.
- **The thinker is decomposed**: small fast 8B-class cells (context-starved
  on purpose — they must read their *paper*: ≤6 visible rows) propose;
  the typesafe.ai System One oracle answers typed questions whose answers
  ARE the relational weights; a mechanical bot (pure Python, zero deps,
  this repo) transcribes, gates, and receipts everything.
- **Granular chain-of-thought**: the JEV walker's path through the graph is
  thinking made of place-to-place motion, not internal narration — and the
  path is literally a melody (see `engine/music.py`).
- **Sticky evolution** (Wave-69 invariants): append-only hash-chained
  receipts; scars survive rewind; the Die Engine (pure-function d20, seeded
  by REAL mothquantum quantum bits when available) turns deadlock into
  structural drift instead of exceptions; the spec gate refuses to compile
  what the pre-registered spec does not cover.

## The question index (the vast part)

`questions/index.json` — 10 families, 701+ instantiated question instances
(`questions/build_pool.py`), each with a **pre-registered spec** whose
`spec_sha` is sealed before any round runs. Families: REL-BOND, DECOMP,
BRIDGE, TENSION, TMSEQ, SOUND, MOTHDRIFT, GUARD, ECHO, PLAY. See
[questions/INDEX.md](questions/INDEX.md).

## Run it

```bash
source ../.env.keys                    # TYPESAFE_API_KEY, MOTH_API_KEY, CF token
python3 questions/build_pool.py runs/night1 42
python3 scripts/run_rounds.py --run runs/night1 --rounds 16 --push-every 8
python3 scripts/run_rounds.py --run runs/night1 --rewind-to 8   # sticky rewind
```

Round flow: sample question → mechanical spec gate → (generator families:
two cells compete, weaver vs trickster) → typesafe judges → mechanical bind
writes the weights → Die Engine on deadlock → one JEV bounce → music segment
every 8 rounds → snapshot every 8 → receipts all the way down.

## Layout

```
engine/matrix.py      the two-sheet external brain (nodes/edges CSV)
engine/receipts.py    hash-chained ledger + STICKY scars + snapshot/rewind
engine/die.py         pure-function d20 + structural drift moves
engine/jev.py         the mechanical walker (joy/value steers, entropy wanders)
engine/typesafe_q.py  System One oracle client (noul/choice/score)
engine/moth.py        mothquantum: quantum entropy (coin-toss-v1) + qrc-midi
engine/cells.py       the decomposed generator cells (CF-8b live; groq relay ready)
engine/music.py       zero-dep SMF writer + weight→sound mappings
questions/            THE VAST QUESTION INDEX (families + specs + pool builder)
scripts/run_rounds.py the marathon runner (competitive construction)
runs/<name>/          receipts.jsonl · scars.jsonl · snapshots/ · music/ · pool.jsonl
tests/                48 zero-dep unittest proofs
```

## CI

`.github/workflows/ci.yml`: `python -m compileall` + full unittest suite.
Local-first: everything green before push (wave-67 discipline).
