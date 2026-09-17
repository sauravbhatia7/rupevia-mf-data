#!/usr/bin/env python3
"""Build Rupevia's compact, ranked mutual-fund snapshot.

App runtime reads only data/mf-snapshot.json. Heavy AMFI/MFAPI work runs here.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import math
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

AMFI_URL = os.getenv("AMFI_URL", "https://portal.amfiindia.com/spages/NAVAll.txt")
MFAPI_BASE = os.getenv("MFAPI_BASE", "https://api.mfapi.in")
OUT = Path(os.getenv("SNAPSHOT_OUT", "data/mf-snapshot.json"))
TOP_N = int(os.getenv("TOP_N", "30"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))
TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "45"))
PERIODS = ("1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y")
UA = "Rupevia-MF-Snapshot/2.1 (+GitHub Actions)"

META = {
    "Large Cap": ("High", "Nifty 100 TRI", "Nifty 50 TRI", .72, 26000),
    "Mid Cap": ("Very High", "Nifty Midcap 150 TRI", "Nifty Midcap Select TRI", .78, 14000),
    "Small Cap": ("Very High", "Nifty Smallcap 250 TRI", "Nifty Smallcap 100 TRI", .82, 9000),
    "Flexi Cap": ("High", "Nifty 500 TRI", "Nifty 200 TRI", .70, 18000),
    "ELSS": ("Very High", "Nifty 500 TRI", "Nifty 200 TRI", .74, 8000),
    "Index": ("High", "Nifty 50 TRI", "Nifty Next 50 TRI", .22, 12000),
    "Hybrid": ("Moderate", "Hybrid Composite", "CRISIL Hybrid Index", .64, 9500),
    "Debt": ("Moderate", "CRISIL Short Duration Debt Index", "CRISIL Corporate Bond Index", .34, 11000),
}


def get(url: str, attempts: int = 4) -> bytes:
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except Exception as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep((1.5 ** i) + random.random())
    raise RuntimeError(f"GET failed: {url}: {last}")


def category(header: str) -> str | None:
    h = re.sub(r"\s+", " ", header.lower())
    if "large cap fund" in h: return "Large Cap"
    if "mid cap fund" in h: return "Mid Cap"
    if "small cap fund" in h: return "Small Cap"
    if "flexi cap fund" in h: return "Flexi Cap"
    if "elss" in h: return "ELSS"
    if "other scheme - index funds" in h or "index funds - equity funds" in h: return "Index"
    if "index funds - debt funds" in h: return "Debt"
    if "hybrid scheme" in h or "hybrid fund" in h: return "Hybrid"
    if "debt scheme" in h or "debt fund" in h: return "Debt"
    return None


def direct_growth(name: str) -> bool:
    n = re.sub(r"\s+", " ", name.lower())
    return "direct" in n and "growth" in n and not re.search(r"\b(idcw|dividend|bonus|payout|reinvest(?:ment)?)\b", n)


def equity_index(name: str) -> bool:
    n = re.sub(r"\s+", " ", name.lower())
    debt = ("crisil ibx", "gilt", "sdl", "government securities", "government bond",
            "target maturity", "maturity fund", "bond index", "debt index",
            "constant maturity", "treasury", "t-bill", "t bill", "aaa bond")
    return not any(x in n for x in debt)


def parse_amfi(text: str) -> list[dict]:
    header, cat, amc = "", None, ""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("scheme code;"):
            continue
        if not re.match(r"^\d+;", line):
            if line.lower().startswith(("open ended schemes(", "close ended schemes(", "interval fund schemes(")):
                header, cat, amc = line, category(line), ""
            elif cat and "mutual fund" in line.lower():
                amc = line
            continue
        if not cat or not header.lower().startswith("open ended schemes("):
            continue
        # Current AMFI format: code;isin1;isin2;scheme name;nav;date
        a = [x.strip() for x in line.split(";")]
        if len(a) < 6:
            continue
        code, isin1, isin2, name, nav_s, date_s = a[:6]
        name = re.sub(r"\s+", " ", name).strip()
        if not direct_growth(name) or (cat == "Index" and not equity_index(name)):
            continue
        try:
            nav = float(nav_s)
            nav_date = dt.datetime.strptime(date_s, "%d-%b-%Y").date()
        except Exception:
            continue
        if nav <= 0:
            continue
        out.append({
            "schemeCode": str(code), "isin": "" if isin1 == "-" else isin1,
            "schemeName": name, "name": name, "category": cat, "fundHouse": amc,
            "amfiCategory": header[header.find("(") + 1:-1] if header.endswith(")") else header,
            "latestNav": nav, "navDate": nav_date.isoformat(),
        })
    return out


def shift_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 - months) // 12
    m = (d.month - 1 - months) % 12 + 1
    nxt = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
    return dt.date(y, m, min(d.day, (nxt - dt.timedelta(days=1)).day))


def target_date(latest: dt.date, p: str) -> dt.date:
    if p == "1M": return shift_months(latest, 1)
    if p == "3M": return shift_months(latest, 3)
    if p == "6M": return shift_months(latest, 6)
    years = {"1Y": 1, "3Y": 3, "5Y": 5, "10Y": 10}[p]
    try: return latest.replace(year=latest.year - years)
    except ValueError: return latest.replace(year=latest.year - years, day=28)


def historical(row: dict) -> dict:
    latest_d = dt.date.fromisoformat(row["navDate"])
    start = target_date(latest_d, "10Y") - dt.timedelta(days=35)
    end = latest_d + dt.timedelta(days=2)
    url = f"{MFAPI_BASE}/mf/{urllib.parse.quote(row['schemeCode'])}?startDate={start.isoformat()}&endDate={end.isoformat()}"
    payload = json.loads(get(url).decode("utf-8"))
    if str(payload.get("status", "")).upper() != "SUCCESS":
        raise RuntimeError("MFAPI status not SUCCESS")
    pts = []
    for x in payload.get("data") or []:
        try:
            d = dt.datetime.strptime(str(x.get("date", "")), "%d-%m-%Y").date()
            n = float(x.get("nav", 0))
            if n > 0: pts.append((d, n))
        except Exception:
            pass
    pts.sort()
    if len(pts) < 10:
        raise RuntimeError("insufficient history")
    returns = {}
    for p in PERIODS:
        t = target_date(latest_d, p)
        base = None
        for d, n in pts:
            if d <= t: base = (d, n)
            else: break
        if not base: continue
        ratio = row["latestNav"] / base[1]
        if ratio <= 0: continue
        if p in ("1M", "3M", "6M"):
            v = (ratio - 1) * 100
        else:
            days = max(1, (latest_d - base[0]).days)
            v = (ratio ** (365.2425 / days) - 1) * 100
        if math.isfinite(v): returns[p] = round(v, 2)
    return {**row, "returns": returns, "historyPoints": len(pts)}


def normalized(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\b(direct|regular|plan|growth|option|fund|scheme)\b", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def old_ranks(old: dict) -> dict[tuple[str, str], int]:
    ans = {}
    for cat, block in (old.get("categories") or {}).items():
        for f in block.get("funds") or []:
            if f.get("schemeCode") and f.get("rank"):
                ans[(cat, str(f["schemeCode"]))] = int(f["rank"])
    return ans


def preview(code: str, cat: str) -> dict:
    risk, bench, bench2, exp0, aum0 = META[cat]
    r = random.Random(int(re.sub(r"\D", "", code) or "1"))
    exp = max(.08, round(exp0 + (r.random() - .5) * (.18 if cat == "Index" else .42), 2))
    aum = round(aum0 * (.55 + r.random() * 1.10))
    consistency = round(72 + r.random() * 22)
    return {"risk": risk, "benchmark": bench, "benchmarkAlt": bench2,
            "expense": exp, "aum": aum, "consistency": consistency,
            "researchFieldStatus": "previewResearch"}


def rank(rows: list[dict], cat: str, previous: dict[tuple[str, str], int]) -> list[dict]:
    def key(x):
        r = x.get("returns") or {}
        return (1 if isinstance(r.get("3Y"), (int, float)) else 0,
                r.get("3Y", -10000), r.get("1Y", -10000),
                r.get("5Y", -10000), r.get("6M", -10000))
    dedup = {}
    for x in rows:
        k = normalized(x["schemeName"])
        if k not in dedup or key(x) > key(dedup[k]): dedup[k] = x
    picked = sorted(dedup.values(), key=key, reverse=True)[:TOP_N]
    out = []
    for pos, x in enumerate(picked, 1):
        prev = previous.get((cat, str(x["schemeCode"])))
        change = 0 if prev is None else prev - pos
        direction = "—" if change == 0 else ("↑" if change > 0 else "↓")
        r = x.get("returns") or {}
        out.append({
            "rank": pos, "previousRank": prev, "rankChange": change, "rankDirection": direction,
            "rankingPeriod": "3Y" if "3Y" in r else ("1Y" if "1Y" in r else "6M"),
            "schemeCode": str(x["schemeCode"]), "isin": x.get("isin", ""),
            "name": x["name"], "schemeName": x["schemeName"], "short": x["schemeName"][:42],
            "category": cat, "amfiCategory": x.get("amfiCategory", ""), "fundHouse": x.get("fundHouse", ""),
            "nav": x["latestNav"], "navDate": x["navDate"],
            "returns": {p: r[p] for p in PERIODS if p in r}, **preview(str(x["schemeCode"]), cat),
        })
    return out


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    try: old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    except Exception: old = {}

    print("Downloading AMFI universe")
    universe = parse_amfi(get(AMFI_URL).decode("utf-8-sig", errors="replace"))
    counts = {c: sum(1 for x in universe if x["category"] == c) for c in META}
    print("Direct Growth candidates:", counts)
    for c, n in counts.items():
        if n < TOP_N: raise RuntimeError(f"not enough {c} candidates: {n}")

    enriched, failures = [], []
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(historical, row): row for row in universe}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            row = futures[fut]
            try: enriched.append(fut.result())
            except Exception as exc:
                failures.append({"schemeCode": row["schemeCode"], "category": row["category"], "error": str(exc)[:160]})
            if i % 25 == 0 or i == len(futures): print(f"History {i}/{len(futures)} ok={len(enriched)} failed={len(failures)}")

    previous = old_ranks(old)
    categories = {}
    for cat in META:
        funds = rank([x for x in enriched if x["category"] == cat], cat, previous)
        if len(funds) != TOP_N: raise RuntimeError(f"snapshot validation failed: {cat}={len(funds)}")
        categories[cat] = {"count": len(funds), "funds": funds}
        print(cat, "Top", len(funds), funds[0]["schemeName"])

    dates = [dt.date.fromisoformat(x["navDate"]) for x in enriched]
    snapshot = {
        "schemaVersion": 2,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sourceAsOf": max(dates).isoformat() if dates else "",
        "topN": TOP_N, "periods": list(PERIODS),
        "rankingRule": "Top 30 per Rupevia category by 3Y annualised NAV return; 1Y/5Y/6M are deterministic tie-breakers.",
        "returnMethod": {"1M": "point-to-point", "3M": "point-to-point", "6M": "point-to-point", "1Y": "annualised", "3Y": "annualised", "5Y": "annualised", "10Y": "annualised"},
        "sources": {"latestNav": "AMFI NAVAll.txt", "history": "MFAPI AMFI mirror", "amfiUrl": AMFI_URL, "mfapiBase": MFAPI_BASE},
        "categories": categories,
        "stats": {"amfiDirectGrowthCandidates": len(universe), "historySucceeded": len(enriched), "historyFailed": len(failures), "publishedFunds": sum(x["count"] for x in categories.values())},
        "failures": failures[:50],
    }
    if snapshot["stats"]["publishedFunds"] != len(META) * TOP_N:
        raise RuntimeError("published fund count validation failed")
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes), as-of {snapshot['sourceAsOf']}")
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise
