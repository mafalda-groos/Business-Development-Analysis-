"""
dashboard.py — Local Flask web dashboard for the L&Co Business Development Pipeline.

Usage:
    python dashboard.py
    Then open http://localhost:5050 in your browser.

Requires: pip install flask
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from flask import Flask, render_template_string, jsonify, request
except ImportError:
    print("Flask is required for the dashboard. Run:  pip install flask")
    sys.exit(1)

from ingestion import run_ingestion
from scorer import LeadScorer, ScoredLead
from report import save_reports

log = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent / "config.json"

app = Flask(__name__)
_cached_leads: list[ScoredLead] = []
_last_run: datetime | None = None


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(use_mock: bool = True) -> list[ScoredLead]:
    global _cached_leads, _last_run
    config = load_config()
    candidates = run_ingestion(config, use_mock=use_mock)
    scorer = LeadScorer(config)
    scored = scorer.score_all(candidates)
    _cached_leads = [l for l in scored if l.tier != "Filtered Out"]
    _last_run = datetime.now(timezone.utc)
    save_reports(_cached_leads, config["output"])
    return _cached_leads


# ---------------------------------------------------------------------------
# HTML template — self-contained, no external dependencies
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>L&amp;Co — Business Development Pipeline</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --black:   #0a0a0a;
      --white:   #fafafa;
      --cream:   #f5f0e8;
      --red:     #c0392b;
      --amber:   #d4860a;
      --green:   #27a155;
      --mid:     #555;
      --light:   #e8e2d8;
      --card-bg: #ffffff;
      --radius:  6px;
      --font:    'Georgia', serif;
      --mono:    'Courier New', monospace;
    }

    body {
      font-family: var(--font);
      background: var(--cream);
      color: var(--black);
      min-height: 100vh;
    }

    header {
      background: var(--black);
      color: var(--white);
      padding: 28px 48px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 3px solid #222;
    }

    header h1 {
      font-size: 1.6rem;
      font-weight: normal;
      letter-spacing: 0.06em;
    }

    header h1 span { color: #aaa; font-size: 0.85rem; margin-left: 16px; }

    .run-btn {
      background: var(--white);
      color: var(--black);
      border: none;
      padding: 10px 24px;
      font-family: var(--mono);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      cursor: pointer;
      border-radius: var(--radius);
      transition: opacity 0.15s;
    }
    .run-btn:hover { opacity: 0.8; }
    .run-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    .meta-bar {
      background: #1a1a1a;
      color: #888;
      font-family: var(--mono);
      font-size: 0.72rem;
      letter-spacing: 0.06em;
      padding: 8px 48px;
    }

    main { max-width: 1280px; margin: 0 auto; padding: 36px 48px 80px; }

    .stats-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      margin-bottom: 40px;
    }

    .stat-card {
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 20px 24px;
      border-left: 4px solid;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .stat-card.tier1 { border-color: var(--red); }
    .stat-card.tier2 { border-color: var(--amber); }
    .stat-card.watch { border-color: var(--green); }
    .stat-card .number { font-size: 2.4rem; font-weight: bold; }
    .stat-card .label { font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.1em; color: var(--mid); margin-top: 4px; }

    .section-title {
      font-size: 1rem;
      font-family: var(--mono);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--mid);
      margin: 32px 0 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--light);
    }

    .lead-card {
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 24px 28px;
      margin-bottom: 16px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      border-left: 4px solid;
      transition: box-shadow 0.15s;
    }
    .lead-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
    .lead-card.tier1 { border-color: var(--red); }
    .lead-card.tier2 { border-color: var(--amber); }
    .lead-card.watch  { border-color: var(--green); }

    .lead-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 12px;
    }

    .company-name { font-size: 1.25rem; font-weight: bold; }

    .score-pill {
      font-family: var(--mono);
      font-size: 0.85rem;
      font-weight: bold;
      padding: 4px 12px;
      border-radius: 20px;
      color: white;
    }
    .score-pill.tier1 { background: var(--red); }
    .score-pill.tier2 { background: var(--amber); }
    .score-pill.watch  { background: var(--green); }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px 16px;
      margin-bottom: 14px;
      font-size: 0.82rem;
    }
    .meta-grid .field { color: var(--mid); font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.06em; }
    .meta-grid .value { font-weight: normal; }

    .why-now {
      background: var(--cream);
      border-radius: 4px;
      padding: 10px 14px;
      font-size: 0.82rem;
      line-height: 1.6;
      margin-bottom: 12px;
      border-left: 2px solid var(--light);
    }
    .why-now strong { font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.08em; color: var(--mid); display: block; margin-bottom: 4px; }

    .score-bar-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .score-segment {
      font-family: var(--mono);
      font-size: 0.68rem;
      letter-spacing: 0.05em;
      color: var(--mid);
    }

    .articles {
      margin-top: 10px;
      font-size: 0.78rem;
    }
    .articles a { color: var(--black); text-decoration: underline; }
    .articles .art-meta { color: var(--mid); font-family: var(--mono); font-size: 0.68rem; }

    .empty { color: var(--mid); font-style: italic; padding: 20px 0; }

    #status-msg { font-family: var(--mono); font-size: 0.75rem; color: #888; padding: 8px 48px; background: #f0ebe0; display: none; }
  </style>
</head>
<body>

<header>
  <h1>L&amp;Co <span>Business Development Pipeline</span></h1>
  <button class="run-btn" id="refreshBtn" onclick="refreshPipeline()">↻ Run Pipeline</button>
</header>
<div class="meta-bar" id="metaBar">Loading...</div>
<div id="status-msg"></div>
<main id="main-content">
  <p class="empty">Loading pipeline data...</p>
</main>

<script>
  function tierClass(tier) {
    if (tier === "Tier 1") return "tier1";
    if (tier === "Tier 2") return "tier2";
    return "watch";
  }

  function renderLeads(data) {
    const { leads, summary, run_date } = data;
    const dt = new Date(run_date);
    document.getElementById("metaBar").textContent =
      `Last run: ${dt.toUTCString()}  |  Tier 1: ${summary.tier1_count}  Tier 2: ${summary.tier2_count}  Watch: ${summary.watch_count}`;

    const tier1 = leads.filter(l => l.tier === "Tier 1");
    const tier2 = leads.filter(l => l.tier === "Tier 2");
    const watch = leads.filter(l => l.tier === "Watch List");

    let html = `
      <div class="stats-row">
        <div class="stat-card tier1"><div class="number">${summary.tier1_count}</div><div class="label">Tier 1 — High Priority Outreach</div></div>
        <div class="stat-card tier2"><div class="number">${summary.tier2_count}</div><div class="label">Tier 2 — Active Pipeline</div></div>
        <div class="stat-card watch"><div class="number">${summary.watch_count}</div><div class="label">Watch List</div></div>
      </div>
    `;

    function renderSection(title, tierLeads, cls) {
      if (!tierLeads.length) return "";
      let s = `<div class="section-title">${title}</div>`;
      for (const l of tierLeads) {
        const b = l.score_breakdown;
        const arts = (l.triggering_articles || []).slice(0, 2)
          .map(a => {
            const d = a.published ? new Date(a.published).toLocaleDateString("en-US",{month:"short",day:"numeric"}) : "";
            return `<div><a href="${a.url}" target="_blank" rel="noopener">${a.title.slice(0,90)}</a> <span class="art-meta">— ${a.source}${d ? ", "+d : ""}</span></div>`;
          }).join("");
        s += `
          <div class="lead-card ${cls}">
            <div class="lead-header">
              <span class="company-name">${l.company}</span>
              <span class="score-pill ${cls}">${Math.round(l.score)} / 100</span>
            </div>
            <div class="meta-grid">
              <div><div class="field">HQ LOCATION</div><div class="value">${l.hq}</div></div>
              <div><div class="field">ANNUAL REVENUE</div><div class="value">${l.revenue}</div></div>
              <div><div class="field">INDUSTRY</div><div class="value">${l.industry}</div></div>
              <div style="grid-column:span 2"><div class="field">TARGET PERSONA</div><div class="value">${l.target_persona}</div></div>
              <div><div class="field">TIER</div><div class="value">${l.tier}</div></div>
            </div>
            <div class="why-now"><strong>WHY NOW — SIGNAL</strong>${l.why_now}</div>
            <div class="score-bar-row">
              <span class="score-segment">Location ${b.location}/25</span>
              <span class="score-segment">·</span>
              <span class="score-segment">Financial ${b.financial_fit}/25</span>
              <span class="score-segment">·</span>
              <span class="score-segment">Partnership ${b.partnership_signal}/30</span>
              <span class="score-segment">·</span>
              <span class="score-segment">Recency ${b.recency_trigger}/20</span>
            </div>
            ${arts ? `<div class="articles" style="margin-top:12px">${arts}</div>` : ""}
          </div>`;
      }
      return s;
    }

    html += renderSection("🔴 Tier 1 — High-Priority Outreach (Score > 80)", tier1, "tier1");
    html += renderSection("🟡 Tier 2 — Active Pipeline (Score 60–80)", tier2, "tier2");
    html += renderSection("🟢 Watch List (Score 40–60)", watch, "watch");

    document.getElementById("main-content").innerHTML = html;
  }

  function showStatus(msg) {
    const el = document.getElementById("status-msg");
    el.style.display = "block";
    el.textContent = msg;
  }
  function hideStatus() {
    document.getElementById("status-msg").style.display = "none";
  }

  async function refreshPipeline() {
    const btn = document.getElementById("refreshBtn");
    btn.disabled = true;
    showStatus("Running pipeline…");
    try {
      const res = await fetch("/api/run", {method: "POST"});
      const data = await res.json();
      if (data.error) { showStatus("Error: " + data.error); return; }
      renderLeads(data);
      hideStatus();
    } catch(e) {
      showStatus("Request failed: " + e.message);
    } finally {
      btn.disabled = false;
    }
  }

  async function loadLatest() {
    try {
      const res = await fetch("/api/leads");
      const data = await res.json();
      renderLeads(data);
    } catch(e) {
      document.getElementById("main-content").innerHTML = `<p class="empty">Failed to load data. Click "Run Pipeline" to start.</p>`;
    }
  }

  loadLatest();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/leads")
def api_leads():
    global _cached_leads, _last_run
    if not _cached_leads:
        try:
            run_pipeline(use_mock=True)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    return _leads_response()


@app.route("/api/run", methods=["POST"])
def api_run():
    use_mock = request.args.get("live", "false").lower() != "true"
    try:
        run_pipeline(use_mock=use_mock)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return _leads_response()


def _leads_response():
    from report import generate_json
    payload = generate_json(_cached_leads, _last_run)
    return app.response_class(payload, mimetype="application/json")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n  L&Co Business Development Pipeline")
    print(f"  Dashboard running at: http://localhost:{port}")
    print(f"  Press Ctrl+C to stop.\n")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    app.run(host="0.0.0.0", port=port, debug=False)
