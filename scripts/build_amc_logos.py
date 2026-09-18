#!/usr/bin/env python3
"""Build an offline AMC logo registry with complete coverage.

Four difficult AMC logos are embedded from user-supplied assets so the registry
never depends on their websites. Existing cached registry entries are reused.
"""
from __future__ import annotations
import base64, concurrent.futures as cf, datetime as dt, html, json, re, urllib.parse, urllib.request
from pathlib import Path

UNIVERSE=Path('data/mf-universe.json')
OUT=Path('data/amc-logos.json')
UA='Mozilla/5.0 (compatible; Rupevia-AMC-Logo-Registry/1.4)'
TIMEOUT=8

DOMAINS={
'360 one':'360.one','ask':'askmutualfund.com','abakkus':'abakkusmf.com','aditya birla':'adityabirlacapital.com','alphagrep':'alphagrepmf.ai','angel one':'angelonemf.com','axis':'axismf.com','bajaj finserv':'bajajamc.com','bandhan':'bandhanmutual.com','bank of india':'boimf.in','baroda bnp':'barodabnpparibasmf.in','canara robeco':'canararobeco.com','capitalmind':'capitalmindmf.com','choice':'choicemf.com','dsp':'dspim.com','edelweiss':'edelweissmf.com','franklin templeton':'franklintempletonindia.com','groww':'growwmf.in','hdfc':'hdfcfund.com','helios':'heliosmf.in','hsbc':'hsbc.co.in','icici prudential':'icicipruamc.com','iti':'itimf.com','invesco':'invescomutualfund.com','jio blackrock':'jioblackrockamc.com','jm financial':'jmfinancialmf.com','kotak mahindra':'kotakmf.com','lic':'licmf.com','mahindra manulife':'mahindramanulife.com','mirae asset':'miraeassetmf.co.in','monarch':'monarchamc.in','motilal oswal':'motilaloswalmf.com','nj':'njmutualfund.com','navi':'navimutualfund.com','nippon india':'mf.nipponindiaim.com','old bridge':'oldbridgemf.com','pgim india':'pgimindiamf.com','ppfas':'ppfas.com','quantum':'quantumamc.com','quant':'quantmutual.com','samco':'samcomf.com','sbi':'sbimf.com','shriram':'shriramamc.in','sundaram':'sundarammutual.com','tata':'tatamutualfund.com','taurus':'taurusmutualfund.com','wealth company':'wealthcompanyamc.in','trust':'trustmf.com','unifi':'unifimf.com','union':'unionmf.com','uti':'utimf.com','whiteoak':'whiteoakamc.com','zerodha':'zerodhafundhouse.com'}

STATIC_URLS={
'Nippon India Mutual Fund':'https://static.paytmmoney.com/amc-logo/RELMF.png',
'Union Mutual Fund':'https://api.finity.in/static/img/amc-logo/low-res/union.png',
'Sundaram Mutual Fund':'https://api.finity.in/static/img/amc-logo/high-res/sundaram.png',
'Quantum Mutual Fund':'https://www.valueresearchonline.com/content-assets/images/228175_fund_manager_changes_in_a_few_schemes_of_quantum_mutual_fund__w1200__.jpg'}

STATIC_DATA={"Nippon India Mutual Fund":"data:image/webp;base64,UklGRiQEAABXRUJQVlA4IBgEAACQGgCdASpgAGAAPnk2l0ekoyIhKPGsSJAPCWwAzFXmXF5UTwXUPvz+O/U2nR9Hfg2cB/APUA/QD9bOsB/9PQB/I/xu9gD/AdYB/HuoA///qAftV1k37Wfpx/8fdw6gD//xS3xP4QdaveB4Af/V6jf4PimeS+iA2L4GuCEYGRFkrrEDRIPIcs+/t+2QLyhDBOUzMGAL43zAuYpKgTopMsc0mrHEEkWqDb4X1lqxpI6JyDZEXqu1bd7MO838NH8PlILslxFB95Czbac3azzVX4muXPlykMg6lHr/RR8qQAD+/UfLB8O6EgA+awWnKe2aUoBuO+DNfLzd7/NrlTEQhKToltDiskSyLEdVV2kRU84eqntrcXcJBRSa9pAx1L7laIrnTE4EbfVBQSWmoEADb+8lP45mO+RZKBzUOTvnkm4fr5x6ihanSPl675uBgm5zzFYxHO6UbCsB+c0MvONDYL7wqPH0m4ds8r/+TsUhftjXnvHGmsyZxdIwYrsUvvOBoIajXXwTk9kINxBplsDVvliDMi0bZatFIq4VlWeNg5XS+JRYIvhZg0alZ0+O6Yf6f/hyPndg+5eoLsX0rwdtGdt8WT/ya22aNVMh23R2yG67h/Les5hqnfNyc7FEFB8wC/nco7Ujb9XcRPqRKTolnfrWUbis06YRV47nzK5D6OVYbTaIkfnrL9z0+XF7B/9vXtFcBo0Ilj9LUx4Jpixqln2UXdwKYv2xk7oVNKSUVgrWUR9U/iAjvpVPwwhA5toJTwK1CuHgV4PSeuKMIn2X/H6DDayrRNWS0H4uPZ4+FV5GPeQ/KFmJBX/nl9/y/8GR/55fgIhJof8sZVg5WyfxJ3tafkHTngVer0TT/TB72rchxKnr13jZJZou5UYwD3LerA1fpBcmaRxny8w8AkIWB1JXBZzQoevm7ujuNSs0Pz9X0CCXK+4/xB5Iog6rDo6Au/Um73KEkBBIpmr87ymfnHrDb9ecOhUVj9C6ZLKkOdGCc8QPPgKnFelJ2kiFSFJTEVvn4VH0OU58sLxA3colRw9VnGMymQaVEPFjIpVJeo3HmFz4wQABn3yIOdXpIX/gHqx5Q+OGdyaCUhwMymtJ9wiBH4UmqiZkR30kr5iinrUke4kmvIcVT/D6E/taPCq+i4pds0VYxGahvyTKsOobvR1hXqcoWsf21k78Y2sqj6JPupNwJvqVSHxMTryme8DWdr4N5K0faZeGL0JJgpZXoreySZ3lg63qC0yY1dnrY/T8LKnHxdcEC0vIKwpCpzAvtr/k7GaU4CZb8K8iN5E9xBnA8AAB3ZryGNfLp1/xTpms1nDAFQEODoKART33kFMetKxR77I3RxRLDt0i1dcQRvM09lVzWhDcgA9WPKHxwzuTQSkOFGCAgAAA","Quantum Mutual Fund":"data:image/webp;base64,UklGRpoEAABXRUJQVlA4II4EAABQGwCdASpgAGAAPnUwlEYkoyIhLxS+SJAOiWwAyu4rfqvaKcT6l+Q/N/cwr5vM/5X/4Pmg9QH5G/4HuAfpH0gPMB+yn7Ye8f6GP+Z6hn+X/x3WU/sB7AH7Aem3+4Hwl/t16V2am9j/+Q5Wf2AyqgadYE8f/pnEhpJpjvkw+mR4P4Devkmp2OCeWmxoEuRUBbfz8/HkxYxUXN6dLjMRPHo3HSmSO/Ag9gwxYyWk0B0dq8X1CN9bGkvla1Svt7+htxoFwQHtB26grddf69oMYmus65OKYd7ZgCc4imsOMLX3DgA7PAD++eUHGHCAP+LLTQfpWxznqBLTh8/P4U+zHg35b8Hpp/naWI7+5Z4oD+Ar3j4HAAEp1rcP/kZiS3apkTOICo7Fqtjpo8RwJYO3xidhMpNQ1NYgnYESJWXJWfLwjxxho/b6byptCQE+QuEDh4+rq9qyvCPZjRsmGNqmifrubAg7D08yyDGzqi0BDrdnsUMKKAkVoJDT2Rknazv+7gYlbA9E2CekE7uQ+bvanimyTiOXJ+oHvuuCj0J/bBovlC8TT23ZQqoNky2xSR2Q3ZmIfmoRw2BlW0/TRQofh71fhXEBEJ42cDLwxLu1E+rBXebeCstlUYS7qvXW+rTxPpQ9/CiArQvGVL5uSHlsWXllhI5PAvi4HrSoTEurUv3M5cjp8AXDNra9Xq2chLLpHot4N4qCWb6OK9AFEkXIlxR6QraiAObill73jSixYY4UKXgD5y3BsFbOR2mm4QBlt3i6rlTugdmP+hm50WScD/vrTJHcXzH9twuD7pV40GoK4fup0WLyO+MO7WP1IEmbYeVVeMgkY1fZuIsh2h9x0Jv03jUzIsHCE9G2igOqjfAnWEUbPb3Pt821/N40P43ae+MemAN/KmDbVnmDU8yVGlaHfaBJeLbv0bWRqzRRKOD8FL6dq9LbzG2RU/9XKHLuWFnIuSZ8iGmxpBUpODTkAf/ODF/L8d7Vjsa9vnHxp7ZqX148wd9MduuDp39zOyfEthbJ7WL/3L8NYe5+coGuvmdxJz8swqfHhUXefm6infcCWvjxgXyS33El7WU+USy1+/Qf5g2olqhsYQB6dmwAUs9WnsiX85LMKnJF/hbJODVqxsgXuFMf9x1EDMgs955cTwG2Chl5Q5+AQNl5v/tyzoPYA86bP8oKQeZUmm1ejk4FM2IPgycZLbtEdZoFb9Wfh0tYpyPe4vRzrYhCKsi5Jz55QMXWTmp3SR8099ksRuJpiE6Ok8o6t6uMHvtX/oAAKrA1YJ+cfNGCwjZ1WyOH/bv3AZ3/lM4gkDA/Ibf/nLnbweLOu2TfHAdyw73cDLc1++iNYT8kHeAZ7ran6Prpg9Gjk4J43COji9iwp32tVZPFtasygMAeVUpkOTJ00rLABs3jjC36vPUUtsXfjCeFYP2dkzl+fit2hsvlEQPR2ThqjxC8XYamR0JayXlzNmHkpbNga83cOLep8h3h9iqrw7zx5+YLorGnW4H2pDw+/laM/T2Awb/Ex5EFcxsqgcbev9AZsKWJijqRBS08fBAAAA==","Union Mutual Fund":"data:image/webp;base64,UklGRg4FAABXRUJQVlA4IAIFAACwGACdASpSAGAAPnk2lkekoyIhKPM86JAPCWoAzYHXfumq9eA84aqP3vjpjwdkU5vzCv1V6RHmA81r0a+gB/a/9v1pPoAeWt7JP7c+lBd6n4evG/0HC7KB4C6T7GF6KOkYEyn4ysusxC3NuL3uOzQ7jc9NK2Z4NtAVpMnoaWHGz87eiXSMRQ+AWyni1sevLqFivqnDUIppERZhZb3szmiN/886Qsv2t1OLoRswP4o92Ph6IfE4huIOssU3VWFb0dwfUEWau0O8ZwfK5xxPAAD+/EoACghpFCTxPxiSlGWJ96nsUs5uWPedtNDQAjPdK7U10Mdht09InR7V4GFvBQV6dHbq0auApU8dOr1aQgVPQpAd5Po5xVcXhMwYwA719td70X5Lue+MDWYfvoOvrRU8gPscC8yeIdpIf6BdalP++y4dQCfmKkNvf6G1dVxwLP4Mytq0KX2UORCM1+q6TbS5Qv2xjRDfy8iKbPHcqQEGfKOxKtnHx6FiPT2dKPaNvOf4sj62goatwz5KbzQA/RWr6C3RMMtkW0TQ7f6vUkt9odeXcc/gecyBrNGL4CgO/x66Iu3C+Rwi8TqL0XDz9w372lnzmdvFqcU/Zy0vwMeF2URFxH17cSeDz+5fvg6zz48y+Xk38WWYQuh/xiczHSamcim1n0Ih7ZtyHOYXwWvRFdZZb6Me5LCSwVSmkP+tfvxLVJcvfknLj2BN/7YCXSKMBkx7HpEn2/rFwzORc8e1WAnYPjhdz23tbNEkDWxfvO5NbaVn4bci3oSTeMiZ59h3ROj52rhwBXPWfPQY6CKezD/sK/Hs6lkZEpe2KrPn+zoOFv5fP87Qp4BzHSuwgTFAzuhS0wOqeUL8AssWB6HwafhSf6J2+YS5FLC3OBlLvpAzC+LFLp0b143jIDsrVMYwY7aUUu5rDBbW4OwkLuUokUzdVMlSK9FYIu8iQPPBHS1jczGzaBaGn+P+a+PsxTA/HfSq6z1xOC69p58HNbIuHhgzFOYIJPme0Xci+F440fWLAEe9CtHeriLhwzff7t2Z/P/1vBPxPH0fxHnbjC8zUBhNhzbfSb77Y95ZCbH9V9jQStMRIyKGrLC0N8jPP6pMVi0F1wlw6GDaD9K5aaYUyrFXJYt9O5Z6K3c0MBbQpb7Kp1G410hxxifHSH/+cLsMA2Zkh0KOsJzxRuRp2qoX9PMmP6WYlU1B+5Tz8FeDZ9gpu7kJr4WUntfsi1zuppG2WqPOf6APC6Hd2IDLg3/AO5HlPs5T/2aiOrey7mbJ0+vdz9w+akp0oP1Q3+RhX1m1Q3FWdQhozt/V5nNnjVbVR1buEMtxtfC5x+c8cW4CG3Nck8w77LV5m+U4hP2QvEYzooMpyn2pgOTTyYbuflYWr0zM17r1d7EOIeink37BF21NB5o4gvpyvsHq/uXiIEth0S1vr1egV7NDDaXHGWayIrPivH048rVoV1HBKwIv6DLOaXQyjoqlAzKdH8faP/4l0tiJxRAjvBTwcQZERq4znKvAWMtpguGmywCBEkthicE1zhBh34Q0sld2bEqTCQKTb8B9mKMKFGwNPRhB2WzvFNtFmfKjIc2dr4Wkn8KjUi31xaIA7ZCkQp4/RPbVOY1gGMKHC7gFm826V3Tz3otwMi+2J/BRWd/Y83jBdMDwdqrJA8iH9uxNshZcUPBB+xD3x9H7ZvLbICgPcoFcPYwAAAAA","Sundaram Mutual Fund":"data:image/webp;base64,UklGRmoEAABXRUJQVlA4IF4EAAAwFwCdASpgAE8APnUulEYkoqIhMzK9+JAOiWgAyJXV215vfcfyi6CnmHwVyCxg+sXHB6lPMA5z3mA/bz1zP476rPOz6jH0VfLk9oe/VZw//OcNev5wJQ78zXyJfVPoxqmxX/n958cvvqk7o6SFB6A1ko1cBtq95q3UbhALOjrq80UhbkDjFPxL+MMxmMRAlnqpRdVoup41Tx7x+V8/f/SCAnRUQbNFMH7rPULR234rx5s6PEG9IMNOkkH6m5dsK4xHsAD+/KgAVaQITj02iLcUf85CaJsAyicaBS39LYGYu+FJ9J8q0EUr9P34/ysfjCRjNK1e5W8MHOUJ3KyaiHGliRGWJ7CF0x+6UGHJpKk9m7dJZGc4t5ZJBZ/PXIXfPvomwPoswIlZkXrzgfk2+Hw6RQRhqg6l/q+iJAg/lrpu0f3h1PcTSpu4g37sA7zOKN83E9rufWhFP/xcokBMEQmIdXNHvxf75HVrMix+rMO5MHF/7yVuEwS46NgnJDCM4aMIwl5OiBcmnpL5rtirPT43y3BIfmu6DG3rYrMjRz/+/DC5xbZO5uwAZVkZQurFQAF4oarDopm/RPIjVSz7UBxtMrqPYwLmBKmXsVvtppVX5UoTVycYV7aZU5XIQY+m2bgd8mqNIOmXrGUkZljreeloL+Jqj1pV7xk0yZOyxXOfh2E/CKjWh5UQk95JQyfb1eintw7zD7opx2eDtxLSWbG4AuNV7wq0g+6JKZFrKPKel0s9RT3kLLLc2KQ75QDiL9f3Z39zOnZWZAm6jDEjvFjdZeRoEw2bAullMdSUgdXUgyFS4Cf5fd7hfLRjP829Y/unKavZx9JRNj60SRoTeDmiYszoEb5yNiIe8/OKFj5qX4JxF/Wo5VyyfB5waTHBNqzb0vHa+vik2Z/atcP77pfL5IvWLb5st7Vp08YKZxzLAGCjbBdhCYaxtkBhSV1nQwIPdiE7m6fKo9mOaykWUSbfc4jP8w330Eb3plJIsHHKQWyA14s7+ZMgUiBbpw+wDBf7/r4rRLAAcOfxQPHgBeYKOCWRP4sQHe7MnF5CkjcgiiZi5D+UKN2pB3zIV4dRyjmz2/NAF1T5yObGm1USsZZKCVc/wUyzQ/O7TvSB6zr0Tb3tKUaRaxqY6G9TJeAOCHKnIMDNAAY8Q500nq9WKQno2HDmqlMimnGDR5Vj5jBHpW5J8/FeCvYqb3tFnfPUy458jRtrtVtEQ4qrppGtEQtqznjvjt99+qLB9E9GFsFcACRBy1ffKK4mauwF7umcomypVlkkOgy2v6dcZ2ffGTHdyZx8kI34ekEr959KLgyVwJB1aEVcdO8yLAjQu0/VfBiBA8EgV86aspGgIHS4C3MQ4MeyZ4aCuQY8XVwMx0nzk12zdG6Vzikj3VbSwISfZFyOe4VkJ3TrNRN8IZfWptaIax9tQWWpkexq6ngFrbrSlOn8b1rnlm03519ovlj5Kb9xJTsWeUYaG1jnlwAAAA=="}

def norm(v):
    s=str(v or '').lower()
    s=re.sub(r'asset management|mutual fund|fund house|limited|ltd\.?',' ',s)
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()

def domain_for(name):
    n=norm(name); keys=[k for k in DOMAINS if k in n]
    return DOMAINS[max(keys,key=len)] if keys else ''

def _mime(raw,header=''):
    h=(header or '').split(';',1)[0].strip().lower()
    if h.startswith('image/'): return h
    if raw.startswith(b'\x89PNG'): return 'image/png'
    if raw[:3]==b'\xff\xd8\xff': return 'image/jpeg'
    if raw.startswith((b'GIF87a',b'GIF89a')): return 'image/gif'
    if raw.startswith(b'\x00\x00\x01\x00'): return 'image/x-icon'
    if b'<svg' in raw[:1500].lower(): return 'image/svg+xml'
    return ''

def _get_image(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        raw=r.read(768000); ct=_mime(raw,r.headers.get('Content-Type',''))
    if not ct or len(raw)<100: raise RuntimeError('not usable image')
    return ct,'data:'+ct+';base64,'+base64.b64encode(raw).decode('ascii')

def _official_urls(domain):
    root='https://'+domain+'/'
    out=[root+'favicon.ico',root+'favicon.png',root+'apple-touch-icon.png']
    try:
        req=urllib.request.Request(root,headers={'User-Agent':UA,'Accept':'text/html,*/*'})
        with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
            page=r.read(400000).decode('utf-8',errors='ignore')
        for tag in re.findall(r'<link\b[^>]*>',page,flags=re.I):
            if not re.search(r'rel=["\'][^"\']*(?:icon|apple-touch-icon)[^"\']*["\']',tag,flags=re.I): continue
            m=re.search(r'href=["\']([^"\']+)["\']',tag,flags=re.I)
            if m: out.append(urllib.parse.urljoin(root,html.unescape(m.group(1))))
    except Exception:
        pass
    return list(dict.fromkeys(out))

def fetch_logo(domain):
    q=urllib.parse.quote(domain,safe=''); qu=urllib.parse.quote('https://'+domain,safe=''); errs=[]
    candidates=[
        ('duckduckgo',f'https://icons.duckduckgo.com/ip3/{domain}.ico'),
        ('google-url',f'https://www.google.com/s2/favicons?domain_url={qu}&sz=128'),
        ('google',f'https://www.google.com/s2/favicons?domain={q}&sz=128'),
        ('clearbit',f'https://logo.clearbit.com/{domain}?size=128')]
    for provider,url in candidates:
        try:
            ct,data=_get_image(url); return ct,data,provider
        except Exception as e:
            errs.append(provider+':'+str(e)[:60])
    for url in _official_urls(domain):
        try:
            ct,data=_get_image(url); return ct,data,'official'
        except Exception as e:
            errs.append('official:'+str(e)[:60])
    raise RuntimeError('; '.join(errs[-6:]))

def resolve(amc,old):
    domain=domain_for(amc)
    if not domain: raise RuntimeError('no domain mapping')
    prev=old.get(amc) or {}
    if prev.get('domain')==domain and str(prev.get('dataUri') or '').startswith('data:image/'):
        return amc,prev
    if amc in STATIC_DATA:
        return amc,{'domain':domain,'mime':'image/webp','provider':'user-supplied-offline','dataUri':STATIC_DATA[amc]}
    if amc in STATIC_URLS:
        try:
            mime,data=_get_image(STATIC_URLS[amc])
            return amc,{'domain':domain,'mime':mime,'provider':'verified-static-url','dataUri':data}
        except Exception:
            pass
    mime,data,provider=fetch_logo(domain)
    return amc,{'domain':domain,'mime':mime,'provider':provider,'dataUri':data}

def main():
    u=json.loads(UNIVERSE.read_text(encoding='utf-8'))
    amcs=list(u.get('amcs') or [])
    old={}
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding='utf-8')).get('logos') or {}
        except Exception: old={}
    logos={}; failures=[]
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs={ex.submit(resolve,a,old):a for a in amcs}
        for fut in cf.as_completed(futs):
            a=futs[fut]
            try:
                k,v=fut.result(); logos[k]=v
                print('logo',k,v.get('provider','cached'),len(v.get('dataUri','')))
            except Exception as e:
                failures.append({'amc':a,'domain':domain_for(a),'error':str(e)[:350]})
    if failures:
        raise RuntimeError('AMC logo coverage failed: '+json.dumps(failures,ensure_ascii=False))
    if len(logos)!=len(amcs):
        raise RuntimeError(f'logo coverage {len(logos)}/{len(amcs)}')
    doc={
        'schemaVersion':1,
        'generatedAt':dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
        'sourceAsOf':u.get('sourceAsOf',''),
        'amcCount':len(amcs),
        'logoCount':len(logos),
        'logos':{a:logos[a] for a in amcs}}
    OUT.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    print('AMC logo registry OK:',len(logos),'/',len(amcs),'bytes',OUT.stat().st_size)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
