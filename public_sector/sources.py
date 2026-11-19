"""US federal spending and opportunity APIs.

USAspending  https://api.usaspending.gov  (free, no key)    POST /api/v2/search/spending_by_award/
SAM.gov      https://api.sam.gov/opportunities/v2/search   (free public API key required)
"""
from __future__ import annotations

import os
import re

from .common import Http

USA = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
SAM = "https://api.sam.gov/opportunities/v2/search"
AWARD_FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Awarding Sub Agency",
                "Start Date", "End Date", "Description", "generated_internal_id"]


def client() -> Http:
    return Http("abm-public-sector-buyers/0.1 (+https://github.com/Rahul-peacenik159/abm-public-sector-buyers)",
                min_interval=0.5, timeout=60)


def awards(http: Http, keywords: list[str], start: str, end: str, award_types: list[str], max_pages: int = 5,
           recipients: list[str] | None = None) -> list[dict]:
    filters = {"keywords": keywords, "time_period": [{"start_date": start, "end_date": end}],
               "award_type_codes": award_types}
    if recipients:
        filters["recipient_search_text"] = recipients
    out = []
    for page in range(1, max_pages + 1):
        j = http.post_json(USA, {"filters": filters, "fields": AWARD_FIELDS, "page": page, "limit": 100,
                                 "sort": "Award Amount", "order": "desc", "subawards": False})
        out += [normalise_award(r) for r in j.get("results", [])]
        if not (j.get("page_metadata") or {}).get("hasNext"):
            break
    return out


def normalise_award(r: dict) -> dict:
    gid = r.get("generated_internal_id") or ""
    return {"award_id": r.get("Award ID") or "", "recipient": r.get("Recipient Name") or "",
            "amount": float(r.get("Award Amount") or 0), "agency": r.get("Awarding Agency") or "",
            "sub_agency": r.get("Awarding Sub Agency") or "", "start": r.get("Start Date") or "",
            "end": r.get("End Date") or "", "description": (r.get("Description") or "")[:300],
            "url": f"https://www.usaspending.gov/award/{gid}" if gid else ""}


def opportunities(http: Http, posted_from: str, posted_to: str, keyword: str | None = None,
                  naics: str | None = None) -> list[dict]:
    """Active SAM.gov notices (dates as MM/dd/yyyy). Needs SAM_API_KEY."""
    key = os.getenv("SAM_API_KEY")
    if not key:
        return []
    params = {"api_key": key, "postedFrom": posted_from, "postedTo": posted_to, "limit": 1000}
    if keyword:
        params["title"] = keyword
    if naics:
        params["ncode"] = naics
    r = http.request("GET", SAM, params=params)
    if r.status_code in (401, 403):
        raise RuntimeError("SAM.gov rejected the API key (check SAM_API_KEY)")
    r.raise_for_status()
    out = []
    for o in r.json().get("opportunitiesData", []) or []:
        if str(o.get("active", "Yes")).lower() not in ("yes", "true"):
            continue
        path = o.get("fullParentPathName") or ""
        out.append({"notice_id": o.get("noticeId", ""), "title": o.get("title", ""), "type": o.get("type", ""),
                    "agency": path.split(".")[0] if path else "", "office": path, "posted": o.get("postedDate", ""),
                    "deadline": o.get("responseDeadLine") or "", "naics": o.get("naicsCode", ""),
                    "solicitation": o.get("solicitationNumber", ""), "url": o.get("uiLink", "")})
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
