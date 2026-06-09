#!/usr/bin/env python3
"""Weekly ingestion from data/master_queue.json.

- Pops the next N *pending* "master" candidates IN ORDER (curated skill→experience list).
- Pops M random "referent" candidates (hosts that run interesting skill retreats).
Each is scraped via scraper.process_url, which applies the skill-development relevance
gate (is_skill_development_retreat). Results update the queue entry status:
  added | rejected (gate said no / not a retreat) | failed (network/parse) .

Budget kill switch is inherited from _llm.call(). Stops cleanly on BudgetExceeded.

Usage:
  python scripts/queue_ingest.py --master 3 --referent 1
  python scripts/queue_ingest.py --master 5 --referent 0   # cheap week, go to 5
"""
import argparse
import json
import random
from pathlib import Path

from _llm import BudgetExceeded, log_run, now_iso
from scraper import process_url

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "data" / "master_queue.json"


def load_queue() -> list[dict]:
    return json.loads(QUEUE_PATH.read_text())


def save_queue(q: list[dict]):
    QUEUE_PATH.write_text(json.dumps(q, indent=2, ensure_ascii=False))


def pick(queue, pool, n, randomize=False):
    pending = [e for e in queue if e["pool"] == pool and e["status"] == "pending"]
    if randomize:
        random.shuffle(pending)
    return pending[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", type=int, default=3, help="Ordered curated candidates to ingest")
    ap.add_argument("--referent", type=int, default=1, help="Random referent candidates to ingest")
    args = ap.parse_args()

    if not QUEUE_PATH.exists():
        print("master_queue.json missing — run build_master_queue.py first.")
        return

    queue = load_queue()
    targets = pick(queue, "master", args.master) + pick(queue, "referent", args.referent, randomize=True)

    started = now_iso()
    total_cost = 0.0
    added = rejected = failed = 0

    for e in targets:
        e["attempts"] = e.get("attempts", 0) + 1
        try:
            r = process_url(e["url"])
            total_cost += r.get("cost", 0) or 0
            if r.get("slug"):
                e["status"] = "added"
                e["added_at"] = now_iso()
                e["note"] = r["slug"]
                added += 1
                print(f"✅ added  {e['url']} → {r['slug']}")
            else:
                e["status"] = "rejected"
                e["note"] = r.get("reason", "skipped")
                rejected += 1
                print(f"⏭️  reject {e['url']} ({e['note']})")
        except BudgetExceeded as ex:
            e["attempts"] -= 1  # don't penalize; budget, not the URL
            print(f"🛑 budget stop: {ex}")
            break
        except Exception as ex:
            # leave as pending if first failure (network), mark failed after 2 tries
            e["status"] = "failed" if e["attempts"] >= 2 else "pending"
            e["note"] = str(ex)[:140]
            failed += 1
            print(f"⚠️  fail   {e['url']} ({e['note']})")

    save_queue(queue)
    remaining = sum(1 for x in queue if x["status"] == "pending")
    log_run(
        agent_name="queue_ingest", started_at=started, finished_at=now_iso(),
        tokens_in=0, tokens_out=0, cost_usd=total_cost,
        items_processed=added, status="ok",
        errors=f"added={added} rejected={rejected} failed={failed} remaining={remaining}",
    )
    print(f"\nqueue_ingest done: +{added} added, {rejected} rejected, {failed} failed, "
          f"{remaining} pending. cost ${total_cost:.4f}")


if __name__ == "__main__":
    main()
