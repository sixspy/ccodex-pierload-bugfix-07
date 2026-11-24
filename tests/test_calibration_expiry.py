"""BUGFIX-07 过期地磅入票回归（过期修庚·第22轮三红夹具）。

三红：
1. 测甲：过期地磅仍落正式票（建票口未按校准有效期拒写）。
2. 测乙：对账仍把过期地磅的票计入正式合计。
3. 争用：两路会话同磅抢建票，未占地磅锁、后到未只记争用痕。

判定期口径只读 calibration_valid_until；不得拿 calibration_date（上次检定日）
冒充有效期，也不得混用两种口径。
"""
from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

import db
import tickets_svc
from app import app
from db import init_db, plus_days_iso, today_iso


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient, user="admin", password="admin123") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _lane(c: TestClient, h: dict, lane_code: str) -> dict:
    lanes = c.get("/api/lanes", headers=h).json()["items"]
    return next(x for x in lanes if x["lane_code"] == lane_code)


def _set_calibration(bridge_code: str, calibration_date: str, valid_until: str) -> None:
    with db.connect() as conn:
        conn.execute(
            """UPDATE weigh_bridges SET calibration_date=?, calibration_valid_until=?
               WHERE bridge_code=?""",
            (calibration_date, valid_until, bridge_code),
        )
        conn.commit()


def _ticket_count(lane_id: int) -> int:
    with db.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) c FROM weigh_tickets WHERE lane_id=?", (lane_id,)
        ).fetchone()["c"]


def _insert_ticket(
    code: str,
    lane_code: str,
    bl_ref: str,
    gross: float,
    created_at: str,
    status: str = "已裁定",
) -> None:
    """过期地磅仍入票夹具：绕过建票口直接落库，模拟已滑入正式册的票。"""
    with db.connect() as conn:
        lane = conn.execute(
            "SELECT id FROM weigh_lanes WHERE lane_code=?", (lane_code,)
        ).fetchone()
        assert lane is not None
        conn.execute(
            """INSERT INTO weigh_tickets(ticket_code,lane_id,bl_ref,vehicle_plate,
               axle_weights,gross_t,generation,status,adjudicated_at,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                code,
                lane["id"],
                bl_ref,
                "夹具车",
                json.dumps([{"axle": 1, "w": gross / 2}, {"axle": 2, "w": gross / 2}]),
                gross,
                1,
                status,
                created_at,
                created_at,
            ),
        )
        conn.commit()


def test_expired_bridge_cannot_enter_formal_ticket():
    """测甲：过期地磅正式零增拒写；判定须读有效期而非上次检定日。"""
    c = TestClient(app)
    h = _auth(c)
    today = today_iso()
    axles = [{"axle": 1, "w": 5.0}, {"axle": 2, "w": 5.0}]

    # 对照组 1：上次检定日已远，但有效期未到 -> 应放行
    # （若误拿 calibration_date 当有效期，这条会被错误拒写）
    _set_calibration("WB-N-01", plus_days_iso(today, -300), plus_days_iso(today, 30))
    lane_ok = _lane(c, h, "LN-N-01-IN")
    ok = c.post(
        "/api/tickets",
        headers=h,
        json={
            "lane_id": lane_ok["id"],
            "bl_ref": "BL-2026-0101",
            "vehicle_plate": "测甲·有效磅",
            "axle_weights": axles,
            "ticket_code": "WT-CAL-OK-001",
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] in ("已裁定", "旁路挂起")

    # 对照组 2：上次检定日很近，但有效期已过 -> 必须拒写
    # （若误拿 calibration_date 当有效期，这条会被错误放行）
    _set_calibration("WB-S-01", plus_days_iso(today, -2), plus_days_iso(today, -1))
    lane_misread = _lane(c, h, "LN-S-01-IN")
    before_misread = _ticket_count(lane_misread["id"])
    bad = c.post(
        "/api/tickets",
        headers=h,
        json={
            "lane_id": lane_misread["id"],
            "bl_ref": "BL-2026-0102",
            "vehicle_plate": "测甲·误读磅",
            "axle_weights": axles,
            "ticket_code": "WT-CAL-BADDATE-001",
        },
    )
    assert bad.status_code == 409, bad.text
    assert "校准" in bad.json()["detail"]
    assert _ticket_count(lane_misread["id"]) == before_misread

    # 主场景：有效期已过的地磅 -> 拒写且正式册零增
    _set_calibration("WB-N-02", plus_days_iso(today, -400), plus_days_iso(today, -1))
    lane_expired = _lane(c, h, "LN-N-02-IN")
    before = _ticket_count(lane_expired["id"])
    res = c.post(
        "/api/tickets",
        headers=h,
        json={
            "lane_id": lane_expired["id"],
            "bl_ref": "BL-2026-0104",
            "vehicle_plate": "测甲·过期磅",
            "axle_weights": axles,
            "ticket_code": "WT-CAL-EXP-001",
        },
    )
    assert res.status_code == 409, res.text
    assert "校准" in res.json()["detail"]
    assert _ticket_count(lane_expired["id"]) == before


def test_reconcile_excludes_ticket_from_expired_bridge():
    """测乙：对账不得把过期地磅的票计入正式合计，有效期内旧票仍应计入。"""
    c = TestClient(app)
    h = _auth(c)
    _set_calibration("WB-N-02", "2026-02-01", "2026-08-01")
    assert (
        c.post(
            "/api/bl",
            headers=h,
            json={
                "bl_code": "BL-2026-0199",
                "cargo_desc": "校准回归货",
                "declared_gross_t": 20.0,
                "vessel_voyage": "回归轮/022",
            },
        ).status_code
        == 200
    )
    # 有效期内建的旧票（20t）：仍属正式
    _insert_ticket(
        "WT-CAL-LEGACY-001",
        "LN-N-02-IN",
        "BL-2026-0199",
        20.0,
        "2026-05-01T08:00:00",
    )
    # 有效期后滑入的票（10t）：不得计正式
    _insert_ticket(
        "WT-CAL-SLIP-001",
        "LN-N-02-IN",
        "BL-2026-0199",
        10.0,
        "2026-09-01T08:00:00",
    )

    recon = c.get("/api/reconcile/BL-2026-0199", headers=h)
    assert recon.status_code == 200, recon.text
    body = recon.json()
    assert body["ticket_sum_t"] == pytest.approx(20.0)
    assert body["balanced"] is True
    unqualified = {t["ticket_code"] for t in body.get("unqualified_tickets", [])}
    assert "WT-CAL-SLIP-001" in unqualified
    assert "WT-CAL-LEGACY-001" not in unqualified


def test_concurrent_build_on_same_bridge_takes_bridge_lock(monkeypatch):
    """争用：两路会话并发打同一过期地磅建票，占地磅锁，后到只记争用痕。"""
    today = today_iso()
    _set_calibration("WB-N-02", plus_days_iso(today, -400), plus_days_iso(today, -1))
    # 同一地磅的第二条车道（夹具直插，避免受车道服务校准拦截影响）
    with db.connect() as conn:
        bridge = conn.execute(
            "SELECT id FROM weigh_bridges WHERE bridge_code='WB-N-02'"
        ).fetchone()
        conn.execute(
            """INSERT INTO weigh_lanes(lane_code,bridge_id,direction,overload_threshold_t,
               side_lane_ref,status,created_at) VALUES (?,?,?,?,?,?,?)""",
            ("LN-N-02-OUT-CAL", bridge["id"], "出闸", 38, "争用旁路", "开放", db.now_iso()),
        )
        conn.commit()

    c1 = TestClient(app)
    c2 = TestClient(app)
    # 双会话同账号：持锁租约须按请求区分，否则同账号两路会互相放行
    h1 = _auth(c1, "admin", "admin123")
    h2 = _auth(c2, "admin", "admin123")
    lane_a = _lane(c1, h1, "LN-N-02-IN")
    lane_b = _lane(c1, h1, "LN-N-02-OUT-CAL")
    bridge_id = lane_a["bridge_id"]

    entered = threading.Event()
    release = threading.Event()
    original = tickets_svc.validate_lane_open

    def slow_lane_check(lane):
        # 第一路持有地磅锁后再进入车道校验，制造确定性的并发窗口
        entered.set()
        release.wait(10)
        return original(lane)

    monkeypatch.setattr(tickets_svc, "validate_lane_open", slow_lane_check)
    results: dict[str, object] = {}

    def build_first():
        results["a"] = c1.post(
            "/api/tickets",
            headers=h1,
            json={
                "lane_id": lane_a["id"],
                "bl_ref": "BL-2026-0104",
                "vehicle_plate": "争用·甲",
                "axle_weights": [{"axle": 1, "w": 5.0}, {"axle": 2, "w": 5.0}],
                "ticket_code": "WT-CAL-RACE-A",
            },
        )

    timer = threading.Timer(10, release.set)
    timer.start()
    t = threading.Thread(target=build_first)
    t.start()
    try:
        assert entered.wait(10), "第一路未进入建票临界区"
        # 后到的一路：地磅锁被占，只允许记争用，不得写业务
        resp_b = c2.post(
            "/api/tickets",
            headers=h2,
            json={
                "lane_id": lane_b["id"],
                "bl_ref": "BL-2026-0104",
                "vehicle_plate": "争用·乙",
                "axle_weights": [{"axle": 1, "w": 5.0}, {"axle": 2, "w": 5.0}],
                "ticket_code": "WT-CAL-RACE-B",
            },
        )
    finally:
        release.set()
        t.join(20)
        timer.cancel()

    resp_a = results.get("a")
    assert resp_a is not None, "第一路未返回"
    assert resp_a.status_code == 409, resp_a.text
    assert "校准" in resp_a.json()["detail"]
    assert resp_b.status_code == 409, resp_b.text
    assert "争用" in resp_b.json()["detail"]

    contention = c1.get("/api/contention", headers=h1).json()["items"]
    bridge_hits = [
        x
        for x in contention
        if x["lock_key"] == f"bridge:{bridge_id}" and x["actor"] == "admin"
    ]
    assert len(bridge_hits) == 1

    with db.connect() as conn:
        created = {
            r["ticket_code"]
            for r in conn.execute(
                "SELECT ticket_code FROM weigh_tickets WHERE ticket_code IN (?,?)",
                ("WT-CAL-RACE-A", "WT-CAL-RACE-B"),
            ).fetchall()
        }
        leftover = conn.execute(
            "SELECT COUNT(*) c FROM pier_locks WHERE lock_key=?",
            (f"bridge:{bridge_id}",),
        ).fetchone()["c"]
    assert created == set()
    assert leftover == 0, "地磅锁未释放"
