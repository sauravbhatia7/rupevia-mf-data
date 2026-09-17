#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures as cf
import datetime as dt
import json, math, os, re, time, urllib.request
from pathlib import Path

SNAP=Path(os.getenv('SNAPSHOT_OUT','data/mf-snapshot.json'))
MFAPI=os.getenv('MFAPI_BASE','https://api.mfapi.in').rstrip('/')
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
WORKERS=int(os.getenv('ENRICH_WORKERS','8'))
UA='Rupevia-MF-Enrichment/4.0'
PERIODS=['1M','3M','6M','1Y','3Y','5Y','10Y','10Y+']
CATEGORY_REFERENCE={
 'Large Cap':'Nifty 100 TRI','Mid Cap':'Nifty Midcap 150 TRI','Small Cap':'Nifty Smallcap 250 TRI',
 'Flexi Cap':'Nifty 500 TRI','ELSS':'Nifty 500 TRI','Index':'Scheme index varies','Hybrid':'Scheme benchmark varies','Debt':'Scheme benchmark varies'
}

def get_json(url, attempts=3):
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last=e
            if i+1<attempts: time.sleep(1.2*(i+1))
    raise RuntimeError(str(last))

def pct(a,b):
    if not b or b<=0:return None
    v=(a/b-1)*100
    return round(v,2) if math.isfinite(v) else None

def annualised(a,b,days):
    if not b or b<=0 or days<=0:return None
    v=((a/b)**(365.2425/days)-1)*100
    return round(v,2) if math.isfinite(v) else None

def target(latest,p):
    months={'1M':1,'3M':3,'6M':6}.get(p)
    if months:
        y=latest.year+(latest.month-1-months)//12;m=(latest.month-1-months)%12+1
        import calendar
        return dt.date(y,m,min(latest.day,calendar.monthrange(y,m)[1]))
    years={'1Y':1,'3Y':3,'5Y':5,'10Y':10}[p]
    try:return latest.replace(year=latest.year-years)
    except:return latest.replace(year=latest.year-years,day=28)

def at_or_before(points,t):
    ans=None
    for d,n in points:
        if d<=t:ans=(d,n)
        else:break
    return ans

def sample_monthly(points):
    by={}
    for d,n in points:by[(d.year,d.month)]=(d,n)
    return [[d.isoformat(),round(n,4)] for d,n in by.values()]

def enrich_one(f):
    code=str(f.get('schemeCode') or '')
    payload=get_json(f'{MFAPI}/mf/{code}')
    pts=[]
    for x in payload.get('data') or []:
        try:
            d=dt.datetime.strptime(str(x.get('date') or ''),'%d-%m-%Y').date();n=float(x.get('nav') or 0)
            if n>0:pts.append((d,n))
        except:pass
    pts=sorted(set(pts))
    if len(pts)<2:raise RuntimeError('insufficient full history')
    latest_d,latest_nav=pts[-1];returns={}
    for p in PERIODS[:-1]:
        b=at_or_before(pts,target(latest_d,p))
        if not b:continue
        v=pct(latest_nav,b[1]) if p in ('1M','3M','6M') else annualised(latest_nav,b[1],(latest_d-b[0]).days)
        if v is not None:returns[p]=v
    inception_d,inception_nav=pts[0];years=(latest_d-inception_d).days/365.2425
    if years>10:
        v=annualised(latest_nav,inception_nav,(latest_d-inception_d).days)
        if v is not None:returns['10Y+']=v
    meta=payload.get('meta') or {}
    return {'returns':returns,'dayReturn':pct(latest_nav,pts[-2][1]),'inceptionDate':inception_d.isoformat(),
      'historyYears':round(years,2),'navSeries':sample_monthly(pts),'historyPointsFull':len(pts),'mfapiMeta':{
      'fundHouse':meta.get('fund_house'),'schemeType':meta.get('scheme_type'),'schemeCategory':meta.get('scheme_category')}}

def norm(s):
    s=str(s or '').lower().replace('&',' and ')
    s=re.sub(r'\b(direct|regular|plan|growth|option|fund|scheme|idcw|dividend)\b',' ',s)
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()

def ter_map(funds):
    out={}
    try:
        amcs=get_json('https://www.amfiindia.com/api/populate-mf')
        if not isinstance(amcs,list):return out
        byname={norm(x.get('mfName')):str(x.get('mfId')) for x in amcs if isinstance(x,dict)}
        needed={norm(f.get('fundHouse')) for f in funds if f.get('fundHouse')};ids=[]
        for n in needed:
            if n in byname:ids.append(byname[n]);continue
            for an,aid in byname.items():
                if n and (n in an or an in n):ids.append(aid);break
        ids=list(dict.fromkeys(ids));today=dt.date.today()
        for aid in ids:
            rows=[]
            for back in range(3):
                y=today.year;m=today.month-back
                while m<=0:m+=12;y-=1
                url=f'https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID={aid}&Month={m:02d}-{y}&strCat=-1&strType=1&page=1&pageSize=10000'
                try:
                    data=get_json(url,2);candidate=data if isinstance(data,list) else (data.get('data') or data.get('aaData') or []) if isinstance(data,dict) else []
                    if candidate:rows=candidate;break
                except:pass
            for r in rows:
                if not isinstance(r,dict):continue
                try:val=float(r.get('D_TER'))
                except:continue
                if not 0<=val<=10:continue
                key=norm(r.get('Scheme_Name'));date=str(r.get('TER_Date') or '')[:10]
                if key and (key not in out or date>=out[key][1]):out[key]=(val,date)
            time.sleep(.35)
    except Exception as e:print('TER enrichment unavailable:',e)
    return out

def main():
    s=json.loads(SNAP.read_text(encoding='utf-8'));funds=[f for b in (s.get('categories') or {}).values() for f in (b.get('funds') or [])]
    for f in funds:
        for k in ('expense','aum','consistency','benchmark','benchmarkAlt','researchFieldStatus','risk'):f.pop(k,None)
        f.update({'expenseRatio':None,'expenseRatioDate':None,'aum':None,'rating':None,'risk':None,'minSip':None,'minLumpsum':None,
          'exitLoad':None,'holdings':None,'sectors':None,'marketCapSplit':None,'assetAllocation':None,'fundManagers':None,
          'investmentObjective':None,'schemeBenchmark':None,'categoryBenchmarkReference':CATEGORY_REFERENCE.get(f.get('category')),
          'dataQuality':'verified-nav-returns; optional fields only when sourced'})
    failures=[]
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(enrich_one,f):f for f in funds}
        for i,fu in enumerate(cf.as_completed(futs),1):
            f=futs[fu]
            try:
                e=fu.result();f.update(e);f['returns']=e['returns']
                if e.get('mfapiMeta',{}).get('fundHouse'):f['fundHouse']=e['mfapiMeta']['fundHouse']
            except Exception as err:failures.append({'schemeCode':f.get('schemeCode'),'error':str(err)[:120]})
            if i%30==0 or i==len(futs):print(f'Full-history enrichment {i}/{len(futs)} failed={len(failures)}')
    ters=ter_map(funds)
    for f in funds:
        n=norm(f.get('name') or f.get('schemeName'));match=ters.get(n)
        if not match:
            cand=[v for k,v in ters.items() if n and (n in k or k in n)]
            if len(cand)==1:match=cand[0]
        if match:f['expenseRatio'],f['expenseRatioDate']=round(match[0],4),match[1]
    for cat,block in (s.get('categories') or {}).items():
        fs=block.get('funds') or []
        for p in PERIODS:
            vals=[float(f.get('returns',{}).get(p)) for f in fs if isinstance(f.get('returns',{}).get(p),(int,float))]
            avg=round(sum(vals)/len(vals),2) if vals else None
            ordered=sorted([f for f in fs if isinstance(f.get('returns',{}).get(p),(int,float))],key=lambda f:f['returns'][p],reverse=True)
            ranks={str(f.get('schemeCode')):i+1 for i,f in enumerate(ordered)}
            for f in fs:
                f.setdefault('periodRank',{})[p]=ranks.get(str(f.get('schemeCode')));f.setdefault('categoryAverage',{})[p]=avg
        block['periods']=PERIODS;block['periodRankScope']='Rupevia published Top 30'
    s['schemaVersion']=3;s['periods']=PERIODS
    s['returnMethod']=dict(s.get('returnMethod') or {},**{'10Y+':'since-inception annualised CAGR; shown only when history exceeds 10 years'})
    s['enrichment']={'fullHistory':'MFAPI AMFI mirror','ter':'AMFI official TER API (best effort)','periodRankScope':'Rupevia published Top 30','truthfulMissingFields':'null'}
    s['quality']=dict(s.get('quality') or {},syntheticResearchFieldsRemoved=True,fullHistoryEnriched=len(funds)-len(failures),fullHistoryFailures=len(failures))
    s['enrichmentFailures']=failures[:50]
    SNAP.write_text(json.dumps(s,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Enriched snapshot',len(funds),'TER matches',sum(1 for f in funds if f.get('expenseRatio') is not None),'failures',len(failures))
if __name__=='__main__':main()
