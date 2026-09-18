#!/usr/bin/env python3
"""Build a compact offline AMC logo registry from the current MF universe.
Uses each AMC's own domain favicon via Google's favicon resolver; existing cached
assets are reused, so normal daily NAV refreshes do not redownload all logos.
"""
from __future__ import annotations
import base64, datetime as dt, json, re, urllib.parse, urllib.request
from pathlib import Path

UNIVERSE=Path('data/mf-universe.json')
OUT=Path('data/amc-logos.json')
UA='Rupevia-AMC-Logo-Registry/1.0 (+GitHub Actions)'
TIMEOUT=30

DOMAINS={
'360 one':'360.one','ask':'askmutualfund.com','abakkus':'abakkusmf.com','aditya birla':'adityabirlacapital.com','alphagrep':'alphagrepmf.ai','angel one':'angelonemf.com','axis':'axismf.com','bajaj finserv':'bajajamc.com','bandhan':'bandhanmutual.com','bank of india':'boimf.in','baroda bnp':'barodabnpparibasmf.in','canara robeco':'canararobeco.com','capitalmind':'capitalmindmf.com','choice':'choicemf.com','dsp':'dspim.com','edelweiss':'edelweissmf.com','franklin templeton':'franklintempletonindia.com','groww':'growwmf.in','hdfc':'hdfcfund.com','helios':'heliosmf.in','hsbc':'hsbc.co.in','icici prudential':'icicipruamc.com','iti':'itimf.com','invesco':'invescomutualfund.com','jio blackrock':'jioblackrockamc.com','jm financial':'jmfinancialmf.com','kotak mahindra':'kotakmf.com','kotak':'kotakmf.com','lic':'licmf.com','mahindra manulife':'mahindramanulife.com','mirae asset':'miraeassetmf.co.in','monarch':'monarchamc.in','motilal oswal':'motilaloswalmf.com','nj':'njmutualfund.com','navi':'navimutualfund.com','nippon india':'nipponindiaim.com','old bridge':'oldbridgemf.com','pgim india':'pgimindiamf.com','ppfas':'ppfas.com','quantum':'quantummf.com','quant':'quantmutual.com','samco':'samcomf.com','sbi':'sbimf.com','shriram':'shriramamc.in','sundaram':'sundarammutual.com','tata':'tatamutualfund.com','taurus':'taurusmutualfund.com','wealth company':'wealthcompanyamc.in','trust':'trustmf.com','unifi':'unifimf.com','union':'unionmf.com','uti':'utimf.com','whiteoak':'whiteoakamc.com','white oak':'whiteoakamc.com','zerodha':'zerodhafundhouse.com'
}

def norm(v:str)->str:
    s=str(v or '').lower()
    s=re.sub(r'asset management|mutual fund|fund house|limited|ltd\.?',' ',s)
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()

def domain_for(name:str)->str:
    n=norm(name); best=''
    for k in DOMAINS:
        if k in n and len(k)>len(best): best=k
    return DOMAINS.get(best,'')

def fetch_logo(domain:str)->tuple[str,str]:
    url='https://www.google.com/s2/favicons?domain='+urllib.parse.quote(domain)+'&sz=128'
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'image/*'})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        raw=r.read(); ct=(r.headers.get_content_type() or 'image/png').lower()
    if len(raw)<100: raise RuntimeError(f'logo too small for {domain}: {len(raw)}')
    if not ct.startswith('image/'): ct='image/png'
    return ct,'data:'+ct+';base64,'+base64.b64encode(raw).decode('ascii')

def main()->int:
    u=json.loads(UNIVERSE.read_text(encoding='utf-8'))
    amcs=list(u.get('amcs') or [])
    old={}
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding='utf-8')).get('logos') or {}
        except Exception: old={}
    logos={}; failures=[]
    for amc in amcs:
        domain=domain_for(amc)
        if not domain:
            failures.append({'amc':amc,'error':'no domain mapping'}); continue
        prev=old.get(amc) or {}
        if prev.get('domain')==domain and str(prev.get('dataUri') or '').startswith('data:image/'):
            logos[amc]=prev; continue
        try:
            mime,data=fetch_logo(domain)
            logos[amc]={'domain':domain,'mime':mime,'dataUri':data}
            print('downloaded',amc,domain,len(data))
        except Exception as exc:
            failures.append({'amc':amc,'domain':domain,'error':str(exc)[:180]})
    if failures:
        raise RuntimeError('AMC logo coverage failed: '+json.dumps(failures,ensure_ascii=False))
    if len(logos)!=len(amcs): raise RuntimeError(f'logo coverage {len(logos)}/{len(amcs)}')
    doc={'schemaVersion':1,'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'sourceAsOf':u.get('sourceAsOf',''),'amcCount':len(amcs),'logoCount':len(logos),'logos':logos}
    OUT.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('AMC logo registry OK:',len(logos),'/',len(amcs),'bytes',OUT.stat().st_size)
    return 0
if __name__=='__main__': raise SystemExit(main())
