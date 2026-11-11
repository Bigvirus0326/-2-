"""배포본 점검 (Qt 版): 창을 보이지 않게 띄워 모든 탭과 창을 열고, 게임 그림을 만들고,
예시 모드를 만들어 검사한 뒤 결과를 JSON 으로 쓴다. `모드 메이커.exe --selftest 결과.json` 으로 실행한다."""
import copy
import json
import os
import shutil
import sys
import tempfile
import traceback

from PySide6.QtWidgets import QApplication

import cardframeqt
import findqt
import gimmick as GM
import ingame
import modgen as M
import artuiqt


def run(report_path):
    rep = {"ok": False, "app_dir": "", "frozen": bool(getattr(sys, "frozen", False)), "steps": []}

    def step(name, fn):
        try:
            result = fn()
            rep["steps"].append({"step": name, "ok": True, "info": result})
        except Exception as e:  # noqa: BLE001
            rep["steps"].append({"step": name, "ok": False, "error": f"{e}", "trace": traceback.format_exc()[-1500:]})

    # 창을 여는 곳은 app_qt 에서 가져온다 (순환을 피하려고 여기서 import)
    import app_qt
    import projectio as IO
    rep["app_dir"] = IO.APP_DIR
    app = QApplication.instance() or QApplication(sys.argv)
    win = app_qt.QtApp()
    win.show()
    app.processEvents()

    for i, page in enumerate(list(win._docks)):          # 모든 탭 (독에 올라 있는 페이지)
        step(f"tab {i}", lambda page=page: (win.select(page), app.processEvents(), "ok")[2])

    def dialogs():
        made = []
        made.append(artuiqt.ArtGuideDialogQt(win, win))
        made.append(artuiqt.ArtApplyDialogQt(win, parent=win))
        made.append(findqt.FindPaletteQt(win, "ㅌ", win))
        made.append(cardframeqt.FrameStyleDialogQt(win, win.project, win.game_assets))
        for w in made:
            w.show()
            app.processEvents()
            w.close()
            w.deleteLater()
        app.processEvents()
        return len(made)
    step("dialogs", dialogs)

    def game():
        a = win.game_assets()
        if a is None:
            return "게임 폴더 없음 (건너뜀)"
        im = ingame.compose(a, win.project, "card", win.project["cards"][0], "ko")
        return f"card render {im.size}"
    step("game assets", game)

    def generate():
        out = tempfile.mkdtemp(prefix="sts2mm_selftest_")
        try:
            p = M.normalize(copy.deepcopy(win.project))
            GM.add_examples(p)
            errs, _warnings = M.validate(p)
            root = M.generate(p, out, log=lambda _m: None)
            return {"validate_errors": errs[:3], "generated": bool(root)}
        finally:
            shutil.rmtree(out, ignore_errors=True)
    step("generate", generate)

    rep["ok"] = all(s["ok"] for s in rep["steps"])
    win.dirty = False
    win.close()
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return 0 if rep["ok"] else 1


def report_path_from_args(argv):
    if "--selftest" not in argv:
        return None
    i = argv.index("--selftest")
    return argv[i + 1] if len(argv) > i + 1 else os.path.join(os.getcwd(), "selftest.json")
