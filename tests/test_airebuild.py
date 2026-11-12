import json
import os
import sys
from unittest import TestCase, skipUnless

import airebuild as AR
import modgen as M

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def _card_with_raw():
    project = M.default_project()
    card = project["cards"][0]
    card["effects"] = [dict(M.new_effect("code"), blocks=[
        {"op": "source_step", "args": {"source": "List<CardModel> list = PileType.Hand.GetPile(Owner).Cards.ToList();"}},
        {"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}])]
    return project, card


def _answer(card_id, blocks):
    body = {"format": "sts2mod-patch", "cards": [{"id": card_id, "effects": [{"kind": "code", "blocks": blocks}]}]}
    return "설명\n```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"


class AIRebuildTests(TestCase):
    def test_request_lists_direct_code_with_plain_explanation(self):
        project, card = _card_with_raw()
        parts = AR.direct_code_parts(project, "card", card)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][0], "카드 목록을 만듭니다.")
        text = AR.request_text(project, "card", card)
        self.assertIn(f'id "{card["id"]}"', text)
        self.assertIn("PileType.Hand", text)          # AI 가 읽을 원본 코드
        self.assertIn("블록만으로", text)

    def test_answer_replaces_only_effects(self):
        project, card = _card_with_raw()
        effects, notes = AR.apply_answer(project, "card", card, _answer(card["id"], [
            {"op": "draw", "args": {"amount": {"t": "num", "v": 2}}}]))
        self.assertIsNotNone(effects)
        self.assertEqual(notes, [])
        self.assertEqual(effects[0]["blocks"][0]["op"], "draw")

    def test_answer_for_another_item_is_refused(self):
        project, card = _card_with_raw()
        effects, notes = AR.apply_answer(project, "card", card, _answer("someone_else", []) + "\n" +
                                         _answer("other_two", []))
        self.assertIsNone(effects)

    def test_answer_that_still_uses_direct_code_is_flagged(self):
        project, card = _card_with_raw()
        effects, notes = AR.apply_answer(project, "card", card, _answer(card["id"], [
            {"op": "source_step", "args": {"source": "Foo();"}}]))
        self.assertTrue(any("직접 코드" in n for n in notes))


class AIRebuildBatchTests(TestCase):
    def setUp(self):
        self.project, self.card = _card_with_raw()
        self.second = self.project["cards"][1]
        self.second["effects"] = [dict(M.new_effect("code"), blocks=[{"op": "source_step", "args": {"source": "Foo();"}}])]

    def test_targets_and_request_cover_all_items_with_direct_code(self):
        pairs = AR.targets(self.project)
        self.assertEqual([it["id"] for _k, it in pairs], [self.card["id"], self.second["id"]])
        self.assertEqual(AR.targets(self.project, [self.second]), [("card", self.second)])
        text = AR.batch_request_text(self.project, pairs)
        self.assertIn(self.card["id"], text)
        self.assertIn("Foo();", text)

    def test_batch_answer_applies_good_items_and_reports_missing(self):
        pairs = AR.targets(self.project)
        found, notes = AR.apply_batch_answer(self.project, pairs, _answer(self.card["id"], [
            {"op": "draw", "args": {"amount": {"t": "num", "v": 2}}}]))
        self.assertEqual(list(found), [("card", self.card["id"])])
        self.assertTrue(any("답에 없습니다" in n for n in notes))


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class AIRebuildButtonTests(TestCase):
    def test_button_only_shows_when_direct_code_is_left(self):
        _app = QApplication.instance() or QApplication(sys.argv)
        import effectqt as E
        project, card = _card_with_raw()
        lst = E.EffectListQt("card", lambda: project, lambda: card, lambda: None)
        self.addCleanup(lst.close)
        lst.set(card["effects"])
        self.assertFalse(lst.ai_btn.isHidden())
        card["effects"][0]["blocks"] = [{"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}]
        lst.refresh()
        self.assertTrue(lst.ai_btn.isHidden())

    def test_batch_dialog_can_close(self):
        _app = QApplication.instance() or QApplication(sys.argv)
        import airebuildqt as R
        project, _card = _card_with_raw()
        dialog = R.BatchRebuildDialogQt(None, project, AR.targets(project))
        dialog.show()
        dialog.reject()   # 창 닫기 (X·닫기 버튼 모두 done() 을 거친다)
        self.assertFalse(dialog.isVisible())

    def test_batch_dialog_can_send_everything_at_once(self):
        _app = QApplication.instance() or QApplication(sys.argv)
        import airebuildqt as R
        project = M.default_project()
        for card in project["cards"]:
            card["effects"] = [dict(M.new_effect("code"), blocks=[{"op": "source_step", "args": {"source": "Foo();"}}])]
        pairs = AR.targets(project) * 3   # BATCH 보다 많게
        dialog = R.BatchRebuildDialogQt(None, project, pairs)
        self.addCleanup(dialog.close)
        self.assertGreater(len(dialog.groups), 1)
        dialog.all_at_once.setChecked(True)
        self.assertEqual([len(g) for g in dialog.groups], [len(pairs)])
        dialog.all_at_once.setChecked(False)
        self.assertEqual(sum(len(g) for g in dialog.groups), len(pairs))

    def test_batch_dialog_saves_group_as_md(self):
        import tempfile
        _app = QApplication.instance() or QApplication(sys.argv)
        import airebuildqt as R
        project, card = _card_with_raw()
        dialog = R.BatchRebuildDialogQt(None, project, AR.targets(project))
        self.addCleanup(dialog.close)
        path = os.path.join(tempfile.mkdtemp(), "req.md")
        dialog.save_request(path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(card["id"], text)
        self.assertIn("PileType.Hand", text)
        self.assertEqual(QApplication.clipboard().text(), AR.CHAT_MESSAGE)   # 파일과 함께 보낼 문장

    def test_batch_dialog_saves_every_group_as_its_own_md(self):
        import tempfile
        _app = QApplication.instance() or QApplication(sys.argv)
        import airebuildqt as R
        project = M.default_project()
        for card in project["cards"]:
            card["effects"] = [dict(M.new_effect("code"), blocks=[{"op": "source_step", "args": {"source": "Foo();"}}])]
        pairs = AR.targets(project) * 3
        dialog = R.BatchRebuildDialogQt(None, project, pairs)
        self.addCleanup(dialog.close)
        folder = tempfile.mkdtemp()
        dialog.save_all(folder)
        files = sorted(os.listdir(folder))
        self.assertEqual(len(files), len(dialog.groups))
        self.assertTrue(files[0].endswith(f"_01_of_{len(dialog.groups):02d}.md"))
