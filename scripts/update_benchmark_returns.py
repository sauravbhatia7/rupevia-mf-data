#!/usr/bin/env python3
from __future__ import annotations
import calendar, concurrent.futures as cf, datetime as dt
import json, math, os, time
from pathlib import Path
import requests

OUT=Path(os.getenv('BENCHMARK_OUT','data/benchmark-returns.json'))
URL='https://niftyindices.com/BackPage/getTotalReturnIndexString'
REPORT_URL='https://www.niftyindices.com/reports/historical-data'
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
WORKERS=int(os.getenv('BENCHMARK_WORKERS','3'))
PERIODS=['1M','3M','6M','1Y','3Y','5Y','10Y','10Y+','Since Inception']
INDEXES={
 'Nifty 50 TRI':'NIFTY 50','Nifty 100 TRI':'NIFTY 100','Nifty 200 TRI':'NIFTY 200',
 'Nifty 500 TRI':'NIFTY 500','Nifty Next 50 TRI':'NIFTY NEXT 50',
 'Nifty Midcap 150 TRI':'NIFTY MIDCAP 150','Nifty Midcap Select TRI':'NIFTY MIDCAP SELECT',
 'Nifty Smallcap 250 TRI':'NIFTY SMALLCAP 250','Nifty Smallcap 100 TRI':'NIFTY SMALLCAP 100'}
CORE={'Nifty 50 TRI','Nifty 100 TRI','Nifty 500 TRI','Nifty Midcap 150 TRI','Nifty Smallcap 250 TRI'}
UA='Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134 Safari/537.36'
HEADERS={
 'Host':'niftyindices.com','Referer':'niftyindices.com','X-Requested-With':'XMLHttpRequest',
 'User-Agent':UA,'Origin':'https://niftyindices.com','Accept':'*/*','Accept-Encoding':'gzip, deflate',
 'Accept-Language':'en-GB,en-US;q=0.9,en;q=0.8','Cache-Control':'no-cache','Connection':'keep-alive',
 'Content-Type':'application/json; charset=UTF-8'}

def month_bounds(d):
    return d.replace(day=1),d.replace(day=calendar.monthrange(d.year,d.month)[1])
def previous_month(d):
    return (d.replace(day=1)-dt.timedelta(days=1))
def shift_months(d,n):
    y=d.year+(d.month-1-n)//12;m=(d.month-1-n)%12+1
    return dt.date(y,m,min(d.day,calendar.monthrange(y,m)[1]))
def shift_years(d,n):
    try:return d.replace(year=d.year-n)
    except ValueError:return d.replace(year=d.year-n,day=28)
def at_or_before(points,target):
    ans=None
    for d,v in points:
        if d<=target:ans=(d,v)
        else:break
    return ans
def pct(a,b):
    if not b or b<=0:return None
    v=(a/b-1)*100
    return round(v,2) if math.isfinite(v) else None
def cagr(a,b,days):
    if not b or b<=0 or days<=0:return None
    v=((a/b)**(365.2425/days)-1)*100
    return round(v,2) if math.isfinite(v) else None

def parse_rows(raw):
    if isinstance(raw,dict) and 'd' in raw:raw=raw['d']
    if isinstance(raw,str):raw=json.loads(raw)
    if not isinstance(raw,list):raise RuntimeError(f'unexpected response type {type(raw).__name__}')
    out=[]
    for x in raw:
        if not isinstance(x,dict):continue
        try:
            ds=str(x.get('Date') or '').strip();d=dt.datetime.strptime(ds,'%d %b %Y').date()
            v=float(str(x.get('TotalReturnsIndex')).replace(',',''))
            if v>0 and math.isfinite(v):out.append((d,v))
        except Exception:pass
    return out

def fetch_month(session,name,d,attempts=3):
    a,b=month_bounds(d);today=dt.date.today();b=min(b,today)
    if a>b:return []
    cinfo={'name':name,'startDate':a.strftime('%d-%b-%Y'),'endDate':b.strftime('%d-%b-%Y'),'indexName':name}
    body={'cinfo':str(cinfo).replace('"',"'")};last=None
    for i in range(attempts):
        try:
            r=session.post(URL,json=body,timeout=TIMEOUT);r.raise_for_status()
            return parse_rows(r.json())
        except Exception as e:
            last=e
            if i+1<attempts:time.sleep(1.2*(i+1))
    raise RuntimeError(f'{name} {a:%Y-%m}: {last}')

def collect_windows(name,months):
    s=requests.Session();s.headers.update(HEADERS);pts=[]
    for d in sorted(months):pts.extend(fetch_month(s,name,d))
    return sorted(set(pts))

def build_one(item):
    label,name=item;today=dt.date.today()
    # Current + previous month first, so returns anchor on the latest official TRI date.
    current_months={today.replace(day=1),previous_month(today).replace(day=1)}
    latest_pts=collect_windows(name,current_months)
    if not latest_pts:raise RuntimeError('no latest official TRI values')
    latest_d,latest_v=latest_pts[-1]
    targets={'1M':shift_months(latest_d,1),'3M':shift_months(latest_d,3),'6M':shift_months(latest_d,6),
             '1Y':shift_years(latest_d,1),'3Y':shift_years(latest_d,3),'5Y':shift_years(latest_d,5),'10Y':shift_years(latest_d,10)}
    months=set(current_months)
    for t in targets.values():
        months.add(t.replace(day=1));months.add(previous_month(t).replace(day=1))
    pts=collect_windows(name,months)
    latest=at_or_before(pts,latest_d)
    if not latest:raise RuntimeError('latest TRI anchor missing after window collection')
    latest_d,latest_v=latest;returns={};anchors={}
    for p,t in targets.items():
        base=at_or_before(pts,t)
        if not base:continue
        days=(latest_d-base[0]).days
        v=pct(latest_v,base[1]) if p in {'1M','3M','6M'} else cagr(latest_v,base[1],days)
        if v is not None:
            returns[p]=v;anchors[p]={'targetDate':t.isoformat(),'usedDate':base[0].isoformat(),'value':round(base[1],4)}
    if not all(p in returns for p in ('1M','3M','6M','1Y','3Y','5Y')):
        raise RuntimeError('missing required standard-period TRI anchors')
    return {'id':label.lower().replace(' tri','').replace(' ','-'),'displayName':label,'sourceName':name,
      'provider':'NSE Indices Limited','methodology':'Total Return Index (price movement + reinvested dividends)',
      'sourceUrl':REPORT_URL,'latestDate':latest_d.isoformat(),'latestValue':round(latest_v,4),'returns':returns,
      'anchors':anchors,'status':'verified-official','historyMode':'target-window official TRI values'}

def main():
    benchmarks=[];failures=[]
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs={ex.submit(build_one,item):item[0] for item in INDEXES.items()}
        for fu in cf.as_completed(futs):
            label=futs[fu]
            try:
                b=fu.result();benchmarks.append(b);print('OK',label,b['latestDate'],b['returns'])
            except Exception as e:
                failures.append({'displayName':label,'error':str(e)[:240]});print('FAILED',label,e)
    benchmarks.sort(key=lambda b:list(INDEXES).index(b['displayName']))
    present={b['displayName'] for b in benchmarks};missing=sorted(CORE-present)
    if missing:raise SystemExit('Missing required core benchmarks: '+', '.join(missing))
    source_as_of=max(b['latestDate'] for b in benchmarks)
    payload={'schemaVersion':1,
      'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
      'sourceAsOf':source_as_of,'provider':'NSE Indices Limited','sourceType':'official Total Return Index history',
      'sourceUrl':REPORT_URL,'periods':PERIODS,
      'returnMethod':{
        '1M/3M/6M':'point-to-point absolute return using official TRI latest value and latest available TRI value at or before target date',
        '1Y/3Y/5Y/10Y':'annualised CAGR using official TRI latest value and latest available TRI value at or before target date',
        '10Y+':'not published in benchmark snapshot because fund/index start dates differ',
        'Since Inception':'not published in benchmark snapshot because fund/index inception dates differ',
        'excessReturn':'fund return minus benchmark return for matching standard 1M through 10Y horizons only'},
      'quality':{'officialProvider':True,'totalReturnIndexOnly':True,'syntheticValues':False,
        'benchmarkCount':len(benchmarks),'coreBenchmarksPresent':len(CORE&present),'failedBenchmarks':len(failures)},
      'benchmarks':benchmarks,'failures':failures}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Wrote',OUT,'benchmarks',len(benchmarks),'failures',len(failures),'as-of',source_as_of)
if __name__=='__main__':main()
