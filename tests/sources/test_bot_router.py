from types import SimpleNamespace
from reels_radar.bot import router
from reels_radar.config import Theme


def test_router_builds_and_account_handler_precedes_generic_callback(db, sdb, tmp_path):
    s = SimpleNamespace(owner_id=1, vault=tmp_path, data_dir=tmp_path)
    rt = router(s, db, {"ИИ": Theme("ИИ", "f", "m")}, sdb)
    names = [h.callback.__name__ for h in rt.callback_query.handlers]
    assert names.index("acb") < names.index("cb")
    msg_names = {h.callback.__name__ for h in rt.message.handlers}
    assert {"cleanup", "clist", "done"} <= msg_names
