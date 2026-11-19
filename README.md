# abm-public-sector-buyers

**Find the government agencies buying your category, who they buy from today, which contracts end soon (the recompete window), and open solicitations to bid on. Free: USAspending.gov and SAM.gov.**

Public-sector buying is public. Every US federal contract award is published on USAspending.gov, and open opportunities on SAM.gov. This repo turns them into an agency-level ABM list with plays.

## What it finds

| Signal | Meaning | Default play |
|---|---|---|
| `contract_ending_soon` | A category contract at this agency ends within 12 months | `recompete_positioning` |
| `incumbent_competitor` | The current contract holder is one of your competitors | `incumbent_displacement` |
| `new_award_in_category` | The agency awarded a new contract in your category recently | `adjacent_expansion` |
| `open_opportunity` | An open SAM.gov notice matches your keywords (needs a free SAM.gov key) | `bid_or_partner` |

Outputs: `accounts_summary.csv` (one row per agency: category spend, top recipients, competitor incumbents, contracts ending soon, open opportunities), `flagged_awards.csv`, `opportunities.csv`, plus `signals.csv/.jsonl`. Accounts are agencies, written as `agency:<name>` in the shared signals format.

## Quickstart

```bash
git clone https://github.com/Rahul-peacenik159/abm-public-sector-buyers.git
cd abm-public-sector-buyers
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m public_sector run                 # USAspending only, no key needed
export SAM_API_KEY=...                      # optional: add open SAM.gov opportunities
python -m public_sector run --sam-days 30
```

Describe your category in [`config/category.yaml`](config/category.yaml): keywords as they appear in contract descriptions, NAICS codes, competitor names (matched to award recipients), windows and weights.

SAM.gov key: sign in at sam.gov, open your profile (Account Details) and request a public API key. It's free.

## Run it on GitHub

Add `SAM_API_KEY` as a repository secret (optional), then **Actions > run > Run workflow**. Agency table and open opportunities on the Summary page; CSVs in the **results** artifact. Re-runs only re-report awards they haven't seen, except contracts ending soon, which stay on the list until they end.

## n8n

[`n8n/sam-opportunities-daily.json`](n8n/sam-opportunities-daily.json): every morning, new SAM.gov notices for your keywords > signals > BigQuery (or Slack).

## BigQuery

Load `out/signals.jsonl` into the shared `abm.signals` table; [`bigquery/10_recompete_pipeline.sql`](bigquery/10_recompete_pipeline.sql) lists agencies by open opportunities and contracts ending soon.

## Limits

- US federal only. State and local buying isn't covered by these APIs.
- Keyword search matches award descriptions, which are often terse; try several phrasings and check `flagged_awards.csv`.
- Recipient matching is by name, so subsidiaries and resellers may be missed. Many software deals run through resellers, so check the description too.

## Part of the open ABM bundles

| Repo | What it adds |
|---|---|
| [abm-tech-footprint](https://github.com/Rahul-peacenik159/abm-tech-footprint) | what accounts run on their website, DNS and email; security and email posture |
| [abm-hiring-signals](https://github.com/Rahul-peacenik159/abm-hiring-signals) | who is hiring for what (Greenhouse, Lever, Ashby public job boards) |
| [abm-public-company-triggers](https://github.com/Rahul-peacenik159/abm-public-company-triggers) | SEC filings: exec changes, M&A, restructuring, keyword mentions, revenue trend |
| [abm-news-pulse](https://github.com/Rahul-peacenik159/abm-news-pulse) | news events per account from GDELT (funding, M&A, launches, leadership, layoffs) |
| [abm-tam-builder](https://github.com/Rahul-peacenik159/abm-tam-builder) | build the account universe from Wikidata, OpenStreetMap and US Census data |
| [abm-dev-community-signals](https://github.com/Rahul-peacenik159/abm-dev-community-signals) | which companies' engineers engage with your or competitors' GitHub repos; HN mentions |
| [abm-market-timing](https://github.com/Rahul-peacenik159/abm-market-timing) | topic and region demand: Wikipedia attention, news volume, Google Trends in BigQuery |
| **abm-public-sector-buyers** (this repo) | government buyers: USAspending awards, incumbents, SAM.gov open opportunities |
| [abm-activation-kit](https://github.com/Rahul-peacenik159/abm-activation-kit) | combine all signals, score, and push to HubSpot, LinkedIn audiences and 1:1 pages |

## License

Apache-2.0. Award and opportunity data are U.S. government public information.
