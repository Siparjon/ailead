import json
import re
from typing import Any

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
OLLAMA_URL = "http://localhost:11434/api/generate"
HTTP_HEADERS = {
    "User-Agent": "ailead-free-mvp/1.0 (personal lead research tool)",
    "Accept": "application/json",
}

CATEGORY_TAGS = {
    "restaurant": [('amenity', 'restaurant')], "restaurants": [('amenity', 'restaurant')],
    "cafe": [('amenity', 'cafe')], "cafes": [('amenity', 'cafe')], "coffee shop": [('amenity', 'cafe')],
    "bar": [('amenity', 'bar')], "gym": [('leisure', 'fitness_centre')], "fitness": [('leisure', 'fitness_centre')],
    "hair salon": [('shop', 'hairdresser')], "barbershop": [('shop', 'hairdresser')],
    "beauty salon": [('shop', 'beauty')], "bakery": [('shop', 'bakery')],
    "clothing store": [('shop', 'clothes')], "clothing": [('shop', 'clothes')],
    "supermarket": [('shop', 'supermarket')], "hotel": [('tourism', 'hotel')],
    "real estate": [('office', 'estate_agent')], "accounting": [('office', 'accountant')],
    "law firm": [('office', 'lawyer')],
}


def geocode_location(location: str) -> tuple[float, float, float, float]:
    response = requests.get(
        NOMINATIM_URL,
        params={"q": location, "format": "json", "limit": 1},
        headers=HTTP_HEADERS,
        timeout=20,
    )
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
            response = requests.post(
                url,
                data={"data": query},
                headers={**HTTP_HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=60,
            )
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
        safe = re.sub(r'[^A-Za-z0-9 .&_-]', '', business_type).strip()
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
            "id": key_id,
            "business_name": name,
            "address": ", ".join(filter(None, [tags_data.get("addr:housenumber"), tags_data.get("addr:street"), tags_data.get("addr:city")])),
            "type": tags_data.get("amenity") or tags_data.get("shop") or tags_data.get("office") or tags_data.get("tourism") or tags_data.get("leisure") or business_type,
            "website": tags_data.get("website") or tags_data.get("contact:website") or "",
            "phone": tags_data.get("phone") or tags_data.get("contact:phone") or "",
            "rating": None, "review_count": None, "google_maps": maps, "status": "",
        })
        if len(places) >= max_results * 3:
            break
    return places[:max_results]


def _deterministic_score(business: dict[str, Any], service: str) -> dict[str, Any]:
    score = 45
    reasons = ["Public business listing found", "Business category matches the search"]
    if business.get("website"): score += 15; reasons.append("A public website is listed")
    if business.get("phone"): score += 10; reasons.append("A public business phone is listed")
    if business.get("address"): score += 10; reasons.append("A public address is listed")
    return {
        "score": min(score, 100), "fit": "medium" if score >= 60 else "low", "reasons": reasons,
        "suggested_service": service,
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
Return ONLY JSON with score (integer 0-100), fit (high/medium/low), reasons (2-4 short factual reasons), suggested_service, outreach (under 500 chars), unknowns.
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


def qualify_leads(places: list[dict[str, Any]], service: str, ideal_customer: str, model: str = "qwen3:4b") -> list[dict[str, Any]]:
    results = []
    for business in places:
        try:
            score = score_lead(business, service, ideal_customer, model)
            ai_mode = "Local AI"
        except Exception:
            score = _deterministic_score(business, service)
            ai_mode = "Rule-based fallback"
        results.append({**business, **score, "ai_mode": ai_mode})
    return sorted(results, key=lambda x: x["score"], reverse=True)
