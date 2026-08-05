"""Default TTLs by context kind (MARKET_CONTEXT_SPEC §4). Seconds."""

DEFAULT_TTLS: dict[str, int] = {
    "quote": 60,  # paper default; live modes tighten via policy.stale_quote_max_age_s
    "market_status": 60,
    "positions": 300,
    "account": 300,
    "sentiment_aggregate": 15 * 60,
    "news": 6 * 3600,
    "analyst_revision": 5 * 24 * 3600,
    "earnings_result": 92 * 24 * 3600,
    "filing": 400 * 24 * 3600,  # durable, but retrieval re-checks latest-known filing
    "company_profile": 30 * 24 * 3600,
}
