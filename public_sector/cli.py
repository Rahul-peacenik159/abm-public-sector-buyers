"""python -m public_sector run
python -m public_sector summary out"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from . import sources
from .common import Snapshots, load_yaml, now, parse_dt, score_rows, signal, summary_or_note, write_outputs

ROOT = Path(__file__).resolve().parent.parent
PACK = "public-sector-buyers"
SUMMARY_FIELDS = ["account_domain", "agency", "score", "top_play", "category_awards", "category_spend_usd",
                  "top_recipients", "competitor_incumbents", "ending_soon", "open_opportunities", "errors"]
AWARD_OUT = ["agency", "sub_agency", "recipient", "amount", "start", "end", "award_id", "description", "url", "flags"]
OPP_OUT = ["agency", "office", "title", "type", "posted", "deadline", "naics", "solicitation", "url"]


def analyse(awards: list[dict], opps: list[dict], cfg: dict, seen: set | None) -> tuple[list, list, list, list]:
    """Agency-level rollup -> (signal rows, summaries, flagged awards, snapshot keys)."""
    today = now().date()
    w, p = cfg["weights"], cfg["plays"]
    comps = [c.lower() for c in cfg.get("competitors", [])]
    by_agency: dict[str, dict] = defaultdict(lambda: {"awards": [], "opps": []})
    for a in awards:
        if a["amount"] < cfg.get("min_award_amount", 0) or not a["agency"]:
            continue
        flags = []
        end, start = parse_dt(a["end"]), parse_dt(a["start"])
        if end and today <= end.date() <= today + timedelta(days=cfg.get("ending_within_days", 365)):
            flags.append("ending_soon")
        if start and start.date() >= today - timedelta(days=cfg.get("new_award_days", 90)):
            flags.append("new_award")
        if any(c in a["recipient"].lower() for c in comps):
            flags.append("competitor")
        a["flags"] = ";".join(flags)
        by_agency[a["agency"]]["awards"].append(a)
    for o in opps:
        by_agency[o["agency"] or "Unknown agency"]["opps"].append(o)

    rows, summaries, keys = [], [], []
    for agency, d in by_agency.items():
        acct = f"agency:{sources.slug(agency)}"
        arows = []
        for a in d["awards"]:
            keys.append(f"award:{a['award_id']}")
            fresh = seen is None or f"award:{a['award_id']}" not in seen
            amt = f"${a['amount']:,.0f}"
            if "ending_soon" in a["flags"]:  # always report: the window matters even if seen before
                arows.append(signal(acct, "contract_ending_soon", a["award_id"], pack=PACK, category="federal_award",
                                    role="trigger", weight=w["contract_ending_soon"], play=p["contract_ending_soon"],
                                    source="usaspending", tool_name=agency, evidence_url=a["url"],
                                    evidence=f"{a['recipient']} {amt}, ends {a['end']} ({a['sub_agency']})"))
            if "competitor" in a["flags"] and fresh:
                arows.append(signal(acct, "incumbent_competitor", a["recipient"], pack=PACK, category="federal_award",
                                    role="competitor", weight=w["incumbent_competitor"], play=p["incumbent_competitor"],
                                    source="usaspending", tool_name=agency, evidence_url=a["url"],
                                    evidence=f"{a['recipient']} {amt}, {a['start']} to {a['end']}"))
            if "new_award" in a["flags"] and fresh:
                arows.append(signal(acct, "new_award_in_category", a["award_id"], pack=PACK, category="federal_award",
                                    role="trigger", weight=w["new_award_in_category"], play=p["new_award_in_category"],
                                    source="usaspending", tool_name=agency, evidence_url=a["url"],
                                    evidence=f"{a['recipient']} {amt} from {a['start']}: {a['description'][:120]}"))
        for o in d["opps"]:
            keys.append(f"opp:{o['notice_id']}")
            arows.append(signal(acct, "open_opportunity", o["notice_id"], pack=PACK, category="sam_opportunity",
                                role="trigger", weight=w["open_opportunity"], play=p["open_opportunity"], source="sam.gov",
                                tool_name=agency, evidence_url=o["url"],
                                evidence=f"{o['type']}: {o['title'][:120]} (respond by {o['deadline'][:10] or 'n/a'})"))
        # agency-level score: the strongest few signals, not hundreds of awards
        top = sorted(arows, key=lambda r: -r["weight"])[:5]
        score, play = score_rows(top)
        spend = sum(a["amount"] for a in d["awards"])
        rec = defaultdict(float)
        for a in d["awards"]:
            rec[a["recipient"]] += a["amount"]
        summaries.append({
            "account_domain": acct, "agency": agency, "score": score, "top_play": play,
            "category_awards": len(d["awards"]), "category_spend_usd": round(spend),
            "top_recipients": "; ".join(f"{r} (${v/1e6:,.1f}M)" for r, v in sorted(rec.items(), key=lambda kv: -kv[1])[:3]),
            "competitor_incumbents": "; ".join(sorted({a["recipient"] for a in d["awards"] if "competitor" in a["flags"]})),
            "ending_soon": sum(1 for a in d["awards"] if "ending_soon" in a["flags"]),
            "open_opportunities": len(d["opps"]), "errors": ""})
        rows += arows
    flagged = sorted((a for d in by_agency.values() for a in d["awards"] if a["flags"]), key=lambda a: -a["amount"])
    return rows, summaries, flagged, keys


def cmd_run(args) -> None:
    cfg = load_yaml(args.config)
    http = sources.client()
    snaps = Snapshots(args.out, "awards")
    end = now().date()
    start = end - timedelta(days=cfg.get("lookback_days", 730))
    errors = []
    print(f"USAspending: contract awards matching {cfg['keywords']} since {start}")
    try:
        awards = sources.awards(http, cfg["keywords"], start.isoformat(), end.isoformat(), cfg.get("award_types", ["A", "B", "C", "D"]),
                                args.pages)
    except Exception as exc:
        awards = []
        errors.append(f"usaspending: {exc}")
    opps = []
    if not args.no_sam:
        frm, to = (end - timedelta(days=args.sam_days)).strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        seen_ids = set()
        try:
            for kw in cfg["keywords"]:
                for o in sources.opportunities(http, frm, to, keyword=kw):
                    if o["notice_id"] not in seen_ids:
                        seen_ids.add(o["notice_id"])
                        opps.append(o)
        except Exception as exc:
            errors.append(f"sam.gov: {exc}")
    rows, summaries, flagged, keys = analyse(awards, opps, cfg, snaps.seen_before("_all"))
    snaps.record("_all", keys)
    stamp = snaps.save()
    out = write_outputs(args.out, rows, summaries, SUMMARY_FIELDS, {
        "repo": "abm-public-sector-buyers", "run_at": stamp, "awards": len(awards), "agencies": len(summaries),
        "opportunities": len(opps), "errors": len(errors), "error_detail": errors, "previous_run": snaps.previous_name,
        "new_items": sum(1 for r in rows if r["signal_type"] in ("new_award_in_category", "incumbent_competitor")),
        "sam_enabled": bool(sources.os.getenv("SAM_API_KEY")) and not args.no_sam},
        extra_files={"flagged_awards.csv": (flagged, AWARD_OUT), "opportunities.csv": (opps, OPP_OUT)})
    print(f"{len(awards)} awards, {len(summaries)} agencies, {len(opps)} open opportunities -> {out}/")
    for e in errors:
        print("  ERROR", e)


def cmd_summary(args) -> None:
    out = Path(args.out)
    print(summary_or_note(out / "accounts_summary.csv",
                          [("agency", "Agency"), ("score", "Score"), ("top_play", "Top play"),
                           ("category_spend_usd", "Category spend (USD)"), ("top_recipients", "Top recipients"),
                           ("competitor_incumbents", "Competitor incumbents"), ("ending_soon", "Ending within 12 mo"),
                           ("open_opportunities", "Open opportunities")], "Public sector buyers", top=30))
    if (out / "opportunities.csv").exists() and (out / "opportunities.csv").stat().st_size > 100:
        print(summary_or_note(out / "opportunities.csv", [("agency", "Agency"), ("title", "Title"), ("type", "Type"),
                                                          ("deadline", "Deadline"), ("url", "Link")], "Open SAM.gov opportunities", top=20))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="public_sector", description="Government buyers for ABM")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", default=str(ROOT / "config" / "category.yaml"))
    r.add_argument("--pages", type=int, default=5, help="USAspending pages of 100 awards (largest first)")
    r.add_argument("--sam-days", type=int, default=30, help="SAM.gov notices posted in the last N days")
    r.add_argument("--no-sam", action="store_true")
    r.add_argument("--out", default="out")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("out", nargs="?", default="out")
    s.set_defaults(func=cmd_summary)
    args = ap.parse_args(argv)
    args.func(args)
