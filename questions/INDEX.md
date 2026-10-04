# The Vast Question Index — human companion

The machine-readable index is [`index.json`](index.json); the pool builder is
[`build_pool.py`](build_pool.py). This doc explains WHY each family asks what
it asks. Every family's `spec` is **pre-registered** — sealed as `spec_sha`
(computed over `canon(spec)`) before any round runs; the runner refuses a
family whose sealed hash differs from the pool row's (anti-post-hoc law,
inherited from the discovery-skin regression of Wave-67).

The oracle is typesafe.ai **System One** (`POST /v1/systemone`, model
`jev-latest`): typed questions — `noul` (yes/no probability), `choice`
(criteria dict), `score` (rubric). One batched call per question instance;
the answers ARE the weights. The oracle never touches the matrix; the
mechanical bot transcribes.

## Families

| family | kind | asks | answers become |
|---|---|---|---|
| REL-BOND | edge | resonance? contradiction? strength rubric? | one weighted edge (joy/entropy/value) |
| DECOMP | node | cell proposes sub-ideas → essential? distinct? | new nodes + feeds edges (self-decomposition) |
| BRIDGE | edge+node | does C genuinely bridge A and B? how load-bearing? | bridge node + 2 bridges edges |
| TENSION | audit | is this recorded relation suspicious? repairable? | sticky scar + entropy bump, or confirm bump |
| TMSEQ | edge | must stage X come before stage Y? | ordered t-minus dependency chain |
| SOUND | params | mode? brightness? density? velocity? | sound.csv rows → the music engine |
| MOTHDRIFT | edge | is this quantum-chosen neighbor worth a link? | echoes edges with moth-entropy weights |
| GUARD | flag | is this node load-bearing enough to guard? | guards.csv → future writes need provenance |
| ECHO | audit | same relation, two phrasings — do they agree? | echo_delta → scar (oracle-instability) or confirm |
| PLAY | game | which game? was the pattern joyful? | games.csv + plays edges (play is epistemic) |

## Expansion law

Families instantiate over (a) the 48-word lexicon and (b) the matrix's own
labels — **the quilt grows questions from its own nodes**. Pool size is
receipted per run (`pool.jsonl`); ≥400 asserted in tests; 701 at seed 42
with a fresh lexicon matrix.

## Competitive construction

Generator families (DECOMP, BRIDGE, TMSEQ) put TWO small cells in
competition each round — **weaver** (strongest missing connection) vs
**trickster** (strangest still-true connection). Both read only their paper
(≤6 rows); the mechanical gate filters; the oracle judges; the winner's
proposal is transcribed; the loser becomes a sticky scar. Failures are
citizens, not noise — and they become percussion in the music.
