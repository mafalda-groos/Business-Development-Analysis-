"""
ingestion.py — Weekly news ingestion layer.

Pulls articles from RSS feeds and a mock company database, then returns
raw lead candidates enriched with metadata needed by the scorer.
"""

import json
import hashlib
import logging
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NewsArticle:
    title: str
    summary: str
    url: str
    published: Optional[datetime]
    source: str
    article_id: str = field(init=False)

    def __post_init__(self):
        self.article_id = hashlib.md5(self.url.encode()).hexdigest()[:10]


@dataclass
class CompanyProfile:
    name: str
    hq_city: str
    hq_state: str
    hq_country: str
    annual_revenue_millions: float
    industry: str
    description: str
    known_partnerships: list[str] = field(default_factory=list)
    website: str = ""
    linkedin_url: str = ""
    stock_ticker: str = ""


@dataclass
class LeadCandidate:
    company: CompanyProfile
    triggering_articles: list[NewsArticle] = field(default_factory=list)
    detected_keywords: list[str] = field(default_factory=list)
    has_leadership_change: bool = False
    has_growth_signal: bool = False
    has_partnership_signal: bool = False
    raw_text_snippet: str = ""


# ---------------------------------------------------------------------------
# Mock company database
# Seeded with realistic enterprise targets matching L&Co's "Target Model."
# In production, replace/supplement with a Crunchbase or Clearbit API call.
# ---------------------------------------------------------------------------

MOCK_COMPANIES: list[CompanyProfile] = [
    CompanyProfile(
        name="Crocs",
        hq_city="Broomfield", hq_state="CO", hq_country="USA",
        annual_revenue_millions=4100,
        industry="Footwear / Lifestyle",
        description="Viral footwear brand with one of the most aggressive cultural collaboration programs in retail.",
        known_partnerships=["Balenciaga", "MSCHF", "KFC", "Post Malone", "Salehe Bembury"],
        website="https://www.crocs.com", stock_ticker="CROX"
    ),
    CompanyProfile(
        name="Yeti",
        hq_city="Austin", hq_state="TX", hq_country="USA",
        annual_revenue_millions=1700,
        industry="Outdoor / Lifestyle",
        description="Premium drinkware and outdoor brand with a fast-growing artist and ambassador collaboration program.",
        known_partnerships=["various artist series", "BUILT FORD TOUGH", "Patagonia"],
        website="https://www.yeti.com", stock_ticker="YETI"
    ),
    CompanyProfile(
        name="Carhartt",
        hq_city="Dearborn", hq_state="MI", hq_country="USA",
        annual_revenue_millions=1100,
        industry="Workwear / Fashion",
        description="Iconic workwear brand with significant fashion crossover and a long history of streetwear collaborations.",
        known_partnerships=["A.P.C.", "Junya Watanabe", "Awake NY", "Brain Dead"],
        website="https://www.carhartt.com"
    ),
    CompanyProfile(
        name="DICK'S Sporting Goods",
        hq_city="Coraopolis", hq_state="PA", hq_country="USA",
        annual_revenue_millions=13000,
        industry="Sporting Goods Retail",
        description="Largest US sporting goods retailer pursuing brand elevation through lifestyle and exclusive product partnerships.",
        known_partnerships=["various exclusive footwear drops", "Nike", "Jordan Brand"],
        website="https://www.dickssportinggoods.com", stock_ticker="DKS"
    ),
    CompanyProfile(
        name="Wendy's",
        hq_city="Dublin", hq_state="OH", hq_country="USA",
        annual_revenue_millions=2200,
        industry="Food & Beverage / QSR",
        description="Fast food brand celebrated for cultural marketing wit, growing into product and media collaborations.",
        known_partnerships=["Postmates", "various gaming and meme collaborations"],
        website="https://www.wendys.com", stock_ticker="WEN"
    ),
    CompanyProfile(
        name="REI Co-op",
        hq_city="Seattle", hq_state="WA", hq_country="USA",
        annual_revenue_millions=3700,
        industry="Outdoor Retail",
        description="Consumer co-op focused on outdoor gear with a values-driven brand and growing lifestyle positioning.",
        known_partnerships=["Patagonia", "Arc'teryx", "various brand activations"],
        website="https://www.rei.com"
    ),
    CompanyProfile(
        name="Procter & Gamble",
        hq_city="Cincinnati", hq_state="OH", hq_country="USA",
        annual_revenue_millions=82000,
        industry="Consumer Packaged Goods",
        description="Global CPG giant with portfolio of household brands increasingly investing in cultural marketing.",
        known_partnerships=["various sports and entertainment sponsorships"],
        website="https://www.pg.com", stock_ticker="PG"
    ),
    CompanyProfile(
        name="General Mills",
        hq_city="Minneapolis", hq_state="MN", hq_country="USA",
        annual_revenue_millions=19900,
        industry="Food & Beverage",
        description="Major food company with brands like Cheerios and Nature Valley; has done limited-edition packaging collaborations.",
        known_partnerships=["various limited-edition artist packaging campaigns"],
        website="https://www.generalmills.com", stock_ticker="GIS"
    ),
    CompanyProfile(
        name="Best Buy",
        hq_city="Richfield", hq_state="MN", hq_country="USA",
        annual_revenue_millions=43500,
        industry="Consumer Electronics Retail",
        description="Electronics retailer pursuing lifestyle brand repositioning and younger-demographic partnerships.",
        known_partnerships=["Apple", "Samsung", "various exclusive drops"],
        website="https://www.bestbuy.com", stock_ticker="BBY"
    ),
    CompanyProfile(
        name="Starbucks",
        hq_city="Seattle", hq_state="WA", hq_country="USA",
        annual_revenue_millions=36200,
        industry="Food & Beverage / Hospitality",
        description="Global coffee brand with a rich history of seasonal LTOs and cultural partnership campaigns.",
        known_partnerships=["Stanley", "Spotify", "various artist cup designs"],
        website="https://www.starbucks.com", stock_ticker="SBUX"
    ),
    CompanyProfile(
        name="Lululemon",
        hq_city="Vancouver", hq_state="BC", hq_country="Canada",
        annual_revenue_millions=9600,
        industry="Activewear / Lifestyle Retail",
        description="Premium activewear brand expanding into lifestyle and cultural marketing with growing collaboration pipeline.",
        known_partnerships=["various local artist programs", "Team Canada"],
        website="https://www.lululemon.com", stock_ticker="LULU"
    ),
    CompanyProfile(
        name="Patagonia",
        hq_city="Ventura", hq_state="CA", hq_country="USA",
        annual_revenue_millions=1500,
        industry="Outdoor Apparel",
        description="Activist outdoor brand with bespoke co-branding and environmental partnership programs.",
        known_partnerships=["various environmental NGOs", "film collaborations"],
        website="https://www.patagonia.com"
    ),
    CompanyProfile(
        name="3M",
        hq_city="St. Paul", hq_state="MN", hq_country="USA",
        annual_revenue_millions=33500,
        industry="Industrial / Consumer Products",
        description="Diversified manufacturer exploring design-forward consumer brand partnerships to boost lifestyle relevance.",
        known_partnerships=[],
        website="https://www.3m.com", stock_ticker="MMM"
    ),
    CompanyProfile(
        name="Tractor Supply Co.",
        hq_city="Brentwood", hq_state="TN", hq_country="USA",
        annual_revenue_millions=14600,
        industry="Farm & Ranch Retail",
        description="Rapidly growing rural lifestyle retailer building brand identity through community and cultural campaigns.",
        known_partnerships=["various country music brand activations"],
        website="https://www.tractorsupply.com", stock_ticker="TSCO"
    ),
    CompanyProfile(
        name="Kroger",
        hq_city="Cincinnati", hq_state="OH", hq_country="USA",
        annual_revenue_millions=148300,
        industry="Grocery Retail",
        description="Largest US supermarket chain pursuing private-label brand elevation and designer food collaboration.",
        known_partnerships=["various exclusive private-label lines"],
        website="https://www.kroger.com", stock_ticker="KR"
    ),
    CompanyProfile(
        name="Duluth Trading Company",
        hq_city="Belleville", hq_state="WI", hq_country="USA",
        annual_revenue_millions=660,
        industry="Workwear / Lifestyle Retail",
        description="Direct-to-consumer workwear brand expanding into lifestyle positioning with a strong regional following.",
        known_partnerships=[],
        website="https://www.duluthtrading.com", stock_ticker="DLTH"
    ),
    CompanyProfile(
        name="Alaska Airlines",
        hq_city="Seattle", hq_state="WA", hq_country="USA",
        annual_revenue_millions=9900,
        industry="Aviation",
        description="Regional airline with Pacific Northwest brand identity investing in livery and cultural brand partnerships.",
        known_partnerships=["Virgin America branding legacy", "various artist livery programs"],
        website="https://www.alaskaair.com", stock_ticker="ALK"
    ),
    CompanyProfile(
        name="H-E-B Grocery",
        hq_city="San Antonio", hq_state="TX", hq_country="USA",
        annual_revenue_millions=38000,
        industry="Grocery Retail",
        description="Beloved Texas grocer with intense regional brand loyalty, increasingly running artist and designer private-label campaigns.",
        known_partnerships=["various Texas artist collaborations"],
        website="https://www.heb.com"
    ),
    CompanyProfile(
        name="Delta Air Lines",
        hq_city="Atlanta", hq_state="GA", hq_country="USA",
        annual_revenue_millions=55700,
        industry="Aviation",
        description="Major US airline investing heavily in premium brand experience and cultural marketing partnerships.",
        known_partnerships=["Porsche", "various lifestyle brand tie-ins"],
        website="https://www.delta.com", stock_ticker="DAL"
    ),
    CompanyProfile(
        name="Chewy",
        hq_city="Dania Beach", hq_state="FL", hq_country="USA",
        annual_revenue_millions=11800,
        industry="Pet Retail / E-commerce",
        description="Online pet retailer building lifestyle brand with growing interest in artist and cultural collaboration for limited drops.",
        known_partnerships=[],
        website="https://www.chewy.com", stock_ticker="CHWY"
    ),
]


# ---------------------------------------------------------------------------
# Mock news articles
# Simulates what the RSS ingestion layer would surface in a real week.
# ---------------------------------------------------------------------------

def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def _news_search(query: str) -> str:
    """Return a Google News search URL for a given headline / query."""
    import urllib.parse
    return "https://news.google.com/search?q=" + urllib.parse.quote(query)


MOCK_NEWS_ARTICLES: list[dict] = [
    {
        "company_name": "Crocs",
        "title": "Crocs Names New VP of Brand Collaboration, Plans Expanded Designer Capsule Pipeline",
        "summary": (
            "Crocs has appointed a new VP of Brand Collaboration tasked with scaling its "
            "designer and artist capsule collection pipeline. The footwear brand, fresh off "
            "viral collaborations with Balenciaga and MSCHF, is reportedly in early talks "
            "with multiple fashion houses for FY26 limited-edition drops."
        ),
        "url": _news_search("Crocs VP Brand Collaboration capsule collection"),
        "published": _days_ago(1),
        "source": "Footwear News",
    },
    {
        "company_name": "Yeti",
        "title": "Yeti Hires CMO from Patagonia, Plans Push into Cultural Brand Partnerships",
        "summary": (
            "Yeti announced today that it has hired a new Chief Marketing Officer from "
            "Patagonia's brand division. Sources say the appointment signals Yeti's intent "
            "to expand from product-driven marketing into broader cultural and artist "
            "partnership programs, including a planned 2026 limited-edition artist series."
        ),
        "url": _news_search("Yeti CMO Patagonia cultural partnerships"),
        "published": _days_ago(2),
        "source": "Ad Age",
    },
    {
        "company_name": "Wendy's",
        "title": "Wendy's Launches 'Wendy's x Culture' — Multi-Year Collaboration and Pop-Up Program",
        "summary": (
            "Wendy's unveiled 'Wendy's x Culture,' a multi-year program of limited-edition "
            "menu items, merch capsules, and experiential pop-ups co-created with musicians, "
            "designers, and gaming brands. The CMO described the initiative as Wendy's bid "
            "to evolve from a fast food chain into a 'cultural lifestyle brand.'"
        ),
        "url": _news_search("Wendys cultural collaboration program pop-up"),
        "published": _days_ago(3),
        "source": "Fast Company",
    },
    {
        "company_name": "Starbucks",
        "title": "Starbucks Q2 Earnings: CEO Signals 'Cultural Partnership Renaissance' in Strategy Refresh",
        "summary": (
            "Starbucks reported Q2 earnings with revenue up 8% YoY. CEO stated on the earnings "
            "call that the company will lean further into 'culturally resonant brand partnerships' "
            "and limited-edition seasonal collaborations to drive foot traffic among Gen Z customers. "
            "Marketing spend is projected to increase 15% in the back half of fiscal year."
        ),
        "url": _news_search("Starbucks Q2 earnings cultural partnerships"),
        "published": _days_ago(3),
        "source": "Bloomberg",
    },
    {
        "company_name": "Carhartt",
        "title": "Carhartt Names Head of Brand Partnerships, Doubles Down on Fashion Crossover",
        "summary": (
            "Carhartt has named a new Head of Brand Partnerships to lead an expanded "
            "collaboration roadmap with fashion houses and emerging streetwear labels. "
            "The workwear icon reported strong growth in its fashion-adjacent lines and "
            "is investing in a dedicated co-creation studio in Detroit."
        ),
        "url": _news_search("Carhartt brand partnerships fashion collaboration"),
        "published": _days_ago(4),
        "source": "Hypebeast",
    },
    {
        "company_name": "General Mills",
        "title": "General Mills Launches 'Taste the Art' Initiative — Designer Packaging LTO Program",
        "summary": (
            "General Mills unveiled a new multi-year 'Taste the Art' program, partnering with "
            "emerging artists to produce limited-edition designer packaging for Wheaties and "
            "Lucky Charms. The CPG giant said the LTO program is central to its strategy of "
            "reaching younger consumers through cultural relevance."
        ),
        "url": _news_search("General Mills Taste the Art designer packaging LTO"),
        "published": _days_ago(5),
        "source": "Ad Age",
    },
    {
        "company_name": "REI Co-op",
        "title": "REI Appoints New Head of Creative Partnerships, Signals Brand Collaboration Push",
        "summary": (
            "REI Co-op has named a new Head of Creative Partnerships, a newly created position "
            "reporting directly to the CMO. The hire is intended to accelerate REI's co-branding "
            "and capsule-collection activity with emerging outdoor and lifestyle brands."
        ),
        "url": _news_search("REI Head of Creative Partnerships co-branding"),
        "published": _days_ago(4),
        "source": "Outdoor Retailer News",
    },
    {
        "company_name": "Delta Air Lines",
        "title": "Delta Unveils 'Delta x Design' Program — Co-Branded Collaborations with Artists and Designers",
        "summary": (
            "Delta Air Lines launched 'Delta x Design,' a structured brand collaboration program "
            "inviting artists, designers, and lifestyle brands to co-create exclusive in-flight "
            "amenity kits, apparel, and experiential pop-ups. Delta's CMO stated the program "
            "positions Delta as a 'cultural brand, not just an airline.'"
        ),
        "url": _news_search("Delta x Design brand collaboration program"),
        "published": _days_ago(6),
        "source": "Fast Company",
    },
    {
        "company_name": "H-E-B Grocery",
        "title": "H-E-B Announces Record Revenue and Expands Into Brand Lifestyle Strategy",
        "summary": (
            "H-E-B reported record annual revenue of $38 billion and unveiled a new strategic "
            "initiative to position the beloved Texas grocer as a 'lifestyle brand.' The company "
            "plans to launch a series of exclusive artist collaborations and limited-edition "
            "private-label design collections starting in Q3."
        ),
        "url": _news_search("H-E-B record revenue lifestyle brand strategy"),
        "published": _days_ago(3),
        "source": "Austin American-Statesman",
    },
    {
        "company_name": "Lululemon",
        "title": "Lululemon Names New VP of Cultural Marketing, Plans Global Collab Campaign",
        "summary": (
            "Lululemon Athletica announced the appointment of a new VP of Cultural Marketing "
            "as part of its plan to deepen artist and cultural brand partnerships globally. "
            "The executive previously led Nike's 'NikeWomen' collaboration series."
        ),
        "url": _news_search("Lululemon VP Cultural Marketing collaboration"),
        "published": _days_ago(2),
        "source": "Retail Brew",
    },
    {
        "company_name": "Kroger",
        "title": "Kroger Investor Day: 'Premium Private Label' Expansion to Include Designer Collaborations",
        "summary": (
            "At its annual Investor Day, Kroger's leadership outlined a strategy to elevate its "
            "Simple Truth and Private Selection brands through designer collaboration and limited-edition "
            "packaging runs. The grocery chain is actively seeking creative agency partners to execute "
            "the program."
        ),
        "url": _news_search("Kroger Investor Day premium private label designer collaboration"),
        "published": _days_ago(7),
        "source": "Grocery Dive",
    },
    {
        "company_name": "3M",
        "title": "3M's Consumer Division Hires CMO with Luxury Brand Background",
        "summary": (
            "3M has hired a new CMO for its Consumer Products division with a background in "
            "luxury goods and co-branded lifestyle campaigns. The appointment suggests 3M is "
            "exploring design-forward brand partnerships to modernize its Post-it and Scotch brands."
        ),
        "url": _news_search("3M Consumer Products CMO luxury brand"),
        "published": _days_ago(5),
        "source": "Marketing Week",
    },
    {
        "company_name": "Tractor Supply Co.",
        "title": "Tractor Supply Co. Sees 22% YoY Growth, Eyes 'Rural Lifestyle Brand' Collaborations",
        "summary": (
            "Tractor Supply reported a 22% year-over-year revenue increase and announced a "
            "strategic pivot to become a 'rural lifestyle brand.' The CEO mentioned plans for "
            "exclusive artist collaborations and limited-edition merchandise programs targeted "
            "at millennial rural homeowners."
        ),
        "url": _news_search("Tractor Supply rural lifestyle brand collaboration"),
        "published": _days_ago(4),
        "source": "CNBC",
    },
]


# ---------------------------------------------------------------------------
# RSS Ingestion (live feed parsing)
# ---------------------------------------------------------------------------

def _fetch_rss(url: str, timeout: int = 10) -> list[NewsArticle]:
    """Fetch and parse a single RSS feed. Returns empty list on any error."""
    articles = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LCo-BDPipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
        root = ET.fromstring(raw)
        channel = root.find("channel")
        items = channel.findall("item") if channel else root.findall(".//item")
        for item in items:
            title = (item.findtext("title") or "").strip()
            summary = (item.findtext("description") or item.findtext("summary") or "").strip()
            url_ = (item.findtext("link") or "").strip()
            pub_str = item.findtext("pubDate") or item.findtext("published") or ""
            published = _parse_date(pub_str)
            if title and url_:
                articles.append(NewsArticle(
                    title=title, summary=summary, url=url_,
                    published=published, source=url
                ))
    except Exception as exc:
        log.warning("RSS fetch failed for %s: %s", url, exc)
    return articles


def _parse_date(date_str: str) -> Optional[datetime]:
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fetch_live_rss_articles(feeds: list[str], lookback_days: int = 7) -> list[NewsArticle]:
    """Pull articles from all configured RSS feeds, filtered to the lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    all_articles = []
    for feed_url in feeds:
        articles = _fetch_rss(feed_url)
        for a in articles:
            if a.published is None or a.published >= cutoff:
                all_articles.append(a)
    log.info("RSS ingestion: %d articles from %d feeds", len(all_articles), len(feeds))
    return all_articles


# ---------------------------------------------------------------------------
# Keyword matching + lead candidate assembly
# ---------------------------------------------------------------------------

def _text_blob(article: NewsArticle) -> str:
    return f"{article.title} {article.summary}".lower()


def _find_keywords(text: str, keyword_list: list[str]) -> list[str]:
    return [kw for kw in keyword_list if kw.lower() in text]


def build_lead_candidates(
    companies: list[CompanyProfile],
    articles: list[NewsArticle],
    config: dict,
) -> list[LeadCandidate]:
    """
    Cross-reference companies against news articles to produce enriched
    LeadCandidate objects ready for scoring.
    """
    partnership_kws = config["partnership_keywords"]
    leadership_kws = config["leadership_change_keywords"]
    growth_kws = config["growth_signal_keywords"]

    candidates: dict[str, LeadCandidate] = {}

    for company in companies:
        candidates[company.name] = LeadCandidate(company=company)

    for article in articles:
        blob = _text_blob(article)
        for name, candidate in candidates.items():
            if name.lower() not in blob and not any(
                part.lower() in blob for part in name.split() if len(part) > 4
            ):
                continue

            candidate.triggering_articles.append(article)

            found_partnership = _find_keywords(blob, partnership_kws)
            found_leadership = _find_keywords(blob, leadership_kws)
            found_growth = _find_keywords(blob, growth_kws)

            candidate.detected_keywords.extend(found_partnership + found_leadership + found_growth)
            candidate.has_partnership_signal = candidate.has_partnership_signal or bool(
                found_partnership or candidate.company.known_partnerships
            )
            candidate.has_leadership_change = candidate.has_leadership_change or bool(found_leadership)
            candidate.has_growth_signal = candidate.has_growth_signal or bool(found_growth)

            if article.title:
                candidate.raw_text_snippet = article.title[:200]

    # Deduplicate detected keywords
    for c in candidates.values():
        c.detected_keywords = list(dict.fromkeys(c.detected_keywords))

    # Also flag partnership signal from known_partnerships baseline
    for c in candidates.values():
        if c.company.known_partnerships:
            c.has_partnership_signal = True

    return list(candidates.values())


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def run_ingestion(config: dict, use_mock: bool = True) -> list[LeadCandidate]:
    """
    Main ingestion entrypoint called by the pipeline.

    Args:
        config:    Parsed config.json dict.
        use_mock:  If True, use curated mock data instead of live RSS feeds.
                   Set to False in production once API keys are configured.
    """
    companies = MOCK_COMPANIES

    if use_mock:
        # Build NewsArticle objects from mock data
        articles = []
        for raw in MOCK_NEWS_ARTICLES:
            articles.append(NewsArticle(
                title=raw["title"],
                summary=raw["summary"],
                url=raw["url"],
                published=raw["published"],
                source=raw["source"],
            ))
        log.info("Using mock dataset: %d companies, %d articles", len(companies), len(articles))
    else:
        lookback = config["pipeline"]["lookback_days"]
        articles = fetch_live_rss_articles(config["rss_feeds"], lookback_days=lookback)

    return build_lead_candidates(companies, articles, config)
