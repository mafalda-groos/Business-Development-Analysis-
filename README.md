# L&Co — Business Development Pipeline

A weekly lead scoring and ingestion system that surfaces high-probability target companies for L&Co outreach. Filters against L&Co's "Target Model" criteria and scores every company 1–100 across four weighted dimensions.

---

## Quick Start

```bash
# Install dependencies (Flask only, for the dashboard)
pip install -r requirements.txt

# Run the pipeline (mock data, generates reports in ./reports/)
python pipeline.py

# Launch the local web dashboard
python dashboard.py
# → open http://localhost:5050
```

---

## Project Structure

```
├── config.json        ← All tunable parameters (thresholds, keywords, weights)
├── pipeline.py        ← CLI entry point
├── ingestion.py       ← News ingestion: RSS feeds + mock company/article database
├── scorer.py          ← Scoring engine (4-dimension weighted algorithm)
├── report.py          ← Output: Markdown, CSV, JSON
├── dashboard.py       ← Local Flask web UI
├── requirements.txt
└── reports/           ← Generated weekly reports (auto-created)
```

---

## Scoring Model

| Dimension | Weight | Max Points | Logic |
|---|---|---|---|
| **Location** | 25% | 25 | Preferred hub (Minneapolis, Seattle, Cincinnati…) = 25 pts. Excluded (NYC, LA, London) = 0 pts. |
| **Financial Fit** | 25% | 25 | $500M–$1B = 15 pts. $1B+ = 25 pts. Below $500M = filtered out. |
| **Partnership Signal** | 30% | 30 | Known LTO/collab history + recent news signal = 30 pts. History only = 20 pts. News only = 15 pts. |
| **Recency Trigger** | 20% | 20 | Leadership change in past 7 days = 20 pts. Growth signal = 15 pts. Any relevant article = 10 pts. |

**Tiers:**
- **Tier 1 — High-Priority Outreach:** Score ≥ 80
- **Tier 2 — Active Pipeline:** Score 60–79
- **Watch List:** Score 40–59
- **Filtered Out:** < $500M revenue

---

## CLI Usage

```bash
# Run with mock data (default)
python pipeline.py

# Pull from live RSS feeds
python pipeline.py --live

# Only print Tier 1 leads to stdout
python pipeline.py --tier1-only

# Score without writing report files
python pipeline.py --no-save
```

---

## Configuration (`config.json`)

All business logic parameters live in `config.json`. Key fields:

| Key | Purpose |
|---|---|
| `financial_thresholds` | Revenue tiers and point values |
| `geographic_exclusions.excluded_cities` | Cities to score 0 on location |
| `geographic_exclusions.preferred_hubs` | Cities that score 25/25 |
| `partnership_keywords` | Terms that trigger partnership signal detection |
| `leadership_change_keywords` | CMO/VP titles that flag recency trigger |
| `growth_signal_keywords` | Earnings/expansion terms that trigger growth signal |
| `pipeline.min_score_tier1` | Score threshold for Tier 1 (default: 80) |
| `rss_feeds` | Live RSS feed URLs used in `--live` mode |

---

## Output Reports

Each run writes three files to `reports/` dated by run date:

| File | Use |
|---|---|
| `pipeline_YYYY-MM-DD.md` | Scannable Markdown brief — best for async sharing |
| `pipeline_YYYY-MM-DD.csv` | Spreadsheet-ready for CRM import |
| `pipeline_YYYY-MM-DD.json` | Structured data for downstream integrations |

---

## Live Data (Production Setup)

The system ships with a curated mock dataset (20 companies, 11 simulated news articles). To switch to live data:

1. Add your feed URLs to `config.json` → `rss_feeds`
2. Run with `python pipeline.py --live`

To connect Crunchbase or Clearbit for real revenue/funding data, replace the `MOCK_COMPANIES` list in `ingestion.py` with an API call — the `CompanyProfile` dataclass accepts the same fields.

---

## Weekly Automation (macOS/Linux)

```bash
# Add to crontab — runs every Monday at 7am
crontab -e
# Add:  0 7 * * 1 cd /path/to/repo && python pipeline.py
```
