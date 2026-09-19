#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import json, math, os, time
from pathlib import Path
import requests

OUT=Path(os.getenv('BENCHMARK_OUT','data/benchmark-returns.json'))
URL='https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString'
REPORT_URL='https://www.niftyindices.com/reports/historical-data'
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','45'))
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/149 Safari/537.36 Rupevia-Benchmark-Updater/1.0'
PERIODS=['1M','3M','6M','1Y','3Y','5Y','10Y','10Y+','Since Inception']
INDEXES={
 'Nifty 50 TRI':['NIFTY 50'],
 'Nifty 100 TRI':['NIFTY 100'],
 'Nifty 200 TRI':['NIFTY 200'],
 'Nifty 500 TRI':['NIFTY 500'],
 'Nifty Next 50 TRI':['NIFTY NEXT 50'],
 'Nifty Midcap 150 TRI':['NIFTY MIDCAP 150'],
 'Nifty Midcap Select TRI':['NIFTY MIDCAP SELECT'],
 'Nifty Smallcap 250 TRI':['NIFTY SMALLCAP 250'],
 'Nifty Smallcap 100 TRI':['NIFTY SMALLCAP 100'],
}
CORE={'Nifty 50 TRI','Nifty 100 TRI','Nifty 500 TRI','Nifty Midcap 150 TRI','Nifty Smallcap 250 TRI'}

def fmt_date(d:dt.date)->str:
    return d.strftime('%d-%b-%Y')

def fetch_rows(name:str,start:dt.date,end:dt.date,attempts=3):
    headers={
      'Content-Type':'application/json; charset=UTF-8',
      'X-Requested-With':'XMLHttpRequest',
      'Referer':REPORT_URL,
      'User-Agent':UA,
      'Accept':'application/json, text/javascript, */*; q=0.01',
    }
    inner=f"{{'name':'{name}','startDate':'{fmt_date(start)}','endDate':'{fmt_date(end)}','indexName':'{name}'}}"
    body={'cinfo':inner}
    last=None
    for i in range(attempts):
        try:
            r=requests.post(URL,headers=headers,data=json.dumps(body),timeout=TIMEOUT)
            r.raise_for_status()
            outer=r.json(); d=outer.get('d',[])
            rows=json.loads(d) if isinstance(d,str) else d
            if not isinstance(rows,list): raise RuntimeError('unexpected response shape')
            if not rows: raise RuntimeError('empty TRI history')
            return rows
        except Exception as e:
            last=e
            if i+1<attempts: time.sleep(1.5*(i+1))
    raise RuntimeError(str(last))

def parse_points(rows):
    out=[]
    for x in rows:
        try:
            ds=str(x.get('Date') or x.get('date') or '').strip()
            d=dt.datetime.strptime(ds,'%d %b %Y').date()
            raw=x.get('TotalReturnsIndex',x.get('Total Returns Index'))
            v=float(str(raw).replace(',',''))
            if v>0 and math.isfinite(v): out.append((d,v))
        except Exception:
            continue
    return sorted(set(out))

def shift_months(d:dt.date,n:int)->dt.date:
    import calendar
    y=d.year+(d.month-1-n)//12; m=(d.month-1-n)%12+1
    return dt.date(y,m,min(d.day,calendar.monthrange(y,m)[1]))

def shift_years(d:dt.date,n:int)->dt.date:
    try:return d.replace(year=d.year-n)
    except ValueError:return d.replace(year=d.year-n,day=28)

def at_or_before(points,target):
    ans=None
    for d,v in points:
        if d<=target: ans=(d,v)
        else: break
    return ans

def pct(a,b):
    if not b or b<=0:return None
    x=(a/b-1)*100
    return round(x,2) if math.isfinite(x) else None

def cagr(a,b,days):
    if not b or b<=0 or days<=0:return None
    x=((a/b)**(365.2425/days)-1)*100
    return round(x,2) if math.isfinite(x) else None

def calc_returns(points):
    latest_d,latest_v=points[-1]
    ret={}
    for p,n in [('1M',1),('3M',3),('6M',6)]:
        b=at_or_before(points,shift_months(latest_d,n))
        if b:
            v=pct(latest_v,b[1])
            if v is not None:ret[p]=v
    for p,n in [('1Y',1),('3Y',3),('5Y',5),('10Y',10)]:
        b=at_or_before(points,shift_years(latest_d,n))
        if b:
            v=cagr(latest_v,b[1],(latest_d-b[0]).days)
            if v is not None:ret[p]=v
    first_d,first_v=points[0]; days=(latest_d-first_d).days; years=days/365.2425
    si=cagr(latest_v,first_v,days) if days>=365 else pct(latest_v,first_v)
    if si is not None: ret['Since Inception']=si
    if years>10:
        v=cagr(latest_v,first_v,days)
        if v is not None:ret['10Y+']=v
    return ret

def monthly_series(points):
    by={}
    for d,v in points:by[(d.year,d.month)]=(d,v)
    return [[d.isoformat(),round(v,4)] for d,v in by.values()]

def slug(s):
    return ''.join(c.lower() if c.isalnum() else '-' for c in s).strip('-').replace('--','-')

def main():
    today=dt.date.today(); start=dt.date(1998,1,1)
    benchmarks=[]; failures=[]
    for label,candidates in INDEXES.items():
        ok=None;err=None
        for name in candidates:
            try:
                rows=fetch_rows(name,start,today)
                pts=parse_points(rows)
                if len(pts)<200: raise RuntimeError(f'insufficient TRI points: {len(pts)}')
                ok=(name,pts);break
            except Exception as e:err=str(e)
        if not ok:
            failures.append({'displayName':label,'error':err or 'unavailable'})
            print('FAILED',label,err)
            continue
        name,pts=ok; latest_d,latest_v=pts[-1]; first_d,first_v=pts[0]
        rets=calc_returns(pts)
        benchmarks.append({
          'id':slug(label.replace(' TRI','')),
          'displayName':label,
          'sourceName':name,
          'provider':'NSE Indices Limited',
          'methodology':'Total Return Index (price movement + reinvested dividends)',
          'sourceUrl':REPORT_URL,
          'latestDate':latest_d.isoformat(),
          'latestValue':round(latest_v,4),
          'historyStart':first_d.isoformat(),
          'historyYears':round((latest_d-first_d).days/365.2425,2),
          'returns':rets,
          'monthlySeries':monthly_series(pts),
          'historyPointsFull':len(pts),
          'status':'verified-official'
        })
        print('OK',label,'points',len(pts),'latest',latest_d,'3Y',rets.get('3Y'))
        time.sleep(.4)
    present={x['displayName'] for x in benchmarks}
    missing_core=sorted(CORE-present)
    if missing_core:
        raise SystemExit('Missing required core benchmarks: '+', '.join(missing_core))
    latest=max((x['latestDate'] for x in benchmarks),default=None)
    payload={
      'schemaVersion':1,
      'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
      'sourceAsOf':latest,
      'provider':'NSE Indices Limited',
      'sourceType':'official Total Return Index history',
      'sourceUrl':REPORT_URL,
      'periods':PERIODS,
      'returnMethod':{
        '1M/3M/6M':'point-to-point absolute return using latest available TRI value at or before target date',
        '1Y/3Y/5Y/10Y':'annualised CAGR using latest available TRI value at or before target date',
        '10Y+':'since-index-inception annualised CAGR; displayed only when history exceeds 10 years',
        'Since Inception':'index-history inception return; annualised when history >=1 year',
        'excessReturn':'fund return minus benchmark return; only compared for matching standard 1M through 10Y horizons'
      },
      'quality':{
        'officialProvider':True,
        'totalReturnIndexOnly':True,
        'syntheticValues':False,
        'benchmarkCount':len(benchmarks),
        'coreBenchmarksPresent':len(CORE & present),
        'failedBenchmarks':len(failures)
      },
      'benchmarks':benchmarks,
      'failures':failures
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Wrote',OUT,'benchmarks',len(benchmarks),'failures',len(failures),'as-of',latest)

if __name__=='__main__':main()
