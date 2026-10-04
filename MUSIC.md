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
