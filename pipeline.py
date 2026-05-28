"""
pipeline.py — Main entry point for the L&Co Business Development Pipeline.

Usage:
    python pipeline.py                     # Run with mock data, generate all reports
    python pipeline.py --live              # Use live RSS feeds instead of mock data
    python pipeline.py --tier1-only        # Print only Tier 1 leads to stdout
    python pipeline.py --no-save           # Score and display without writing files
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from ingestion import run_ingestion
from scorer import LeadScorer
from report import save_reports, generate_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def print_summary(scored_leads, tier1_only: bool = False):
    tier1 = [l for l in scored_leads if l.tier == "Tier 1"]
    tier2 = [l for l in scored_leads if l.tier == "Tier 2"]
    watch  = [l for l in scored_leads if l.tier == "Watch List"]

    def _print_section(title, leads):
        if not leads:
            return
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")
        for lead in leads:
            c = lead.company
            rev = c.annual_revenue_millions
            rev_str = f"${rev/1000:.1f}B" if rev >= 1000 else f"${rev:.0f}M"
            print(f"\n  [{lead.score:.0f}/100]  {c.name}")
            print(f"  {'─'*50}")
            print(f"  HQ:       {c.hq_city}, {c.hq_state or c.hq_country}")
            print(f"  Revenue:  {rev_str}  |  {c.industry}")
            print(f"  Persona:  {lead.target_persona}")
            print(f"  Why Now:  {lead.why_now[:140]}...")
            print(f"  Scores:   Location {lead.breakdown.location_score:.0f}/25  "
                  f"Financial {lead.breakdown.financial_score:.0f}/25  "
                  f"Partnership {lead.breakdown.partnership_score:.0f}/30  "
                  f"Recency {lead.breakdown.recency_score:.0f}/20")

    _print_section("🔴  TIER 1 — HIGH-PRIORITY OUTREACH (Score > 80)", tier1)
    if not tier1_only:
        _print_section("🟡  TIER 2 — ACTIVE PIPELINE (Score 60–80)", tier2)
        _print_section("🟢  WATCH LIST (Score 40–60)", watch)

    print(f"\n{'─'*70}")
    print(f"  PIPELINE SUMMARY  |  {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    print(f"  Tier 1: {len(tier1)}  |  Tier 2: {len(tier2)}  |  Watch List: {len(watch)}")
    print(f"{'─'*70}\n")


def run(args):
    log.info("Loading config from %s", CONFIG_PATH)
    config = load_config()

    # --- Ingestion ---
    log.info("Starting ingestion (mode=%s)", "live RSS" if args.live else "mock data")
    candidates = run_ingestion(config, use_mock=not args.live)
    log.info("Ingestion complete: %d candidate companies", len(candidates))

    # --- Scoring ---
    scorer = LeadScorer(config)
    scored = scorer.score_all(candidates)
    actionable = [l for l in scored if l.tier != "Filtered Out"]
    log.info(
        "Scoring complete: %d actionable leads (Tier 1: %d, Tier 2: %d, Watch: %d)",
        len(actionable),
        sum(1 for l in actionable if l.tier == "Tier 1"),
        sum(1 for l in actionable if l.tier == "Tier 2"),
        sum(1 for l in actionable if l.tier == "Watch List"),
    )

    # --- Console output ---
    print_summary(actionable, tier1_only=args.tier1_only)

    # --- File output ---
    if not args.no_save:
        paths = save_reports(actionable, config["output"])
        log.info("Reports saved:")
        for fmt, path in paths.items():
            log.info("  %-10s  %s", fmt, path)

    return actionable


def main():
    parser = argparse.ArgumentParser(
        description="L&Co Business Development Pipeline — Weekly Lead Scoring"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Pull from live RSS feeds instead of mock data"
    )
    parser.add_argument(
        "--tier1-only", action="store_true",
        help="Only print Tier 1 leads to stdout"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Score and display but do not write report files"
    )
    args = parser.parse_args()

    try:
        run(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as exc:
        log.error("Pipeline failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
