# AI Lead Finder — Free MVP

A small local-first lead finder for discovering public business listings and qualifying them as potential bookkeeping/accounting leads.

## What it does

1. Geocodes a city/area with OpenStreetMap Nominatim.
2. Finds public business listings with OpenStreetMap + Overpass — no paid API key required.
3. Scores each business with a local Ollama model when available.
4. Falls back to a simple deterministic score if Ollama is not running.
5. Generates a short reason and personalized first outreach message.
6. Lets you download the results as CSV.

## Setup on Windows

Requirements: Python 3.11+

```powershell
pip install -r requirements.txt
streamlit run app.py
```

### Optional: local AI

Install Ollama for Windows from https://ollama.com/download/windows, then in PowerShell:

```powershell
ollama pull qwen3:4b
```

Keep Ollama running and use `qwen3:4b` in the Streamlit sidebar. The model runs locally, so this MVP does not need an OpenAI API key.

If your computer is not powerful enough for the model, the app still works using the free rule-based fallback.

## First test

Use:

- Location: `Kuala Lumpur, Malaysia`
- Business type: `restaurants`
- Service: `bookkeeping and basic financial reporting`
- Businesses: `10`

Then click **Find leads**.

## Important

The MVP uses public place/business information from OpenStreetMap. It does not automatically send messages or collect private/personal data. Verify business details and review outreach manually before contacting anyone.
