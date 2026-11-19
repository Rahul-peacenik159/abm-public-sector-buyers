import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from public_sector import cli, common, sources
from public_sector.common import load_yaml

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "fixtures"
CFG = load_yaml(ROOT / "config" / "category.yaml")
FIXED = datetime(2026, 11, 20, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed(monkeypatch):
    monkeypatch.setattr(common, "now", lambda: FIXED)
    monkeypatch.setattr(cli, "now", lambda: FIXED)


class FakeResp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status
    def json(self): return self.data
    def raise_for_status(self): pass


class FakeHttp:
    def __init__(self):
        self.posted = []
    def post_json(self, url, payload, **kw):
        self.posted.append(payload)
        return json.loads((FX / "usaspending.json").read_text())
    def request(self, method, url, params=None, **kw):
        assert params["api_key"] == "k"
        return FakeResp(json.loads((FX / "sam.json").read_text()))


def test_awards_request_and_normalise():
    http = FakeHttp()
    rows = sources.awards(http, ["identity management"], "2024-11-20", "2026-11-20", ["A", "B", "C", "D"])
    f = http.posted[0]["filters"]
    assert f["keywords"] == ["identity management"] and f["award_type_codes"] == ["A", "B", "C", "D"]
    assert rows[0]["recipient"] == "OKTA INC" and rows[0]["url"].endswith("/award/CONT_AWD_AW1")


def test_opportunities(monkeypatch):
    monkeypatch.setenv("SAM_API_KEY", "k")
    opps = sources.opportunities(FakeHttp(), "10/21/2026", "11/20/2026", keyword="identity")
    assert len(opps) == 1 and opps[0]["agency"] == "DEPT OF DEFENSE" and opps[0]["deadline"].startswith("2026-12-15")
    monkeypatch.delenv("SAM_API_KEY")
    assert sources.opportunities(FakeHttp(), "a", "b") == []


def test_analyse():
    awards = [sources.normalise_award(r) for r in json.loads((FX / "usaspending.json").read_text())["results"]]
    rows, summaries, flagged, keys = cli.analyse(awards, [], CFG, None)
    va = next(s for s in summaries if s["agency"] == "Department of Veterans Affairs")
    assert va["competitor_incumbents"] == "OKTA INC" and va["ending_soon"] == 1 and va["category_awards"] == 2
    types = {r["signal_type"] for r in rows}
    assert {"contract_ending_soon", "incumbent_competitor", "new_award_in_category"} <= types
    assert not any(s["agency"] == "Department of Energy" for s in summaries)  # below min amount
    rows2, *_ = cli.analyse(awards, [], CFG, set(keys))
    assert {r["signal_type"] for r in rows2} == {"contract_ending_soon"}


def test_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("SAM_API_KEY", "k")
    monkeypatch.setattr(sources, "client", lambda: FakeHttp())
    out = tmp_path / "out"
    cli.main(["run", "--out", str(out)])
    agencies = {r["agency"]: r for r in csv.DictReader(open(out / "accounts_summary.csv"))}
    assert agencies["DEPT OF DEFENSE"]["open_opportunities"] == "1"
    assert agencies["DEPT OF DEFENSE"]["top_play"] == "bid_or_partner"
    assert list(csv.DictReader(open(out / "flagged_awards.csv")))[0]["recipient"] == "OKTA INC"
