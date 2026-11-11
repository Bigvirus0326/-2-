import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import blockcode as B
import modgen as M


class CompoundConditionsTests(unittest.TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project['cards'][0]
        self.weak = {'t':'has', 'who':'it', 'power':'Weak'}
        self.half = {'t':'hp_percent', 'who':'it', 'op':'<=', 'value':{'t':'num','v':50}}

    def compile(self, blocks):
        before = copy.deepcopy(blocks)
        lines, errors = B.compile_blocks(blocks, self.project, M._Ctx('card',self.card))
        self.assertEqual(errors, [])
        self.assertEqual(blocks, before)
        return '\n'.join(lines)

    def group(self, mode='all', items=None):
        return {'t':'group','mode':mode,'items':items if items is not None else [self.weak,self.half]}

    def test_enemy_all_any_are_inside_candidate_filter_before_random_selection(self):
        b = B.new_block('filtered_enemies')
        b['args'].update(power='removed_legacy_power', conditions=self.group())
        b['body'] = [B.new_block('no_effect')]
        code = self.compile([b])
        predicate = code[code.index('.Where('):code.index('.ToList()')]
        self.assertIn('enemy?.GetPowerAmount', predicate)
        self.assertIn('enemy.CurrentHp', predicate)
        self.assertIn(' * 100m <= ', predicate)
        self.assertIn(' && ', predicate)
        self.assertNotIn(' || ', predicate)
        self.assertLess(code.index('50m'),code.index('NextItem'))
        b['args']['conditions']['mode'] = 'any'
        self.assertIn(' || ', self.compile([b]))
        self.assertIn('또는',B.describe([b],self.project,'card'))

    def test_candidate_card_conditions_work_with_manual_and_random_selection(self):
        items = [{'t':'card_is','card':'picked','filter':'Attack'},
                 {'t':'not','a':{'t':'card_is','card':'picked','filter':'upgraded'}}]
        for mode in ('pick_each','random_each'):
            b = B.new_block(mode)
            b['args']['conditions'] = self.group(items=items)
            code = self.compile([b])
            self.assertIn('.Type == CardType.Attack',code)
            self.assertIn('.IsUpgraded',code)
            self.assertNotIn('this.Type',code)

    def test_player_selection_filters_player_creatures_and_syncs_manual_choice(self):
        b = B.new_block('filtered_players')
        b['args'].update(conditions=self.group(),enemy_mode='choose')
        action = B.new_block('energy_to')
        action['args']['player'] = '@selected_player'
        b['body'] = [action]
        code = self.compile([b])
        self.assertIn('.PlayerCreatures.Where',code)
        self.assertIn('enemy.IsAlive',code)
        self.assertIn('TargetType.AnyAlly',code)
        self.assertNotIn('TargetType.AnyEnemy',code)
        self.assertIn('?.Player is { } selectedPlayer',code)
        self.assertIn('WaitForRemoteChoice',code)

    def test_deck_presence_can_test_exact_card_or_keyword_in_other_player_deck(self):
        c = {'t':'pile_count','who':'it','pile':'Deck','card_id':self.card['id'],
             'filter':'Any','op':'>=','count':{'t':'num','v':1}}
        b = B.new_block('filtered_players')
        b['args']['conditions'] = self.group(items=[c])
        code = self.compile([b])
        self.assertIn('(enemy)?.Player is { }',code)
        self.assertIn('PileType.Deck.GetPile',code)
        self.assertIn(' is '+M.item_cls(self.project,'card',self.card),code)
        c.update(card_id='',filter='kw:Retain',pile='Hand')
        code = self.compile([b])
        self.assertIn('PileType.Hand.GetPile',code)
        self.assertIn('CardKeyword.Retain',code)

    def test_general_if_supports_deck_condition_and_nested_groups(self):
        b = B.new_block('if')
        deck = {'t':'pile_count','who':'self','pile':'Deck','filter':'Attack','card_id':'',
                'op':'>=','count':{'t':'var','name':'limit'}}
        b['args']['cond'] = self.group(items=[deck,self.group('any',[])])
        code = self.compile([b])
        self.assertIn('decimal v_limit',code)
        self.assertIn('PileType.Deck.GetPile',code)
        self.assertIn('&& true',code)

    def test_legacy_condition_seed_and_empty_group(self):
        b = B.new_block('filtered_enemies')
        group = B.selection_condition(b)
        self.assertEqual(group['items'][0],self.weak)
        b['args'].update(enemy_filter='hp_below',limit={'t':'num','v':50})
        self.assertEqual(B.selection_condition(b)['items'][0],self.half)
        b['args'].update(enemy_filter='all',conditions=self.group(items=[]))
        self.assertNotIn('GetPowerAmount',self.compile([b]))

    def test_invalid_group_and_missing_card_are_reported(self):
        for condition in (self.group('invalid'), {'t':'card_identity','card_id':'missing'},
                          {'t':'pile_count','pile':'invalid','card_id':'','count':{'t':'num','v':1}}):
            b = B.new_block('if')
            b['args']['cond'] = condition
            _,errors = B.compile_blocks([b],self.project,M._Ctx('card',self.card))
            self.assertTrue(errors)

    @unittest.skipUnless(shutil.which('dotnet'), 'dotnet SDK required')
    def test_generated_predicates_execute_all_any_nested_and_boundary_cases(self):
        generator = B._Gen(self.project,M._Ctx('card',self.card))
        generator.its.append('candidate')
        all_expr = generator.cond(self.group())
        any_expr = generator.cond(self.group('any'))
        nested = generator.cond(self.group(items=[self.group('any'),{'t':'not','a':self.weak}]))
        self.assertEqual(generator.errors,[])
        program = '''
using System;
class Enemy {
 public int CurrentHp, MaxHp=100, Weak;
 public int GetPowerAmount<T>() => Weak;
}
namespace MegaCrit.Sts2.Core.Models.Powers { public class WeakPower {} }
class Program {
 static bool All(Enemy? candidate) => ALL_EXPR;
 static bool Any(Enemy? candidate) => ANY_EXPR;
 static bool Nested(Enemy? candidate) => NESTED_EXPR;
 static void Check(bool x) { if(!x) throw new Exception("predicate mismatch"); }
 static void Main() {
  Check(All(new Enemy {Weak=1,CurrentHp=50}));
  Check(!All(new Enemy {Weak=1,CurrentHp=51}));
  Check(!All(new Enemy {Weak=0,CurrentHp=20}));
  Check(Any(new Enemy {Weak=1,CurrentHp=80}));
  Check(Any(new Enemy {Weak=0,CurrentHp=20}));
  Check(!Any(new Enemy {Weak=0,CurrentHp=80}));
  Check(!All(null) && !Any(null));
  Check(!Any(new Enemy {Weak=0,CurrentHp=0,MaxHp=0}));
  Check(Nested(new Enemy {Weak=0,CurrentHp=20}));
  Check(!Nested(new Enemy {Weak=1,CurrentHp=20}));
  Console.WriteLine("compound predicates OK");
 }
}
'''.replace('ALL_EXPR',all_expr).replace('ANY_EXPR',any_expr).replace('NESTED_EXPR',nested)
        with tempfile.TemporaryDirectory(prefix='sts2-conditions-') as folder:
            root=Path(folder)
            (root/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net9.0</TargetFramework><Nullable>enable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>',encoding='utf-8')
            (root/'Program.cs').write_text(program,encoding='utf-8')
            result=subprocess.run(['dotnet','run','--project',str(root/'Probe.csproj'),'--verbosity','quiet'],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('compound predicates OK',result.stdout)


if __name__ == '__main__':
    unittest.main()
