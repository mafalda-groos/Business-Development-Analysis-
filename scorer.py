"""
scorer.py — Lead scoring engine.

Applies the four-dimension weighted scoring model and returns
a ScoredLead with full breakdown and tier classification.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from ingestion import LeadCandidate, NewsArticle


# ---------------------------------------------------------------------------
# Output structures
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    location_score: float = 0.0        # 0–25
    financial_score: float = 0.0       # 0–25
    partnership_score: float = 0.0     # 0–30
    recency_score: float = 0.0         # 0–20
    total: float = 0.0

    def as_dict(self) -> dict:
        return {
            "location": round(self.location_score, 1),
            "financial_fit": round(self.financial_score, 1),
            "partnership_signal": round(self.partnership_score, 1),
            "recency_trigger": round(self.recency_score, 1),
            "total": round(self.total, 1),
        }


@dataclass
class ScoredLead:
    candidate: LeadCandidate
    breakdown: ScoreBreakdown
    tier: str                           # "Tier 1", "Tier 2", "Watch List", "Filtered Out"
    why_now: str                        # One-paragraph human-readable signal summary
    target_persona: str                 # Recommended outreach title
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def company(self):
        return self.candidate.company

    @property
    def score(self) -> float:
        return self.breakdown.total


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

class LeadScorer:
    def __init__(self, config: dict):
        self.cfg = config
        self.weights = config["scoring_weights"]
        self.fin = config["financial_thresholds"]
        self.geo = config["geographic_exclusions"]
        self.pipeline_cfg = config["pipeline"]
        self.personas = config["target_personas"]
        self.lookback_days = config["pipeline"]["lookback_days"]

    # --- Individual dimension scorers ---

    def _score_location(self, candidate: LeadCandidate) -> float:
        """
        25 points max.
        - 25: HQ in a preferred non-Tier-1-hub city
        - 15: HQ outside excluded cities but not in preferred list
        - 0:  HQ in an excluded city (NYC, LA, London)
        """
        city = candidate.company.hq_city
        country = candidate.company.hq_country

        excluded = [c.lower() for c in self.geo["excluded_cities"]]
        preferred = [c.lower() for c in self.geo["preferred_hubs"]]

        city_lower = city.lower()

        if any(excl in city_lower for excl in excluded):
            return 0.0

        if any(pref in city_lower for pref in preferred):
            return 25.0

        # Outside excluded but not in preferred hub list — partial credit
        if country.upper() in ("USA", "CANADA", "AUSTRALIA"):
            return 15.0

        return 10.0

    def _score_financial(self, candidate: LeadCandidate) -> float:
        """
        25 points max.
        - 0:  < $500M
        - 15: $500M–$1B
        - 25: $1B+
        """
        rev = candidate.company.annual_revenue_millions
        t1_min = self.fin["tier_1_min_revenue_millions"]
        t1_max = self.fin["tier_1_max_revenue_millions"]
        t1_pts = self.fin["tier_1_points"]
        t2_pts = self.fin["tier_2_points"]

        if rev < t1_min:
            return 0.0
        elif rev < t1_max:
            return float(t1_pts)
        else:
            return float(t2_pts)

    def _score_partnership(self, candidate: LeadCandidate) -> float:
        """
        30 points max.
        - 30: Explicit partnership signal in recent news AND known history
        - 20: Known partnership history (no recent news signal)
        - 15: Recent partnership keyword in news but no prior history
        - 5:  Mentioned in news only peripherally
        - 0:  No signal
        """
        has_history = bool(candidate.company.known_partnerships)
        has_news_signal = candidate.has_partnership_signal and bool(candidate.triggering_articles)

        # Check if any article explicitly mentions collaboration/partnership keywords
        news_collab_count = sum(
            1 for kw in candidate.detected_keywords
            if any(pk.lower() in kw.lower() for pk in self.cfg["partnership_keywords"])
        )

        if has_history and has_news_signal and news_collab_count > 0:
            return 30.0
        elif has_history and has_news_signal:
            return 25.0
        elif has_history:
            return 20.0
        elif has_news_signal and news_collab_count > 0:
            return 15.0
        elif bool(candidate.triggering_articles):
            return 5.0
        return 0.0

    def _score_recency(self, candidate: LeadCandidate) -> float:
        """
        20 points max.
        - 20: Leadership change article within past 7 days
        - 15: Growth/strategic signal article within past 7 days
        - 10: Any relevant article within past 7 days
        - 0:  No recent trigger
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        recent_articles = [
            a for a in candidate.triggering_articles
            if a.published and a.published >= cutoff
        ]

        if not recent_articles:
            return 0.0

        if candidate.has_leadership_change:
            return 20.0
        elif candidate.has_growth_signal:
            return 15.0
        else:
            return 10.0

    # --- Why-Now narrative generator ---

    def _build_why_now(self, candidate: LeadCandidate, breakdown: ScoreBreakdown) -> str:
        c = candidate.company
        parts = []

        if candidate.triggering_articles:
            latest = sorted(
                [a for a in candidate.triggering_articles if a.published],
                key=lambda a: a.published,
                reverse=True
            )
            article = latest[0] if latest else candidate.triggering_articles[0]
            parts.append(f'"{article.title}" ({article.source})')

        signals = []
        if candidate.has_leadership_change:
            signals.append("new leadership appointment in brand/marketing")
        if candidate.has_growth_signal:
            signals.append("growth mode / strategic expansion signal")
        if candidate.has_partnership_signal:
            signals.append("active partnership or LTO program")
        if c.known_partnerships:
            signals.append(f"proven collaboration track record ({', '.join(c.known_partnerships[:2])})")

        if signals:
            parts.append("Key signals: " + "; ".join(signals) + ".")

        if not parts:
            parts.append("Company meets baseline financial and geographic criteria.")

        return " | ".join(parts)

    # --- Persona mapping ---

    def _map_persona(self, candidate: LeadCandidate) -> str:
        c = candidate.company

        if candidate.has_leadership_change:
            for kw in candidate.detected_keywords:
                for persona in self.personas:
                    if any(p.lower() in kw.lower() for p in persona.split()):
                        return persona

        industry = c.industry.lower()
        if "retail" in industry:
            return "Head of Global Partnerships / Design Partnership Team"
        elif "food" in industry or "beverage" in industry or "grocery" in industry:
            return "VP of Brand Collaboration / Creative Director of LTOs"
        elif "tech" in industry or "streaming" in industry:
            return "Head of Cultural Partnerships / VP of Brand Experience"
        elif "apparel" in industry or "activewear" in industry or "fashion" in industry:
            return "VP of Brand Collaboration / Creative Director"
        elif "aviation" in industry or "airline" in industry:
            return "VP of Marketing Partnerships / Head of Brand Experience"
        else:
            return "VP of Brand Partnerships / Chief Marketing Officer"

    # --- Eligibility gate ---

    def _is_eligible(self, candidate: LeadCandidate) -> bool:
        """Hard filter: must meet minimum financial threshold."""
        return (
            candidate.company.annual_revenue_millions
            >= self.fin["tier_1_min_revenue_millions"]
        )

    # --- Tier classification ---

    def _classify_tier(self, score: float) -> str:
        min_tier1 = self.pipeline_cfg["min_score_tier1"]
        min_tier2 = self.pipeline_cfg["min_score_tier2"]
        if score >= min_tier1:
            return "Tier 1"
        elif score >= min_tier2:
            return "Tier 2"
        elif score >= 40:
            return "Watch List"
        else:
            return "Filtered Out"

    # --- Main scoring method ---

    def score(self, candidate: LeadCandidate) -> ScoredLead:
        if not self._is_eligible(candidate):
            breakdown = ScoreBreakdown()
            return ScoredLead(
                candidate=candidate,
                breakdown=breakdown,
                tier="Filtered Out",
                why_now="Does not meet minimum revenue threshold ($500M+).",
                target_persona="N/A",
            )

        loc = self._score_location(candidate)
        fin = self._score_financial(candidate)
        par = self._score_partnership(candidate)
        rec = self._score_recency(candidate)
        total = loc + fin + par + rec

        breakdown = ScoreBreakdown(
            location_score=loc,
            financial_score=fin,
            partnership_score=par,
            recency_score=rec,
            total=round(total, 1),
        )

        return ScoredLead(
            candidate=candidate,
            breakdown=breakdown,
            tier=self._classify_tier(total),
            why_now=self._build_why_now(candidate, breakdown),
            target_persona=self._map_persona(candidate),
        )

    def score_all(self, candidates: list[LeadCandidate]) -> list[ScoredLead]:
        scored = [self.score(c) for c in candidates]
        return sorted(scored, key=lambda s: s.score, reverse=True)
