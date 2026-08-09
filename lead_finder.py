import json
import os
from typing import Any

import requests
from openai import OpenAI

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.primaryType",
    "places.types",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.internationalPhoneNumber",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
])


def search_places(query: str, api_key: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search Google Places Text Search (New)."""
    page_size = min(max(max_results, 1), 20)
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "textQuery": query,
        "pageSize": page_size,
        "languageCode": "en",
    }
    response = requests.post(PLACES_URL, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    places = response.json().get("places", [])
    return places[:max_results]


def normalize_place(place: dict[str, Any]) -> dict[str, Any]:
    display = place.get("displayName") or {}
    return {
        "id": place.get("id", ""),
        "business_name": display.get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "type": place.get("primaryType", ""),
        "types": place.get("types", []),
        "website": place.get("websiteUri", ""),
        "google_maps": place.get("googleMapsUri", ""),
        "phone": place.get("internationalPhoneNumber", ""),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "status": place.get("businessStatus", ""),
    }


def score_lead(
    business: dict[str, Any],
    service: str,
    ideal_customer: str,
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    """Use the model as a second-pass qualifier. It must not invent facts."""
    prompt = f"""
You are a B2B lead qualification assistant.

Service being sold: {service}
Ideal customer description: {ideal_customer}

Business data (public data only):
{json.dumps(business, ensure_ascii=False, indent=2)}

Score how promising this business is as a potential customer from 0 to 100.
Use only the supplied facts. Do NOT invent revenue, employee count, owner names,
financial problems, or contact details. If something is unknown, say unknown.

Return ONLY valid JSON with exactly these keys:
score: integer 0-100
fit: one of "high", "medium", "low"
reasons: array of 2-4 short factual reasons
suggested_service: short string
outreach: short personalized first message, maximum 500 characters
unknowns: array of facts that would need verification
"""
    response = client.responses.create(model=model, input=prompt)
    text = response.output_text.strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Small recovery for accidental markdown fences.
        cleaned = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(cleaned)

    result["score"] = max(0, min(100, int(result.get("score", 0))))
    result["fit"] = result.get("fit", "low")
    result["reasons"] = result.get("reasons", [])
    result["suggested_service"] = result.get("suggested_service", service)
    result["outreach"] = result.get("outreach", "")
    result["unknowns"] = result.get("unknowns", [])
    return result


def qualify_leads(
    places: list[dict[str, Any]],
    service: str,
    ideal_customer: str,
    client: OpenAI,
    model: str,
) -> list[dict[str, Any]]:
    results = []
    seen = set()
    for raw_place in places:
        business = normalize_place(raw_place)
        key = business["id"] or business["business_name"].lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            score = score_lead(business, service, ideal_customer, client, model)
        except Exception as exc:
            score = {
                "score": 0,
                "fit": "low",
                "reasons": [f"AI scoring failed: {exc}"],
                "suggested_service": service,
                "outreach": "",
                "unknowns": [],
            }
        results.append({**business, **score})
    return sorted(results, key=lambda x: x["score"], reverse=True)
