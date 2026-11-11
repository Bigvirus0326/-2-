"""줄바꿈하는 가로 배치 (Qt 의 FlowLayout 예제와 같은 방식).

블록 한 줄을 문장처럼 놓는다. 칸이 길면 다음 줄로 넘어간다.
"""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy


class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._space = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), dry_run=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, dry_run=False)

    def sizeHint(self):
        # 지금 너비에서 필요한 높이 (칸이 줄을 넘기면 그만큼 높다)
        parent = self.parentWidget()
        width = parent.width() if parent is not None and parent.width() > 0 else 400
        return QSize(width, self.heightForWidth(width))

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _layout(self, rect, dry_run):
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        right = rect.right() - margins.right()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible() and not dry_run:
                continue
            size = item.sizeHint()
            next_x = x + size.width() + self._space
            if next_x - self._space > right and line_height > 0:
                x = rect.x() + margins.left()
                y += line_height + self._space
                next_x = x + size.width() + self._space
                line_height = 0
            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y), size))
            x = next_x
            line_height = max(line_height, size.height())
        return y + line_height - rect.y() + margins.bottom()
