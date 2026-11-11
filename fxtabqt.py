"""'🎨 이펙트 · 버튼' 탭의 Qt 版 (두 개의 하위 탭: 이펙트 그리기, 전투 버튼).

app 에서 필요한 것: project, mark_dirty(), game_assets(), 그리고 선택적으로 ui(화면 배율).
"""
from PySide6.QtWidgets import QTabWidget

import fxrules as R
import gimmick as GM
from buttonqt import ButtonDesignerQt
from fxqt import EffectPainterQt
from gimmickqt import unique_gimmick_id


class FxTabQt(QTabWidget):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.z = max(1.0, min(1.6, getattr(app, "ui", 1.0)))
        R._ASSETS["get"] = app.game_assets     # 전투 화면 모형이 게임 그림을 쓸 때 부르는 곳
        self.painter = EffectPainterQt(self)
        self.buttons = ButtonDesignerQt(self)
        self.addTab(self.painter, "🎨 이펙트 그리기")
        self.addTab(self.buttons, "🔘 전투 버튼")

    @property
    def project(self):
        return self.app.project

    @property
    def g(self):
        """정규화는 비어 있을 때만 (매번 하면 편집 중인 참조가 끊긴다)."""
        g = self.app.project.get("gimmicks")
        if not isinstance(g, dict) or "effects" not in g or "buttons" not in g:
            GM.normalize(self.app.project)
        return self.app.project["gimmicks"]

    def load_project(self):
        self.painter.load()
        self.buttons.load()

    def dirty(self):
        self.app.mark_dirty()

    def unique(self, base):
        return unique_gimmick_id(self.app.project, base)
