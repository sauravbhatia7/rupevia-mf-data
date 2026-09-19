#!/usr/bin/env python3
"""GitHub-runner adapter for Rupevia's ranked MF snapshot.

Uses MFAPI's cached AMFI latest universe, but publishes only a statistically
credible non-future NAV date window. Protects the previous known-good snapshot
from corrupt/future/older replacement while preserving rank continuity.
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import json
import math
import re
from collections import Counter
from zoneinfo import ZoneInfo

import update_snapshot as core

FRESHNESS_DAYS = 7
RANK_BASELINE_VERSION = 1
MIN_SUPPORT_COUNT = 30
MIN_SUPPORT_SHARE = 0.05
IST = ZoneInfo('Asia/Kolkata')
LEGACY_NAME_PATTERNS = (
    'segregated portfolio',
    'segregated port',
    'side pocket',
    'side-pocket',
)
FEED_AUDIT = {'credibleFeedAsOf': None, 'futureRowsIgnored': 0, 'dateSupportThreshold': 0}


def _date(value: object) -> dt.date | None:
    try:
        return dt.datetime.strptime(str(value or '').strip(), '%d-%m-%Y').date()
    except Exception:
        return None


def _iso_date(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or '').strip())
    except Exception:
        return None


def _publisher_day(generated_at: object) -> dt.date | None:
    try:
        t = dt.datetime.fromisoformat(str(generated_at).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(IST).date()
    except Exception:
        return None


def _legacy_name(name: str) -> bool:
    n = re.sub(r'\s+', ' ', name.lower()).strip()
    return any(token in n for token in LEGACY_NAME_PATTERNS)


def _credible_feed_date(payload: list[dict]) -> tuple[dt.date, int, int]:
    today = dt.datetime.now(dt.timezone.utc).astimezone(IST).date()
    parsed = [_date(x.get('date')) for x in payload if isinstance(x, dict)]
    future = [d for d in parsed if d and d > today]
    dates = [d for d in parsed if d and d <= today]
    if not dates:
        raise RuntimeError('MFAPI /mf/latest contained no non-future NAV dates')
    counts = Counter(dates)
    threshold = max(MIN_SUPPORT_COUNT, math.ceil(len(dates) * MIN_SUPPORT_SHARE))
    supported = [d for d, n in counts.items() if n >= threshold]
    if not supported:
        raise RuntimeError(f'no credible NAV date meets support threshold {threshold}; top={counts.most_common(5)}')
    return max(supported), len(future), threshold


def parse_latest(text: str) -> list[dict]:
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise RuntimeError('MFAPI /mf/latest did not return a list')

    feed_as_of, future_rows, threshold = _credible_feed_date(payload)
    min_active_date = feed_as_of - dt.timedelta(days=FRESHNESS_DAYS)
    FEED_AUDIT.update(credibleFeedAsOf=feed_as_of.isoformat(), futureRowsIgnored=future_rows, dateSupportThreshold=threshold)

    out = []
    for x in payload:
        if not isinstance(x, dict):
            continue
        scheme_type = str(x.get('schemeType') or x.get('scheme_type') or '')
        if 'open ended' not in scheme_type.lower():
            continue
        scheme_category = str(x.get('schemeCategory') or x.get('scheme_category') or '')
        cat = core.category(scheme_category)
        if not cat:
            continue
        name = str(x.get('schemeName') or x.get('scheme_name') or '').strip()
        if not name or _legacy_name(name) or not core.direct_growth(name):
            continue
        if cat == 'Index' and not core.equity_index(name):
            continue
        try:
            code = str(x.get('schemeCode') or x.get('scheme_code') or '').strip()
            nav = float(x.get('nav') or 0)
            nav_date = _date(x.get('date'))
        except Exception:
            continue
        if not code or nav <= 0 or nav_date is None or nav_date > feed_as_of or nav_date < min_active_date:
            continue
        out.append({
            'schemeCode': code,
            'isin': str(x.get('isinGrowth') or x.get('isin_growth') or ''),
            'schemeName': name,
            'name': name,
            'category': cat,
            'fundHouse': str(x.get('fundHouse') or x.get('fund_house') or ''),
            'amfiCategory': scheme_category,
            'latestNav': nav,
            'navDate': nav_date.isoformat(),
        })

    print(f"MFAPI credible feed as-of {feed_as_of.isoformat()}; publishing NAV >= {min_active_date.isoformat()}; future rows ignored={future_rows}; support threshold={threshold}")
    return out


def _snapshot_date_sane(snap: dict) -> tuple[bool, str]:
    today = dt.datetime.now(dt.timezone.utc).astimezone(IST).date()
    source = _iso_date(snap.get('sourceAsOf'))
    pubday = _publisher_day(snap.get('generatedAt'))
    if source is None or pubday is None or source > today or source > pubday:
        return False, 'future-or-invalid sourceAsOf/generatedAt'
    cats = ['Large Cap','Mid Cap','Small Cap','Flexi Cap','ELSS','Index','Hybrid','Debt']
    if set(snap.get('categories') or {}) != set(cats):
        return False, 'category set mismatch'
    codes = set()
    total = 0
    for cat in cats:
        funds = ((snap.get('categories') or {}).get(cat) or {}).get('funds') or []
        if len(funds) != core.TOP_N:
            return False, f'{cat} count {len(funds)}'
        for i, f in enumerate(funds, 1):
            nd = _iso_date(f.get('navDate'))
            code = str(f.get('schemeCode') or '')
            try: nav = float(f.get('nav'))
            except Exception: nav = 0
            if int(f.get('rank') or 0) != i or not code.isdigit() or code in codes or nav <= 0:
                return False, f'{cat} rank/code/nav integrity'
            if nd is None or nd > source or (source - nd).days > FRESHNESS_DAYS:
                return False, f'{cat} NAV date integrity'
            codes.add(code); total += 1
    if total != 8 * core.TOP_N or len(codes) != total:
        return False, 'published fund uniqueness/count'
    return True, 'ok'


def _previous_is_good(old: dict) -> bool:
    source = _iso_date(old.get('sourceAsOf'))
    pubday = _publisher_day(old.get('generatedAt'))
    today = dt.datetime.now(dt.timezone.utc).astimezone(IST).date()
    return bool(source and pubday and source <= today and source <= pubday)


def main() -> int:
    core.AMFI_URL = core.MFAPI_BASE.rstrip('/') + '/mf/latest'
    core.parse_amfi = parse_latest

    previous_bytes = core.OUT.read_bytes() if core.OUT.exists() else None
    try:
        previous_snapshot = json.loads(previous_bytes.decode('utf-8')) if previous_bytes else {}
    except Exception:
        previous_snapshot = {}

    original_old_ranks = core.old_ranks
    def guarded_old_ranks(old: dict):
        quality = old.get('quality') or {}
        if quality.get('rankingBaselineVersion') != RANK_BASELINE_VERSION:
            return {}
        return original_old_ranks(old)
    core.old_ranks = guarded_old_ranks

    rc = core.main()
    if rc != 0 or not core.OUT.exists():
        return rc

    try:
        snap = json.loads(core.OUT.read_text(encoding='utf-8'))
        sane, reason = _snapshot_date_sane(snap)
        if not sane:
            raise RuntimeError('snapshot date/integrity validation failed: ' + reason)
        credible = _iso_date(FEED_AUDIT.get('credibleFeedAsOf'))
        source = _iso_date(snap.get('sourceAsOf'))
        if credible is None or source is None or source > credible:
            raise RuntimeError('snapshot sourceAsOf exceeds credible feed date')
        if _previous_is_good(previous_snapshot):
            old_source = _iso_date(previous_snapshot.get('sourceAsOf'))
            if old_source and source < old_source:
                raise RuntimeError(f'anti-downgrade: new {source} < previous good {old_source}')

        snap['sources'] = {
            'latestNav': 'MFAPI /mf/latest (AMFI mirror)',
            'history': 'MFAPI AMFI mirror',
            'mfapiBase': core.MFAPI_BASE,
        }
        snap['quality'] = {
            'activeNavFreshnessDays': FRESHNESS_DAYS,
            'excludesStaleSchemes': True,
            'excludesSegregatedPortfolios': True,
            'rankingBaselineVersion': RANK_BASELINE_VERSION,
            'dateSanityVersion': 1,
            'credibleFeedAsOf': FEED_AUDIT['credibleFeedAsOf'],
            'futureFeedRowsIgnored': FEED_AUDIT['futureRowsIgnored'],
            'dateSupportThreshold': FEED_AUDIT['dateSupportThreshold'],
            'antiDowngrade': True,
        }
        raw = (json.dumps(snap, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        core.OUT.write_bytes(raw)
        bundle_path = core.OUT.parent / 'mf-snapshot.json.gz.b64'
        bundle_path.write_text(base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode('ascii') + '\n', encoding='ascii')
        print(f'Bundle export: {bundle_path} ({bundle_path.stat().st_size} bytes)')
        return 0
    except Exception:
        if previous_bytes is not None:
            core.OUT.write_bytes(previous_bytes)
        elif core.OUT.exists():
            core.OUT.unlink()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
