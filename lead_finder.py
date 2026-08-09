import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OLLAMA_URL = "http://localhost:11434/api/generate"
DDG_URL = "https://html.duckduckgo.com/html/"
HTTP_HEADERS = {
    "User-Agent": "ailead-free-mvp/1.1 (personal lead research tool)",
    "Accept": "text/html,application/xhtml+xml,application/json",
}

CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant")], "restaurants": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")], "cafes": [("amenity", "cafe")], "coffee shop": [("amenity", "cafe")],
    "bar": [("amenity", "bar")], "gym": [("leisure", "fitness_centre")], "fitness": [("leisure", "fitness_centre")],
    "hair salon": [("shop", "hairdresser")], "barbershop": [("shop", "hairdresser")],
    "beauty salon": [("shop", "beauty")], "bakery": [("shop", "bakery")],
    "clothing store": [("shop", "clothes")], "clothing": [("shop", "clothes")],
    "supermarket": [("shop", "supermarket")], "hotel": [("tourism", "hotel")],
    "real estate": [("office", "estate_agent")], "accounting": [("office", "accountant")],
    "law firm": [("office", "lawyer")],
}

SOCIAL_DOMAINS = {
    "instagram.com": "instagram", "facebook.com": "facebook", "linkedin.com": "linkedin",
    "tiktok.com": "tiktok", "youtube.com": "youtube", "x.com": "x", "twitter.com": "twitter",
    "wa.me": "whatsapp",
}
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def geocode_location(location: str) -> tuple[float, float, float, float]:
    response = requests.get(NOMINATIM_URL, params={"q": location, "format": "json", "limit": 1}, headers=HTTP_HEADERS, timeout=20)
    response.raise_for_status()
    results = response.json()
    if not results:
        raise ValueError(f"Could not find location: {location}")
    item = results[0]
    lat, lon = float(item["lat"]), float(item["lon"])
    bbox = item.get("boundingbox")
    if bbox:
        south, north, west, east = map(float, bbox)
        if abs(north - south) > 0.8 or abs(east - west) > 0.8:
            south, north, west, east = lat - 0.12, lat + 0.12, lon - 0.12, lon + 0.12
    else:
        south, north, west, east = lat - 0.12, lat + 0.12, lon - 0.12, lon + 0.12
    return south, west, north, east


def _overpass_query(query: str) -> dict[str, Any]:
    last_error = None
    for url in OVERPASS_URLS:
        try:
            response = requests.post(url, data={"data": query}, headers={**HTTP_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
            if response.ok:
                return response.json()
            last_error = f"{response.status_code} from {url}: {response.text[:200]}"
        except requests.RequestException as exc:
            last_error = str(exc)
    raise RuntimeError(f"All OpenStreetMap Overpass servers failed. Last error: {last_error}")


def search_places(location: str, business_type: str, max_results: int = 20) -> list[dict[str, Any]]:
    south, west, north, east = geocode_location(location)
    key = business_type.strip().lower()
    tags = CATEGORY_TAGS.get(key)
    if tags:
        clauses = "\n".join(f'  nwr["{tag}"="{value}"]({south},{west},{north},{east});' for tag, value in tags)
    elif "restaurant" in key:
        clauses = f'  nwr["amenity"="restaurant"]({south},{west},{north},{east});'
    elif "shop" in key or "store" in key:
        clauses = f'  nwr["shop"]({south},{west},{north},{east});'
    else:
        safe = re.sub(r"[^A-Za-z0-9 .&_-]", "", business_type).strip()
        clauses = f'  nwr["name"~"{safe}",i]({south},{west},{north},{east});' if safe else f'  nwr["name"]({south},{west},{north},{east});'
    query = f"""
[out:json][timeout:25];
(
{clauses}
);
out center tags;
"""
    elements = _overpass_query(query).get("elements", [])
    places, seen = [], set()
    for element in elements:
        tags_data = element.get("tags", {})
        name = tags_data.get("name")
        if not name:
            continue
        key_id = str(element.get("id"))
        if key_id in seen:
            continue
        seen.add(key_id)
        center = element.get("center", {})
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        maps = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else ""
        places.append({
            "id": key_id, "business_name": name,
            "address": ", ".join(filter(None, [tags_data.get("addr:housenumber"), tags_data.get("addr:street"), tags_data.get("addr:city")])),
            "type": tags_data.get("amenity") or tags_data.get("shop") or tags_data.get("office") or tags_data.get("tourism") or tags_data.get("leisure") or business_type,
            "website": tags_data.get("website") or tags_data.get("contact:website") or "",
            "phone": tags_data.get("phone") or tags_data.get("contact:phone") or "",
            "rating": None, "review_count": None, "google_maps": maps, "status": "",
        })
        if len(places) >= max_results * 3:
            break
    return places[:max_results]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _search_web(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Public web search; no paid search API and no login/bypass."""
    try:
        r = requests.get(DDG_URL, params={"q": query}, headers=HTTP_HEADERS, timeout=20)
        r.raise_for_status()
        results = []
        for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.I | re.S):
            url = match.group(1)
            title = re.sub(r"<.*?>", "", match.group(2)).strip()
            if url.startswith("//duckduckgo.com/l/"):
                m = re.search(r"uddg=([^&]+)", url)
                if m:
                    from urllib.parse import unquote
                    url = unquote(m.group(1))
            if url.startswith("http"):
                results.append({"title": title, "url": url.split("#")[0]})
            if len(results) >= limit:
                break
        return results
    except requests.RequestException:
        return []


def _extract_contacts_from_html(html: str, base_url: str) -> dict[str, Any]:
    emails = sorted(set(EMAIL_RE.findall(html)))
    phones = sorted(set(PHONE_RE.findall(html)))
    socials = {}
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        absolute = urljoin(base_url, href)
        domain = _domain(absolute)
        for social_domain, label in SOCIAL_DOMAINS.items():
            if domain == social_domain or domain.endswith("." + social_domain):
                socials.setdefault(label, absolute)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<.*?>", " ", text)
    return {"emails": emails[:10], "phones": phones[:10], "socials": socials, "page_text": re.sub(r"\s+", " ", text)[:12000]}


def enrich_lead(business: dict[str, Any]) -> dict[str, Any]:
    """Enrich a lead with PUBLIC web contacts/profiles. No login, private data, or bypassing site controls."""
    name = business["business_name"]
    location = business.get("address", "")
    website = business.get("website", "")
    enrichment = {
        "public_emails": [], "public_phones": [], "socials": {},
        "linkedin": "", "facebook": "", "instagram": "", "tiktok": "", "youtube": "", "x": "",
        "whatsapp": "", "contact_page": "", "search_sources": [], "web_summary": "",
    }
    urls = [website] if website else []
    search_results = _search_web(f'"{name}" "{location}"', limit=8)
    enrichment["search_sources"] = [x["url"] for x in search_results]
    for item in search_results:
        url, domain = item["url"], _domain(item["url"])
        for social_domain, label in SOCIAL_DOMAINS.items():
            if domain == social_domain or domain.endswith("." + social_domain):
                enrichment.setdefault(label, "")
                if not enrichment[label]:
                    enrichment[label] = url
        if not website and domain and not any(domain == d or domain.endswith("." + d) for d in SOCIAL_DOMAINS):
            website = url
            business["website"] = url
            urls.append(url)
    checked, page_texts = set(), []
    for url in urls[:2]:
        if not url.startswith("http") or url in checked:
            continue
        checked.add(url)
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=15, allow_redirects=True)
            if not r.ok:
                continue
            data = _extract_contacts_from_html(r.text, r.url)
            enrichment["public_emails"].extend(data["emails"])
            enrichment["public_phones"].extend(data["phones"])
            enrichment["socials"].update(data["socials"])
            page_texts.append(data["page_text"])
            base = r.url.rstrip("/") + "/"
            for path in ("contact", "contact-us", "about", "about-us"):
                candidate = urljoin(base, path)
                if candidate in checked:
                    continue
                try:
                    cr = requests.get(candidate, headers=HTTP_HEADERS, timeout=10)
                    if cr.ok and "text/html" in cr.headers.get("content-type", "text/html"):
                        cdata = _extract_contacts_from_html(cr.text, cr.url)
                        enrichment["public_emails"].extend(cdata["emails"])
                        enrichment["public_phones"].extend(cdata["phones"])
                        enrichment["socials"].update(cdata["socials"])
                        enrichment["contact_page"] = enrichment["contact_page"] or cr.url
                        page_texts.append(cdata["page_text"])
                except requests.RequestException:
                    pass
        except requests.RequestException:
            pass
    enrichment["public_emails"] = sorted(set(enrichment["public_emails"]))[:10]
    enrichment["public_phones"] = sorted(set(enrichment["public_phones"]))[:10]
    for label, url in enrichment["socials"].items():
        enrichment[label] = enrichment.get(label) or url
    enrichment["web_summary"] = " ".join(page_texts)[:5000]
    business.update(enrichment)
    return business


def _deterministic_score(business: dict[str, Any], service: str) -> dict[str, Any]:
    score, reasons = 45, ["Public business listing found", "Business category matches the search"]
    if business.get("website"): score += 8; reasons.append("A public website is listed")
    if business.get("public_emails"): score += 10; reasons.append("A public business email was found")
    if business.get("linkedin") or business.get("instagram") or business.get("facebook"): score += 8; reasons.append("A public social/profile page was found")
    if business.get("public_phones") or business.get("phone"): score += 5; reasons.append("A public business phone is available")
    return {
        "score": min(score, 100), "fit": "high" if score >= 75 else "medium" if score >= 60 else "low",
        "reasons": reasons, "suggested_service": service,
        "outreach": f"Hi! I came across {business['business_name']} and wanted to ask if you currently have someone handling your bookkeeping and monthly financial admin. I help small businesses with this work and would be happy to discuss it.",
        "unknowns": ["Business size", "Current bookkeeping setup", "Whether bookkeeping support is currently needed"],
    }


def score_lead(business: dict[str, Any], service: str, ideal_customer: str, model: str = "qwen3:4b") -> dict[str, Any]:
    prompt = f"""
You are a careful B2B lead qualification assistant.
Service being sold: {service}
Ideal customer: {ideal_customer}
PUBLIC BUSINESS DATA:
{json.dumps(business, ensure_ascii=False, indent=2)}
Score how promising this business is from 0 to 100. Use ONLY supplied facts. Never invent revenue, employees, owners, pain points, or contacts. Unknown information must stay unknown.
Return ONLY JSON with score (integer 0-100), fit (high/medium/low), reasons (2-5 short factual reasons), suggested_service, outreach (under 600 chars), unknowns.
"""
    response = requests.post(OLLAMA_URL, json={"model": model, "prompt": prompt, "stream": False, "format": "json"}, timeout=120)
    response.raise_for_status()
    result = json.loads(response.json().get("response", "").strip())
    result["score"] = max(0, min(100, int(result.get("score", 0))))
    result["fit"] = result.get("fit", "low")
    result["reasons"] = result.get("reasons", [])
    result["suggested_service"] = result.get("suggested_service", service)
    result["outreach"] = result.get("outreach", "")
    result["unknowns"] = result.get("unknowns", [])
    return result


def qualify_leads(places: list[dict[str, Any]], service: str, ideal_customer: str, model: str = "qwen3:4b", enrich: bool = True) -> list[dict[str, Any]]:
    results = []
    for business in places:
        if enrich:
            business = enrich_lead(business)
        try:
            score = score_lead(business, service, ideal_customer, model)
            ai_mode = "Local AI"
        except Exception:
            score = _deterministic_score(business, service)
            ai_mode = "Rule-based fallback"
        results.append({**business, **score, "ai_mode": ai_mode})
    return sorted(results, key=lambda x: x["score"], reverse=True)
