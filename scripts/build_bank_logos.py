#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests

OUT = Path("data/bank-logos.json")
SOURCE_REPO = "praveenpuglia/indian-banks"
BASE = "https://raw.githubusercontent.com/praveenpuglia/indian-banks/main/assets/logos/{slug}/{kind}.svg"
UA = "Rupevia-Bank-Logo-Builder/1.0"

# Rupevia bank id -> stable IFSC-prefix slug in the source logo repository.
BANKS = [
    ("sbi", "State Bank of India", "sbin"),
    ("hdfc", "HDFC Bank", "hdfc"),
    ("icici", "ICICI Bank", "icic"),
    ("axis", "Axis Bank", "utib"),
    ("kotak", "Kotak Mahindra Bank", "kkbk"),
    ("bob", "Bank of Baroda", "barb"),
    ("pnb", "Punjab National Bank", "punb"),
    ("canara", "Canara Bank", "cnrb"),
    ("union", "Union Bank of India", "ubin"),
    ("indian", "Indian Bank", "idib"),
    ("boi", "Bank of India", "bkid"),
    ("cbi", "Central Bank of India", "cbin"),
    ("idbi", "IDBI Bank", "ibkl"),
    ("indus", "IndusInd Bank", "indb"),
    ("federal", "Federal Bank", "fdrl"),
    ("yes", "YES BANK", "yesb"),
    ("idfc", "IDFC FIRST Bank", "idfb"),
    ("rbl", "RBL Bank", "ratn"),
    ("au", "AU Small Finance Bank", "aubl"),
    ("bandhan", "Bandhan Bank", "bdbl"),
]


def fetch_svg(slug: str):
    errors = []
    for kind in ("symbol", "logo"):
        url = BASE.format(slug=slug, kind=kind)
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
            r.raise_for_status()
            raw = r.content
            text = raw.decode("utf-8", "strict").strip()
            if not re.search(r"<svg\b", text, re.I):
                raise ValueError("not SVG")
            if len(raw) < 80 or len(raw) > 2_000_000:
                raise ValueError(f"unexpected SVG size {len(raw)}")
            if re.search(r"<script\b", text, re.I):
                raise ValueError("script element found in SVG")
            # Keep assets self-contained. External image/font/script URLs are not allowed.
            if re.search(r"(?:href|src)\s*=\s*['\"]https?://", text, re.I):
                raise ValueError("external URL found in SVG")
            return kind, url, raw
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{kind}: {exc}")
    raise RuntimeError("; ".join(errors))


def main() -> None:
    logos = {}
    for app_id, name, slug in BANKS:
        kind, url, raw = fetch_svg(slug)
        logos[app_id] = {
            "name": name,
            "slug": slug,
            "variant": kind,
            "dataUri": "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii"),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sourceUrl": url,
        }
        print(app_id, name, kind, len(raw))

    if len(logos) != 20:
        raise RuntimeError(f"expected 20 logos, got {len(logos)}")
    if len({v["sha256"] for v in logos.values()}) != 20:
        raise RuntimeError("duplicate bank logo assets detected")

    payload = {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "assetCount": len(logos),
        "sourceRepo": SOURCE_REPO,
        "sourceLicenseNote": "Bank logos/trademarks remain property of their respective owners; bundled only for bank identification in Rupevia.",
        "logos": logos,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print("bank logo registry OK:", payload["assetCount"])


if __name__ == "__main__":
    main()
