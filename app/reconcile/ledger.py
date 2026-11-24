from decimal import Decimal

from app.catalog import SPEC
from app.reconcile.checks import all_checks


def build_ledger(intake, prepared, prepare_issues, results, disputes=None):
    counts = dict(intake["counts"])
    counts["prepared"] = len(prepared)
    counts["prepare_issues"] = len(prepare_issues)
    counts["computed"] = len(results)
    balanced = counts["input"] == counts["accepted"] + counts["isolated"] + counts["duplicates"] + counts["ignored"]
    metric = sum((item.get("metric") for item in results if item.get("metric") is not None), Decimal("0"))
    if disputes is None:
        disputes = {"pairs": [], "groups": [], "disputed_rides": [], "cleared_rides": [],
                    "counts": {}, "held_total": "0", "booked_total": "0"}
    counts.update(disputes.get("counts", {}))

    # 原始骑行一条也不能少：采信进入计算，其余必须在隔离/重复/忽略留痕
    ride_complete = counts["accepted"] == counts["computed"]
    # 每条争议骑行都能回溯到具体重叠配对
    traceable = set(disputes.get("disputed_rides", [])) == {
        key for pair in disputes.get("pairs", []) for key in pair["disputed"]}
    # 争议款守恒：入账 + 挂账 = 应收合计
    conserved = Decimal(disputes.get("booked_total", "0")) + Decimal(disputes.get("held_total", "0")) == metric
    checks = [
        {"id": "source", "label": "来源行守恒", "ok": balanced},
        {"id": "computed", "label": "计算条目完整", "ok": counts["computed"] == len(results)},
        {"id": "ride_complete", "label": "原始骑行不缺失", "ok": ride_complete},
        {"id": "dispute_trace", "label": "争议配对可追溯", "ok": traceable},
        {"id": "suspense_balance", "label": "挂账款额守恒", "ok": conserved},
    ]
    return {"counts": counts, "balanced": balanced, "metric_field": SPEC.get("metric_field", "metric"),
            "metric_total": str(metric),
            "booked_total": disputes.get("booked_total", "0"),
            "held_total": disputes.get("held_total", "0"),
            "overlap_pairs": disputes.get("pairs", []),
            "overlap_groups": disputes.get("groups", []),
            "disputed_rides": disputes.get("disputed_rides", []),
            "cleared_rides": disputes.get("cleared_rides", []),
            "checks": checks, "all_checks": all_checks(checks)}
