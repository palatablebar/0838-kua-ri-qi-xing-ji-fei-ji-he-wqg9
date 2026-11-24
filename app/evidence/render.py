from app.errors import DomainIssue
from app.evidence.manifest import stable_digest


def render(run):
    if run is None:
        raise DomainIssue("RUN_NOT_FOUND", 404)
    if run["status"] != "APPROVED":
        raise DomainIssue("NOT_APPROVED", 409)
    artifact = {
        "schema": "workbench-evidence/v1",
        "run_id": run["run_id"],
        "project": run["project"],
        "rule": run["rule"],
        "profile": run["profile"],
        "source": run["source"],
        "counts": run["counts"],
        "ledger": run["ledger"],
        "disputes": {"pairs": run.get("disputes", {}).get("pairs", []),
                     "groups": run.get("disputes", {}).get("groups", []),
                     "disputed_rides": run.get("disputes", {}).get("disputed_rides", []),
                     "cleared_rides": run.get("disputes", {}).get("cleared_rides", []),
                     "held_total": run.get("disputes", {}).get("held_total", "0")},
        "summary": run["summary"],
        "review": {"status": run["status"], "revision": run["revision"], "comment": run["comment"]},
    }
    artifact["artifact_sha256"] = stable_digest(artifact)
    return artifact
