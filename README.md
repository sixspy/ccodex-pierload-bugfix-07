# 港口过磅闸口（pierload）

数据工程母仓：港区地磅过磅 → 超重旁路挂起 → 裁定放行 → 闸代快照 → 提单册对账。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器访问 http://localhost:11500

- 管理账号：`admin` / `admin123`
- 读写账号：`writer` / `writer123`

## 本地开发

```powershell
cd projects/13-pierload
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8000
```

静态页仍由 FastAPI 托管于同一进程。

## 自测

```powershell
$env:PYTHONPATH="backend"
python -m pytest
python scripts/count_loc.py
```

## 地磅校准口径

- 判定只读 `weigh_bridges.calibration_valid_until`（有效期截止日）；`calibration_date`
  只是上次检定日，不得拿来当有效期，两种口径不得混用。
- 建票口 `POST /api/tickets` 先占地磅锁 `bridge:{bridge_id}`，再占车道锁；
  有效期已过即 409 拒写，正式册零增。同磅并发时后到的一路只记争用痕。
- 对账只把落在地磅校准有效期内的票计入正式合计，过期期间滑入的票列在
  `unqualified_tickets`，不计正式。
- 五页同源：车道、总览、对账、过磅、地磅的校准状态全部取自 `backend/calibration.py`。
- 回归用例：`tests/test_calibration_expiry.py`（测甲/测乙/争用三红）。