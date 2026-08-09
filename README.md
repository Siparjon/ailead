# AI Lead Finder

A small MVP that finds local businesses and uses an OpenAI model to score them as potential bookkeeping/accounting leads.

## What it does

1. Search businesses with Google Places API (New).
2. Deduplicate results.
3. Ask an OpenAI model to score each business from 0–100 for the service you want to sell.
4. Generate a short reason and a personalized first outreach message.
5. Show results in a sortable table and let you download CSV.

## Setup

Requirements: Python 3.11+

```bash
pip install -r requirements.txt
cp .env.example .env
```

Add API keys to `.env`:

```env
OPENAI_API_KEY=your_openai_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
OPENAI_MODEL=gpt-5-mini
```

Then run:

```bash
streamlit run app.py
```

## Google Places setup

Enable **Places API (New)** in your Google Cloud project and create an API key. The app uses Text Search (New) with an explicit field mask.

## Important

The MVP only uses public business information returned by the Places API. It does not automatically send messages or scrape private/personal data. Review leads and outreach manually before contacting anyone.
