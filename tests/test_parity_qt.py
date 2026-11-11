import copy
import json
import os
import shutil
import sys
import tempfile
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

import findcore as FC
import modgen as M
import projectops as PO

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)


class FindTests(TestCase):
    def test_initial_consonants_find_a_korean_name(self):
        self.assertTrue(FC.matches("ㅅㅂ", "수비"))
        self.assertFalse(FC.matches("ㅈㄱ", "수비"))

    def test_the_default_project_lists_its_cards(self):
        project = M.default_project()
        kinds = {kind for kind, *_rest in FC.all_entries(project)}
        self.assertIn("card", kinds)
        self.assertIn("character", kinds)


class MergeTests(TestCase):
    def test_a_second_project_is_added_and_clashing_ids_get_a_number(self):
        mine = M.default_project()
        other = copy.deepcopy(M.default_project())
        counts, renamed = PO.merge_into(mine, other)
        self.assertTrue(renamed)
        self.assertEqual(counts["cards"], len(other["cards"]))
        ids = [c["id"] for c in mine["cards"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("합쳤습니다", PO.merge_summary(counts, renamed))

    def test_a_project_with_new_ids_only_adds_the_items(self):
        mine = M.default_project()
        other = M.default_project()
        for key in ("cards", "relics", "potions", "powers"):
            for it in other[key]:
                it["id"] = "other_" + it["id"]
        counts, renamed = PO.merge_into(mine, other)
        self.assertFalse(renamed)
        self.assertEqual(counts["relics"], len(other["relics"]))


class PackAssetsTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pack_test_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_a_picture_is_copied_into_the_assets_folder_and_the_path_becomes_relative_to_it(self):
        picture = os.path.join(self.dir, "art.png")
        with open(picture, "wb") as f:
            f.write(b"not really a png, but the bytes are copied as they are")
        project = M.default_project()
        project["cards"][0]["image"] = picture
        sources, missing = PO.pack_plan(project)
        self.assertEqual(missing, [])
        project_path = os.path.join(self.dir, "mod.sts2mod.json")
        packed, count, created = PO.pack_assets(project, project_path, sources)
        self.assertEqual(count, 1)
        new_path = packed["cards"][0]["image"]
        self.assertTrue(os.path.isfile(new_path))
        self.assertTrue(new_path.startswith(os.path.join(self.dir, "assets")))
        self.assertEqual(project["cards"][0]["image"], picture)          # 원래 프로젝트는 바꾸지 않는다

    def test_a_missing_picture_is_reported_before_copying(self):
        project = M.default_project()
        project["cards"][0]["image"] = os.path.join(self.dir, "none.png")
        _sources, missing = PO.pack_plan(project)
        self.assertEqual(len(missing), 1)
