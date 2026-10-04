# MUSIC.md — how the weights become sound

Every piece is a deterministic function of receipted run state. Rewind the
run and replay: the same music comes back — except the percussion, which
re-emits from the STICKY scar log, so even after a rewind the failures stay
audible. Scars survive rewind in the mix the same way they survive in the
mind.

## Files in a run (`runs/<name>/music/`)

| file | what it is |
|---|---|
| `seg_XXXX-XXXX.mid` | one segment per 8 rounds, emitted live by the runner |
| `full_suite.mid` | the whole run, one bar per round |
| `jev_drone.mid` | the web's balance as a sustained tremolo drone |
| `die_etudes.mid` | 20 bars, one per die face |
| `moth_qrc.mid` | the moth as musician: qrc-midi-v1 quantum MIDI, or a moth-bit-seeded etude (receipted fallback) |

## Mappings

**Round chord** (`round_chord`): root = sha256(matrix_hash+round) mod 12 on
C3..B3; mode = the round's dominant relation type (`contradicts→phrygian`,
`resonates→lydian`, `transforms→dorian`, `echoes→pentatonic`, `tminus→minor`,
`supports→major`…); voicing = the mutation's value mapped to scale degrees;
velocity = 40 + value×80; duration = (1−entropy) beats. High-entropy rounds
literally decay faster.

**JEV melody** (`jev_melody`): the walker's path → pentatonic degrees by node
name hash. The granular chain-of-thought — place-to-place motion instead of
internal narration — as an audible line.

**Scar hit** (`scar_hit`): channel 10 percussion (snare/hat alternating),
one per sticky scar at its round position. The failures are the beat.

**Cell duet** (`duet_note`): each accepted generator proposal becomes a note
in its persona's voice — weaver on channel 3, trickster on channel 4. Higher
value sings higher; higher entropy shortens the note. Competitive
construction as two voices trading phrases.

**Drone** (`jev_drone`): one re-articulated pad tone per round; velocity
tremolo follows the web's `balance` metric — you can hear the web settle.

**Die Etudes** (`die_etude`): face 1–5 (scar_backoff) plays phrygian falling
figures; 6–9 (entropy_jitter) scattered fourths; 10–13 (node_fission)
mirrored pairs; 14–17 (edge_rewire) wide leaps; 18–19 (moth_edge) a six-note
curve; 20 (double_or_bust) everything at once.

## Provenance

No hand-picked notes anywhere: every byte of every file traces to a receipt
in `receipts.jsonl` / `scars.jsonl` / `leaderboard.csv` via the mappings
above. The composer is the run.

## Wave 2 forms (Task 71-b)

Four stricter shapes, composed from the existing night1/night2 ledgers by
`scripts/music_wave2.py` (engine's `MidiWriter` and pitch math reused; runs/
untouched). Same law as wave 1: rewind the run, the music comes back.

**`music/scar_counterpoint.mid`** — 65 night1 scars against 19 night2 scars,
first-species counterpoint. Cantus firmus (ch0, phrygian on E3): one whole
note per night1 scar in round order; pitch degree = round(entropy×13.99),
where a scar's receipted entropy is the mean of its own payload floats
(`distinct`/`essential`/`bridges`/`repairable`/`suspicious`/`fits`) — the 27
float-less scars (cell-indeterminate: payload is only `family`/`qid` or
`qid`/`why`) take the web's disorder `1−balance` at their round from
`leaderboard.csv` — which is why the CF keeps returning to its reciting
tone: indeterminate scars pin the line to the final. Counterpoint (ch1):
night2's 19 scars cycled against them (index i mod 19, i.e. scar round
numbers matched modulo the other voice's count); the vertical interval is
chosen by `(round_n1 + round_n2) mod 4` → 3rd/5th/6th/8ve, forced into
contrary motion against the CF (range-clamp falls back to the flipped
interval), with parallel perfects avoided by advancing the consonance slot.
It fits the story because scars are the ledger's stubborn dissonances — yet
paired with the second night's failures they lock into consonance: two runs'
rejections resolve against each other, 65 bars at 100bpm (~156s), 130 notes.

**`music/ledger_canon.mid`** — strict real canon at the fifth over the raw
receipt stream. Leader (ch0, D dorian): night1 `receipts.jsonl` lines 1–32
(all receipt types: oracle/mutation/cell/jev/run-end/oracle-fail), the first
hex byte of each line's hash-chained `hash` → degree `byte mod 7`, one
quarter-note each. Follower (ch1): the identical 32 hashes transposed
exactly +7 semitones (D dorian → A dorian, asserted in code), entering 8
sixteenths late — the ledger imitating itself, verbatim, at the dominant.
Free bass (ch2): night2's first 32 receipts, same hash→degree treatment, as
running eighths two octaves down. A hash-chained ledger is already a canon
(each line repeats its predecessor in disguised form); this just lets you
hear it — 96 notes, ~23s at 88bpm.

**`music/jev_tension_fugue.mid`** — three-voice fugue over the JEV walker
ledger (`leaderboard.csv` carries no JEV columns, so the 106 `jev` receipts
are the score; node weights read from `matrix/nodes.csv`, 99 rows). Step =
one eighth-note per walker receipt. Subject (ch0): the walker's node `joy`
per position, degree = round(joy×13.99), D4. Answer (ch1): the `value`
column inverted (1−value) at the dominant A4, entering at position 16.
Countersubject (ch2): the `entropy` column on D3, entering at position 32.
Episodes fire on receipted degree-zero moments — the walker standing on a
graph-degree-zero node of `edges.csv` (the web's only one, `loop`,
origin_round 0, visited once at position 15) or a walk that never leaves its
start node (26 single-node walks) → 26 episode steps where the subject plays
its melodic inversion about the modal fifth (degree → 16−degree). Tension is
the fugue's native form — a subject stated, answered, and woven against
itself is exactly what the JEV web does to joy/value/entropy — 270 notes,
~31s at 104bpm.

**`music/rewind_palinode.mid`** — the palinode: the song that un-composes
itself. Forward pass: night1 rounds 8→40 (33 bars) as wave-1 `round_chords`
— root = sha256 of the round's final `matrix_hash`, mode from the round's
receipted relation (`rel`) → `REL_TO_MODE`, else `sound.csv` mode telemetry,
else the dominant mutation verb (delta→dorian, confirmed→major, fun→lydian,
brightness→mixolydian, bridges→pentatonic, fits→phrygian), voicing from the
round's payload floats, duration from its entropy (mutation `entropy`, else
1−balance). Hinge: the round-40 rewind receipt itself (ledger idx 265,
`scars_preserved: 22, to_round: 40`) — root from its `matrix_hash`, voiced
by 22/40, plus one raw channel-10 accent: the fold, audible. Retrograde:
rounds 40→8, each chord's voicing reversed (`vals[::-1]`) — the same
receipted pitches un-playing in reverse order. On top, the scar-hit
percussion (night1 scars, rounds 8–40: 15 hits per pass, 30 total) is NOT
retrograded: it re-sounds at each pass's bar position in forward round
order, because scars are sticky — rewind the run and the music un-writes
itself, but the failures keep beating. 164 notes, ~143s at 112bpm.

Validation: `scripts/music_wave2.py` re-parses every file with a minimal SMF
reader (MThd header + division 480, MTrk event walk incl. running status,
End-of-Track required, no trailing bytes) and asserts all four parse before
reporting note counts and durations.

## The quantum arrangement (engine.moth.qrc_midi, first night live)

`music/jev_path_qrc_triple.mid` — the triple web's own chain-of-thought
(96 path nodes from night1's 118 JEV walks over the woven night1+night2+night3
webs), pentatonic-mapped like `jev_melody`, uploaded through the moth assets
flow, learned by the qrc-midi-v1 quantum reservoir (training_loss 2.56 → 1.47
→ 1.16 — it genuinely learned), and returned as a fresh arrangement. The
learned model itself is kept as an artifact: `runs/night1/qrc-model-triple.json`
(vocabulary, readout_weights, internal_state). Receipt `qrc-midi` in the
night1 ledger carries the full job provenance (asset id, job id, latency).
The 123-byte result is small; the CONTRACT it proves is not — see
docs/MOTH-PROBE.md for the 97-receipted-request journey to this closed loop.
