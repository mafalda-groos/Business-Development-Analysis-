"""
api/index.py — Vercel serverless Flask app.

Single function handles all /api/* routes. The dashboard is served as a static
index.html at the root. Reports are computed on-demand (no filesystem
persistence in serverless).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

# Project root is one level up from this file. Add it to import path so we
# can pull in the shared ingestion/scorer/report modules.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ingestion import run_ingestion
from scorer import LeadScorer
from report import generate_json

CONFIG_PATH = ROOT / "config.json"

app = Flask(__name__)


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _compute_leads(use_mock: bool = True):
    """Run the full ingestion + scoring pipeline and return actionable leads."""
    config = _load_config()
    candidates = run_ingestion(config, use_mock=use_mock)
    scored = LeadScorer(config).score_all(candidates)
    return [l for l in scored if l.tier != "Filtered Out"]


def _leads_payload(use_mock: bool = True):
    leads = _compute_leads(use_mock=use_mock)
    return generate_json(leads, datetime.now(timezone.utc))


@app.route("/api/leads")
def api_leads():
    try:
        payload = _leads_payload(use_mock=True)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return app.response_class(payload, mimetype="application/json")


@app.route("/api/run", methods=["POST", "GET"])
def api_run():
    use_mock = request.args.get("live", "false").lower() != "true"
    try:
        payload = _leads_payload(use_mock=use_mock)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return app.response_class(payload, mimetype="application/json")


@app.route("/api/cron")
def api_cron():
    """Hit by Vercel Cron weekly. Computes the report so warmup is done; in
    production this would push to email/Slack/storage."""
    try:
        leads = _compute_leads(use_mock=True)
        tier1 = sum(1 for l in leads if l.tier == "Tier 1")
        return jsonify({
            "status": "ok",
            "run_date": datetime.now(timezone.utc).isoformat(),
            "tier1_count": tier1,
            "total_leads": len(leads),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})
