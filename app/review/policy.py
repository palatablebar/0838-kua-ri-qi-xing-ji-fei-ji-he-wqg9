def approval_allowed(payload):
    # 阻断项为零，且对账检查全部通过（含争议挂账未决时批次不得签发）
    if int(payload["summary"].get("REJECT", 0)) != 0:
        return False
    ledger = payload.get("ledger")
    if ledger is not None and not ledger.get("all_checks", False):
        return False
    return True
