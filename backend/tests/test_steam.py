"""Steam 元数据抓取:结果分类(成功 / 不可访问 / 错误)。"""
from app.models import Mod
from app.services import steam


def test_fetch_details_classifies_result_codes(settings, monkeypatch):
    """result=9(已删除/下架)与 result=2 归为 unavailable;非 GMod 物品归为 error。"""
    def fake_post(s, form):
        return {"response": {"publishedfiledetails": [
            {"publishedfileid": "9", "result": 9},
            {"publishedfileid": "1", "result": 1, "consumer_app_id": 4000, "title": "ok"},
            {"publishedfileid": "2", "result": 2},
            {"publishedfileid": "7", "result": 1, "consumer_app_id": 730, "title": "other"},
        ]}}

    monkeypatch.setattr(steam, "_post_with_retry", fake_post)
    ok, failed = steam.fetch_details(settings, ["9", "1", "2", "7"])
    assert set(ok) == {"1"}
    kinds = {f["id"]: f["kind"] for f in failed}
    assert kinds == {"9": "unavailable", "2": "unavailable", "7": "error"}
    reasons = {f["id"]: f["reason"] for f in failed}
    assert "删除或下架" in reasons["9"]


def test_refresh_marks_unavailable_not_error(db, settings, monkeypatch):
    """result≠1 的已下架物品应记为 unavailable,而不是 error。"""
    db.add(Mod(workshop_id="2868728788", folder_name="2868728788"))
    db.commit()
    monkeypatch.setattr(steam, "fetch_details", lambda s, ids: ({}, [
        {"id": "2868728788", "reason": "该创意工坊物品已被删除或下架", "kind": "unavailable"}]))
    stats = steam.refresh_metadata(db, settings, ["2868728788"])
    db.commit()
    assert stats == {"refreshed": 0, "skipped": 0, "failed": 0, "unavailable": 1}
    m = db.get(Mod, "2868728788")
    assert m.metadata_state == "unavailable"
    assert "删除或下架" in m.metadata_error


def test_refresh_marks_wrong_app_as_error(db, settings, monkeypatch):
    """物品不属于 Garry's Mod 属真正错误,应记为 error。"""
    db.add(Mod(workshop_id="111", folder_name="111"))
    db.commit()
    monkeypatch.setattr(steam, "fetch_details", lambda s, ids: ({}, [
        {"id": "111", "reason": "该物品不属于 Garry's Mod(AppId=4000)", "kind": "error"}]))
    stats = steam.refresh_metadata(db, settings, ["111"])
    db.commit()
    assert stats["failed"] == 1 and stats["unavailable"] == 0
    assert db.get(Mod, "111").metadata_state == "error"