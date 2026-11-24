from app.domain.calculate import calculate_rows
from app.domain.overlap import resolve_overlaps
from app.domain.prepare import prepare_rows
from app.review.policy import approval_allowed
from app.service import pipeline


def trip(trip_id, bike_id, start, end, debit, paused="0", distance="1000"):
    return {"trip_id": trip_id, "bike_id": bike_id, "start_at": start, "end_at": end,
            "paused_minutes": paused, "distance_m": distance, "wallet_debit": debit, "plan": "standard"}


def decide(rows):
    items, issues = prepare_rows(rows)
    assert issues == []
    results = calculate_rows(items)
    # 复刻 service 中第 4 阶段的调用顺序
    from app.domain.decision import decide_rows
    results = decide_rows(results)
    disputes = resolve_overlaps(results)
    return results, disputes


def by_label(results, label):
    return next(item for item in results if item.get("label") == label)


def test_non_overlapping_rides_are_clear():
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:15", "2026-11-20 08:30", "1.00"),
    ])
    assert all(item["overlap_state"] == "CLEAR" for item in results)
    assert disputes["counts"]["overlap_pairs"] == 0
    assert disputes["held_total"] == "0"


def test_touching_intervals_do_not_overlap():
    # 首尾相接（半开区间）不算同一时段两趟
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:15", "2026-11-20 09:00", "3.00"),
    ])
    assert disputes["pairs"] == []
    assert by_label(results, "A1")["overlap_state"] == "CLEAR"


def test_single_matching_side_books_normally():
    # 同一时段两趟：A 实扣与应收相符，B 对不上
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:20", "0.50"),
    ])
    a1, a2 = by_label(results, "A1"), by_label(results, "A2")
    assert a1["overlap_state"] == "CLEARED"
    assert a1["verdict"] == "PASS"
    assert a2["overlap_state"] == "DISPUTED"
    assert a2["verdict"] == "REJECT" and a2["reason"] == "OVERLAP_DISPUTE"
    pair = disputes["pairs"][0]
    assert pair["outcome"] == "SINGLE_MISMATCH"
    assert pair["resolution"] == "PARTIAL_BOOKED"
    assert pair["cleared"] == ["A1"] and pair["disputed"] == ["A2"]


def test_both_match_holds_both_and_blocks_batch():
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:15", "1.00"),
    ])
    assert {item["overlap_state"] for item in results} == {"DISPUTED"}
    assert disputes["pairs"][0]["outcome"] == "BOTH_MATCH"
    assert all(item["verdict"] == "REJECT" for item in results)
    payload = pipeline_payload_with_disputes(results, disputes)
    assert approval_allowed(payload) is False


def test_both_mismatch_holds_both():
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "0.10"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:15", "0.20"),
    ])
    assert disputes["pairs"][0]["outcome"] == "BOTH_MISMATCH"
    assert {item["overlap_state"] for item in results} == {"DISPUTED"}


def test_wrong_trip_against_two_disjoint_rides_does_not_shelve_group():
    # 错单 A3 先撞 A1（A1 相符）、再撞 A2（A2 相符），A1/A2 互不重叠
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 09:00", "2026-11-20 09:15", "1.00"),
        trip("A3", "B1", "2026-11-20 08:10", "2026-11-20 09:05", "9.00"),
    ])
    # 整组连通但只挂错单 A3，两趟有凭据的车费照常入账
    assert len(disputes["groups"]) == 1
    assert by_label(results, "A1")["overlap_state"] == "CLEARED"
    assert by_label(results, "A2")["overlap_state"] == "CLEARED"
    assert by_label(results, "A3")["overlap_state"] == "DISPUTED"
    assert disputes["disputed_rides"] == ["A3"]
    assert set(disputes["cleared_rides"]) == {"A1", "A2"}
    assert all(pair["resolution"] == "PARTIAL_BOOKED" for pair in disputes["pairs"])


def test_different_bikes_never_conflict():
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:20", "0.10"),
        trip("A2", "B2", "2026-11-20 08:00", "2026-11-20 08:20", "0.10"),
    ])
    assert disputes["pairs"] == []
    assert all(item["overlap_state"] == "CLEAR" for item in results)


def test_held_takes_priority_when_ride_is_cleared_in_one_pair():
    # A1 与 A2 配对中本应保留（A2 对不上），但 A1 与 A3 又都相符 -> A1 必须挂账
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:10", "0.50"),
        trip("A3", "B1", "2026-11-20 08:08", "2026-11-20 08:15", "1.00"),
    ])
    a1 = by_label(results, "A1")
    assert a1["overlap_state"] == "DISPUTED"
    assert a1["verdict"] == "REJECT"
    assert "A1" not in disputes["cleared_rides"]
    assert "A1" in disputes["disputed_rides"]


def test_disputed_fare_is_suspended_not_lost():
    results, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:20", "0.50"),
    ])
    total = sum(item["fare"] for item in results)
    assert int(disputes["held_total"]) + int(disputes["booked_total"]) == total
    assert int(disputes["held_total"]) == by_label(results, "A2")["fare"]


def test_disputed_ride_is_traceable_to_pair():
    _, disputes = decide([
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:20", "0.50"),
    ])
    referenced = {key for pair in disputes["pairs"] for key in pair["disputed"]}
    assert set(disputes["disputed_rides"]) == referenced


def test_ledger_includes_overlap_checks(tmp_path):
    payload = pipeline_overlap_payload(tmp_path)
    check_ids = {check["id"] for check in payload["ledger"]["checks"]}
    assert {"ride_complete", "dispute_trace", "suspense_balance"} <= check_ids
    assert payload["ledger"]["all_checks"] is True


def test_ledger_blocks_signoff_when_suspense_open(tmp_path):
    payload = pipeline_overlap_payload(tmp_path)
    assert payload["summary"]["REJECT"] >= 1
    assert approval_allowed(payload) is False


def test_resolve_overlaps_is_deterministic():
    rows = [
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:20", "0.50"),
    ]
    first_results, first = decide(rows)
    second_results, second = decide([dict(item) for item in rows])
    assert first == second
    assert [item["verdict"] for item in first_results] == [item["verdict"] for item in second_results]


def pipeline_payload_with_disputes(results, disputes):
    # 与 service 阶段输出同构的最小负载，供签发闸门判断
    summary = {"PASS": 0, "REVIEW": 0, "REJECT": 0}
    for item in results:
        summary[item["verdict"]] += 1
    return {"summary": summary,
            "ledger": {"all_checks": disputes["counts"]["disputed_rides"] == 0}}


def pipeline_overlap_payload(tmp_path):
    import csv
    import io

    from app.catalog import SPEC

    rows = [
        trip("A1", "B1", "2026-11-20 08:00", "2026-11-20 08:15", "1.00"),
        trip("A2", "B1", "2026-11-20 08:05", "2026-11-20 08:20", "0.50"),
        trip("A3", "B2", "2026-11-20 10:00", "2026-11-20 10:15", "1.00"),
    ]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(SPEC["columns"])
    for item in rows:
        writer.writerow([item[column] for column in SPEC["columns"]])
    path = tmp_path / "overlap.csv"
    path.write_text(stream.getvalue(), encoding="utf-8")
    return pipeline("clean", str(path))
