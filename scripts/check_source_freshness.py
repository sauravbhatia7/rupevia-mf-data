#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, json, math, os, urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
SNAP=Path(os.getenv('SNAPSHOT_OUT','data/mf-snapshot.json'))
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
UA='Rupevia-MF-Freshness/2.0 (+GitHub Actions)'
MIN_SUPPORT_COUNT=int(os.getenv('DATE_SUPPORT_MIN','30'))
MIN_SUPPORT_SHARE=float(os.getenv('DATE_SUPPORT_SHARE','0.05'))
IST=ZoneInfo('Asia/Kolkata')

def get_json(url:str):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))

def parse_date(v):
    try:return dt.datetime.strptime(str(v or '').strip(),'%d-%m-%Y').date()
    except Exception:return None

def credible_feed_date(payload):
    if not isinstance(payload,list): raise RuntimeError('MFAPI latest feed is not a list')
    today=dt.datetime.now(dt.timezone.utc).astimezone(IST).date()
    parsed=[parse_date(x.get('date')) for x in payload if isinstance(x,dict)]
    future=[d for d in parsed if d and d>today]
    dates=[d for d in parsed if d and d<=today]
    if not dates: raise RuntimeError('MFAPI latest feed has no non-future NAV dates')
    counts=Counter(dates)
    threshold=max(MIN_SUPPORT_COUNT,math.ceil(len(dates)*MIN_SUPPORT_SHARE))
    supported=[d for d,n in counts.items() if n>=threshold]
    if not supported:
        top=counts.most_common(5)
        raise RuntimeError(f'No credible MFAPI NAV date meets support threshold {threshold}; top={top}')
    return max(supported),len(future),threshold,today

def main():
    payload=get_json(BASE+'/mf/latest')
    feed,future_rows,threshold,today=credible_feed_date(payload)
    current=None
    if SNAP.exists():
        try:
            s=json.loads(SNAP.read_text(encoding='utf-8'))
            if s.get('sourceAsOf'): current=dt.date.fromisoformat(s['sourceAsOf'])
        except Exception: pass
    current_invalid=bool(current and current>today)
    refresh=current is None or current_invalid or feed>current
    print(f'credible_feed_as_of={feed.isoformat()} current={current.isoformat() if current else "none"} current_invalid={str(current_invalid).lower()} future_rows_ignored={future_rows} support_threshold={threshold} refresh={str(refresh).lower()}')
    out=os.getenv('GITHUB_OUTPUT')
    if out:
        with open(out,'a',encoding='utf-8') as f:
            f.write(f'refresh={str(refresh).lower()}\n')
            f.write(f'feed_as_of={feed.isoformat()}\n')
            f.write(f'future_rows_ignored={future_rows}\n')
            f.write(f'date_support_threshold={threshold}\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
