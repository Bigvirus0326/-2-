"""Execute the emitted expiry logic with small game-model substitutes."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import gimmick as G


@unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK required")
class CardNumberRuntimeTests(unittest.TestCase):
    def test_damage_expiration_stacking_and_independent_cards(self):
        source = r'''using System;
using System.Collections.Generic;
using System.Linq;
using MegaCrit.Sts2.Core.Models;
namespace MegaCrit.Sts2.Core.Localization.DynamicVars {
 public class DynamicVar { public decimal BaseValue {get;set;} }
 public class DamageVar : DynamicVar {}
 public class BlockVar : DynamicVar {}
 public class CardsVar : DynamicVar {}
 public class EnergyVar : DynamicVar {}
 public class HealVar : DynamicVar {}
 public class HpLossVar : DynamicVar {}
 public class MaxHpVar : DynamicVar {}
 public class GoldVar : DynamicVar {}
}
namespace MegaCrit.Sts2.Core.Models {
 public class CardModel {
  public event Action? Played;
  public Dictionary<string,MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar> DynamicVars = new();
  public void EndOfTurnCleanup() { }
  public void Play() => Played?.Invoke();
 }
}
namespace HarmonyLib {
 public class HarmonyPatch : Attribute { public HarmonyPatch(Type t,string name) {} }
 public class HarmonyPostfix : Attribute {}
}
''' + G.gen_card_number_runtime("Test") + r'''
public static class Program {
 static CardModel Card(decimal value) {
  var c = new CardModel(); c.DynamicVars["Damage"] = new MegaCrit.Sts2.Core.Localization.DynamicVars.DamageVar {BaseValue=value}; return c;
 }
 static void Check(CardModel c,decimal expected) {
  if (c.DynamicVars["Damage"].BaseValue != expected) throw new Exception($"Expected {expected}, got {c.DynamicVars["Damage"].BaseValue}");
 }
 public static void Main() {
  var a=Card(10); var b=Card(20);
  TestGimmicks.EditCardDamage(a,3,false,"combat"); Check(a,13); Check(b,20);
  TestGimmicks.EditCardDamage(a,5,false,"turn"); Check(a,18);
  TestGimmicks.EditCardDamage(a,2,false,"played"); Check(a,20);
  TestGimmicks.ExpireCardDamage(a,"turn"); Check(a,15);
  a.Play(); Check(a,13); a.Play(); Check(a,13);
  var c=Card(10);
  TestGimmicks.EditCardDamage(c,8,false,"turn");
  TestGimmicks.EditCardDamage(c,7,true,"combat"); Check(c,7);
  TestGimmicks.ExpireCardDamage(c,"turn"); Check(c,7);
  TestGimmicks.EditCardDamage(c,20,true,"played"); Check(c,20);
  c.Play(); Check(c,7);
  var d=Card(10);
  TestGimmicks.EditCardDamage(d,-30,false,"turn"); Check(d,0);
  TestGimmicks.ExpireCardDamage(d,"turn"); Check(d,10);
  TestGimmicks.EditCardDamage(d,3,false,"turn");
  d.DynamicVars["Damage"].BaseValue += 2; // unrelated upgrade survives expiry
  TestGimmicks.ExpireCardDamage(d,"turn"); Check(d,12);
  var empty=new CardModel(); TestGimmicks.EditCardDamage(empty,3,false,"turn"); empty.Play();
  TestGimmicks.EditCardDamage(b,5,false,"played"); Check(b,25);
  TestGimmicks.ExpireCardDamage(b,"turn"); Check(b,25); b.Play(); Check(b,20);
  var mixed=Card(6);
  mixed.DynamicVars["Block"] = new MegaCrit.Sts2.Core.Localization.DynamicVars.BlockVar {BaseValue=5};
  mixed.DynamicVars["Cards"] = new MegaCrit.Sts2.Core.Localization.DynamicVars.CardsVar {BaseValue=2};
  mixed.DynamicVars["Energy"] = new MegaCrit.Sts2.Core.Localization.DynamicVars.EnergyVar {BaseValue=1};
  mixed.DynamicVars["Custom"] = new MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar {BaseValue=99};
  TestGimmicks.EditCardNumber(mixed,"block",4,false,"turn");
  TestGimmicks.EditCardNumber(mixed,"draw",1,false,"played");
  TestGimmicks.EditCardNumber(mixed,"energy",3,true,"combat");
  if(mixed.DynamicVars["Block"].BaseValue!=9 || mixed.DynamicVars["Cards"].BaseValue!=3) throw new Exception("numeric edit");
  Check(mixed,6);
  mixed.Play();
  if(mixed.DynamicVars["Cards"].BaseValue!=2 || mixed.DynamicVars["Block"].BaseValue!=9) throw new Exception("separate expiry");
  TestGimmicks.ExpireCardDamage(mixed,"turn");
  if(mixed.DynamicVars["Block"].BaseValue!=5 || mixed.DynamicVars["Energy"].BaseValue!=3 || mixed.DynamicVars["Custom"].BaseValue!=99) throw new Exception("numeric expiry");
  Console.WriteLine("damage expiry OK");
 }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/"Probe.cs").write_text(source,encoding="utf-8")
            (folder/"Probe.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net9.0</TargetFramework><OutputType>Exe</OutputType><Nullable>enable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>')
            result=subprocess.run(["dotnet","run","--project",str(folder/"Probe.csproj"),"--verbosity","quiet"],capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode(errors="replace"))
            self.assertIn(b"damage expiry OK",result.stdout)
