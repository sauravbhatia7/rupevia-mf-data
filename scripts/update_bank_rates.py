#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, io, json, math, os, re
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd, requests
from bs4 import BeautifulSoup

OUT=Path(os.getenv('BANK_RATES_OUT','data/bank-rates.json'))
SEED=Path(os.getenv('BANK_RATES_SEED','data/bank-rates-seed.json'))
TIMEOUT=int(os.getenv('HTTP_TIMEOUT','30'))
UA='Rupevia-Bank-Rates/2.0 (+GitHub Actions)'
TARGETS=(12,24,36,60)
MAX_DELTA=float(os.getenv('MAX_RATE_DELTA','0.80'))
SUPPORTED_AUTO={'sbi','hdfc','kotak','pnb','canara','indian','boi','cbi'}
SAME_CARD_RD={'sbi','hdfc','canara','cbi'}

def clean(x): return re.sub(r'\s+',' ',str(x or '').replace('\xa0',' ')).strip()
def fetch(url):
    r=requests.get(url,headers={'User-Agent':UA,'Accept':'text/html,*/*'},timeout=TIMEOUT,allow_redirects=True)
    r.raise_for_status(); return r.text

def valid_rate(v):
    try: v=float(v)
    except: return False
    return math.isfinite(v) and 4.0 <= v <= 9.5

def valid_savings(v):
    try: v=float(v)
    except: return False
    return math.isfinite(v) and 1.5 <= v <= 5.0

def near(v,base,delta=MAX_DELTA):
    return valid_rate(v) and valid_rate(base) and abs(float(v)-float(base)) <= delta

def date_from_text(text):
    text=clean(text)
    hits=[]
    pats=[r'(?:w\.?e\.?f\.?|with effect from|effective from|applicable from|revised(?: rates)?(?: w\.?e\.?f\.?)?)\s*[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?(?:\s+|[-/.])(?:[A-Za-z]{3,9}|\d{1,2})(?:\s+|[-/.,])\d{2,4})']
    for pat in pats:
        for m in re.finditer(pat,text,re.I):
            raw=re.sub(r'(st|nd|rd|th)','',m.group(1),flags=re.I).replace(',',' ')
            raw=re.sub(r'\s+',' ',raw).strip(' .-')
            for f in ('%d %B %Y','%d %b %Y','%d-%m-%Y','%d/%m/%Y','%d.%m.%Y','%d %B %y','%d %b %y'):
                try: hits.append(dt.datetime.strptime(raw,f).date()); break
                except: pass
    return max(hits).isoformat() if hits else None

def duration_range(label):
    s=clean(label).lower().replace('yrs','years').replace('yr','year').replace('mnths','months').replace('mths','months').replace('mth','month')
    vals=[]
    for m in re.finditer(r'(?:(\d+)\s*years?)?\s*(?:(\d+)\s*months?)?\s*(?:(\d+)\s*days?)?',s):
        if any(m.groups()):
            d=int(m.group(1) or 0)*365.2425+int(m.group(2) or 0)*30.4375+int(m.group(3) or 0)
            if d: vals.append(d)
    if not vals:return None
    if len(vals)==1:
        v=vals[0]
        if re.search(r'(and above|or above|above upto|above up to|and up to|to 10 years)',s): return (v,3652.5)
        return (v-3,v+3)
    return (min(vals)-3,max(vals)+3)

def label_matches(label,months):
    rr=duration_range(label)
    if not rr:return False
    target=months*30.4375
    return rr[0] <= target <= rr[1]

def row_numbers(row):
    vals=[]
    for x in row:
        txt=clean(x).replace(',','')
        for m in re.finditer(r'(?<!\d)(\d{1,2}(?:\.\d{1,3})?)\s*%?',txt):
            v=float(m.group(1))
            if 1.5 <= v <= 10.5: vals.append(v)
    return vals

def anchored_rates(html,base,base_senior):
    try: dfs=pd.read_html(io.StringIO(html))
    except Exception: dfs=[]
    out={}; senior={}
    for months in TARGETS:
        key=str(months); b=base.get(key); sb=base_senior.get(key)
        if not valid_rate(b): continue
        candidates=[]
        for df in dfs:
            if df.empty: continue
            for _,row in df.astype(str).iterrows():
                label=' '.join(clean(x) for x in list(row.iloc[:2]))
                if not label_matches(label,months): continue
                nums=row_numbers(row.tolist())
                for v in nums:
                    if near(v,b): candidates.append((abs(v-b),v,nums))
        if not candidates: continue
        candidates.sort(key=lambda x:x[0]); gv=candidates[0][1]
        out[key]=round(gv,2)
        nums=candidates[0][2]
        if valid_rate(sb):
            sc=[v for v in nums if v >= gv and v <= gv+1.5 and abs(v-sb)<=MAX_DELTA]
            if sc: senior[key]=round(min(sc,key=lambda v:abs(v-sb)),2)
    return out,senior

def merge_safe(base,new):
    out=dict(base or {})
    for k,v in (new or {}).items():
        old=out.get(k)
        if valid_rate(v) and (not valid_rate(old) or abs(float(v)-float(old))<=MAX_DELTA): out[k]=round(float(v),2)
    return out

def main():
    if not SEED.exists(): raise SystemExit('bank-rates-seed.json missing')
    seed=json.loads(SEED.read_text(encoding='utf-8'))
    try: previous=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else seed
    except: previous=seed
    prev={b['id']:b for b in previous.get('banks',[])}
    now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
    rows=[]; failures=[]
    for s in seed['banks']:
        bid=s['id']; p=prev.get(bid,{})
        row=json.loads(json.dumps(s))
        for fld in ('fdRates','fdSeniorRates','rdRates','rdSeniorRates'):
            safe=dict(s.get(fld) or {})
            for k,v in (p.get(fld) or {}).items():
                anchor=safe.get(k)
                if valid_rate(anchor) and near(v,anchor): safe[k]=round(float(v),2)
            row[fld]=safe
        if s.get('savingsRate') is not None:
            pv=p.get('savingsRate')
            row['savingsRate']=round(float(pv),2) if valid_savings(pv) and abs(float(pv)-float(s['savingsRate']))<=1.0 else s['savingsRate']
        row['sourceCheckedAt']=now
        row['productStatus']=dict(s.get('productStatus') or {})
        row['productEffectiveDate']=dict(s.get('productEffectiveDate') or {})
        if bid in SUPPORTED_AUTO:
            try:
                html=fetch(row['sources']['fd']); txt=BeautifulSoup(html,'html.parser').get_text(' ',strip=True)
                nr,ns=anchored_rates(html,row['fdRates'],row['fdSeniorRates'])
                if nr:
                    row['fdRates']=merge_safe(row['fdRates'],nr); row['fdSeniorRates']=merge_safe(row['fdSeniorRates'],ns)
                    row['productStatus']['fd']='verified-official-auto'; row['productEffectiveDate']['fd']=date_from_text(txt) or row['productEffectiveDate'].get('fd')
                elif row['fdRates']: row['productStatus']['fd']='last-verified-official'
            except Exception as e:
                if row['fdRates']: row['productStatus']['fd']='last-verified-official'
                failures.append({'bank':bid,'product':'fd','error':str(e)[:160]})
            if bid in SAME_CARD_RD and row['fdRates']:
                row['rdRates']=dict(row['fdRates']); row['rdSeniorRates']=dict(row['fdSeniorRates'])
                row['productStatus']['rd']='verified-official-same-as-term-card'
                row['productEffectiveDate']['rd']=row['productEffectiveDate'].get('fd')
            elif row.get('rdRates'):
                try:
                    html=fetch(row['sources']['rd']); txt=BeautifulSoup(html,'html.parser').get_text(' ',strip=True)
                    nr,ns=anchored_rates(html,row['rdRates'],row['rdSeniorRates'])
                    if nr:
                        row['rdRates']=merge_safe(row['rdRates'],nr); row['rdSeniorRates']=merge_safe(row['rdSeniorRates'],ns)
                        row['productStatus']['rd']='verified-official-auto'; row['productEffectiveDate']['rd']=date_from_text(txt) or row['productEffectiveDate'].get('rd')
                    else: row['productStatus']['rd']='last-verified-official'
                except Exception as e:
                    row['productStatus']['rd']='last-verified-official'; failures.append({'bank':bid,'product':'rd','error':str(e)[:160]})
        dates=[d for d in row['productEffectiveDate'].values() if d]
        row['effectiveDate']=max(dates) if dates else None
        row['verified']=bool(row['fdRates'] or row['rdRates'] or row.get('savingsRate') is not None)
        rows.append(row)
    snap={
      'schemaVersion':2,'generatedAt':now,'sourceAsOf':max([b.get('effectiveDate') or '' for b in rows] or ['']),
      'bankCount':len(rows),'targetTenuresMonths':list(TARGETS),
      'scope':seed['scope'],'method':seed['method']+' Automatic parsing is anchored to last vetted official card rates; implausible jumps are rejected and the last verified cache is retained.',
      'banks':rows,
      'stats':{'banksWithAnyVerified':sum(b['verified'] for b in rows),'fdBanksWith24M':sum('24' in b['fdRates'] for b in rows),'rdBanksWith24M':sum('24' in b['rdRates'] for b in rows),'savingsVerified':sum(b.get('savingsRate') is not None for b in rows)},
      'failures':failures[:100]
    }
    OUT.write_text(json.dumps(snap,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('Rupevia bank snapshot',snap['stats'],'as-of',snap['sourceAsOf'],'failures',len(failures))
    if snap['stats']['fdBanksWith24M'] < 5 or snap['stats']['rdBanksWith24M'] < 5: raise SystemExit('Insufficient verified 24M coverage')

if __name__=='__main__': main()
