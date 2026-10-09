"""Mod 类型:标签映射推导 + 列表按类型筛选 + 类型清单接口。"""
from app.models import Mod
from app.services import categories, steam


def test_derive_category_ignores_case_and_picks_first_type():
    assert categories.derive_category(["Addon", "Weapon", "Fun"]) == "Weapon"
    assert categories.derive_category(["Addon", "map"]) == "Map"       # 小写标签
    assert categories.derive_category(["addon", "tool"]) == "Tool"
    assert categories.derive_category(["Model", "Comic"]) == "Model"   # 取首个类型
    assert categories.derive_category(["Fun", "Cartoon"]) == "Other"   # 无类型标签
    assert categories.derive_category([]) == "Other"
    assert categories.derive_category(None) == "Other"


def test_category_zh():
    assert categories.category_zh("Weapon") == "武器"
    assert categories.category_zh("Model") == "模型/角色"
    assert categories.category_zh("Other") == "其他"
    assert categories.category_zh("") == "其他"


def test_apply_details_sets_category():
    mod = Mod(workshop_id="1")
    steam.apply_details(mod, {"title": "t", "tags": [{"tag": "Addon"}, {"tag": "Weapon"}]})
    assert mod.category == "Weapon"


def test_mod_list_category_filter_and_categories_endpoint(auth, db):
    from tests.conftest import WID_A, WID_B
    db.add_all([
        Mod(workshop_id=WID_A, folder_name=WID_A, category="Weapon"),
        Mod(workshop_id=WID_B, folder_name=WID_B, category="Map"),
    ])
    db.commit()

    r = auth.get("/api/mods", params={"category": "Weapon"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["workshop_id"] == WID_A
    assert body["items"][0]["category_zh"] == "武器"

    r2 = auth.get("/api/mods/categories")
    assert r2.status_code == 200, r2.text
    items = {i["value"]: i for i in r2.json()["items"]}
    assert items["Weapon"] == {"value": "Weapon", "label": "武器", "count": 1}
    assert items["Map"]["count"] == 1