#!/usr/bin/env python3
"""Build Rupevia's lightweight full active Direct-Growth MF universe.
No history calls are made here; fund detail loads one selected scheme's daily history on demand.
"""
from __future__ import annotations
import base64, datetime as dt, gzip, json, os, re, urllib.request
from pathlib import Path

BASE=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
OUT=Path(os.getenv('UNIVERSE_OUT','data/mf-universe.json'))
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
FRESHNESS_DAYS=int(os.getenv('ACTIVE_FRESHNESS_DAYS','7'))
UA='Rupevia-MF-Universe/1.0 (+GitHub Actions)'
BAD=('segregated portfolio','segregated port','side pocket','side-pocket')

def get_json(url:str):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        return json.loads(r.read().decode('utf-8'))

def dparse(v):
    try:return dt.datetime.strptime(str(v or '').strip(),'%d-%m-%Y').date()
    except Exception:return None

def direct_growth(name:str)->bool:
    n=re.sub(r'\s+',' ',name.lower())
    return 'direct' in n and 'growth' in n and not re.search(r'\b(idcw|dividend|bonus|payout|reinvest(?:ment)?)\b',n)

def broad_group(cat:str)->str:
    c=(cat or '').lower()
    if 'equity' in c:return 'Equity'
    if 'debt' in c:return 'Debt'
    if 'hybrid' in c:return 'Hybrid'
    if 'solution' in c:return 'Solution Oriented'
    if 'other' in c or 'index' in c or 'fof' in c:return 'Other'
    return 'Other'

def subcat(cat:str)->str:
    c=re.sub(r'\s+',' ',str(cat or '')).strip()
    if ' - ' in c:return c.split(' - ',1)[1].strip()
    return c

def norm_name(v:str)->str:
    n=v.lower().replace('&',' and ')
    n=re.sub(r'\b(direct|regular|plan|growth|option|scheme)\b',' ',n)
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',n)).strip()

def main():
    payload=get_json(BASE+'/mf/latest')
    if not isinstance(payload,list):raise RuntimeError('MFAPI /mf/latest did not return list')
    dates=[dparse(x.get('date')) for x in payload if isinstance(x,dict)]
    dates=[d for d in dates if d]
    if not dates:raise RuntimeError('no valid NAV dates')
    feed=max(dates); min_date=feed-dt.timedelta(days=FRESHNESS_DAYS)
    rows=[]
    for x in payload:
        if not isinstance(x,dict):continue
        st=str(x.get('schemeType') or x.get('scheme_type') or '')
        if 'open ended' not in st.lower():continue
        name=re.sub(r'\s+',' ',str(x.get('schemeName') or x.get('scheme_name') or '')).strip()
        if not name or not direct_growth(name):continue
        nl=name.lower()
        if any(b in nl for b in BAD):continue
        date=dparse(x.get('date'))
        try: nav=float(x.get('nav') or 0)
        except Exception:nav=0
        code=str(x.get('schemeCode') or x.get('scheme_code') or '').strip()
        if not code or nav<=0 or date is None or date<min_date:continue
        cat=str(x.get('schemeCategory') or x.get('scheme_category') or '').strip()
        fh=str(x.get('fundHouse') or x.get('fund_house') or '').strip()
        rows.append({'schemeCode':code,'isin':str(x.get('isinGrowth') or x.get('isin_growth') or ''),'name':name,'schemeName':name,'fundHouse':fh,'schemeType':st,'amfiCategory':cat,'group':broad_group(cat),'subCategory':subcat(cat),'nav':nav,'navDate':date.isoformat()})
    dedup={}
    for r in rows:
        k=(norm_name(r['name']),r['fundHouse'].lower())
        old=dedup.get(k)
        rv=(r['navDate'],int(r['schemeCode']) if r['schemeCode'].isdigit() else 0)
        ov=(old['navDate'],int(old['schemeCode']) if old and old['schemeCode'].isdigit() else 0) if old else None
        if old is None or rv>ov: dedup[k]=r
    rows=sorted(dedup.values(),key=lambda r:(r['fundHouse'].lower(),r['name'].lower()))
    amcs=sorted({r['fundHouse'] for r in rows if r['fundHouse']})
    doc={'schemaVersion':1,'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'sourceAsOf':feed.isoformat(),'source':'MFAPI /mf/latest (AMFI mirror)','scope':'Active/recent open-ended Direct Growth schemes; full-search universe, not Rupevia ranking universe.','fundCount':len(rows),'amcCount':len(amcs),'amcs':amcs,'funds':rows}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8')
    OUT.write_bytes(raw)
    (OUT.parent/'mf-universe.json.gz.b64').write_text(base64.b64encode(gzip.compress(raw,compresslevel=9,mtime=0)).decode('ascii')+'\n',encoding='ascii')
    print('universe',len(rows),'amcs',len(amcs),'as-of',feed.isoformat(),'raw',len(raw))
    return 0
if __name__=='__main__': raise SystemExit(main())
