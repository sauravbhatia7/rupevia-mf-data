#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, json, math, os, time, urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
SNAP=Path(os.getenv('SNAPSHOT_OUT','data/mf-snapshot.json'))
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','25'))
ATTEMPTS=int(os.getenv('SOURCE_ATTEMPTS','4'))
UA='Rupevia-MF-Freshness/2.1'
MIN_SUPPORT_COUNT=int(os.getenv('DATE_SUPPORT_MIN','30'))
MIN_SUPPORT_SHARE=float(os.getenv('DATE_SUPPORT_SHARE','0.05'))
IST=ZoneInfo('Asia/Kolkata')

def get_json(url:str):
    last=None
    for i in range(ATTEMPTS):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last=e
            if i+1<ATTEMPTS:
                time.sleep(min(8,1.5*(i+1)))
    raise RuntimeError(str(last))

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
    out=os.getenv('GITHUB_OUTPUT')
    try:
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
        if out:
            with open(out,'a',encoding='utf-8') as f:
                f.write(f'refresh={str(refresh).lower()}\nfeed_as_of={feed.isoformat()}\nfuture_rows_ignored={future_rows}\ndate_support_threshold={threshold}\n')
        return 0
    except Exception as e:
        # A temporary upstream outage must preserve the last-known-good snapshot
        # and must not turn the scheduled updater red or generate failure spam.
        print(f'upstream freshness check unavailable; preserving current snapshot: {e}')
        if out:
            with open(out,'a',encoding='utf-8') as f:
                f.write('refresh=false\nfeed_as_of=\nsource_unavailable=true\n')
        return 0

if __name__=='__main__': raise SystemExit(main())
