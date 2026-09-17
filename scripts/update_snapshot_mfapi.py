#!/usr/bin/env python3
"""GitHub-runner adapter: use MFAPI's cached AMFI latest universe.

The core rank/return engine stays in update_snapshot.py; only universe ingestion
is replaced because portal.amfiindia.com may not return NAVAll.txt reliably to
hosted CI runners.

Quality guardrails here ensure Rupevia publishes only currently active/recent
Direct Growth schemes. MFAPI's /mf/latest can retain historical rows for merged
or discontinued schemes, so rows with stale NAV dates and segregated/side-pocket
portfolios are excluded before any ranking work begins.
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import json
import re

import update_snapshot as core

FRESHNESS_DAYS = 7
RANK_BASELINE_VERSION = 1
LEGACY_NAME_PATTERNS = (
    "segregated portfolio",
    "segregated port",
    "side pocket",
    "side-pocket",
)


def _date(value: object) -> dt.date | None:
    try:
        return dt.datetime.strptime(str(value or "").strip(), "%d-%m-%Y").date()
    except Exception:
        return None


def _legacy_name(name: str) -> bool:
    n = re.sub(r"\s+", " ", name.lower()).strip()
    return any(token in n for token in LEGACY_NAME_PATTERNS)


def parse_latest(text: str) -> list[dict]:
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise RuntimeError("MFAPI /mf/latest did not return a list")

    all_dates = [_date(x.get("date")) for x in payload if isinstance(x, dict)]
    all_dates = [d for d in all_dates if d is not None]
    if not all_dates:
        raise RuntimeError("MFAPI /mf/latest contained no valid NAV dates")
    feed_as_of = max(all_dates)
    min_active_date = feed_as_of - dt.timedelta(days=FRESHNESS_DAYS)

    out = []
    for x in payload:
        if not isinstance(x, dict):
            continue
        scheme_type = str(x.get("schemeType") or x.get("scheme_type") or "")
        if "open ended" not in scheme_type.lower():
            continue
        scheme_category = str(x.get("schemeCategory") or x.get("scheme_category") or "")
        cat = core.category(scheme_category)
        if not cat:
            continue
        name = str(x.get("schemeName") or x.get("scheme_name") or "").strip()
        if not name or _legacy_name(name):
            continue
        if not core.direct_growth(name):
            continue
        if cat == "Index" and not core.equity_index(name):
            continue
        try:
            code = str(x.get("schemeCode") or x.get("scheme_code") or "").strip()
            nav = float(x.get("nav") or 0)
            nav_date = _date(x.get("date"))
        except Exception:
            continue
        if not code or nav <= 0 or nav_date is None or nav_date < min_active_date:
            continue
        out.append({
            "schemeCode": code,
            "isin": str(x.get("isinGrowth") or x.get("isin_growth") or ""),
            "schemeName": name,
            "name": name,
            "category": cat,
            "fundHouse": str(x.get("fundHouse") or x.get("fund_house") or ""),
            "amfiCategory": scheme_category,
            "latestNav": nav,
            "navDate": nav_date.isoformat(),
        })

    print(
        f"MFAPI feed as-of {feed_as_of.isoformat()}; "
        f"publishing candidates with NAV >= {min_active_date.isoformat()}"
    )
    return out


def main() -> int:
    core.AMFI_URL = core.MFAPI_BASE.rstrip("/") + "/mf/latest"
    core.parse_amfi = parse_latest

    original_old_ranks = core.old_ranks

    def guarded_old_ranks(old: dict):
        quality = old.get("quality") or {}
        if quality.get("rankingBaselineVersion") != RANK_BASELINE_VERSION:
            return {}
        return original_old_ranks(old)

    core.old_ranks = guarded_old_ranks

    rc = core.main()
    if rc == 0 and core.OUT.exists():
        snap = json.loads(core.OUT.read_text(encoding="utf-8"))
        snap["sources"] = {
            "latestNav": "MFAPI /mf/latest (AMFI mirror)",
            "history": "MFAPI AMFI mirror",
            "mfapiBase": core.MFAPI_BASE,
        }
        snap["quality"] = {
            "activeNavFreshnessDays": FRESHNESS_DAYS,
            "excludesStaleSchemes": True,
            "excludesSegregatedPortfolios": True,
            "rankingBaselineVersion": RANK_BASELINE_VERSION,
        }
        raw = (json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        core.OUT.write_bytes(raw)
        bundle_path = core.OUT.parent / "mf-snapshot.json.gz.b64"
        bundle_path.write_text(
            base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii") + "\n",
            encoding="ascii",
        )
        print(f"Bundle export: {bundle_path} ({bundle_path.stat().st_size} bytes)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())