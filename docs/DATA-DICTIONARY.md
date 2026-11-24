# 字段定义

| 字段 | 类型 | 说明 |
|---|---|---|
| `trip_id` | text | 主键 |
| `bike_id` | text | 业务字段 |
| `start_at` | datetime | 业务字段 |
| `end_at` | datetime | 业务字段 |
| `paused_minutes` | int | 业务字段 |
| `distance_m` | int | 业务字段 |
| `wallet_debit` | money | 业务字段 |
| `plan` | text | 业务字段 |

空字符串、`-`、`NA`、`null` 和 `未提供` 按空值处理。金额字段在整理层转为整数分或整数最小单位；日期按 ISO 日期解析；带时间的字段按本地时间解析。标识字段保持为文本，前导零不会被去除。

## 判定与对账字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `fare` | int（分） | 计算应收车费 |
| `overlap_state` | enum | `CLEAR` 未卷入重叠；`CLEARED` 卷入重叠但实扣相符、照常入账；`DISPUTED` 争议挂账，判定升级为 `REJECT` |
| `overlap_with` | list | 与本行发生时间重叠的骑行主键 |
| `verdict` | enum | `PASS` / `REVIEW` / `REJECT`，争议挂账固定为 `REJECT`，原因码 `OVERLAP_DISPUTE` |
| `booked_total` | int（分） | 本批照常入账车费合计 |
| `held_total` | int（分） | 本批争议挂账车费合计，与 `booked_total` 之和等于应收合计 |
| `overlap_pairs` | list | 重叠配对明细，含双方主键、是否相符、裁决结果与各自应收/实扣 |
