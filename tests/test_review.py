import csv
import io

from tests.domain_cases import run_profile


def create(client, profile="clean"):
    response = client.post("/api/runs", json={"profile": profile})
    assert response.status_code == 200
    return response.get_json()


def test_clean_run_is_created(client):
    run = create(client)
    assert run["status"] == "DRAFT"
    assert run["revision"] == 0


def test_same_request_is_idempotent(client):
    first = create(client)
    second = create(client)
    assert first["run_id"] == second["run_id"]
    assert first["counts"] == second["counts"]


def test_clean_run_can_be_approved(client):
    run = create(client)
    response = client.post(f"/api/runs/{run['run_id']}/review", json={"decision": "APPROVED", "comment": "已核验", "expected_revision": 0})
    assert response.status_code == 200
    assert response.get_json()["status"] == "APPROVED"


def test_dirty_run_is_blocked(client):
    run = create(client, "dirty")
    response = client.post(f"/api/runs/{run['run_id']}/review", json={"decision": "APPROVED", "comment": "尝试签发", "expected_revision": 0})
    assert response.status_code == 409
    assert response.get_json()["code"] == "GATE_BLOCKED"


def test_stale_revision_is_rejected(client):
    run = create(client)
    first = client.post(f"/api/runs/{run['run_id']}/review", json={"decision": "APPROVED", "comment": "首次", "expected_revision": 0})
    assert first.status_code == 200
    second = client.post(f"/api/runs/{run['run_id']}/review", json={"decision": "APPROVED", "comment": "旧版本", "expected_revision": 0})
    assert second.status_code == 409
    assert second.get_json()["code"] == "STALE_REVIEW"


def test_comment_is_saved(client):
    run = create(client)
    response = client.post(f"/api/runs/{run['run_id']}/review", json={"decision": "APPROVED", "comment": "复核通过", "expected_revision": 0})
    assert response.get_json()["comment"] == "复核通过"


def _overlap_file(tmp_path):
    from app.catalog import SPEC
    rows = [
        {"trip_id": "A1", "bike_id": "B1", "start_at": "2026-11-20 08:00", "end_at": "2026-11-20 08:15",
         "paused_minutes": "0", "distance_m": "1000", "wallet_debit": "1.00", "plan": "standard"},
        {"trip_id": "A2", "bike_id": "B1", "start_at": "2026-11-20 08:05", "end_at": "2026-11-20 08:20",
         "paused_minutes": "0", "distance_m": "1000", "wallet_debit": "0.50", "plan": "standard"},
    ]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(SPEC["columns"])
    for item in rows:
        writer.writerow([item[column] for column in SPEC["columns"]])
    path = tmp_path / "overlap.csv"
    path.write_text(stream.getvalue(), encoding="utf-8")
    return path


def test_overlap_dispute_blocks_signoff(client, tmp_path):
    # 通过阶段接口确认争议已被识别
    from app.service import pipeline
    payload = pipeline("clean", str(_overlap_file(tmp_path)))
    assert payload["disputes"]["counts"]["disputed_rides"] == 1
    assert payload["summary"]["REJECT"] == 1

    run = client.post("/api/runs", json={"profile": "clean"}).get_json()
    # 正常样例无争议，可签发；带争议的批次通过闸门函数拒绝
    from app.review.policy import approval_allowed
    assert approval_allowed(payload) is False
    assert approval_allowed(run) is True


def test_rerun_same_batch_does_not_double_book(client):
    first = create(client)
    second = create(client)
    # 同一来源重跑命中同一请求键，复用草稿而不是再入一笔账
    assert first["run_id"] == second["run_id"]
    assert first["run_key"] == second["run_key"]
    assert first["ledger"]["metric_total"] == second["ledger"]["metric_total"]
    assert first["ledger"]["booked_total"] == second["ledger"]["booked_total"]
    assert first["ledger"]["held_total"] == second["ledger"]["held_total"]
    third = create(client)
    assert third["run_id"] == first["run_id"]
