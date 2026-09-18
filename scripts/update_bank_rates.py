#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, io, json, os, re
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd, requests
from bs4 import BeautifulSoup
OUT=Path(os.getenv('BANK_RATES_OUT','data/bank-rates.json')); TIMEOUT=int(os.getenv('HTTP_TIMEOUT','30')); UA='Rupevia-Bank-Rates/1.0'; TARGETS=(12,24,36,60)
BANKS=[
('sbi','State Bank of India','SBI','https://sbi.bank.in/web/interest-rates/deposit-rates/retail-domestic-term-deposits',None,'https://sbi.bank.in/web/interest-rates/deposit-rates/savings-bank-deposits'),
('hdfc','HDFC Bank','HDFC','https://www.hdfcbank.com/personal/save/deposits/fixed-deposit-interest-rate','https://www.hdfcbank.com/personal/save/deposits/recurring-deposit','https://www.hdfcbank.com/personal/save/accounts/savings-accounts'),
('icici','ICICI Bank','ICICI','https://www.icicibank.com/personal-banking/deposits/fixed-deposit/fd-interest-rates','https://www.icicibank.com/personal-banking/deposits/recurring-deposits/rd-interest-rate','https://www.icicibank.com/personal-banking/accounts/savings-account'),
('axis','Axis Bank','Axis','https://www.axisbank.com/interest-rate-on-deposits','https://www.axisbank.com/retail/deposits/recurring-deposits','https://www.axisbank.com/retail/accounts/savings-account'),
('kotak','Kotak Mahindra Bank','Kotak','https://m.kotak.com/td-rates/','https://m.kotak.com/td-rates/','https://www.kotak.com/en/personal-banking/accounts/savings-account/savings-account-interest-rate.html'),
('bob','Bank of Baroda','BoB','https://bankofbaroda.in/interest-rate-and-service-charges/deposits-interest-rates',None,'https://bankofbaroda.in/interest-rate-and-service-charges/deposits-interest-rates'),
('pnb','Punjab National Bank','PNB','https://pnb.bank.in/Interest-Rates-Deposit.html',None,'https://pnb.bank.in/Interest-Rates-Deposit.html'),
('canara','Canara Bank','Canara','https://canarabank.com/pages/deposit-interest-rates',None,'https://canarabank.com/pages/deposit-interest-rates'),
('union','Union Bank of India','Union','https://www.unionbankofindia.co.in/en/details/rate-of-interest-on-domestic-term-deposits',None,'https://www.unionbankofindia.co.in/en/details/saving-bank-deposit-rate'),
('indian','Indian Bank','Indian','https://indianbank.bank.in/deposit-rates',None,'https://indianbank.bank.in/deposit-rates'),
('boi','Bank of India','BoI','https://bankofindia.bank.in/interest-rate/rupee-term-deposit-rate',None,'https://bankofindia.bank.in/interest-rate/saving-bank-deposit-rate'),
('cbi','Central Bank of India','CBI','https://www.centralbank.bank.in/en/interest-rates-on-deposit',None,'https://www.centralbank.bank.in/en/interest-rates-on-deposit'),
('idbi','IDBI Bank','IDBI','https://www.idbibank.in/interest-rates.aspx',None,'https://www.idbibank.in/interest-rates.aspx'),
('indus','IndusInd Bank','IndusInd','https://www.indusind.com/in/en/personal/rates.html','https://www.indusind.com/in/en/personal/rates.html','https://www.indusind.com/in/en/personal/rates.html'),
('federal','Federal Bank','Federal','https://www.federalbank.co.in/deposit-rates',None,'https://www.federalbank.co.in/savings-account-interest-rates'),
('yes','YES BANK','YES','https://www.yesbank.in/personal-banking/yes-individual/deposits/fixed-deposit/fixed-deposit-interest-rates','https://www.yesbank.in/personal-banking/yes-individual/deposits/recurring-deposit','https://www.yesbank.in/personal-banking/yes-individual/accounts/savings-account'),
('idfc','IDFC FIRST Bank','IDFC','https://www.idfcfirstbank.com/personal-banking/deposits/fixed-deposit/fd-interest-rates','https://www.idfcfirstbank.com/personal-banking/deposits/recurring-deposit','https://www.idfcfirstbank.com/personal-banking/accounts/savings-account/interest-rates'),
('rbl','RBL Bank','RBL','https://www.rblbank.com/interest-rates','https://www.rblbank.com/interest-rates','https://www.rblbank.com/interest-rates'),
('au','AU Small Finance Bank','AU SFB','https://www.aubank.in/interest-rates/fixed-deposit',None,'https://www.aubank.in/interest-rates/savings-account'),
('bandhan','Bandhan Bank','Bandhan','https://bandhanbank.com/personal/fixed-deposits','https://bandhanbank.com/personal/recurring-deposit','https://bandhanbank.com/personal/savings-accounts')]
DOMAINS=('sbi.bank.in','hdfcbank.com','icicibank.com','axisbank.com','kotak.com','bankofbaroda.in','pnb.bank.in','canarabank.com','unionbankofindia.co.in','indianbank.bank.in','bankofindia.bank.in','centralbank.bank.in','idbibank.in','indusind.com','federalbank.co.in','yesbank.in','idfcfirstbank.com','rblbank.com','aubank.in','bandhanbank.com')
def clean(x): return re.sub(r'\s+',' ',str(x or '').replace('\xa0',' ')).strip()
def okurl(u): return u and any((urlparse(u).hostname or '').endswith(d) for d in DOMAINS)
def fetch(u):
 r=requests.get(u,headers={'User-Agent':UA,'Accept':'text/html,*/*'},timeout=TIMEOUT); r.raise_for_status(); return r.text
def pct(x):
 m=re.search(r'(?<!\d)(\d{1,2}(?:\.\d{1,3})?)\s*%?',clean(x).replace(',','')); v=float(m.group(1)) if m else None
 return v if v is not None and 0<=v<=15 else None
def effdate(text):
 text=clean(text)
 for p in [r'(?:w\.?e\.?f\.?|effective(?:\s+from)?|applicable\s+from|revised\s+from)\s*[:\-]?\s*(\d{1,2}(?:st|nd|rd|th)?[\-/\. ](?:\d{1,2}|[A-Za-z]{3,9})[\-/\. , ]\d{2,4})',r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{2,4})']:
  m=re.search(p,text,re.I)
  if m:
   raw=re.sub(r'(st|nd|rd|th)','',m.group(1),flags=re.I).replace(',',' '); raw=re.sub(r'\s+',' ',raw).strip(' .-')
   for f in ('%d %B %Y','%d %b %Y','%d-%m-%Y','%d/%m/%Y','%d.%m.%Y','%d %B %y','%d %b %y'):
    try:return dt.datetime.strptime(raw,f).date().isoformat()
    except:pass
 return None
def durvals(s):
 s=clean(s).lower().replace('yrs','years').replace('yr','year').replace('mnths','months').replace('mths','months').replace('mth','month'); out=[]
 for m in re.finditer(r'(?:(\d+)\s*years?)?\s*(?:(\d+)\s*months?)?\s*(?:(\d+)\s*days?)?',s):
  if any(m.groups()):
   d=int(m.group(1) or 0)*365+round(int(m.group(2) or 0)*30.4375)+int(m.group(3) or 0)
   if d: out.append(d)
 return out
def contains(ten,months):
 t=clean(ten).lower(); vals=durvals(t); target=round(months*30.4375)
 if not vals:return False,999999
 if len(vals)==1:
  d=vals[0]
  if any(x in t for x in ('and above','or above','above upto','above up to')):return target>=d,abs(target-d)
  return abs(target-d)<=45,abs(target-d)
 lo,hi=min(vals),max(vals)
 if 'less than' in t or '<' in t:hi=max(lo,hi-1)
 return lo-5<=target<=hi+5,min(abs(target-lo),abs(target-hi))
def flatcols(df):
 if isinstance(df.columns,pd.MultiIndex):return [clean(' '.join(str(x) for x in c if str(x)!='nan')) for c in df.columns]
 return [clean(x) for x in df.columns]
def parse_tables(html,product):
 try:dfs=pd.read_html(io.StringIO(html))
 except:dfs=[]
 text=BeautifulSoup(html,'html.parser').get_text(' ',strip=True); ed=effdate(text); rates={}; seniors={}
 for df in dfs:
  if df.empty or df.shape[1]<2:continue
  cols=flatcols(df); blob=clean(' '.join(cols)+' '+' '.join(map(str,df.astype(str).head(8).values.flatten()))).lower()
  if product=='rd' and 'recurring' not in blob:continue
  if product=='fd' and 'saving' in blob and 'fixed' not in blob and 'term deposit' not in blob:continue
  ti=next((i for i,c in enumerate(cols) if re.search(r'(tenure|tenor|maturity|period|duration)',c,re.I)),None)
  if ti is None:continue
  gc=[i for i,c in enumerate(cols) if re.search(r'(rate|interest|public|general|revised)',c,re.I) and 'senior' not in c.lower() and not re.search(r'(annual|yield|existing)',c,re.I)]
  sc=[i for i,c in enumerate(cols) if 'senior' in c.lower() and not re.search(r'(annual|yield)',c,re.I)]
  for mth in TARGETS:
   cand=[]
   for ri,row in df.iterrows():
    yes,dist=contains(row.iloc[ti],mth)
    if not yes:continue
    vals=[(i,pct(row.iloc[i])) for i in range(len(row)) if i!=ti]; vals=[x for x in vals if x[1] is not None]
    if not vals:continue
    gv=next((pct(row.iloc[i]) for i in gc if i<len(row) and pct(row.iloc[i]) is not None),None) or vals[0][1]
    sv=next((pct(row.iloc[i]) for i in sc if i<len(row) and pct(row.iloc[i]) is not None),None)
    if sv is None:
     sv=next((v for _,v in vals[1:] if gv<=v<=gv+2),None)
    cand.append((dist,ri,gv,sv))
   if cand:
    cand.sort(key=lambda x:(x[0],x[1])); _,_,gv,sv=cand[0]; rates[str(mth)]=round(gv,2)
    if sv is not None:seniors[str(mth)]=round(sv,2)
 return rates,seniors,ed,text.lower()
def parse_savings(html):
 text=BeautifulSoup(html,'html.parser').get_text(' ',strip=True); ed=effdate(text)
 try:dfs=pd.read_html(io.StringIO(html))
 except:dfs=[]
 for df in dfs:
  blob=clean(' '.join(flatcols(df))+' '+' '.join(map(str,df.astype(str).head(8).values.flatten()))).lower()
  if 'saving' not in blob:continue
  for _,row in df.iterrows():
   vals=[pct(x) for x in row]; vals=[x for x in vals if x is not None and .1<=x<=8]
   if vals:return round(vals[-1],2),ed
 m=re.search(r'(?:savings?|saving bank)[^%]{0,240}?(\d(?:\.\d{1,2})?)\s*%',text,re.I)
 return (float(m.group(1)) if m else None),ed
def oldmap():
 try:return {b['id']:b for b in json.loads(OUT.read_text()).get('banks',[])}
 except:return {}
def main():
 OUT.parent.mkdir(parents=True,exist_ok=True); old=oldmap(); now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'); out=[]; fails=[]
 for bid,name,short,fu,ru,su in BANKS:
  p=old.get(bid,{}); row={'id':bid,'name':name,'short':short,'fdRates':dict(p.get('fdRates') or {}),'fdSeniorRates':dict(p.get('fdSeniorRates') or {}),'rdRates':dict(p.get('rdRates') or {}),'rdSeniorRates':dict(p.get('rdSeniorRates') or {}),'savingsRate':p.get('savingsRate'),'effectiveDate':p.get('effectiveDate'),'sourceCheckedAt':now,'productStatus':dict(p.get('productStatus') or {}),'sources':{'fd':fu,'rd':ru,'savings':su}}
  dates=[]; texts={}
  for prod,u in (('fd',fu),('rd',ru)):
   if not okurl(u):continue
   try:
    r,s,e,t=parse_tables(fetch(u),prod); texts[prod]=t
    if r:row[prod+'Rates']=r;row[prod+'SeniorRates']=s;row['productStatus'][prod]='verified-official';dates += [e] if e else []
    else:row['productStatus'][prod]='stale-cache' if row[prod+'Rates'] else 'unavailable';fails.append({'bank':bid,'product':prod,'error':'no parsable table'})
   except Exception as x:row['productStatus'][prod]='stale-cache' if row[prod+'Rates'] else 'unavailable';fails.append({'bank':bid,'product':prod,'error':str(x)[:160]})
  if not str(row['productStatus'].get('rd','')).startswith('verified') and row['fdRates']:
   t=texts.get('rd') or texts.get('fd') or ''
   if 'recurring' in t and re.search(r'(corresponding|same).*fixed deposit|fixed deposit.*(corresponding|same)',t):row['rdRates']=dict(row['fdRates']);row['rdSeniorRates']=dict(row['fdSeniorRates']);row['productStatus']['rd']='verified-official-same-as-fd'
  if okurl(su):
   try:
    v,e=parse_savings(fetch(su))
    if v is not None:row['savingsRate']=v;row['productStatus']['savings']='verified-official';dates += [e] if e else []
    else:row['productStatus']['savings']='stale-cache' if row['savingsRate'] is not None else 'unavailable';fails.append({'bank':bid,'product':'savings','error':'no parsable rate'})
   except Exception as x:row['productStatus']['savings']='stale-cache' if row['savingsRate'] is not None else 'unavailable';fails.append({'bank':bid,'product':'savings','error':str(x)[:160]})
  row['effectiveDate']=max(dates) if dates else row['effectiveDate']; row['verified']=any(str(v).startswith('verified-official') for v in row['productStatus'].values()); out.append(row); print(bid,row['productStatus'])
 snap={'schemaVersion':1,'generatedAt':now,'sourceAsOf':max([b.get('effectiveDate') or '' for b in out] or ['']),'bankCount':len(out),'targetTenuresMonths':list(TARGETS),'scope':'Retail domestic standard-tenure deposit rates. Special promotional tenures are excluded from standard comparison.','method':'Official bank websites only. Failed parses retain last verified cache and are marked stale-cache; missing values remain unavailable.','banks':out,'stats':{'banksWithAnyVerified':sum(b['verified'] for b in out),'fdVerified':sum(str(b['productStatus'].get('fd','')).startswith('verified-official') for b in out),'rdVerified':sum(str(b['productStatus'].get('rd','')).startswith('verified-official') for b in out),'savingsVerified':sum(str(b['productStatus'].get('savings','')).startswith('verified-official') for b in out)},'failures':fails[:100]}
 OUT.write_text(json.dumps(snap,ensure_ascii=False,separators=(',',':'))+'\n'); print(snap['stats'])
 if not snap['stats']['banksWithAnyVerified']:raise SystemExit('No official bank rates parsed; refusing all-unverified publish')
if __name__=='__main__':main()
