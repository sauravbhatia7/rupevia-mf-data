#!/usr/bin/env python3
"""GitHub-runner adapter: use MFAPI's cached AMFI latest universe.

The core rank/return engine stays in update_snapshot.py; only universe ingestion
is replaced because portal.amfiindia.com may not return NAVAll.txt reliably to
hosted CI runners.
"""
from __future__ import annotations

import datetime as dt
import json

import update_snapshot as core


def parse_latest(text: str) -> list[dict]:
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise RuntimeError("MFAPI /mf/latest did not return a list")
    out = []
    for x in payload:
        scheme_type = str(x.get("schemeType") or x.get("scheme_type") or "")
        if "open ended" not in scheme_type.lower():
            continue
        scheme_category = str(x.get("schemeCategory") or x.get("scheme_category") or "")
        cat = core.category(scheme_category)
        if not cat:
            continue
        name = str(x.get("schemeName") or x.get("scheme_name") or "").strip()
        if not core.direct_growth(name):
            continue
        if cat == "Index" and not core.equity_index(name):
            continue
        try:
            code = str(x.get("schemeCode") or x.get("scheme_code") or "").strip()
            nav = float(x.get("nav") or 0)
            date_s = str(x.get("date") or "").strip()
            nav_date = dt.datetime.strptime(date_s, "%d-%m-%Y").date()
        except Exception:
            continue
        if not code or nav <= 0:
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
    return out


def main() -> int:
    core.AMFI_URL = core.MFAPI_BASE.rstrip("/") + "/mf/latest"
    core.parse_amfi = parse_latest
    rc = core.main()
    if rc == 0 and core.OUT.exists():
        snap = json.loads(core.OUT.read_text(encoding="utf-8"))
        snap["sources"] = {
            "latestNav": "MFAPI /mf/latest (AMFI mirror)",
            "history": "MFAPI AMFI mirror",
            "mfapiBase": core.MFAPI_BASE,
        }
        core.OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
