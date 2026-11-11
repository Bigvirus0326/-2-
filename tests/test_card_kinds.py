import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import blockcode as B
import cardkind as K
import gimmick as G
import modgen as M


class CardKindTests(unittest.TestCase):
    def setUp(self):
        self.project = G.normalize(M.default_project())
        self.card = self.project["cards"][0]

    def test_native_curse_status_and_quest_generate(self):
        for native in ("Curse", "Status", "Quest"):
            K.apply(self.project, self.card, native)
            K.defaults_for_type(self.card)
            self.card["effects"] = []
            code = M.gen_card(self.project, self.card)
            self.assertIn("CardType." + native, code)
            self.assertIn(native, dict(B.CARD_TYPES))
            self.assertIn(native, dict(G.card_filters(self.project)))
            if native != "Quest":
                self.assertIn("CardRarity." + native, code)
                self.assertIn("CardKeyword.Unplayable", code)
                self.assertEqual(self.card["target"], "Self")

    def test_custom_kind_roundtrip_filter_tooltip_and_native_base(self):
        key = K.create(self.project, "폭발술", "Skill", "폭발술 카드의 설명")
        K.apply(self.project, self.card, key)
        self.project = G.normalize(json.loads(json.dumps(self.project)))
        self.card = self.project["cards"][0]
        self.assertEqual(K.selected(self.project, self.card), key)
        tid = key[5:]
        self.assertIn(("tag:" + tid, "#폭발술 카드"), G.card_filters(self.project))
        self.assertIn('card.Type == ' + K.runtime_class(self.project), G.filter_expr(self.project, "tag:" + tid, "card"))
        self.assertTrue(G.card_tips(self.project, self.card))
        code = M.gen_card(self.project, self.card)
        self.assertIn("CardType.Skill", code)
        self.assertNotIn("CardType.kind:", code)
        self.assertIn("public override CardType Type =>", code)
        self.assertNotIn("폭발술", G.card_prefix_text(self.project, self.card, "ko"))
        loc = M.gen_localization(self.project, "ko")
        tag = G.find_tag(self.project, tid)
        self.assertEqual(loc["gameplay_ui"][K.loc_key(self.project, tag)], "폭발술")
        runtime = K.gen_runtime(self.project)
        self.assertIn("[CustomEnum] public static CardType", runtime)
        self.assertIn("TypeNamePatch", runtime)
        for getter in ("FramePath", "PortraitBorderPath", "AncientTextBgPath"):
            self.assertIn('"' + getter + '", MethodType.Getter', runtime)
        self.assertFalse(G.validate(self.project)[0])

    def test_switch_kind_preserves_other_tags_and_defaults_are_explicit(self):
        self.project["gimmicks"]["tags"].append(G.new_tag("other"))
        self.card["gtags"] = ["other"]
        a = K.create(self.project, "분류 A", "Attack")
        b = K.create(self.project, "분류 B", "Power")
        K.apply(self.project, self.card, a)
        K.apply(self.project, self.card, b)
        self.assertEqual(self.card["gtags"], ["other", b[5:]])
        K.apply(self.project, self.card, "Curse")
        self.assertEqual(self.card["gtags"], ["other"])
        before = copy.deepcopy(self.card)
        K.selected(self.project, self.card)
        self.assertEqual(self.card, before)

    def test_create_rejects_empty_duplicate_and_invalid_base_without_mutating(self):
        for name, base in (("", "Skill"), ("공격", "Skill"), ("잘못된", "Fake")):
            before = copy.deepcopy(self.project)
            with self.assertRaises(ValueError):
                K.create(self.project, name, base)
            self.assertEqual(self.project, before)

    def test_imported_type_override_is_replaced_without_duplicate_override(self):
        key = K.create(self.project, "변형", "Power")
        K.apply(self.project, self.card, key)
        self.card["clone"] = {"body": "public override CardType Type => CardType.Attack;", "pool": "mine"}
        code = M.gen_card(self.project, self.card)
        self.assertEqual(code.count("public override CardType Type"), 1)
        self.assertIn("private CardType MakerOriginalType", code)

    @unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK required")
    def test_independent_identity_localized_label_and_safe_visual_fallback(self):
        first = K.create(self.project, "폭발술", "Power")
        K.apply(self.project, self.card, first)
        second = K.create(self.project, "주술", "Curse")
        mid = self.project["mod"]["id"]
        cls = mid + "CardKinds"
        one, two = M.pascal(first[5:]), M.pascal(second[5:])
        stub = r'''
using System;
using System.Reflection;
namespace BaseLib.Patches.Content { public class CustomEnumAttribute : Attribute {} }
namespace HarmonyLib {
 public enum MethodType { Getter }
 public class HarmonyPrefix : Attribute {}
 public class HarmonyPatch : Attribute {
  public HarmonyPatch(Type t,string s){} public HarmonyPatch(Type t,string s,MethodType m){} }
}
namespace MegaCrit.Sts2.Core.Entities.Cards {
 public enum CardType { None, Attack, Skill, Power, Status, Curse, Quest }
 public enum CardRarity { Common, Ancient }
 public static class CardTypeExtensions { public static void ToLocString(){} }
}
namespace MegaCrit.Sts2.Core.Localization {
 public class LocString(string table,string key) { public string Key=key; public string Table=table; }
}
namespace MegaCrit.Sts2.Core.Helpers { public static class ImageHelper { public static string GetImagePath(string s)=>"res://"+s; } }
namespace MegaCrit.Sts2.Core.Models {
 using MegaCrit.Sts2.Core.Entities.Cards;
 public class CardModel { public virtual CardType Type=>CardType.Skill; public CardRarity Rarity;
 public static string MissingPortraitPath=>"beta"; }
}
'''
        program = f'''
class Card : MegaCrit.Sts2.Core.Models.CardModel {{ {K.member(self.project, self.card)} }}
class Program {{
 static void Check(bool value) {{ if(!value) throw new Exception("Custom card kind regression"); }}
 static object[] Call(string name, params object[] args) {{
  var type=typeof({cls}).GetNestedType(name,BindingFlags.NonPublic)!;
  type.GetMethod("Prefix",BindingFlags.Static|BindingFlags.NonPublic)!.Invoke(null,args); return args;
 }}
 static void Main() {{
  {cls}.{one}=(CardType)1001; {cls}.{two}=(CardType)1002;
  var card=new Card();
  Check(card.Type!={cls}.{two} && card.Type!=CardType.Attack && card.Type!=CardType.Skill && card.Type!=CardType.Power);
  Check(card.Type=={cls}.{one});
  Check({cls}.TryVisualType(card.Type,out var visual) && visual==CardType.Power);
  Check(!{cls}.TryVisualType(CardType.Attack,out _));
  var label=(LocString)Call("TypeNamePatch",card.Type,null!)[1];
  Check(label.Key=="{K.loc_key(self.project, G.find_tag(self.project, first[5:]))}" && label.Table=="gameplay_ui");
  Check(((string)Call("FramePathPatch",card,"")[1]).EndsWith("card_frame_power_s.tres"));
  Check(((string)Call("PortraitBorderPathPatch",card,"")[1]).EndsWith("card_portrait_border_power_s.tres"));
  Check(((string)Call("AncientTextBgPathPatch",card,"")[1]).EndsWith("ancient_text_bg_power.png.tres"));
  card.Rarity=CardRarity.Ancient;
  Check((string)Call("FramePathPatch",card,"")[1]=="beta");
  Check({cls}.TryVisualType({cls}.{two},out visual) && visual==CardType.Curse);
  Console.WriteLine("custom types OK");
 }}
}}
'''
        usings = f"using {mid}.{mid}Code.Cards; using MegaCrit.Sts2.Core.Entities.Cards; using MegaCrit.Sts2.Core.Localization;\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"Kinds.cs").write_text(K.gen_runtime(self.project), encoding="utf-8")
            (root/"Program.cs").write_text(usings+stub+program, encoding="utf-8")
            (root/"Run.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net9.0</TargetFramework><OutputType>Exe</OutputType><Nullable>enable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>', encoding="utf-8")
            result = subprocess.run(["dotnet", "run", "--project", str(root/"Run.csproj"), "--verbosity", "quiet"], capture_output=True, encoding="utf-8", errors="replace", timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("custom types OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
