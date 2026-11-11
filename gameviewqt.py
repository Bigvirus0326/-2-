"""'게임 화면' 그림 (Tk 의 game_image · thumb · ext_image 와 같다).

게임 파일로 합성한 화면을 보여 준다. 게임 파일이나 Pillow 가 없으면 간단한 그림으로 돌아간다.
도감·다른 모드처럼 칸이 많은 곳은 백그라운드 스레드에서 만들고, 끝나면 ready 신호로 다시 그린다.
"""
import json
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QWidget

import preview_qt as PQ

try:
    import ingame
except Exception:  # noqa: BLE001 - Pillow 가 없으면 게임 화면은 끈다
    ingame = None

CACHE_LIMIT = 600


class GameViews(QObject):
    changed = Signal()     # 모드·스택 수가 바뀌었다 (그림 칸들이 다시 그린다)
    ready = Signal()       # 백그라운드에서 만든 그림이 생겼다

    def __init__(self, assets_fn, project_of, parent=None):
        super().__init__(parent)
        self.assets_fn = assets_fn          # 게임 파일 묶음을 돌려 준다 (없으면 None)
        self.project_of = project_of        # 지금 프로젝트를 돌려 준다
        self.mode = "game" if ingame else "simple"
        self.stacks = 3
        self._cache = {}
        self._pending = set()
        self._failed = set()                # 만들다 실패한 그림은 다시 만들지 않는다
        self._lock = threading.Lock()

    # ---- 설정 ----
    def set_mode(self, mode):
        if mode != self.mode and (mode == "simple" or ingame):
            self.mode = mode
            self.changed.emit()

    def set_stacks(self, value):
        value = max(1, int(value))
        if value != self.stacks:
            self.stacks = value
            self.changed.emit()

    def available(self):
        return self.mode == "game" and ingame is not None

    def version(self):
        assets = self.assets_fn()
        return assets.version if assets else "?"

    # ---- 만들기 ----
    def image(self, kind, item, lang, upgraded, stacks):
        """(PIL 이미지 또는 None, 오류 글 또는 None). 같은 입력이면 저장해 둔 것을 쓴다."""
        if ingame is None:
            return None, "Pillow 가 설치되어 있지 않습니다 (pip install pillow)."
        assets = self.assets_fn()
        if assets is None:
            return None, ingame.last_error() or "게임 파일을 찾지 못했습니다."
        project = self.project_of()
        ch = project["character"]
        ch_key = {k: ch.get(k) for k in ("enabled", "color", "placeholder", "card_h", "card_s", "card_v",
                                         "energy_icon_image", "energy_text_icon_image", "frame_style")}
        try:
            key = json.dumps([kind, item, lang, upgraded, stacks, ch_key, project.get("powers", []),
                              project.get("card_frames", []) if kind == "card" else None,
                              project.get("gimmicks", {})], sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            key = None
        if key and key in self._cache:
            return self._cache[key], None
        try:
            img = ingame.compose(assets, project, kind, item, lang, upgraded, stacks)
        except Exception as e:  # noqa: BLE001 - 그림 하나가 실패해도 화면은 계속 그린다
            return None, str(e)
        if key:
            self._store(key, img)
        return img, None

    def lookup(self, key, make):
        """저장해 둔 그림을 바로 돌려 준다. 없으면 None 을 돌려 주고, 백그라운드에서 make() 로 만든다."""
        if key in self._cache:
            return self._cache[key]
        with self._lock:
            if key in self._pending or key in self._failed:
                return None
            self._pending.add(key)

        def work():
            try:
                img = make()
            except Exception:  # noqa: BLE001
                img = None
            with self._lock:
                self._pending.discard(key)
                if img is None:
                    self._failed.add(key)
            if img is not None:
                self._store(key, img)
            try:
                self.ready.emit()
            except RuntimeError:            # 창을 닫아 이 객체가 지워졌다: 더 그릴 것이 없다
                pass

        threading.Thread(target=work, daemon=True).start()
        return None

    def _store(self, key, img):
        with self._lock:
            if len(self._cache) > CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = img

    def pixmap(self, img):
        return PQ._qpixmap(img)

    def ext_image(self, em, kind, item, lang, upgraded):
        """다른 모드 항목의 게임 화면. 없으면 None (그 사이 백그라운드에서 만든다)."""
        import modimport as MI
        if not self.available() or self.assets_fn() is None:
            return None
        key = ("ext", em.root, kind, item.get("class"), lang, upgraded, self.stacks)

        def make():
            return ingame.compose(self.assets_fn(), self.project_of(), kind, MI.preview_item(em, item), lang, upgraded, self.stacks)
        return self.lookup(key, make)

    def thumb(self, key, make_item, kind, lang, upgraded, stacks, w, h):
        """도감의 칸 그림: 크기 w×h 에 맞춘다. key 가 같으면 저장해 둔 것을 쓴다."""
        if not self.available():
            return None
        full = ("thumb", key, kind, lang, upgraded, stacks, int(w), int(h))

        def make():
            k = 2                                  # 항상 크게 그려 두고 줄인다 (작게 그린 것을 키우면 흐려진다)
            img = ingame.compose(self.assets_fn(), self.project_of(), kind, make_item(), lang, upgraded, stacks, k=k)
            scale = min(w / img.size[0], h / img.size[1])
            return img.resize((max(1, int(img.size[0] * scale)), max(1, int(img.size[1] * scale))), ingame.Image.LANCZOS)
        return self.lookup(full, make)


class GameModeBar(QWidget):
    """'게임 화면 / 간단히' 고르기. 같은 설정을 도감·다른 모드·항목 미리보기가 함께 쓴다."""

    def __init__(self, views, parent=None):
        super().__init__(parent)
        self.views = views
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.game = QRadioButton("게임 화면")
        self.simple = QRadioButton("간단히")
        group = QButtonGroup(self)
        for button in (self.game, self.simple):
            group.addButton(button)
            row.addWidget(button)
        self.game.setEnabled(ingame is not None)
        self.game.toggled.connect(lambda on: on and views.set_mode("game"))
        self.simple.toggled.connect(lambda on: on and views.set_mode("simple"))
        views.changed.connect(self._sync)
        self._sync()

    def _sync(self):
        for button in (self.game, self.simple):
            button.blockSignals(True)
        self.game.setChecked(self.views.mode == "game")
        self.simple.setChecked(self.views.mode != "game")
        for button in (self.game, self.simple):
            button.blockSignals(False)
