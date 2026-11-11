"""카드 라이브러리 (Qt 版): 원작 캐릭터 · 참고 프로젝트 · 원작 키워드에서 카드를 골라 가져오거나 적용한다.

Tk 의 card_library.py 와 같은 규칙. 화면 밖으로 끌어 놓기(드래그)는 아직 없다 — 버튼으로 같은 일을 한다.
원작 코드 읽기(디컴파일)는 백그라운드에서 하고 끝나면 화면 스레드에서 보여 준다.
"""
import copy
import json
import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QVBoxLayout, QWidget, QCheckBox, QLineEdit)

import modgen as M
import modimport as MI
import preview_qt as PQ
import projectio as IO
import card_library_rules as CLR
import previewcore as PV
from itemtabqt import all_ids

IMAGE_BOX = (235, 165)


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


class CardLibraryQt(QDialog):
    run_on_ui = Signal(object)          # 백그라운드 작업이 끝난 뒤 화면 스레드에서 실행할 일

    def __init__(self, app, card_page, parent=None):
        super().__init__(parent)
        self.setWindowTitle("카드 라이브러리")
        self.app = app
        self.card_page = card_page
        self.sources = {}
        self.assets = None
        self.rows = []
        self.reading = False
        self.run_on_ui.connect(lambda fn: fn())
        self.resize(1100, 620)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        open_game = QPushButton("원작 캐릭터 열기")
        open_game.clicked.connect(self.open_game)
        top.addWidget(open_game)
        open_projects = QPushButton("프로젝트 파일 열기…")
        open_projects.clicked.connect(self.open_projects)
        top.addWidget(open_projects)
        top.addStretch(1)
        self.upgraded = QCheckBox("강화(+)")
        self.upgraded.toggled.connect(lambda _c: self.show_card())
        top.addWidget(self.upgraded)
        top.addWidget(QLabel("항목 검색"))
        self.search = QLineEdit()
        self.search.setMaximumWidth(220)
        self.search.textChanged.connect(lambda _t: self.refresh_cards())
        top.addWidget(self.search)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        left = QWidget()
        lc = QVBoxLayout(left)
        lc.addWidget(QLabel("열린 캐릭터 · 프로젝트"))
        self.groups = QListWidget()
        self.groups.currentRowChanged.connect(lambda _r: self.refresh_cards())
        lc.addWidget(self.groups, 1)
        split.addWidget(left)
        middle = QWidget()
        mc = QVBoxLayout(middle)
        mc.addWidget(QLabel("항목"))
        self.cards = QListWidget()
        self.cards.currentRowChanged.connect(lambda _r: self.show_card())
        mc.addWidget(self.cards, 1)
        split.addWidget(middle)
        detail = QWidget()
        dc = QVBoxLayout(detail)
        dc.addWidget(QLabel("선택한 항목"))
        self.art = QLabel()
        self.art.setFixedSize(*IMAGE_BOX)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc.addWidget(self.art)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        dc.addWidget(self.info, 1)
        split.addWidget(detail)
        split.setStretchFactor(2, 1)
        split.setSizes([220, 260, 480])

        self.status = QLabel("원작 또는 프로젝트 파일을 열고 카드를 선택하세요.")
        root.addWidget(self.status)
        foot = QHBoxLayout()
        self.add_btn = QPushButton("선택한 카드 가져오기")
        self.add_btn.clicked.connect(lambda: self.add())
        self.apply_btn = QPushButton("편집 중인 카드에 적용")
        self.apply_btn.clicked.connect(lambda: self.apply_selected())
        self.code_btn = QPushButton("원작 코드·수치 보기")
        self.code_btn.clicked.connect(self.show_code)
        self.remove_btn = QPushButton("내 풀에서 제거")
        self.remove_btn.clicked.connect(self.remove)
        for button in (self.add_btn, self.apply_btn, self.code_btn, self.remove_btn):
            foot.addWidget(button)
        foot.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.close)
        foot.addWidget(close)
        root.addLayout(foot)
        self.show_card()

    # ---- 원본 · 프로젝트 열기 ----
    def open_game(self):
        import ingame
        folder = self.app.settings.get("sts2_path")
        if not folder or not (Path(folder) / "SlayTheSpire2.pck").is_file():
            folder = QFileDialog.getExistingDirectory(self, "SlayTheSpire2.pck가 있는 설치 폴더")
        if not folder:
            return
        try:
            self.assets = ingame.GameAssets(folder)
            groups = CLR.original_sources(self.assets)
            groups.update(CLR.item_sources(self.assets))
            if not groups:
                raise ValueError("원작 카드 목록을 찾을 수 없습니다.")
            for key, source in groups.items():
                self.sources["game:" + key] = source
            self.refresh_groups("game:" + ("ironclad" if "ironclad" in groups else next(iter(groups))))
        except Exception as exc:  # noqa: BLE001 - 사용자에게 그대로 보여 준다
            _warn(self, str(exc))

    def open_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "참고할 캐릭터 프로젝트 선택", "",
                                                "모드 메이커 프로젝트 (*.sts2mod.json *.json)")
        for path in paths:
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict) or not isinstance(raw.get("cards"), list):
                    raise ValueError("카드 목록이 있는 모드 메이커 프로젝트를 선택하세요.")
                project = IO._resolve_project_image_paths(M.normalize(raw), os.path.dirname(path))
                self.sources[path] = {"title": M.text(project["character"], "name", "ko") + " · " + Path(path).name,
                                      "cards": project["cards"], "project": project}
                self.refresh_groups(path)
            except Exception as exc:  # noqa: BLE001
                _warn(self, f"{path}\n{exc}")

    def refresh_groups(self, selected):
        keys = list(self.sources)
        self.groups.blockSignals(True)
        self.groups.clear()
        for key in keys:
            self.groups.addItem(self.sources[key]["title"])
        self.groups.setCurrentRow(keys.index(selected))
        self.groups.blockSignals(False)
        self.refresh_cards()

    def source(self):
        row = self.groups.currentRow()
        values = list(self.sources.values())
        return values[row] if 0 <= row < len(values) else {}

    def refresh_cards(self):
        query = self.search.text().strip().casefold()
        self.rows = [c for c in self.source().get("cards", [])
                     if any(query in str(c.get(k, "")).casefold() for k in ("id", "name_ko", "name_en", "name_zh"))]
        self.cards.blockSignals(True)
        self.cards.clear()
        for card in self.rows:
            self.cards.addItem(M.text(card, "name", "ko") or card["id"])
        self.cards.blockSignals(False)
        if self.rows:
            self.cards.setCurrentRow(0)
        self.show_card()

    def selection(self):
        row = self.cards.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def show_card(self):
        card, source = self.selection(), self.source()
        lines = []
        imported = False
        self.art.clear()
        if card:
            lines = [M.text(card, "name", "ko") + "  ·  " + card["id"]]
            for lang in ("ko", "en", "zh"):
                desc = self._description(card, source, lang)
                lines.append(f"{M.text(card, 'name', lang)}\n{desc}")
            self._show_art(card, source)
            imported = bool(source.get("game")) and card["id"] in \
                self.app.project["character"].get("game_" + source.get("kind", "cards"), {})
        self.info.setPlainText("\n\n".join(lines))
        kind = source.get("kind", "cards")
        self.add_btn.setEnabled(bool(card) and (not imported or kind == "cards"))
        self.add_btn.setText("＋ 새 카드로 가져오기" if kind == "cards" else "프로젝트에 추가")
        current = self._current_card()
        name = M.text(current, "name", "ko") if current else ""
        can_apply = bool(card) and bool(current) and (not source.get("game") or kind == "card_keywords")
        self.apply_btn.setEnabled(can_apply)
        if kind == "card_keywords":
            self.apply_btn.setText(f"‘{name}’에 키워드 적용")
        else:
            self.apply_btn.setText(f"‘{name}’에 덮어쓰기…" if name else "덮어쓸 카드를 선택하세요")
        self.code_btn.setEnabled(bool(card) and bool(source.get("game")) and not kind and not self.reading)
        self.remove_btn.setEnabled(imported)

    def _description(self, card, source, lang):
        if source.get("game"):
            desc = card.get("desc_" + lang, "")
            if "raw_vars" in card:
                desc = PV.fill_values({}, desc, card, self.upgraded.isChecked())
            return desc
        p = source["project"]
        return PV.fill_values(p, M.description(p, card, "card", lang), card, self.upgraded.isChecked())

    def _show_art(self, card, source):
        try:
            pm = None
            if source.get("game") and card.get("portrait") and self.assets is not None:
                pic = self.assets.texture(card["portrait"]).copy()
                pic.thumbnail(IMAGE_BOX)
                pm = PQ._qpixmap(pic)
            elif card.get("image"):
                pm = PQ.pixmap(card["image"], IMAGE_BOX[0], IMAGE_BOX[1], "contain")
            if isinstance(pm, QPixmap) and not pm.isNull():
                self.art.setPixmap(pm)
        except (ImportError, OSError, ValueError, KeyError, AttributeError):
            pass

    def _current_card(self):
        tab = self.card_page
        return tab.items[tab.cur] if tab.cur is not None and tab.cur < len(tab.items) else None

    # ---- 가져오기 · 적용 · 제거 ----
    def apply_keyword(self, selected):
        tab = self.card_page
        card = self._current_card()
        if card is None or not selected:
            _info(self, "카드 탭에서 적용할 카드를 먼저 선택하세요.")
            return
        keyword = M.pascal(selected["id"].lower())
        if keyword not in card["keywords"]:
            card["keywords"].append(keyword)
            self.app.mark_dirty()
            tab.refresh_list(tab.cur)
        self.status.setText(f"{M.text(card, 'name', 'ko')}에 적용됨")

    def apply_selected(self, card=None, source=None):
        card = card or self.selection()
        source = source or self.source()
        tab = self.card_page
        if not card:
            return False
        if source.get("game") and source.get("kind", "cards") == "cards":
            return self.add(card, source)
        if tab.cur is None or tab.cur >= len(tab.items):
            _info(self, "카드 탭에서 적용할 카드를 먼저 선택하세요.")
            return False
        if source.get("kind") == "card_keywords":
            self.apply_keyword(card)
            return True
        if source.get("game"):
            return False
        if not _ask(self, "현재 카드의 내용과 효과를 선택한 카드로 바꿀까요?\n카드 ID와 전용 캐릭터 설정은 유지됩니다."):
            return False
        index = tab.cur
        old = tab.items[index]
        try:
            project = CLR.import_project_card(self.app.project, source["project"], card, all_ids(self.app.project))
        except ValueError as exc:
            _warn(self, str(exc))
            return False
        replacement = project["cards"].pop()
        imported_id = replacement["id"]
        CLR.rename_refs(replacement, imported_id, old["id"])
        replacement["id"] = old["id"]
        replacement["pool_character"] = old.get("pool_character", "")
        project["cards"][index] = replacement
        self.app.project = project
        self.app.mark_dirty()
        self.app.load_all()
        tab.refresh_list(index)
        self.status.setText(f"{M.text(replacement, 'name', 'ko')}을(를) 편집 중인 카드에 적용했습니다.")
        return True

    def add(self, card=None, source=None):
        card, source = card or self.selection(), source or self.source()
        if not card:
            return False
        if source.get("game") and source.get("kind", "cards") == "cards":
            return self.import_game_copy(card)
        if source.get("game"):
            ch = self.app.project["character"]
            kind = source.get("kind", "cards")
            if kind in ("cards", "relics", "potions") and not ch.get("enabled"):
                _info(self, "캐릭터 탭에서 새 캐릭터 만들기를 켜면 원작 카드를 풀에 추가할 수 있습니다.")
                return False
            ch.setdefault("game_" + kind, {})[card["id"]] = dict(card) if kind in ("powers", "card_keywords") \
                else M.text(card, "name", "ko")
        else:
            try:
                self.app.project = CLR.import_project_card(self.app.project, source["project"], card,
                                                           all_ids(self.app.project))
            except ValueError as exc:
                _warn(self, str(exc))
                return False
        self.app.mark_dirty()
        self.app.load_all()
        if not source.get("game"):
            tab = self.card_page
            index = len(self.app.project["cards"]) - 1
            tab.search.setText("")
            tab.refresh_list(index)
        self.status.setText(f"{M.text(card, 'name', 'ko')} 추가됨")
        self.show_card()
        return True

    def import_game_copy(self, card):
        if self.reading:
            self.status.setText("원작 코드를 읽는 중입니다.")
            return False
        project = self.app.project
        folder = self.assets.sts2_path
        self.reading = True
        self.status.setText("원작 카드 효과를 가져오는 중…")

        def work():
            try:
                code, _ = CLR.read_original_code(folder, card["id"])
                self.run_on_ui.emit(lambda: self._finish_game_copy(project, card, code, None))
            except Exception as exc:  # noqa: BLE001
                self.run_on_ui.emit(lambda: self._finish_game_copy(project, card, None, exc))
        threading.Thread(target=work, daemon=True).start()
        return True

    def _finish_game_copy(self, project, card, code, exc):
        self.reading = False
        if exc is not None:
            self._original_error(card, exc)
            return
        try:
            if self.app.project is not project:
                raise ValueError("프로젝트가 변경되었습니다. 카드를 다시 가져오세요.")
            em = MI.ExtMod()
            em.classes = {c.name: c for c in MI.parse_cs(code)}
            MI._extract_items(em)
            item = next((it for it in em.items["card"] if it["class"] == M.pascal(card["id"].lower())), None)
            if item is None:
                raise ValueError("원작 카드의 기본 클래스와 효과를 확인할 수 없습니다.")
            item.update({k: v for k, v in card.items() if k.startswith(("name_", "desc_"))})
            copy_card = MI.clone_item(em, item, project)
            copy_card["clone"]["game_original"] = True
            self.add(copy_card, {"project": {"cards": [copy_card]}})
        except Exception as e:  # noqa: BLE001
            self._original_error(card, e)

    def remove(self):
        card = self.selection()
        if not card or not self.source().get("game"):
            return
        ch = self.app.project["character"]
        key = "game:" + card["id"]
        kind = self.source().get("kind", "cards")
        if kind == "powers" and any(key == val for val in CLR._strings(self.app.project)):
            _info(self, "이 파워를 사용하는 효과를 먼저 변경하세요.")
            return
        if kind == "relics" and key in ch["relics"]:
            if not _ask(self, "시작 유물에서도 제거할까요?"):
                return
            ch["relics"] = [v for v in ch["relics"] if v != key]
        if kind == "cards" and any(row["card"] == key for row in ch["deck"]):
            if not _ask(self, "시작 덱에서도 이 카드를 제거할까요?"):
                return
            ch["deck"] = [row for row in ch["deck"] if row["card"] != key]
        ch.get("game_" + kind, {}).pop(card["id"], None)
        self.app.mark_dirty()
        self.app.load_all()
        self.status.setText("내 카드 풀에서 제거했습니다.")
        self.show_card()

    # ---- 원작 코드 ----
    def _original_error(self, card, exc):
        detail = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(exc)).strip()
        if not detail:
            detail = "실패한 도구가 오류 설명을 반환하지 않았습니다. .NET SDK와 게임 설치 경로를 확인해 주세요."
        title = f"원작 카드 {card['id']} 읽기 실패"
        self.status.setText(f"{title} · {detail.splitlines()[0][:80]}")
        self.app.log(f"[오류] {title} ({type(exc).__name__})\n{detail}")
        _warn(self, f"{title}\n\n{type(exc).__name__}\n{detail}")

    def show_code(self):
        card = self.selection()
        if not card or not self.source().get("game") or self.reading:
            return
        if "_source" in card:
            self._display_code(card)
            return
        self.reading = True
        self.status.setText("원작 카드 코드를 읽는 중…")
        folder = self.assets.sts2_path

        def work():
            try:
                code, raw = CLR.read_original_code(folder, card["id"], self.app.log)
                self.run_on_ui.emit(lambda: self._code_ready(card, code, raw, None))
            except Exception as exc:  # noqa: BLE001
                self.run_on_ui.emit(lambda: self._code_ready(card, None, None, exc))
        threading.Thread(target=work, daemon=True).start()

    def _code_ready(self, card, code, raw, exc):
        self.reading = False
        if exc is not None:
            self._original_error(card, exc)
        else:
            card["_source"], card["raw_vars"] = code, raw
            self._display_code(card)
            self.status.setText("원작 수치를 설명에 반영했습니다.")
        self.show_card()

    def _display_code(self, card):
        dialog = QDialog(self)
        dialog.setWindowTitle((M.text(card, "name", "ko") or card["id"]) + " · 원작 코드")
        dialog.resize(900, 640)
        col = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setStyleSheet("font-family: Consolas;")
        view.setPlainText(card["_source"])
        col.addWidget(view)
        dialog.show()
        self._code_dialogs = getattr(self, "_code_dialogs", []) + [dialog]
