import copy
import unittest

import blockcode as B
import blockfamilies as F
import modgen as M


class EnemySelectionTests(unittest.TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project['cards'][0]
        self.block = B.new_block('filtered_enemies')
        hit = B.new_block('damage')
        hit['args']['who'] = 'it'
        self.block['body'] = [hit]

    def compile(self, blocks=None):
        lines, errors = B.compile_blocks(blocks or [self.block], self.project, M._Ctx('card', self.card))
        self.assertEqual(errors, [])
        return '\n'.join(lines)

    def test_random_power_selection_filters_before_sampling_without_replacement(self):
        code = self.compile()
        self.assertIn('GetPowerAmount<global::MegaCrit.Sts2.Core.Models.Powers.WeakPower>() > 0', code)
        self.assertIn('.Remove(', code)
        self.assertIn('Math.Clamp((int)(2m), 0,', code)
        self.assertIn('CombatTargets.NextItem', code)
        self.assertLess(code.index('GetPowerAmount'), code.index('NextItem'))
        self.assertIn('약화', B.describe([self.block], self.project, 'card'))

    def test_manual_health_selection_uses_filtered_pool_and_synchronizes_choice(self):
        self.block['args'].update(enemy_filter='hp_below', enemy_mode='choose', count={'t':'num','v':1})
        code = self.compile()
        self.assertIn('(decimal)enemy.CurrentHp * 100m <= (decimal)enemy.MaxHp', code)
        self.assertIn('Math.Clamp(30m, 0m, 100m)', code)
        self.assertIn('enemy.MaxHp > 0', code)
        self.assertIn('StartTargeting(TargetType.AnyEnemy', code)
        self.assertIn('SyncLocalChoice', code)
        self.assertIn('WaitForRemoteChoice', code)
        self.assertIn('SignalPlayerChoiceEnded', code)
        self.assertIn('.Contains(targetNode.Entity)', code)
        self.assertIn('체력 30% 이하', B.describe([self.block], self.project, 'card'))

    def test_nested_manual_selections_have_distinct_local_names_and_restore_it(self):
        self.block['args']['enemy_mode'] = 'choose'
        nested = copy.deepcopy(self.block)
        self.block['body'].insert(0, nested)
        code = self.compile()
        names = [line.strip().split(' = ')[0].split()[-1] for line in code.splitlines()
                 if ' = new global::System.Collections.Generic.List<int>();' in line]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)
        self.assertEqual(code.count('StartTargeting(TargetType.AnyEnemy'), 2)

    def test_family_switch_preserves_condition_and_legacy_behaviour(self):
        block = B.new_block('select_enemies')
        F.switch(block, 'filtered_enemies', B.SPECS)
        block['args']['limit'] = {'t':'num','v':20}
        F.switch(block, 'each_enemy', B.SPECS)
        self.assertNotIn('GetPowerAmount', self.compile([block]))
        F.switch(block, 'filtered_enemies', B.SPECS)
        self.assertEqual(block['args']['limit']['v'], 20)
        self.assertIn('{power}', B.block_caption(block))
        block['args']['enemy_filter'] = 'hp_below'
        self.assertNotIn('{power}', B.block_caption(block))
        self.assertIn('{limit}', B.block_caption(block))

    def test_no_power_health_above_and_all_modes(self):
        self.block['args'].update(enemy_filter='no_power', enemy_mode='all')
        code = self.compile()
        self.assertIn('GetPowerAmount<global::MegaCrit.Sts2.Core.Models.Powers.WeakPower>() <= 0', code)
        self.assertIn('.AddRange(', code)
        self.assertNotIn('NextItem', code)
        self.block['args']['enemy_filter'] = 'hp_above'
        self.assertIn('CurrentHp * 100m >=', self.compile())

    def test_invalid_condition_is_reported(self):
        self.block['args']['power'] = 'missing'
        _, errors = B.compile_blocks([self.block], self.project, M._Ctx('card', self.card))
        self.assertTrue(errors)


if __name__ == '__main__':
    unittest.main()
