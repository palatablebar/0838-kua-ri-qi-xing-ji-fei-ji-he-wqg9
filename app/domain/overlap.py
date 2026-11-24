"""同一车辆时间重叠骑行的争议裁决。

裁决以骑行对为最小单位：

* 仅一方实扣（wallet_debit）与应收（fare）相符：相符一方照常入账，
  另一方作为争议款挂账。
* 两方都相符或都对不上：两方都挂账，批次不得签发。

一张错单可能先后撞上两趟互不重叠的骑行，裁决按配对逐条进行，
只挂真正对不上账的那一方，不会把整组连通骑行一并搁置。
"""


def label_of(item):
    return item.get("label") or str(item.get("trip_id", ""))


def _intervals_overlap(a, b):
    # 半开区间 [start_at, end_at)：首尾相接不算重叠
    if a["bike_id"] != b["bike_id"]:
        return False
    return a["start_at"] < b["end_at"] and b["start_at"] < a["end_at"]


def _matched(item):
    return item["wallet_debit"] == item["fare"]


def _components(adjacency, order):
    """按输入顺序稳定输出连通分量（同一辆车的重叠骑行组）。"""
    seen = set()
    groups = []
    for node in order:
        if node not in adjacency or node in seen:
            continue
        stack = [node]
        members = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            members.append(current)
            stack.extend(adjacency[current] - seen)
        groups.append(sorted(members, key=order.index))
    return groups


def resolve_overlaps(items):
    """标记重叠骑行并返回争议明细。

    在每条骑行上写入：
    * overlap_state：CLEAR（未卷入重叠）/ CLEARED（卷入但凭实扣保留入账）/
      DISPUTED（争议挂账，判定升级为 REJECT）
    * overlap_with：发生重叠的对向骑行标签
    """
    for item in items:
        item.setdefault("overlap_state", "CLEAR")
        item.setdefault("overlap_with", [])

    by_label = {label_of(item): item for item in items}
    order = [label_of(item) for item in items]
    adjacency = {}
    pairs = []
    disputed = set()
    cleared = set()

    for index in range(len(items)):
        left = items[index]
        for right_index in range(index + 1, len(items)):
            right = items[right_index]
            if not _intervals_overlap(left, right):
                continue

            label_left, label_right = label_of(left), label_of(right)
            left["overlap_with"].append(label_right)
            right["overlap_with"].append(label_left)
            adjacency.setdefault(label_left, set()).add(label_right)
            adjacency.setdefault(label_right, set()).add(label_left)

            match_left, match_right = _matched(left), _matched(right)
            if match_left and not match_right:
                outcome = "SINGLE_MISMATCH"
                pair_cleared, pair_disputed = [label_left], [label_right]
            elif match_right and not match_left:
                outcome = "SINGLE_MISMATCH"
                pair_cleared, pair_disputed = [label_right], [label_left]
            else:
                pair_cleared, pair_disputed = [], [label_left, label_right]
                outcome = "BOTH_MATCH" if match_left and match_right else "BOTH_MISMATCH"

            pairs.append({
                "pair_id": f"OVP-{len(pairs) + 1:03d}",
                "bike_id": left["bike_id"],
                "trips": [label_left, label_right],
                "a_match": match_left,
                "b_match": match_right,
                "outcome": outcome,
                "resolution": "PARTIAL_BOOKED" if pair_cleared else "HELD",
                "cleared": pair_cleared,
                "disputed": pair_disputed,
                "fares": [left["fare"], right["fare"]],
                "wallet_debits": [left["wallet_debit"], right["wallet_debit"]],
            })
            cleared.update(pair_cleared)
            disputed.update(pair_disputed)

    # 同一骑行可能在一个配对中被保留、在另一个配对中被挂账：挂账优先
    cleared -= disputed

    for key in cleared:
        by_label[key]["overlap_state"] = "CLEARED"
    for key in disputed:
        row = by_label[key]
        row["overlap_state"] = "DISPUTED"
        row["verdict"] = "REJECT"
        row["reason"] = "OVERLAP_DISPUTE"

    groups = []
    for members in _components(adjacency, order):
        bike_id = next(by_label[key]["bike_id"] for key in members)
        groups.append({
            "bike_id": bike_id,
            "trips": members,
            "cleared": [key for key in members if key in cleared],
            "disputed": [key for key in members if key in disputed],
        })

    disputed_rows = [by_label[key] for key in order if key in disputed]
    held_total = sum(item["fare"] for item in disputed_rows)
    metric_total = sum(item["fare"] for item in items)

    return {
        "pairs": pairs,
        "groups": groups,
        "disputed_rides": [key for key in order if key in disputed],
        "cleared_rides": [key for key in order if key in cleared],
        "counts": {
            "overlap_pairs": len(pairs),
            "overlap_groups": len(groups),
            "disputed_rides": len(disputed),
            "cleared_rides": len(cleared),
        },
        "held_total": str(held_total),
        "booked_total": str(metric_total - held_total),
    }


def empty_disputes():
    return {
        "pairs": [],
        "groups": [],
        "disputed_rides": [],
        "cleared_rides": [],
        "counts": {"overlap_pairs": 0, "overlap_groups": 0, "disputed_rides": 0, "cleared_rides": 0},
        "held_total": "0",
        "booked_total": "0",
    }
