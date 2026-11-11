import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import modgen as M
import gimmick as G
import blockcode as B

@unittest.skipUnless(shutil.which("dotnet"), "dotnet SDK required")
class TagRuntimeTests(unittest.TestCase):
    def test_generated_counters_and_aura_restore_without_overwriting_cost(self):
        p = G.normalize(M.default_project())
        tag = G.new_tag("holder")
        tag.update(event_blocks={"hand_play": [B.new_block("energy")]}, played_every=3,
                   played_filter="kw:Exhaust", hand_cost_enabled=True, hand_cost_amount=1)
        tag["event_blocks"]["hand_aura"] = [
            {"op":"hand_aura_stat", "args":{"stat":stat,"filter":"kw:Exhaust","amount":{"t":"num","v":3}}}
            for stat in ("damage","block")]
        p["gimmicks"]["tags"] = [tag]
        turn = "\n".join(M.keyword_card_hooks(p, p["cards"][0])[0])
        tag["played_scope"] = "combat"
        combat = "\n".join(M.keyword_card_hooks(p, p["cards"][0])[0])
        tag["hand_cost_enabled"] = False
        tag["event_blocks"]["hand_aura"] = [
            {"op":"hand_aura_stat", "args":{"stat":stat,"active_pile":pile,"filter":"kw:Exhaust",
             "amount":{"t":"num","v":-n if stat=="cost" else n}}}
            for pile,n in (("Hand",1),("Draw",2),("Discard",3)) for stat in ("cost","damage","block")]
        pile_hooks="\n".join(M.keyword_card_hooks(p,p["cards"][0])[0])
        grant=B.new_block("aura_card_effect")
        grant["args"].update(active_pile="Discard",target_pile="Hand",filter="kw:Exhaust")
        energy=B.new_block("energy"); energy["args"]["amount"]={"t":"num","v":2}
        grant["body"]=[energy]
        tag["event_blocks"]["hand_aura"]=[grant]+[
            {"op":"hand_aura_stat","args":{"active_pile":"Discard","target_pile":"Hand","filter":"kw:Exhaust","stat":stat,"amount":{"t":"num","v":-2 if stat=="cost" else 4}}}
            for stat in ("cost","damage","block")]
        power_boost=B.new_block("aura_power_amount")
        power_boost["args"].update(active_pile="Discard",target_pile="Hand",filter="kw:Exhaust")
        tag["event_blocks"]["hand_aura"].append(power_boost)
        target_hooks="\n".join(M.keyword_card_hooks(p,p["cards"][0])[0])
        stubs = r'''using System; using System.Linq; using System.Collections.Generic; using System.Threading.Tasks;
public class AbstractModel {}
public class PowerModel {}
public class PlayerChoiceContext {}
public enum PileType { None, Hand, Draw, Discard, Play }
public static class PileTypeExtensions { public static Pile GetPile(this PileType type, Player p) => type == PileType.Hand ? p.PlayerCombatState.Hand : type == PileType.Draw ? p.PlayerCombatState.DrawPile : p.PlayerCombatState.DiscardPile; }
public enum CardKeyword { Exhaust }
[Flags] public enum ValueProp { Move=1 }
public class Combat { public int RoundNumber = 1; }
public class Creature { public bool IsDead; public Combat CombatState = new(); }
public class Pile { public PileType Type; public List<CardModel> Cards = new(); }
public class PlayerState { public Pile Hand = new(){Type=PileType.Hand}; public Pile DrawPile = new(){Type=PileType.Draw}; public Pile DiscardPile = new(){Type=PileType.Discard}; public Pile PlayPile = new(){Type=PileType.Play}; public List<CardModel> AllCards = new(); }
public class Player { public PlayerState PlayerCombatState = new(); public Creature Creature = new(); public decimal Energy; }
public class EnergyCost { public bool CostsX; }
public class CardPlay { public CardModel Card = null!; }
public class CardModel : AbstractModel {
 public Pile? Pile => new[]{Owner.PlayerCombatState.Hand,Owner.PlayerCombatState.DrawPile,Owner.PlayerCombatState.DiscardPile,Owner.PlayerCombatState.PlayPile}.FirstOrDefault(p=>p.Cards.Contains(this));
 public Player Owner = null!; public EnergyCost EnergyCost = new(); public HashSet<CardKeyword> Keywords = new();
 public bool Tagged = true; public int Notices;
 public virtual Task AfterCardPlayed(PlayerChoiceContext c, CardPlay p) => Task.CompletedTask;
 public virtual Task AfterCardChangedPiles(CardModel c, PileType p, AbstractModel? a) => Task.CompletedTask;
 public virtual bool TryModifyEnergyCostInCombat(CardModel c, decimal cost, out decimal value) {value=cost;return false;}
 public virtual decimal ModifyDamageAdditive(Creature? target, decimal amount, ValueProp props, Creature? dealer, CardModel? source, CardPlay? play) => 0m;
 public virtual decimal ModifyBlockAdditive(Creature target, decimal block, ValueProp props, CardModel? source, CardPlay? play) => 0m;
 public virtual decimal ModifyPowerAmountGivenAdditive(PowerModel power, Creature giver, decimal amount, Creature? target, CardModel? source) => 0m;
 public void InvokeEnergyCostChanged() { Notices++; }
}
public static class PlayerCmd { public static Task GainEnergy(decimal n, Player p) {p.Energy+=n;return Task.CompletedTask;} }
namespace MyMod.MyModCode.Gimmicks { public static class MyModGimmicks {public static bool HasTag(CardModel c,string id)=>c.Tagged;} }
'''
        main = r'''
public static class Program {
 static void Check(bool ok,string label) { if(!ok) throw new Exception(label); }
 public static async Task Main() {
  var player=new Player(); var holder=new TurnHolder {Owner=player}; var other=new CardModel {Owner=player};
  other.Keywords.Add(CardKeyword.Exhaust); player.PlayerCombatState.Hand.Cards.Add(holder);
  player.PlayerCombatState.AllCards.AddRange(new[]{holder,other}); var ctx=new PlayerChoiceContext();
  async Task Play(CardModel c) => await holder.AfterCardPlayed(ctx,new CardPlay{Card=c});
  await Play(holder); await Play(new CardModel{Owner=player}); await Play(new CardModel{Owner=new Player()});
  await Play(other); await Play(other); Check(player.Energy==0,"only matching own other cards count");
  await Play(other); Check(player.Energy==1,"third match fires");
  await Play(other); player.Creature.CombatState.RoundNumber++; await Play(other); await Play(other);
  Check(player.Energy==1,"turn resets partial count"); await Play(other); Check(player.Energy==2,"new turn threshold");
  Check(holder.TryModifyEnergyCostInCombat(other,2,out var value)&&value==1,"aura discount");
  holder.TryModifyEnergyCostInCombat(other,0,out value); Check(value==0,"floor zero");
  Check(!holder.TryModifyEnergyCostInCombat(holder,2,out value)&&value==2,"self excluded");
  other.EnergyCost.CostsX=true; Check(!holder.TryModifyEnergyCostInCombat(other,2,out value),"X excluded"); other.EnergyCost.CostsX=false;
  Check(holder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==3,"damage aura");
  Check(holder.ModifyBlockAdditive(player.Creature,5,ValueProp.Move,other,null)==3,"block aura");
  Check(holder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,holder,null)==0,"self damage excluded");
  var untagged=new CardModel{Owner=player};
  Check(holder.ModifyBlockAdditive(player.Creature,5,ValueProp.Move,untagged,null)==0,"keyword filter");
  player.PlayerCombatState.Hand.Cards.Clear(); await Play(other);
  Check(holder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==0,"damage restores on leave");
  Check(holder.ModifyBlockAdditive(player.Creature,5,ValueProp.Move,other,null)==0,"block restores on leave");
  Check(!holder.TryModifyEnergyCostInCombat(other,5,out value)&&value==5,"leaving hand restores unrelated cost");
  await holder.AfterCardChangedPiles(holder,PileType.Hand,null); Check(other.Notices==1,"refresh displayed costs");
  var second=new CombatHolder{Owner=player}; player.PlayerCombatState.Hand.Cards.Add(second);
  await second.AfterCardPlayed(ctx,new CardPlay{Card=other}); player.Creature.CombatState.RoundNumber++;
  await second.AfterCardPlayed(ctx,new CardPlay{Card=other}); await second.AfterCardPlayed(ctx,new CardPlay{Card=other});
  Check(player.Energy==3,"combat carries count across turns");
  await second.AfterCardPlayed(ctx,new CardPlay{Card=other}); player.Creature.CombatState=new Combat();
  await second.AfterCardPlayed(ctx,new CardPlay{Card=other}); await second.AfterCardPlayed(ctx,new CardPlay{Card=other});
  Check(player.Energy==3,"new combat resets count");
  var pileHolder=new PileHolder{Owner=player};
  void Put(PileType? pile) {
   player.PlayerCombatState.Hand.Cards.Clear(); player.PlayerCombatState.DrawPile.Cards.Clear(); player.PlayerCombatState.DiscardPile.Cards.Clear();
   if(pile.HasValue) pile.Value.GetPile(player).Cards.Add(pileHolder);
  }
  foreach(var pair in new[]{(PileType.Hand,1m),(PileType.Draw,2m),(PileType.Discard,3m)}) {
   Put(pair.Item1);
   Check(pileHolder.TryModifyEnergyCostInCombat(other,5,out value)&&value==5-pair.Item2,"cost switches by source pile");
   Check(pileHolder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==pair.Item2,"damage switches by source pile");
   Check(pileHolder.ModifyBlockAdditive(player.Creature,5,ValueProp.Move,other,null)==pair.Item2,"block switches by source pile");
  }
  Put(null);
  Check(!pileHolder.TryModifyEnergyCostInCombat(other,5,out value)&&value==5,"all cost rules released");
  Check(pileHolder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==0,"all damage rules released");
  Check(pileHolder.ModifyBlockAdditive(player.Creature,5,ValueProp.Move,other,null)==0,"all block rules released");
  var targetHolder=new TargetHolder{Owner=player}; player.PlayerCombatState.DiscardPile.Cards.Add(targetHolder);
  player.PlayerCombatState.Hand.Cards.Add(other);
  Check(targetHolder.TryModifyEnergyCostInCombat(other,5,out value)&&value==3,"discard source buffs hand cost");
  Check(targetHolder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==4,"discard source buffs hand damage");
  player.PlayerCombatState.Hand.Cards.Remove(other); player.PlayerCombatState.PlayPile.Cards.Add(other);
  await targetHolder.AfterCardChangedPiles(other,PileType.Hand,null);
  Check(targetHolder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==4,"hand-origin damage continues while playing");
  Check(targetHolder.ModifyPowerAmountGivenAdditive(new PowerModel(),player.Creature,1,player.Creature,other)==2,"existing power application gets plus two");
  Check(targetHolder.ModifyPowerAmountGivenAdditive(new PowerModel(),player.Creature,-1,player.Creature,other)==0,"power removals are not boosted");
  Check(targetHolder.ModifyPowerAmountGivenAdditive(new PowerModel(),player.Creature,1,player.Creature,targetHolder)==0,"saved source effect is not boosted twice");
  player.PlayerCombatState.PlayPile.Cards.Remove(other); player.PlayerCombatState.DiscardPile.Cards.Add(other);
  await targetHolder.AfterCardChangedPiles(other,PileType.Play,null);
  Check(targetHolder.ModifyDamageAdditive(null,6,ValueProp.Move,player.Creature,other,null)==0,"target pile restriction after play");
  decimal before=player.Energy; await targetHolder.AfterCardPlayed(ctx,new CardPlay{Card=other});
  Check(player.Energy==before+2,"stored effect runs for hand-origin matching card");
  player.PlayerCombatState.DiscardPile.Cards.Remove(targetHolder); player.PlayerCombatState.DrawPile.Cards.Add(targetHolder);
  await targetHolder.AfterCardPlayed(ctx,new CardPlay{Card=other});
  Check(player.Energy==before+2,"stored effect stops when source leaves selected pile");
 }
}
'''
        with tempfile.TemporaryDirectory(prefix="tag-runtime-") as temp:
            root = Path(temp)
            (root/"Program.cs").write_text(stubs+"class TurnHolder : CardModel {"+turn+"}\nclass CombatHolder : CardModel {"+combat+"}\nclass PileHolder : CardModel {"+pile_hooks+"}\nclass TargetHolder : CardModel {"+target_hooks+"}\n"+main, encoding="utf-8")
            (root/"Run.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net9.0</TargetFramework><OutputType>Exe</OutputType><Nullable>enable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>',encoding="utf-8")
            result = subprocess.run(["dotnet","run","--project",str(root/"Run.csproj"),"--verbosity","quiet"], capture_output=True,encoding="utf-8",errors="replace",timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
