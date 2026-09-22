#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures as cf
import datetime as dt
import json, os, time, urllib.request
from pathlib import Path

BASE=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','25'))
WORKERS=int(os.getenv('HISTORY_WORKERS','8'))
ATTEMPTS=int(os.getenv('HISTORY_ATTEMPTS','3'))
UA='Rupevia-MF-Daily-History/1.0'
SNAP=Path('data/mf-snapshot.json')
OUT=Path('data/history')
OUT.mkdir(parents=True,exist_ok=True)

def fetch(code):
    last=None
    for i in range(ATTEMPTS):
        try:
            req=urllib.request.Request(f'{BASE}/mf/{code}',headers={'User-Agent':UA,'Accept':'application/json','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
                x=json.loads(r.read().decode('utf-8'))
            series=[]
            for q in x.get('data') or []:
                try:
                    d=dt.datetime.strptime(str(q.get('date') or ''),'%d-%m-%Y').date()
                    n=float(q.get('nav') or 0)
                    if n>0: series.append([d.isoformat(),n])
                except Exception: pass
            series=sorted(set((d,float(n)) for d,n in series))
            if len(series)<2: raise RuntimeError('insufficient history')
            payload={'schemaVersion':1,'schemeCode':str(code),'source':'MFAPI AMFI mirror','sourceAsOf':series[-1][0],'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z'),'navSeries':[[d,round(n,6)] for d,n in series]}
            return code,payload,None
        except Exception as e:
            last=e
            if i+1<ATTEMPTS: time.sleep(1.2*(i+1))
    return code,None,str(last)

def main():
    s=json.loads(SNAP.read_text(encoding='utf-8'))
    codes=sorted({str(f['schemeCode']) for b in s['categories'].values() for f in b['funds']})
    ok=failed=changed=0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for code,payload,err in ex.map(fetch,codes):
            if payload is None:
                failed+=1
                print('history failed',code,err)
                continue
            ok+=1
            p=OUT/f'{code}.json'
            raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n'
            if not p.exists() or p.read_text(encoding='utf-8')!=raw:
                p.write_text(raw,encoding='utf-8'); changed+=1
    print(f'daily history complete: {ok}/{len(codes)} fetched, {failed} failed, {changed} changed')
    # Upstream outages are not a release failure; preserve existing last-known-good history files.
    return 0

if __name__=='__main__': raise SystemExit(main())
