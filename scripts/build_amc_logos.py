#!/usr/bin/env python3
"""Build an offline AMC logo registry with complete coverage."""
from __future__ import annotations
import base64, concurrent.futures as cf, datetime as dt, html, json, re, urllib.parse, urllib.request
from pathlib import Path
UNIVERSE=Path('data/mf-universe.json'); OUT=Path('data/amc-logos.json')
UA='Mozilla/5.0 (compatible; Rupevia-AMC-Logo-Registry/1.3)'; TIMEOUT=8
DOMAINS={
'360 one':'360.one','ask':'askmutualfund.com','abakkus':'abakkusmf.com','aditya birla':'adityabirlacapital.com','alphagrep':'alphagrepmf.ai','angel one':'angelonemf.com','axis':'axismf.com','bajaj finserv':'bajajamc.com','bandhan':'bandhanmutual.com','bank of india':'boimf.in','baroda bnp':'barodabnpparibasmf.in','canara robeco':'canararobeco.com','capitalmind':'capitalmindmf.com','choice':'choicemf.com','dsp':'dspim.com','edelweiss':'edelweissmf.com','franklin templeton':'franklintempletonindia.com','groww':'growwmf.in','hdfc':'hdfcfund.com','helios':'heliosmf.in','hsbc':'hsbc.co.in','icici prudential':'icicipruamc.com','iti':'itimf.com','invesco':'invescomutualfund.com','jio blackrock':'jioblackrockamc.com','jm financial':'jmfinancialmf.com','kotak mahindra':'kotakmf.com','lic':'licmf.com','mahindra manulife':'mahindramanulife.com','mirae asset':'miraeassetmf.co.in','monarch':'monarchamc.in','motilal oswal':'motilaloswalmf.com','nj':'njmutualfund.com','navi':'navimutualfund.com','nippon india':'mf.nipponindiaim.com','old bridge':'oldbridgemf.com','pgim india':'pgimindiamf.com','ppfas':'ppfas.com','quantum':'quantumamc.com','quant':'quantmutual.com','samco':'samcomf.com','sbi':'sbimf.com','shriram':'shriramamc.in','sundaram':'sundarammutual.com','tata':'tatamutualfund.com','taurus':'taurusmutualfund.com','wealth company':'wealthcompanyamc.in','trust':'trustmf.com','unifi':'unifimf.com','union':'unionmf.com','uti':'utimf.com','whiteoak':'whiteoakamc.com','zerodha':'zerodhafundhouse.com'}
STATIC={
'Nippon India Mutual Fund':'https://static.paytmmoney.com/amc-logo/RELMF.png',
'Union Mutual Fund':'https://api.finity.in/static/img/amc-logo/low-res/union.png',
'Sundaram Mutual Fund':'https://api.finity.in/static/img/amc-logo/high-res/sundaram.png',
'Quantum Mutual Fund':'https://www.valueresearchonline.com/content-assets/images/228175_fund_manager_changes_in_a_few_schemes_of_quantum_mutual_fund__w1200__.jpg'}
def norm(v):
 s=str(v or '').lower(); s=re.sub(r'asset management|mutual fund|fund house|limited|ltd\\.?',' ',s); return re.sub(r'\\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()
def domain_for(name):
 n=norm(name); keys=[k for k in DOMAINS if k in n]; return DOMAINS[max(keys,key=len)] if keys else ''
def _mime(raw,header=''):
 h=(header or '').split(';',1)[0].strip().lower()
 if h.startswith('image/'): return h
 if raw.startswith(b'\\x89PNG'): return 'image/png'
 if raw[:3]==b'\\xff\\xd8\\xff': return 'image/jpeg'
 if raw.startswith((b'GIF87a',b'GIF89a')): return 'image/gif'
 if raw.startswith(b'\\x00\\x00\\x01\\x00'): return 'image/x-icon'
 if b'<svg' in raw[:1500].lower(): return 'image/svg+xml'
 return ''
def _get_image(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'})
 with urllib.request.urlopen(req,timeout=TIMEOUT) as r: raw=r.read(768000); ct=_mime(raw,r.headers.get('Content-Type',''))
 if not ct or len(raw)<100: raise RuntimeError('not usable image')
 return ct,'data:'+ct+';base64,'+base64.b64encode(raw).decode('ascii')
def _official_urls(domain):
 root='https://'+domain+'/'; out=[root+'favicon.ico',root+'favicon.png',root+'apple-touch-icon.png']
 try:
  req=urllib.request.Request(root,headers={'User-Agent':UA,'Accept':'text/html,*/*'})
  with urllib.request.urlopen(req,timeout=TIMEOUT) as r: page=r.read(400000).decode('utf-8',errors='ignore')
  for tag in re.findall(r'<link\\b[^>]*>',page,flags=re.I):
   if not re.search(r'rel=["\\\'][^"\\\']*(?:icon|apple-touch-icon)[^"\\\']*["\\\']',tag,flags=re.I): continue
   m=re.search(r'href=["\\\']([^"\\\']+)["\\\']',tag,flags=re.I)
   if m: out.append(urllib.parse.urljoin(root,html.unescape(m.group(1))))
 except Exception: pass
 return list(dict.fromkeys(out))
def fetch_logo(domain):
 q=urllib.parse.quote(domain,safe=''); qu=urllib.parse.quote('https://'+domain,safe=''); errs=[]
 for provider,url in [('duckduckgo',f'https://icons.duckduckgo.com/ip3/{domain}.ico'),('google-url',f'https://www.google.com/s2/favicons?domain_url={qu}&sz=128'),('google',f'https://www.google.com/s2/favicons?domain={q}&sz=128'),('clearbit',f'https://logo.clearbit.com/{domain}?size=128')]:
  try:
   ct,data=_get_image(url); return ct,data,provider
  except Exception as e: errs.append(provider+':'+str(e)[:60])
 for url in _official_urls(domain):
  try:
   ct,data=_get_image(url); return ct,data,'official'
  except Exception as e: errs.append('official:'+str(e)[:60])
 raise RuntimeError('; '.join(errs[-6:]))
def resolve(amc,old):
 domain=domain_for(amc)
 if not domain: raise RuntimeError('no domain mapping')
 prev=old.get(amc) or {}
 if prev.get('domain')==domain and str(prev.get('dataUri') or '').startswith('data:image/'): return amc,prev
 if amc in STATIC:
  try:
   mime,data=_get_image(STATIC[amc]); return amc,{'domain':domain,'mime':mime,'provider':'verified-static','dataUri':data}
  except Exception: pass
 mime,data,provider=fetch_logo(domain); return amc,{'domain':domain,'mime':mime,'provider':provider,'dataUri':data}
def main():
 u=json.loads(UNIVERSE.read_text(encoding='utf-8')); amcs=list(u.get('amcs') or []); old={}
 if OUT.exists():
  try: old=json.loads(OUT.read_text(encoding='utf-8')).get('logos') or {}
  except Exception: old={}
 logos={}; failures=[]
 with cf.ThreadPoolExecutor(max_workers=10) as ex:
  futs={ex.submit(resolve,a,old):a for a in amcs}
  for fut in cf.as_completed(futs):
   a=futs[fut]
   try:
    k,v=fut.result(); logos[k]=v; print('logo',k,v.get('provider','cached'),len(v.get('dataUri','')))
   except Exception as e: failures.append({'amc':a,'domain':domain_for(a),'error':str(e)[:350]})
 if failures: raise RuntimeError('AMC logo coverage failed: '+json.dumps(failures,ensure_ascii=False))
 if len(logos)!=len(amcs): raise RuntimeError(f'logo coverage {len(logos)}/{len(amcs)}')
 doc={'schemaVersion':1,'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'sourceAsOf':u.get('sourceAsOf',''),'amcCount':len(amcs),'logoCount':len(logos),'logos':{a:logos[a] for a in amcs}}
 OUT.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\\n',encoding='utf-8'); print('AMC logo registry OK:',len(logos),'/',len(amcs),'bytes',OUT.stat().st_size); return 0
if __name__=='__main__': raise SystemExit(main())
