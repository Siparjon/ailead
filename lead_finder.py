import json
import re
import socket
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = ["https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
OLLAMA_URL = "http://localhost:11434/api/generate"
DDG_URL = "https://html.duckduckgo.com/html/"
HTTP_HEADERS = {"User-Agent": "ailead-free-mvp/1.4 (personal lead research tool)", "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
CATEGORY_TAGS = {"restaurant":[("amenity","restaurant")],"restaurants":[("amenity","restaurant")],"cafe":[("amenity","cafe")],"cafes":[("amenity","cafe")],"coffee shop":[("amenity","cafe")],"bar":[("amenity","bar")],"gym":[("leisure","fitness_centre")],"fitness":[("leisure","fitness_centre")],"hair salon":[("shop","hairdresser")],"barbershop":[("shop","hairdresser")],"beauty salon":[("shop","beauty")],"bakery":[("shop","bakery")],"clothing store":[("shop","clothes")],"clothing":[("shop","clothes")],"supermarket":[("shop","supermarket")],"hotel":[("tourism","hotel")],"real estate":[("office","estate_agent")],"accounting":[("office","accountant")],"law firm":[("office","lawyer")]}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
SOCIAL_DOMAINS = {"linkedin.com":"linkedin","instagram.com":"instagram","facebook.com":"facebook","tiktok.com":"tiktok","youtube.com":"youtube","x.com":"x","twitter.com":"x","wa.me":"whatsapp"}
ROLE_WORDS = ("owner","founder","co-founder","ceo","director","managing director","manager","principal")
CONTACT_WORDS = ("contact","about","team","leadership","management","founder","owner")


def _domain(url:str)->str:
    try:return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:return ""


def _safe_public_url(url:str)->bool:
    try:
        p=urlparse(url)
        if p.scheme not in {"http","https"} or not p.hostname:return False
        host=p.hostname.lower()
        if host in {"localhost","127.0.0.1","::1"} or host.endswith(".local"):return False
        for info in socket.getaddrinfo(host,None):
            ip=info[4][0]
            if ip.startswith(("10.","192.168.","127.")) or (ip.startswith("172.") and 16<=int(ip.split(".")[1])<=31):return False
        return True
    except Exception:return False


def geocode_location(location:str)->tuple[float,float,float,float]:
    r=requests.get(NOMINATIM_URL,params={"q":location,"format":"json","limit":1},headers=HTTP_HEADERS,timeout=12);r.raise_for_status();data=r.json()
    if not data:raise ValueError(f"Could not find location: {location}")
    x=data[0];lat,lon=float(x["lat"]),float(x["lon"]);bbox=x.get("boundingbox")
    if bbox:
        south,north,west,east=map(float,bbox)
        if abs(north-south)>0.8 or abs(east-west)>0.8:south,north,west,east=lat-.12,lat+.12,lon-.12,lon+.12
    else:south,north,west,east=lat-.12,lat+.12,lon-.12,lon+.12
    return south,west,north,east


def _overpass_query(query:str)->dict[str,Any]:
    last=""
    for url in OVERPASS_URLS:
        try:
            r=requests.post(url,data={"data":query},headers={**HTTP_HEADERS,"Content-Type":"application/x-www-form-urlencoded"},timeout=35)
            if r.ok:return r.json()
            last=f"{r.status_code} from {url}"
        except requests.RequestException as e:last=str(e)
    raise RuntimeError(f"All Overpass servers failed: {last}")


def search_places(location:str,business_type:str,max_results:int=20)->list[dict[str,Any]]:
    south,west,north,east=geocode_location(location);key=business_type.strip().lower();tags=CATEGORY_TAGS.get(key)
    if tags:clauses="\n".join(f' nwr["{a}"="{b}"]({south},{west},{north},{east});' for a,b in tags)
    elif "restaurant" in key:clauses=f' nwr["amenity"="restaurant"]({south},{west},{north},{east});'
    elif "shop" in key or "store" in key:clauses=f' nwr["shop"]({south},{west},{north},{east});'
    else:
        safe=re.sub(r"[^A-Za-z0-9 .&_-]","",business_type).strip();clauses=f' nwr["name"~"{safe}",i]({south},{west},{north},{east});'
    q=f"[out:json][timeout:25];({clauses});out center tags;";elements=_overpass_query(q).get("elements",[]);out=[];seen=set()
    for e in elements:
        t=e.get("tags",{});name=t.get("name");eid=str(e.get("id"))
        if not name or eid in seen:continue
        seen.add(eid);c=e.get("center",{});lat=e.get("lat",c.get("lat"));lon=e.get("lon",c.get("lon"))
        out.append({"id":eid,"business_name":name,"address":", ".join(filter(None,[t.get("addr:housenumber"),t.get("addr:street"),t.get("addr:city")])),"type":t.get("amenity") or t.get("shop") or t.get("office") or t.get("tourism") or t.get("leisure") or business_type,"website":t.get("website") or t.get("contact:website") or "","phone":t.get("phone") or t.get("contact:phone") or "","google_maps":f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else ""})
        if len(out)>=max_results*4:break
    return out


@lru_cache(maxsize=512)
def _search_web_cached(query:str,limit:int=8)->tuple[tuple[str,str],...]:
    try:
        r=requests.get(DDG_URL,params={"q":query},headers=HTTP_HEADERS,timeout=8);r.raise_for_status();soup=BeautifulSoup(r.text,"html.parser");out=[]
        for item in soup.select(".result")[:limit]:
            a=item.select_one("a.result__a")
            if not a:continue
            href=a.get("href","")
            if "uddg=" in href:href=unquote(parse_qs(urlparse(href).query).get("uddg",[href])[0])
            if href.startswith("http"):out.append((a.get_text(" ",strip=True),href))
        return tuple(out)
    except requests.RequestException:return tuple()


def _search_web(query:str,limit:int=8)->list[dict[str,str]]:return [{"title":t,"url":u} for t,u in _search_web_cached(query,limit)]


def _extract_page(html:str,base:str)->dict[str,Any]:
    soup=BeautifulSoup(html,"html.parser");text=soup.get_text(" ",strip=True);emails=sorted(set(EMAIL_RE.findall(html+" "+text)))[:20];phones=sorted(set(PHONE_RE.findall(text)))[:20];socials={}
    for a in soup.find_all("a",href=True):
        u=urljoin(base,a["href"]);d=_domain(u)
        for sd,label in SOCIAL_DOMAINS.items():
            if d==sd or d.endswith("."+sd):socials.setdefault(label,u)
    return {"text":text[:12000],"emails":emails,"phones":phones,"socials":socials,"links":[urljoin(base,a["href"]) for a in soup.find_all("a",href=True)][:150]}


def _crawl_site(root:str,max_pages:int=3)->dict[str,Any]:
    if not root or not _safe_public_url(root):return {}
    if not root.startswith("http"):root="https://"+root
    q=deque([root]);visited=set();emails=set();phones=set();socials={};pages=[];dm=[];contact_page=""
    while q and len(visited)<max_pages:
        url=q.popleft().split("#")[0]
        if url in visited or not _safe_public_url(url) or _domain(url)!=_domain(root):continue
        visited.add(url)
        try:
            r=requests.get(url,headers=HTTP_HEADERS,timeout=6,allow_redirects=True)
            if not r.ok or "text/html" not in r.headers.get("content-type",""):continue
            soup=BeautifulSoup(r.text,"html.parser");data=_extract_page(r.text,r.url);emails.update(data["emails"]);phones.update(data["phones"]);socials.update(data["socials"]);pages.append({"title":soup.title.get_text(" ",strip=True) if soup.title else "","url":r.url});low=data["text"].lower()
            if any(w in low for w in ROLE_WORDS):
                for role in ROLE_WORDS:
                    idx=low.find(role)
                    if idx>=0:dm.append(data["text"][max(0,idx-120):idx+260]);break
            if not contact_page and any(w in (r.url.lower()+" "+low[:2000]) for w in CONTACT_WORDS):contact_page=r.url
            for link in data["links"]:
                if _domain(link)==_domain(root) and any(w in link.lower() for w in CONTACT_WORDS):q.append(link)
        except (requests.RequestException,ValueError):continue
    return {"public_emails":sorted(emails)[:20],"public_phones":sorted(phones)[:20],"socials":socials,"website_pages_scanned":len(pages),"website_pages":pages,"decision_maker_evidence":dm[:10],"contact_page":contact_page}


def enrich_lead(business:dict[str,Any],location:str,crawl_pages:int=3,deep:bool=True)->dict[str,Any]:
    name=business["business_name"];search=_search_web(f'"{name}" "{location}"',5);website=business.get("website","")
    if not website:
        blocked=("facebook.com","instagram.com","linkedin.com","tiktok.com","youtube.com","x.com","twitter.com")
        website=next((x["url"] for x in search if _domain(x["url"]) and not any(_domain(x["url"]).endswith(d) for d in blocked)),"")
    if website:business["website"]=website
    site=_crawl_site(website,max(1,min(crawl_pages,5))) if website else {};dm_search=[];social_search=[]
    if deep:
        dm_search=_search_web(f'"{name}" "{location}" owner founder director LinkedIn',5);social_search=_search_web(f'"{name}" "{location}" Instagram Facebook',5)
    profiles={}
    for x in dm_search+social_search:
        d=_domain(x["url"])
        for sd,label in SOCIAL_DOMAINS.items():
            if d==sd or d.endswith("."+sd):profiles.setdefault(label,x["url"])
    profiles.update({k:v for k,v in site.get("socials",{}).items() if k not in profiles});business.update(site);business["public_emails"]=sorted(set(site.get("public_emails",[])));business["public_phones"]=sorted(set(site.get("public_phones",[])+([business.get("phone")] if business.get("phone") else [])))
    for label in ("linkedin","instagram","facebook","tiktok","youtube","x","whatsapp"):business[label]=profiles.get(label,"")
    business["search_sources"]=[x["url"] for x in search+dm_search+social_search][:20];return business


def _deterministic_score(b:dict[str,Any],service:str)->dict[str,Any]:
    score=35;reasons=["Public business listing found","Business category matches the search"]
    if b.get("website"):score+=10;reasons.append("Public website found")
    if b.get("public_emails"):score+=15;reasons.append("Public business email found")
    if b.get("public_phones"):score+=7;reasons.append("Public business phone found")
    if b.get("linkedin"):score+=8;reasons.append("Public LinkedIn presence found")
    if b.get("decision_maker_evidence"):score+=10;reasons.append("Public owner/leadership evidence found")
    return {"score":min(score,100),"fit":"high" if score>=75 else "medium" if score>=60 else "low","reasons":reasons,"suggested_service":service,"outreach":f"Hi! I came across {b['business_name']} and wanted to ask if you currently have someone handling your bookkeeping and monthly financial admin. I help small businesses with this work and would be happy to discuss it.","unknowns":["Business size","Current bookkeeping setup","Whether bookkeeping support is currently needed"]}


def score_lead(b:dict[str,Any],service:str,ideal_customer:str,model:str="qwen3:4b")->dict[str,Any]:
    prompt=f"You are a careful B2B lead qualification assistant. Service: {service}. Ideal customer: {ideal_customer}. PUBLIC DATA ONLY:\n{json.dumps(b,ensure_ascii=False,indent=2)}\nScore 0-100. Prioritize reachable businesses and evidence of a decision maker. Never invent names, revenue, employees, pain points or contacts. Return ONLY JSON: score, fit, reasons (2-5 factual reasons), suggested_service, outreach (under 600 chars), unknowns."
    r=requests.post(OLLAMA_URL,json={"model":model,"prompt":prompt,"stream":False,"format":"json"},timeout=90);r.raise_for_status();x=json.loads(r.json().get("response","").strip());x["score"]=max(0,min(100,int(x.get("score",0))));x["fit"]=x.get("fit","low");x["reasons"]=x.get("reasons",[]);x["suggested_service"]=x.get("suggested_service",service);x["outreach"]=x.get("outreach","");x["unknowns"]=x.get("unknowns",[]);return x


def qualify_leads(places:list[dict[str,Any]],service:str,ideal_customer:str,model:str="qwen3:4b",enrich:bool=True,location:str="",require_contact:bool=True,require_website:bool=False,crawl_pages:int=3,progress_callback=None,deep:bool=True)->list[dict[str,Any]]:
    # Hard cap research candidates. Searching 60 businesses sequentially was the main bottleneck.
    candidates=places[:min(len(places),30)];results=[]
    if not enrich:enriched=candidates
    else:
        workers=min(8,max(2,len(candidates)));enriched=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(enrich_lead,raw,location,crawl_pages,deep):raw for raw in candidates};done=0
            for fut in as_completed(futures):
                done+=1
                try:enriched.append(fut.result())
                except Exception:enriched.append(futures[fut])
                if progress_callback:progress_callback(done,len(candidates))
    for b in enriched:
        has_contact=bool(b.get("public_emails") or b.get("public_phones") or b.get("linkedin") or b.get("instagram") or b.get("facebook") or b.get("whatsapp"))
        if require_website and not b.get("website"):continue
        if require_contact and not has_contact:continue
        try:score=score_lead(b,service,ideal_customer,model);mode="Local AI"
        except Exception:score=_deterministic_score(b,service);mode="Rule-based fallback"
        results.append({**b,**score,"ai_mode":mode})
    return sorted(results,key=lambda x:x["score"],reverse=True)
