#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, json, os, urllib.request
from pathlib import Path

BASE=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
SNAP=Path(os.getenv('SNAPSHOT_OUT','data/mf-snapshot.json'))
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
UA='Rupevia-MF-Freshness/1.0 (+GitHub Actions)'

def get_json(url:str):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))

def parse_date(v):
    try:return dt.datetime.strptime(str(v or '').strip(),'%d-%m-%Y').date()
    except Exception:return None

def main():
    payload=get_json(BASE+'/mf/latest')
    dates=[parse_date(x.get('date')) for x in payload if isinstance(x,dict)] if isinstance(payload,list) else []
    dates=[d for d in dates if d]
    if not dates: raise RuntimeError('MFAPI latest feed has no valid NAV date')
    feed=max(dates)
    current=None
    if SNAP.exists():
        try:
            s=json.loads(SNAP.read_text(encoding='utf-8'))
            if s.get('sourceAsOf'): current=dt.date.fromisoformat(s['sourceAsOf'])
        except Exception: pass
    refresh=current is None or feed>current
    print(f'feed_as_of={feed.isoformat()} current={current.isoformat() if current else "none"} refresh={str(refresh).lower()}')
    out=os.getenv('GITHUB_OUTPUT')
    if out:
        with open(out,'a',encoding='utf-8') as f:
            f.write(f'refresh={str(refresh).lower()}\n')
            f.write(f'feed_as_of={feed.isoformat()}\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
