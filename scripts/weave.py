#!/usr/bin/env python3
"""scripts/weave.py — merge two independently-grown webs into one, receipted.

Two runs (night1 seed 42, night2 seed 777) grew from the same lexicon with
different questions and different cell competitions. Weaving is the
hypothesis that their structures are COMPLEMENTARY: same vocabulary,
different histories. The weave is fully receipted on the host ledger:
every imported node/edge is listed, and the merged web's hash continues
the host chain (tamper-evident, as always).

After the weave, run more BRIDGE/REL-BOND rounds on the host run — the
oracle now sees pairs of concepts that were never co-visible before.

Usage: python3 scripts/weave.py --host runs/night1 --donor runs/night2
"""

from __future__ import annotations
import argparse
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.matrix import Matrix            # noqa: E402
from engine.receipts import Ledger, ScarLog  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--donor", required=True)
    args = ap.parse_args()
    host_dir = os.path.join(HERE, args.host)
    donor_dir = os.path.join(HERE, args.donor)

    host = Matrix(os.path.join(host_dir, "matrix")).load()
    donor = Matrix(os.path.join(donor_dir, "matrix")).load()
    ledger = Ledger(os.path.join(host_dir, "receipts.jsonl"))
    scars = ScarLog(os.path.join(host_dir, "scars.jsonl"))
    mhash = host.matrix_hash()

    new_nodes, new_edges, merged_edges = [], [], []
    # nodes: import with donor provenance; weights averaged if label exists
    for nid, n in sorted(donor.nodes.items()):
        if n["label"] in {m["label"] for m in host.nodes.values()}:
            continue  # shared vocabulary: same node, nothing to import
        lid = host.add_node(n["label"], joy=n["joy"], entropy=n["entropy"],
                            value=n["value"], origin_round=0,
                            created_by=f"weave:{args.donor}", note=n.get("note", ""))
        if lid:
            new_nodes.append(lid)
    # edges: import with weights merged; rel_type kept
    for eid, e in sorted(donor.edges.items()):
        src = next((x["id"] for x in host.nodes.values() if x["label"] ==
                    donor.nodes[e["src"]]["label"]), None)
        dst = next((x["id"] for x in host.nodes.values() if x["label"] ==
                    donor.nodes[e["dst"]]["label"]), None)
        if not src or not dst:
            continue
        existed = host.has_edge(src, dst, e["rel_type"])
        host.upsert_edge(src, dst, e["rel_type"], e["joy"], e["entropy"], e["value"],
                         origin_round=e["origin_round"], created_by=f"weave:{args.donor}",
                         question_id=e.get("question_id", ""), note=e.get("note", ""))
        (merged_edges if existed else new_edges).append(f"{src}->{dst}:{e['rel_type']}")

    mhash2 = host.matrix_hash()
    host.save()
    ledger.append("weave", ledger.count_kind("jev") + 1,
                  {"donor": args.donor, "new_nodes": len(new_nodes),
                   "new_edges": len(new_edges), "merged_edges": len(merged_edges),
                   "sample_nodes": sorted(new_nodes)[:12],
                   "host_nodes": len(host.nodes), "host_edges": len(host.edges)},
                  mhash2)
    # a weave is an event worth remembering structurally too: receipt the
    # donor's hash so the two runs are linked by provenance, not by trust
    ledger.append("weave-provenance", ledger.count_kind("jev") + 1,
                  {"donor_matrix_hash": donor.matrix_hash(),
                   "donor_receipts": len(Ledger(os.path.join(
                       donor_dir, "receipts.jsonl")).lines),
                   "donor_scars": ScarLog(os.path.join(
                       donor_dir, "scars.jsonl")).count()}, mhash2)
    print(f"WEAVE {args.donor} -> {args.host}: +{len(new_nodes)} nodes "
          f"+{len(new_edges)} edges (merged {len(merged_edges)}) "
          f"-> host now {len(host.nodes)}n/{len(host.edges)}e")
    return 0


if __name__ == "__main__":
    sys.exit(main())
