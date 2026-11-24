from decimal import Decimal

from app.catalog import SPEC
from app.service import pipeline
from tests.domain_cases import CLEAN


def payload():
    return pipeline("clean")


def test_source_rows_are_balanced():
    assert payload()["ledger"]["balanced"] is True


def test_counts_add_up():
    counts = payload()["counts"]
    assert counts["input"] == counts["accepted"] + counts["isolated"] + counts["duplicates"] + counts["ignored"]


def test_accepted_count_matches_sample():
    assert payload()["counts"]["accepted"] == 5


def test_computed_count_matches_rule():
    assert payload()["counts"]["computed"] == 5


def test_metric_total_matches_rows():
    data = payload()
    assert Decimal(data["ledger"]["metric_total"]) == Decimal("1050")


def test_ledger_checks_pass():
    assert all(item["ok"] for item in payload()["ledger"]["checks"])


def test_ledger_carries_overlap_guards():
    ledger = payload()["ledger"]
    check_ids = {item["id"] for item in ledger["checks"]}
    assert {"ride_complete", "dispute_trace", "suspense_balance"} <= check_ids
    # 无争议样例：入账即应收，挂账为零
    assert ledger["held_total"] == "0"
    assert ledger["booked_total"] == ledger["metric_total"]
    assert ledger["disputed_rides"] == [] and ledger["overlap_pairs"] == []


def test_no_source_ride_is_missing():
    data = payload()
    # 来源行要么进入计算，要么在隔离/重复/忽略中留痕
    counts = data["counts"]
    assert counts["input"] - counts["computed"] == counts["isolated"] + counts["duplicates"] + counts["ignored"]
