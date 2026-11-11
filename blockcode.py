"""
블록 코딩 -> C# 변환.

프로그램 = 블록 목록. 블록 = {"op": 이름, "args": {...}, "body": [...], "else": [...]}
값(value) = {"t": "num"|"stack"|"stat"|"count"|"energy"|"amount"|"round"|"rand"|"var"|"op", ...}
조건(cond) = {"t": "cmp"|"chance"|"has"|"and"|"or"|"not", ...}

같은 블록이 카드 / 유물 / 물약 / 파워 어디에 있든 그 자리에 맞는 C# 를 만든다 (modgen._Ctx 이름 사용).
"""
from __future__ import annotations

import copy
import blockfamilies as F

# ---------------------------------------------------------------------------
# 블록 정의 (팔레트와 화면이 같이 쓴다)
# ---------------------------------------------------------------------------
CATS = {
    "action": ("행동", "#4c97ff"),
    "card": ("카드 조작", "#9966ff"),
    "flow": ("흐름", "#ffab19"),
    "var": ("변수", "#ff8c1a"),
    "gimmick": ("기믹 (소환·자원·선택)", "#d6457a"),
    "class": ("직업 시스템 (구체·별·골골이)", "#2a9d8f"),
    "fx": ("이펙트 · 버튼", "#e07a1f"),
}

# 템플릿의 {이름} 자리에 입력 칸이 들어간다.
SPECS = {
    "source_amount": {"cat":"action", "ko":"가져온 효과 수치 {amount}", "args":{"amount":("value", {"t":"num","v":1})}},
    "source_step": {"cat":"action", "ko":"직접 코드 {source}", "args":{"source":("source", "")}},
    "source_hit": {"cat":"action", "ko":"{target}에게 피해 {stat} · {hits}회", "args":{"target":("who_one","target"), "stat":("raw_stat","V0"), "hits":("int",1)}},
    "no_effect": {"cat": "flow", "ko": "사용 시 효과 없음", "args": {}},
    "original_play": {"cat": "action", "ko": "원본 카드 사용 효과 실행", "args": {}},
    # 네이티브 블록으로 바꾸지 못한 호출·반복 (csblocks). 칸 이름·종류는 블록마다 다르다.
    "src_call": {"cat": "action", "ko": "직접 호출", "args": {}},
    "src_loop": {"cat": "flow", "ko": "직접 반복 {head}", "args": {"head": ("code", "")}, "body": True},
    "damage": {"cat": "action", "ko": "{who}에게 피해 {amount}를 {hits}번  힘·약화 적용 {powered}",
               "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}),
                        "hits": ("int", 1), "powered": ("bool", True)}},
    "card_attack": {"cat": "action", "ko": "공격 {who}에게 {amount} 피해 · {hits}회 · 이펙트 {vfx} · 효과음 {sfx} · 추가 효과 인수 {fx_extra}",
                    "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}),
                             "hits": ("value", {"t": "num", "v": 1}), "vfx": ("code", ""), "sfx": ("code", ""),
                             "fx_extra": ("code", "")}},
    "block": {"cat": "action", "ko": "방어도 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "lose_block": {"cat": "action", "ko": "{who}의 방어도 {amount} 없애기",
                   "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 5})}},
    "draw": {"cat": "action", "ko": "카드 {amount}장 뽑기", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "energy": {"cat": "action", "ko": "에너지 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "energy_to": {"cat": "action", "ko": "플레이어 {player} 에너지 {amount} 얻기", "args": {"player": ("code", "Owner"), "amount": ("value", {"t": "num", "v": 1})}},
    "gold_to": {"cat": "action", "ko": "플레이어 {player} 골드 {amount} 얻기", "args": {"player": ("code", "Owner"), "amount": ("value", {"t": "num", "v": 10})}},
    "lose_block_to": {"cat": "action", "ko": "생물 {creature} 방어도 {amount} 없애기",
                      "args": {"creature": ("code", "target"), "amount": ("value", {"t": "num", "v": 5})}},
    "kill_creature": {"cat": "action", "ko": "생물 {creature} 처치", "args": {"creature": ("code", "target")}},
    "lose_gold": {"cat": "action", "ko": "플레이어 {player} 골드 {amount} 잃기 · 사유 {loss_type}",
                  "args": {"player": ("code", "Owner"), "amount": ("value", {"t": "num", "v": 5}),
                           "loss_type": ("code", "GoldLossType.Spent")}},
    "end_turn": {"cat": "action", "ko": "플레이어 {player} 턴 종료 · 취소 가능 {can_back_out}",
                 "args": {"player": ("code", "Owner"), "can_back_out": ("code", "false")}},
    "heal": {"cat": "action", "ko": "{who} 체력 {amount} 회복",
             "args": {"who": ("who_multi", "self"), "amount": ("value", {"t": "num", "v": 3})}},
    "lose_hp": {"cat": "action", "ko": "{who} 체력 {amount} 잃기 (방어도 무시)",
                "args": {"who": ("who_multi", "self"), "amount": ("value", {"t": "num", "v": 2})}},
    "max_hp": {"cat": "action", "ko": "최대 체력 {amount} 증가", "args": {"amount": ("value", {"t": "num", "v": 2})}},
    "gold": {"cat": "action", "ko": "골드 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 10})}},
    "apply_power": {"cat": "action", "ko": "{who}에게 {power} {amount} 부여 · 조용히 {silent}",
                    "args": {"who": ("who_multi", "target"), "power": ("power", "Weak"),
                             "amount": ("value", {"t": "num", "v": 1}), "silent": ("bool", False)}},
    "apply_power_to": {"cat": "action", "ko": "생물 {creature}에게 {power} {amount} 부여 · 조용히 {silent}",
                       "args": {"creature": ("code", "target"), "power": ("power", "Weak"),
                                "amount": ("value", {"t": "num", "v": 1}), "silent": ("bool", False)}},
    "apply_power_type": {"cat": "action", "ko": "생물 {creature}에게 파워 유형 {power_type} {amount} 부여 · 출처 {source}",
                         "args": {"creature": ("code", "target"), "power_type": ("code", "MegaCrit.Sts2.Core.Models.Powers.StrengthPower"),
                                  "amount": ("value", {"t": "num", "v": 1}), "source": ("code", "this"),
                                  "silent": ("bool", False)}},
    "power_apply_type": {"cat": "action", "ko": "PowerCmd · {creature}에게 파워 {power_type} {amount} 적용",
                         "args": {"creature": ("code", "target"), "power_type": ("code", "StrengthPower"),
                                  "amount": ("value", {"t": "num", "v": 1}), "applier": ("code", "Owner.Creature"),
                                  "source": ("code", "this")}},
    "power_apply_model": {"cat": "action", "ko": "PowerCmd · {power} 모델을 {creature}에게 {amount} 적용",
                          "args": {"power": ("code", "powerModel"), "creature": ("code", "target"),
                                   "amount": ("value", {"t": "num", "v": 1}), "applier": ("code", "Owner.Creature"),
                                   "source": ("code", "this")}},
    "block_to": {"cat": "action", "ko": "생물 {creature}에게 방어도 {amount} · 상태 효과 보정 {powered}",
                 "args": {"creature": ("code", "target"), "amount": ("value", {"t": "num", "v": 5}),
                          "powered": ("bool", True), "card_play": ("bool", True)}},
    "damage_to": {"cat": "action", "ko": "생물 {creature}에게 피해 {amount} · 힘 적용 {powered} · 방어도 무시 {unblockable}",
                  "args": {"creature": ("code", "target"), "amount": ("value", {"t": "num", "v": 6}),
                           "powered": ("bool", True), "unblockable": ("bool", False),
                           "attacker": ("code", ""), "source_card": ("code", ""), "card_play": ("code", ""),
                           "context": ("code", "choiceContext")}},
    "heal_to": {"cat": "action", "ko": "생물 {creature} 체력 {amount} 회복",
                "args": {"creature": ("code", "target"), "amount": ("value", {"t": "num", "v": 3})}},
    "remove_power": {"cat": "action", "ko": "{who}의 {power} {amount} 제거 (0 = 전부)",
                     "args": {"who": ("who_multi", "target"), "power": ("power", "Weak"),
                              "amount": ("value", {"t": "num", "v": 0})}},
    "remove_power_model": {"cat": "action", "ko": "파워 모델 {power} 제거", "args": {"power": ("code", "powerModel")}},
    "flash": {"cat": "action", "ko": "반짝임 표시 (유물·파워)", "args": {}},
    "hand": {"cat": "card", "ko": "손패의 {ctype} {which} {count}장 {action}",
             "args": {"ctype": ("card_filter", "Any"), "which": ("which", "random"),
                      "count": ("value", {"t": "num", "v": 1}), "action": ("hand_action", "upgrade")}},
    "keyword_this": {"cat": "card", "ko": "이 카드에 {keyword} {action}",
                     "args": {"keyword": ("keyword", "Retain"), "action": ("kw_action", "add")}},
    "keyword_cards": {"cat": "card", "ko": "{where}의 {ctype} {which} {count}장에 {keyword} {action}",
                      "args": {"where": ("kw_where", "hand"), "ctype": ("card_filter", "Any"), "which": ("which", "all"),
                               "count": ("value", {"t": "num", "v": 1}), "keyword": ("keyword", "Retain"),
                               "action": ("kw_action", "add")}},
    "add_card": {"cat": "card", "ko": "{card} {count}장을 {pile}에 만들기",
                 "args": {"card": ("card", "this"), "count": ("value", {"t": "num", "v": 1}), "pile": ("pile", "Hand")}},
    "card_exhaust": {"cat": "card", "ko": "카드 {card} 소멸 · 사용 중 {played} · 다른 효과 발동 {triggered}",
                     "args": {"card": ("code", "cardModel"), "played": ("bool", False), "triggered": ("bool", False)}},
    "card_upgrade": {"cat": "card", "ko": "카드 {card} 강화 · 강화 후 카드 표시 {style}",
                     "args": {"card": ("code", "cardModel"), "style": ("code", "")}},
    "card_autoplay": {"cat": "card", "ko": "카드 {card} 자동 사용 · 대상 {target} · 종류 {type} · X 저장 {skip_x} · 연출 생략 {skip_visuals}",
                      "args": {"card": ("code", "cardModel"), "target": ("code", "target"),
                               "type": ("code", "AutoPlayType.Default"), "skip_x": ("code", "false"),
                               "skip_visuals": ("code", "false")}},
    "card_discard": {"cat": "card", "ko": "카드 또는 목록 {cards} 버리기", "args": {"cards": ("code", "cards")}},
    "card_keyword": {"cat": "card", "ko": "카드 {card}에 {keyword} {action}",
                     "args": {"card": ("code", "cardModel"), "keyword": ("keyword", "Exhaust"),
                              "action": ("kw_action", "add")}},
    "card_add_keyword_model": {"cat": "card", "ko": "카드 모델 {card}에 키워드 식 {keyword} 추가",
                               "args": {"card": ("code", "cardModel"), "keyword": ("code", "CardKeyword.Exhaust")}},
    "card_add_generated": {"cat": "card", "ko": "생성 카드 {card}를 {pile}에 추가",
                            "args": {"card": ("code", "cardModel"), "pile": ("pile", "Hand")}},
    "card_add_pile": {"cat": "card", "ko": "카드 식 {cards}를 더미 {pile}에 추가 · 추가 인수 {extra}",
                      "args": {"cards": ("code", "cardModel"), "pile": ("code", "PileType.Hand"), "extra": ("code", "")}},
    "card_add_generated_many": {"cat": "card", "ko": "생성 카드 목록 {cards}를 {pile}에 추가 · 플레이어 {player} · 위치 {position}",
                                "args": {"cards": ("code", "cards"), "pile": ("code", "PileType.Hand"),
                                         "player": ("code", "Owner"), "position": ("code", "CardPilePosition.Random")}},
    "card_preview": {"cat": "card", "ko": "게임에서 카드 {cards} 보여주기 · 표시 시간 {scale}초 · 배치 {style}",
                     "args": {"cards": ("code", "cards"), "scale": ("value", {"t": "num", "v": 1}),
                              "style": ("code", "")}},
    "card_preview_cards": {"cat": "card", "ko": "게임에서 카드 {cards} 보여주기 · 표시 시간 {scale}초",
                            "args": {"cards": ("code", "cardModel"), "scale": ("code", "")}},
    "draw_to": {"cat": "card", "ko": "플레이어 {player} 카드 {amount}장 뽑기",
                "args": {"player": ("code", "Owner"), "amount": ("value", {"t": "num", "v": 1})}},
    "card_remove_combat": {"cat": "card", "ko": "전투에서 카드 {cards} 제거",
                            "args": {"cards": ("code", "cardModel")}},
    "shuffle_draw_pile": {"cat": "card", "ko": "플레이어 {player}의 뽑을 카드 더미 섞기",
                           "args": {"player": ("code", "Owner")}},
    "stun": {"cat": "action", "ko": "생물 또는 플레이어 {creature} 기절시키기",
             "args": {"creature": ("code", "target")}},
    "autoplay_draw_pile": {"cat": "card", "ko": "플레이어 {player}의 뽑을 카드 더미에서 자동 사용 · 장수 {count} · 위치 {position} · 소멸 {force_exhaust}",
                           "args": {"player": ("code", "Owner"), "count": ("value", {"t": "num", "v": 1}),
                                    "position": ("code", "CardPilePosition.Top"), "force_exhaust": ("code", "false")}},
    "potion_add_type": {"cat": "card", "ko": "물약 종류 {potion_type}를 플레이어 {player}에게 지급",
                         "args": {"potion_type": ("code", "Catalyst"), "player": ("code", "Owner")}},
    "potion_add_model": {"cat": "card", "ko": "물약 모델 {potion}을 플레이어 {player}에게 지급",
                          "args": {"potion": ("code", "potionModel"), "player": ("code", "Owner")}},
    "potion_add_model_at": {"cat": "card", "ko": "플레이어 {player}의 물약 슬롯 {slot}에 모델 {potion} 추가",
                             "args": {"potion": ("code", "potionModel"), "player": ("code", "Owner"), "slot": ("code", "potionSlotIndex")}},
    "potion_discard": {"cat": "card", "ko": "물약 {potion} 버리기", "args": {"potion": ("code", "potionModel")}},
    "card_set_cost_until_played": {"cat": "card", "ko": "카드 {card} 비용을 {amount}(으)로 사용 시까지 설정",
                                    "args": {"card": ("code", "cardModel"), "amount": ("value", {"t": "num", "v": 0})}},
    "card_free_this_turn": {"cat": "card", "ko": "카드 {card} 이번 턴 비용 무료",
                             "args": {"card": ("code", "cardModel")}},
    "card_notify_cost_changed": {"cat": "card", "ko": "카드 {card} 비용 변경 알림",
                                  "args": {"card": ("code", "cardModel")}},
    "card_upgrade_internal": {"cat": "card", "ko": "카드 {card} 강화 수치 적용 (직접 처리용)",
                               "args": {"card": ("code", "cardModel")}},
    "card_finalize_upgrade_internal": {"cat": "card", "ko": "카드 {card} 강화 처리 마무리 (직접 처리용)",
                                        "args": {"card": ("code", "cardModel")}},
    "card_transform_to": {"cat": "card", "ko": "카드 {card}를 카드 종류 {card_type}로 변환",
                          "args": {"card": ("code", "cardModel"), "card_type": ("code", "Strike")}},
    "modify_power_amount": {"cat": "action", "ko": "파워 {power} 수치 {amount}만큼 변경",
                             "args": {"power": ("code", "powerModel"), "amount": ("value", {"t": "num", "v": 1})}},
    "set_current_hp": {"cat": "action", "ko": "대상 {creature} 현재 체력을 {amount}로 설정",
                        "args": {"creature": ("code", "Owner.Creature"), "amount": ("value", {"t": "num", "v": 1})}},
    "orb_channel_model": {"cat": "class", "ko": "구체 모델 {orb} 영창", "args": {"orb": ("code", "orbModel.ToMutable()")}},
    "add_pet_model": {"cat": "class", "ko": "생물 {pet}를 플레이어 {player}의 동료로 추가",
                      "args": {"pet": ("code", "petCreature"), "player": ("code", "Owner")}},
    "orb_channel_type": {"cat": "class", "ko": "구체 유형 {orb_type} 영창 · 플레이어 {player}",
                          "args": {"orb_type": ("code", "BloodOrb"), "player": ("code", "Owner")}},
    "orb_passive_model": {"cat": "class", "ko": "구체 모델 {orb} 지속 효과 · 대상 {target}",
                           "args": {"orb": ("code", "orbModel"), "target": ("code", "null")}},
    "orb_slots_to": {"cat": "class", "ko": "플레이어 {player} 구체 슬롯 {amount}개 추가",
                     "args": {"player": ("code", "Owner"), "amount": ("value", {"t": "num", "v": 1})}},
    "wait": {"cat": "flow", "ko": "{duration}초 기다리기", "args": {"duration": ("value", {"t": "num", "v": 1})}},
    "wait_scaled": {"cat": "flow", "ko": "게임 속도에 맞춰 기다리기 · 최소 {minimum} · 최대 {maximum}",
                    "args": {"minimum": ("code", "0.1f"), "maximum": ("code", "0.25f")}},
    "trigger_creature_anim": {"cat": "action", "ko": "생물 {creature} 동작 {animation} 재생 · 지연 {delay}",
                               "args": {"creature": ("code", "target"), "animation": ("code", '"Attack"'), "delay": ("code", "0.15f")}},
    "play_vfx_on_creature": {"cat": "fx", "ko": "생물 {creature}에 이펙트 {vfx} 재생",
                              "args": {"creature": ("code", "target"), "vfx": ("code", '"vfx/vfx_attack_slash"')}},
    "doom_kill": {"cat": "action", "ko": "Doom 처치 대상 {creatures}", "args": {"creatures": ("code", "creatures")}},
    "if": {"cat": "flow", "ko": "만약 {cond} 이면", "args": {"cond": ("cond", {"t": "chance", "pct": {"t": "num", "v": 50}})},
           "body": True},
    "if_else": {"cat": "flow", "ko": "만약 {cond} 이면", "args": {"cond": ("cond", {"t": "chance", "pct": {"t": "num", "v": 50}})},
                "body": True, "else": True, "sections": [("else", "아니면")]},
    "repeat": {"cat": "flow", "ko": "{times}번 반복", "args": {"times": ("value", {"t": "num", "v": 2})}, "body": True},
    "each_enemy": {"cat": "flow", "ko": "모든 적 각각에게 (안에서 '그 적')", "args": {}, "body": True},
    "random_enemy": {"cat": "flow", "ko": "무작위 적 1명에게 (안에서 '그 적')", "args": {}, "body": True},
    "filtered_enemies": {"cat": "flow", "ko": "{enemy_filter} · 파워 {power} · 기준 {limit} · 여러 조건 {conditions} · {enemy_mode} {count}명 (안에서 '그 적/플레이어')", "args": {
        "enemy_filter": ("enemy_filter", "power"), "power": ("power", "Weak"),
        "limit": ("value", {"t": "num", "v": 30}), "enemy_mode": ("enemy_mode", "random"),
        "count": ("value", {"t": "num", "v": 2}), "conditions": ("cond", {"t":"group", "mode":"all", "items":[]})}, "body": True},
    "filtered_players": {"cat":"flow", "ko":"플레이어 중 {conditions} · {enemy_mode} 최대 {count}명 (안에서 '그 적/플레이어')",
        "args":{"conditions":("cond",{"t":"group","mode":"all","items":[]}), "enemy_mode":("enemy_mode","all"),
                "count":("value",{"t":"num","v":1})}, "body":True},
    "edit_var": {"cat": "var", "ko": "변수 {name}을 {amount} {edit_mode}",
                 "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 1}), "edit_mode": ("number_edit", "add")}},
    "set_var": {"cat": "var", "ko": "변수 {name} 을(를) {amount}(으)로 정하기",
                "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 0})}},
    "change_var": {"cat": "var", "ko": "변수 {name} 에 {amount} 더하기",
                   "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 1})}},
    # ---- 카드 인스턴스 상태 (같은 카드가 여러 장이어도 한 장마다 따로) ----
    "card_state_edit": {"cat": "card", "ko": "{card}의 저장 값 {key}를 {amount} {edit_mode}",
                        "args": {"card": ("card_ref", "this"), "key": ("varname", "count"),
                                 "amount": ("value", {"t": "num", "v": 1}), "edit_mode": ("number_edit", "add")}},
    "card_state_set": {"cat": "card", "ko": "카드 {card}의 저장 값 {key} 을(를) {amount}(으)로 정하기",
                       "args": {"card": ("card_ref", "this"), "key": ("varname", "count"),
                                "amount": ("value", {"t": "num", "v": 0})}},
    "card_state_change": {"cat": "card", "ko": "카드 {card}의 저장 값 {key} 에 {amount} 더하기",
                          "args": {"card": ("card_ref", "this"), "key": ("varname", "count"),
                                   "amount": ("value", {"t": "num", "v": 1})}},
    "card_var_new": {"cat": "card", "ko": "카드 {card}에 저장 값 {key} 만들기 · 처음 값 {amount} · 카드 복사 시 {on_clone} · 전투 종료 시 {on_end}",
                     "args": {"card": ("card_ref", "this"), "key": ("varname", "count"),
                              "amount": ("value", {"t": "num", "v": 0}),
                              "on_clone": ("clone_policy", "copy"), "on_end": ("end_policy", "drop")}},
    "card_var_remove": {"cat": "card", "ko": "카드 {card}의 저장 값 {key} 지우기",
                        "args": {"card": ("card_ref", "this"), "key": ("varname", "count")}},
    "aura_power_amount": {"cat":"card", "ko":"이 카드가 {active_pile}에 있는 동안 {target_pile}의 다른 {filter}가 부여하는 {power_filter} 중첩 {amount}만큼 변경",
                          "args":{"active_pile":("aura_pile","Hand"),"target_pile":("aura_target_pile","Any"),"filter":("aura_filter","Any"),"power_filter":("aura_power_filter","Any"),"amount":("value",{"t":"num","v":2})}},
    "aura_card_effect": {"cat":"card", "ko":"이 카드가 {active_pile}에 있을 때 {target_pile}의 다른 {filter}를 사용하면 추가 효과 실행",
                         "args":{"active_pile":("aura_pile","Hand"),"target_pile":("aura_target_pile","Any"),"filter":("aura_filter","Any")},"body":True},
    "hand_aura_stat": {"cat": "card", "ko": "이 카드가 {active_pile}에 있는 동안 {target_pile}의 다른 {filter}의 {stat} {amount}만큼 변경",
                       "args": {"active_pile": ("aura_pile", "Hand"), "target_pile": ("aura_target_pile", "Any"), "filter": ("aura_filter", "Any"), "stat": ("aura_stat", "cost"),
                                "amount": ("value", {"t": "num", "v": -1})}},
    "card_number_edit": {"cat": "card", "ko": "{card}의 {stat}을 {amount} {edit_mode} · {duration}",
                         "args": {"card": ("card_ref", "picked"), "stat": ("card_stat", "cost"),
                                  "amount": ("value", {"t": "num", "v": -1}), "edit_mode": ("number_edit", "add"),
                                  "duration": ("cost_duration", "combat")}},
    "card_cost_edit": {"cat": "card", "ko": "{card}의 비용을 {amount} {edit_mode} · {cost_duration}",
                       "args": {"card": ("card_ref", "picked"), "amount": ("value", {"t": "num", "v": -1}),
                                "edit_mode": ("number_edit", "add"), "cost_duration": ("cost_duration", "combat")}},
    "card_damage_edit": {"cat": "card", "ko": "{card}의 피해량을 {amount} {edit_mode} (이번 전투 · 모든 피해 수치)",
                         "args": {"card": ("card_ref", "picked"), "amount": ("value", {"t": "num", "v": 3}),
                                  "edit_mode": ("number_edit", "add")}},
    "card_do": {"cat": "card", "ko": "카드 {card}: {action}",
                "args": {"card": ("card_ref", "this"), "action": ("pick_action", "draw_at")}},
    "card_ref_keyword": {"cat": "card", "ko": "카드 {card}에 키워드 {keyword} {action}",
                         "args": {"card": ("card_ref", "this"), "keyword": ("keyword", "Retain"),
                                  "action": ("kw_action", "add")}},
    "card_tag": {"cat": "gimmick", "ko": "카드 {card}에 기믹 태그 {tag} {action} (그 한 장만)",
                 "args": {"card": ("card_ref", "this"), "tag": ("gtag", ""), "action": ("kw_action", "add")}},
    "card_enchant": {"cat": "card", "ko": "카드 {card}에 추가 능력 (인챈트) {enchant} {amount} 부여",
                     "args": {"card": ("card_ref", "this"), "enchant": ("enchant", "Inky"),
                              "amount": ("value", {"t": "num", "v": 1})}},
    "card_enchant_clear": {"cat": "card", "ko": "카드 {card}의 추가 능력 (인챈트) 없애기",
                           "args": {"card": ("card_ref", "this")}},
    "add_card_pos": {"cat": "card", "ko": "{card} {count}장을 뽑을 카드 더미 {pos}번째에 넣기 (1=맨 위 · -1=맨 아래 · 0=무작위)",
                     "args": {"card": ("card", "this"), "count": ("value", {"t": "num", "v": 1}),
                              "pos": ("value", {"t": "num", "v": -1})}},
    "draw_bottom": {"cat": "card", "ko": "뽑을 카드 더미 {pos}번째 카드부터 {count}장 뽑기 (1=맨 위 · -1=맨 아래)",
                    "args": {"pos": ("value", {"t": "num", "v": -1}), "count": ("value", {"t": "num", "v": 1})}},
    # ---- 기믹 ----
    "summon": {"cat": "gimmick", "ko": "{summon} 소환 (있으면 단계 상승)", "args": {"summon": ("summon", "")}},
    "command": {"cat": "gimmick", "ko": "{summon} 지금 행동시키기 (지휘)", "args": {"summon": ("summon_any", "*")}},
    "unsummon": {"cat": "gimmick", "ko": "{summon} 돌려보내기", "args": {"summon": ("summon", "")}},
    "pay": {"cat": "gimmick", "ko": "{power} {amount} 을(를) 낼 수 있으면 내고",
            "args": {"power": ("power", ""), "amount": ("value", {"t": "num", "v": 1})},
            "body": True, "else": True, "sections": [("else", "낼 수 없으면")]},
    "choice": {"cat": "gimmick", "ko": "하나 고르기  ① {opt1}",
               "args": {"opt1": ("label", {"ko": "공격", "en": "Attack"}), "opt2": ("label", {"ko": "방어", "en": "Defend"}),
                        "opt3": ("label", {"ko": "", "en": ""})},
               "body": True, "else": True, "third": True,
               "sections": [("else", "② {opt2}"), ("third", "③ {opt3}  (이름을 비우면 둘 중 고르기)")]},
    "shared_call": {"cat":"flow", "ko":"내 블록 {name} · 입력1 {first} · 입력2 {second}",
                    "args":{"name":("shared_name",""), "first":("value",{"t":"num","v":1}), "second":("value",{"t":"num","v":1})}},
    "pick_each": {"cat": "gimmick", "ko": "{pile}에서 {ctype} {count}장 골라 한 장마다 실행",
                  "args": {"pile": ("pick_pile", "Hand"), "ctype": ("card_filter", "Any"),
                           "count": ("value", {"t": "num", "v": 1}), "conditions": ("cond", {"t":"group","mode":"all","items":[]})}, "body": True},
    "random_each": {"cat": "gimmick", "ko": "{pile}에서 {ctype} 무작위 {count}장을 골라 한 장마다 실행",
                    "args": {"pile": ("pick_pile", "Hand"), "ctype": ("card_filter", "Any"),
                             "count": ("value", {"t": "num", "v": 1}), "conditions": ("cond", {"t":"group","mode":"all","items":[]})}, "body": True},
    "picked_action": {"cat": "gimmick", "ko": "고른 카드에 실행: {action}",
                      "args": {"action": ("pick_action", "upgrade")}},
    "random_transform": {"cat": "gimmick", "body": True, "ko": "{pile}의 {ctype} 중 무작위 {count}장을 {result_pool}의 {result_filter} 중 한 장으로 변화",
                         "args": {"pile": ("pick_pile", "Hand"), "ctype": ("card_filter", "Any"),
                                  "result_pool": ("result_pool", ""), "result_filter": ("result_filter", "Any"), "count": ("value", {"t": "num", "v": 1})}},
    "pick_transform": {"cat": "gimmick", "ko": "{pile}에서 {ctype} {count}장 골라 {card}로 변화시키기",
                       "args": {"pile": ("pick_pile", "Hand"), "ctype": ("card_filter", "Any"),
                                "count": ("value", {"t": "num", "v": 1}), "card": ("card", "this")}},
    "pick": {"cat": "gimmick", "ko": "{pile}에서 {ctype} {count}장 골라서 {action}",
             "args": {"pile": ("pick_pile", "Discard"), "ctype": ("card_filter", "Any"),
                      "count": ("value", {"t": "num", "v": 1}), "action": ("pick_action", "hand")}},
    "delayed": {"cat": "gimmick", "ko": "{when} {times}번 실행 (예약)",
                "args": {"when": ("delay_when", "start"), "times": ("value", {"t": "num", "v": 1})}, "body": True},
    # ---- 직업 시스템 ----
    "channel": {"cat": "class", "ko": "구체 {orb} {count}개 영창",
                "args": {"orb": ("orb", "Lightning"), "count": ("value", {"t": "num", "v": 1})}},
    "evoke": {"cat": "class", "ko": "{which} 구체를 {count}번 발현",
              "args": {"which": ("evoke_which", "front"), "count": ("value", {"t": "num", "v": 1})}},
    "orb_passive_all": {"cat": "class", "ko": "모든 구체의 지속 효과 발동", "args": {}},
    "orb_slots": {"cat": "class", "ko": "구체 슬롯 {amount}개 추가 (음수면 감소)", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "orb_grow": {"cat": "class", "ko": "이 구체의 발현 수치 +{amount} (구체 전용)", "args": {"amount": ("value", {"t": "num", "v": 2})}},
    "stars": {"cat": "class", "ko": "별 {amount} 얻기 (음수면 잃기)", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "forge": {"cat": "class", "ko": "단조 {amount}", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "osty_summon": {"cat": "class", "ko": "골골이 소환 {amount} (있으면 최대 체력 증가)", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "osty_attack": {"cat": "class", "ko": "골골이가 {who}에게 피해 {amount}를 {hits}번",
                    "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}), "hits": ("int", 1)}},
    "osty_kill": {"cat": "class", "ko": "골골이 희생 (죽이기)", "args": {}},
    "pet_summon": {"cat": "class", "ko": "동료 {pet} 소환 {amount} (있으면 최대 체력 증가, 쓰러졌으면 되살림)",
                   "args": {"pet": ("pet", ""), "amount": ("value", {"t": "num", "v": 5})}},
    "pet_attack": {"cat": "class", "ko": "동료 {pet} 가 {who}에게 피해 {amount}를 {hits}번",
                   "args": {"pet": ("pet", ""), "who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}),
                            "hits": ("int", 1)}},
    "pet_act": {"cat": "class", "ko": "동료 {pet} 지금 행동", "args": {"pet": ("pet", "")}},
    "pet_kill": {"cat": "class", "ko": "동료 {pet} 희생 (쓰러뜨리기)", "args": {"pet": ("pet", "")}},
    # ---- 이펙트 · 버튼 ----
    "fx": {"cat": "fx", "ko": "이펙트 {fx} 를 {who} 위치에 재생", "args": {"fx": ("fx", ""), "who": ("who_multi", "self")}},
    "button_switch": {"cat": "fx", "ko": "버튼 {button} {switch}", "args": {"button": ("button", ""), "switch": ("switch_state", "on")}},
    "button_on": {"cat": "fx", "ko": "버튼 {button} 켜기", "args": {"button": ("button", "")}},
    "button_off": {"cat": "fx", "ko": "버튼 {button} 끄기", "args": {"button": ("button", "")}},
    "sfx": {"cat": "fx", "ko": "소리 {path} 재생 · 음량 {volume}",
            "args": {"path": ("code", '"event:/sfx"'), "volume": ("value", {"t": "num", "v": 1})}},
}

# Call Mapping can connect unknown APIs from any imported mod to these shared
# blocks. Keep the list derived from the block schemas so the editor and importer
# cannot silently drift apart.
_MANUAL_MAP_FIELD_KINDS = {"value", "code", "bool", "int", "who_multi", "power", "keyword", "kw_action"}
_MANUAL_MAP_CATEGORIES = {"action", "card", "class", "fx"}
_MANUAL_MAP_EXCLUDED = {"source_amount", "source_step", "source_hit", "original_play", "src_call"}
MANUAL_MAP_OPS = tuple(
    op for op, spec in SPECS.items()
    if op not in _MANUAL_MAP_EXCLUDED and spec.get("cat") in _MANUAL_MAP_CATEGORIES and
    all(kind in _MANUAL_MAP_FIELD_KINDS for kind, _default in spec.get("args", {}).values())
)

EVOKE_WHICH = [("front", "맨 앞"), ("last", "맨 뒤")]
ORB_COUNTS = [("count", "구체 수"), ("slots", "구체 슬롯 수"), ("empty", "빈 구체 슬롯 수")]
OSTY_STATS = [("hp", "골골이 현재 체력"), ("maxhp", "골골이 최대 체력")]
PALETTE = [
    ("action", ["original_play", "source_step", "damage", "card_attack", "damage_to", "block", "block_to", "lose_block", "lose_block_to", "kill_creature", "doom_kill", "trigger_creature_anim", "draw", "energy", "heal", "heal_to", "lose_hp", "max_hp", "gold",
                "apply_power", "apply_power_to", "apply_power_type", "power_apply_type", "power_apply_model",
                "remove_power", "remove_power_model", "modify_power_amount", "set_current_hp", "energy_to", "gold_to",
                "lose_gold", "end_turn", "stun", "flash"]),
    ("card", ["hand", "add_card", "card_exhaust", "card_upgrade", "card_autoplay", "card_discard", "card_keyword", "card_add_keyword_model",
               "card_add_generated", "card_add_pile", "card_add_generated_many", "card_preview", "card_preview_cards", "card_remove_combat",
               "draw_to", "shuffle_draw_pile", "autoplay_draw_pile", "potion_add_type", "potion_add_model", "potion_add_model_at", "potion_discard",
               "card_set_cost_until_played", "card_free_this_turn", "card_notify_cost_changed", "card_upgrade_internal",
               "card_finalize_upgrade_internal", "card_transform_to", "keyword_this", "keyword_cards",
               "card_state_edit", "card_var_new", "card_var_remove", "card_number_edit", "hand_aura_stat", "aura_power_amount", "aura_card_effect", "card_do",
               "card_ref_keyword", "card_enchant", "card_enchant_clear", "add_card_pos", "draw_bottom"]),
    ("flow", ["shared_call", "if", "if_else", "repeat", "each_enemy", "random_enemy", "filtered_players", "wait", "wait_scaled"]),
    ("var", ["edit_var"]),
    ("gimmick", ["pay", "summon", "command", "unsummon", "choice", "pick", "random_transform", "pick_transform", "pick_each", "random_each", "picked_action", "card_tag", "delayed"]),
    ("class", ["channel", "orb_channel_model", "orb_channel_type", "orb_passive_model", "evoke", "orb_passive_all", "orb_slots", "orb_slots_to", "orb_grow", "stars", "forge",
               "osty_summon", "osty_attack", "osty_kill", "pet_summon", "pet_attack", "pet_act", "pet_kill", "add_pet_model"]),
    ("fx", ["fx", "button_switch", "sfx", "play_vfx_on_creature"]),
]
PALETTE = [(cat,[op for op in ops if op != "picked_action"]) for cat,ops in F.install(SPECS, PALETTE)]

BODY_KEYS = ("body", "else", "third")
PICK_PILES = [("Hand", "손패"), ("Draw", "뽑을 카드 더미"), ("Discard", "버린 카드 더미"), ("Exhaust", "소멸한 카드 더미")]
PREVIEW_STYLES = [("", "기본 배치"),
                  ("global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.None", "보여주지 않기"),
                  ("global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.HorizontalLayout", "가로로 나란히"),
                  ("global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.MessyLayout", "겹쳐서 배치"),
                  ("global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.EventLayout", "이벤트 화면 배치"),
                  ("global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.GridLayout", "격자로 배치")]


def preview_style_options(op):
    # Game PreviewInternal rejects event/grid layouts for combat piles.
    if op == "card_preview":
        return [(value,label) for value,label in PREVIEW_STYLES if not value.endswith(("EventLayout", "GridLayout"))]
    return list(PREVIEW_STYLES)


def preview_style_expr(value):
    value = str(value or "").strip()
    if value in ("", "CardPreviewStyle.Default"):
        return ""
    if value.startswith("CardPreviewStyle."):
        return "global::MegaCrit.Sts2.Core.Nodes.CommonUi." + value
    return value


CARD_STATS = [("cost", "비용"), ("damage", "피해량"), ("block", "방어도"),
              ("draw", "카드 장수 (뽑기 등)"), ("energy", "에너지 획득량"), ("heal", "체력 회복량"),
              ("lose_hp", "체력 손실량"), ("max_hp", "최대 체력 증가량"), ("gold", "골드 획득량")]
CARD_STAT_EN = {"cost":"cost", "damage":"damage values", "block":"Block values", "draw":"card counts",
                "energy":"Energy gained", "heal":"healing", "lose_hp":"HP loss", "max_hp":"Max HP gained", "gold":"Gold gained"}
NUMBER_EDITS = [("add", "만큼 변경"), ("set", "으로 설정")]
COST_DURATIONS = [("combat", "이번 전투"), ("turn", "이번 턴"), ("played", "다음 사용 시까지")]
PICK_ACTIONS = [("hand", "손으로 가져오기"), ("draw_at", "뽑을 더미 N번째에 놓기"), ("exhaust", "소멸"), ("discard", "버리기"),
                ("upgrade", "강화 (이번 전투)"), ("random_transform", "무작위 카드로 변화")]
# 예전 저장본의 '맨 위/맨 아래' -> N번째 (1 = 맨 위, -1 = 맨 아래, 0 = 무작위 위치)
OLD_POS = {"top": 1, "bottom": -1, "Top": 1, "Bottom": -1, "Random": 0, "draw_top": 1, "draw_bottom": -1}
DELAY_WHEN = [("start", "다음 내 턴 시작에"), ("end", "이번 턴이 끝날 때")]
# 카드 인스턴스 참조: 같은 카드가 여러 장 있어도 그 한 장(CardModel 인스턴스)을 가리킨다
CARD_REFS = [("this", "이 카드 (지금 사용 중인 그 한 장)"), ("picked", "고른 카드 (한 장마다 실행 안)"),
             ("draw_at", "뽑을 카드 더미 N번째 카드")]
CARD_REFS_KO = {"this": "이 카드", "picked": "고른 카드", "draw_top": "뽑을 카드 더미 맨 위 카드",
                "draw_bottom": "뽑을 카드 더미 맨 아래 카드"}
CARD_REFS_EN = {"this": "this card", "picked": "the chosen card", "draw_top": "the top card of your draw pile",
                "draw_bottom": "the bottom card of your draw pile"}
CLONE_POLICIES = [("copy", "값 복사"), ("reset", "복사하지 않음")]
END_POLICIES = [("drop", "지우기 (이번 전투만)"), ("keep", "덱의 그 카드에 남기기")]


def pos_n(kind, n):
    """(종류, N) -> (새 종류, N). 예전 'draw_top'/'top' 등은 draw_at + N 으로."""
    if kind in OLD_POS:
        return "draw_at", OLD_POS[kind]
    try:
        n = int(float(n if n not in (None, "") else 1))
    except (TypeError, ValueError):
        n = 1
    return kind, n


def nth_word(n, lang):
    """1 -> '1번째' / -1 -> '아래에서 1번째' / 0 -> '무작위'."""
    if lang == "ko":
        return "무작위 위치" if n == 0 else (f"{n}번째" if n > 0 else f"아래에서 {-n}번째")
    if n == 0:
        return "a random position"
    k = abs(n)
    suf = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{k}{suf} from the {'top' if n > 0 else 'bottom'}"


def ref_word(d, lang, key="card"):
    """카드 참조를 말로 ('이 카드' / '뽑을 카드 더미 2번째 카드')."""
    ref, n = pos_n(d.get(key, "this"), d.get(key + "_n"))
    if ref == "draw_at":
        return f"뽑을 카드 더미 {nth_word(n, 'ko')} 카드" if lang == "ko" else f"the card {nth_word(n, 'en')} of your draw pile"
    return CARD_REFS_KO.get(ref, "이 카드") if lang == "ko" else CARD_REFS_EN.get(ref, "this card")
# 게임 인챈트 (MegaCrit.Sts2.Core.Models.Enchantments)
ENCHANTS = [("Inky", "Inky (잉크)"), ("Sharp", "Sharp (날카로움)"), ("Swift", "Swift (신속)"), ("Steady", "Steady (안정)"),
            ("Nimble", "Nimble (민첩)"), ("Adroit", "Adroit (능숙)"), ("Vigorous", "Vigorous (활력)"),
            ("Momentum", "Momentum (가속)"), ("Instinct", "Instinct (본능)"), ("Imbued", "Imbued (주입)"),
            ("Glam", "Glam (화려함)"), ("Goopy", "Goopy (끈적)"), ("Slither", "Slither (미끄러짐)"),
            ("Spiral", "Spiral (나선)"), ("Sown", "Sown (씨앗)"), ("PerfectFit", "PerfectFit (안성맞춤)"),
            ("RoyallyApproved", "RoyallyApproved (왕실 인증)"), ("SoulsPower", "SoulsPower (영혼의 힘)"),
            ("Corrupted", "Corrupted (타락)"), ("Clone", "Clone (복제)"), ("SlumberingEssence", "SlumberingEssence (잠든 정수)"),
            ("TezcatarasEmber", "TezcatarasEmber (테즈카타라의 불씨)")]


def card_is_filters(project):
    """'카드가 ~이다' 조건에 쓸 목록: 종류·기믹 태그·키워드·인챈트."""
    import gimmick as G
    import modgen as M
    return (list(G.card_filters(project)) + [("kw:" + k, f"키워드 {n}") for k, n in M.CARD_KEYWORDS] +
            [("enchanted", "인챈트가 있음"), ("upgraded", "강화됨")])


def _card_is_word(project, who, f, lang):
    """'이 카드에 [보존] 키워드가 있음' / '이 카드가 공격 카드' (조건문에서 '있으면'·'이면'이 붙는다)."""
    import gimmick as G
    import modgen as M
    f = f or "Any"
    ko = lang == "ko"
    if f.startswith("kw:"):
        n = M.KEYWORD_NAMES.get(lang, M.KEYWORD_NAMES["en"]).get(f[3:], f[3:])
        return f"{who}에 [gold]{n}[/gold] 키워드가 있음" if ko else f"{who} has [gold]{n}[/gold]"
    if f == "enchanted":
        return f"{who}에 인챈트가 있음" if ko else f"{who} is enchanted"
    if f == "upgraded":
        return f"{who}{_jj(who, '이', '가')} 강화된 카드" if ko else f"{who} is upgraded"
    w = G.filter_word(project, f, lang)
    return f"{who}{_jj(who, '이', '가')} {w}" if ko else f"{who} is {w}"
PLAYED_SCOPES = [("turn", "이번 턴에"), ("combat", "이번 전투에서")]

WHO = {"self": "나", "target": "대상", "it": "그 적/플레이어", "all": "모든 적", "random": "무작위 적"}
WHO_EN = {"self": "you", "target": "the target", "it": "that enemy", "all": "ALL enemies", "random": "a random enemy"}
CARD_TYPES = [("Any", "아무"), ("Attack", "공격"), ("Skill", "스킬"), ("Power", "파워"),
              ("Curse", "저주"), ("Status", "상태 이상"), ("Quest", "퀘스트")]
WHICH = [("random", "무작위로"), ("all", "전부")]
HAND_ACTIONS = [("upgrade", "강화"), ("exhaust", "소멸"), ("discard", "버리기")]
KW_WHERE = [("hand", "손패"), ("draw", "뽑을 카드 더미"), ("discard", "버린 카드 더미"), ("all", "모든 카드 더미")]
KW_ACTIONS = [("add", "부여"), ("remove", "제거")]
PILES = [("Hand", "손패"), ("Draw", "뽑을 카드 더미"), ("Discard", "버린 카드 더미")]
STATS = [("hp", "현재 체력"), ("maxhp", "최대 체력"), ("block", "방어도")]
COUNTS = [("hand", "손패 카드 수"), ("draw", "뽑을 카드 수"), ("discard", "버린 카드 수"), ("exhaust", "소멸한 카드 수"),
          ("enemies", "살아 있는 적 수")]
CMP_OPS = [(">=", "≥"), (">", ">"), ("==", "="), ("<", "<"), ("<=", "≤"), ("!=", "≠")]
ARITH = [("+", "+"), ("-", "−"), ("*", "×"), ("/", "÷")]


def who_options(owner_kind, multi=True):
    opts = [("self", "나")]
    if owner_kind in ("card", "potion"):
        opts.append(("target", "대상"))
    if owner_kind == "power":
        opts[0] = ("self", "나(소유자)")
        opts.append(("target", "상대(트리거)"))
    if owner_kind in ("summon", "button"):
        opts[0] = ("self", "나(플레이어)")
    if owner_kind == "pet":
        opts[0] = ("self", "나(동료 자신)")
    opts.append(("it", "그 적/플레이어 (반복 안)"))
    if multi:
        opts += [("all", "모든 적"), ("random", "무작위 적")]
    return opts


COMPACT_ALIASES = {"set_var": ("edit_var", "edit_mode", "set"), "change_var": ("edit_var", "edit_mode", "add"),
                   "card_state_set": ("card_state_edit", "edit_mode", "set"), "card_state_change": ("card_state_edit", "edit_mode", "add"),
                   "button_on": ("button_switch", "switch", "on"), "button_off": ("button_switch", "switch", "off")}


def compact_op(op):
    if op in ("card_cost_edit", "card_damage_edit"):
        return "card_number_edit"
    mapped = COMPACT_ALIASES.get(op, (op,))[0]
    if op == "picked_action":
        return "card_do"
    return F.LEGACY.get(mapped, mapped)


def expand_compact(b):
    if b.get("op") in F.FAMILIES:
        original = b.get("_compact_origin", b)
        b = dict(b, op=F.variant(b, SPECS), _compact_origin=original)
    op, a = b.get("op"), b.get("args", {})
    if op == "edit_var":
        return dict(b, op="set_var" if a.get("edit_mode", "add") == "set" else "change_var")
    if op == "card_state_edit":
        return dict(b, op="card_state_set" if a.get("edit_mode", "add") == "set" else "card_state_change")
    if op == "button_switch":
        return dict(b, op="button_on" if a.get("switch", "on") == "on" else "button_off")
    return b


def upgrade_numeric_blocks(blocks):
    """Migrate editable copies, including old presets, without changing references."""
    for b in walk(blocks):
        F.migrate(b, SPECS)
        if b.get("op") in COMPACT_ALIASES:
            op, field, value = COMPACT_ALIASES[b["op"]]
            b["op"] = op
            b.setdefault("args", {})[field] = value
        if b.get("op") in ("card_cost_edit", "card_damage_edit"):
            a = b.setdefault("args", {})
            cost = b["op"] == "card_cost_edit"
            a["stat"] = "cost" if cost else "damage"
            a["duration"] = a.pop("cost_duration", "combat") if cost else "combat"
            b["op"] = "card_number_edit"
        if b.get("op") == "picked_action":
            b["op"] = "card_do"
            b.setdefault("args", {})["card"] = "picked"
        F.migrate(b, SPECS)
    return blocks


def new_block(op):
    if op in F.FAMILIES:
        b = new_block(F.FAMILIES[op][1][0][0])
        F.migrate(b, SPECS)
        return b
    spec = SPECS[op]
    b = {"op": op, "args": {k: copy.deepcopy(v[1]) for k, v in spec["args"].items()}}
    if spec.get("body"):
        b["body"] = []
    if spec.get("else"):
        b["else"] = []
    if spec.get("third"):
        b["third"] = []
    if op in ("summon", "unsummon"):
        b["args"]["summon"] = _first_summon()
    if op == "fx":
        p = _PROJECT_HINT.get("p") or {}
        fx = (p.get("gimmicks") or {}).get("effects") or []
        b["args"]["fx"] = fx[0]["id"] if fx else ""
    if op.startswith("pet_"):
        p = _PROJECT_HINT.get("p") or {}
        pt = (p.get("gimmicks") or {}).get("pets") or []
        b["args"]["pet"] = pt[0]["id"] if pt else ""
    if op in ("button_switch", "button_on", "button_off"):
        p = _PROJECT_HINT.get("p") or {}
        bt = (p.get("gimmicks") or {}).get("buttons") or []
        b["args"]["button"] = bt[0]["id"] if bt else ""
    if op == "pay":
        b["args"]["power"] = _first_custom_power()
    return b


_PROJECT_HINT = {}


def set_project_hint(project):
    """새 블록의 기본값(첫 소환수·첫 새 파워)을 고를 때 쓸 프로젝트."""
    _PROJECT_HINT["p"] = project


def _first_summon():
    p = _PROJECT_HINT.get("p") or {}
    s = (p.get("gimmicks") or {}).get("summons") or []
    return s[0]["id"] if s else ""


def _first_custom_power():
    p = _PROJECT_HINT.get("p") or {}
    pw = p.get("powers") or []
    return "c:" + pw[0]["id"] if pw else "Strength"


def block_spec(b):
    return F.block_spec(b, SPECS)


def fix_unknown_blocks(blocks):
    """지워진 블록(예: 예전 Manosaba 전용 블록)은 '직접 코드' 블록으로 바꾼다. 안에 든 블록도 같이 고친다."""
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        op = b.get("op")
        if op not in SPECS:
            out.append({"op": "source_step", "args": {"source": f"// 지워진 블록: {op}"}})
            continue
        nb = dict(b)
        for key in ("body", "else", "third"):
            if isinstance(nb.get(key), list):
                nb[key] = fix_unknown_blocks(nb[key])
        out.append(nb)
    return out


def block_caption(b):
    """블록에 보일 글 ({칸} 자리 포함). 원본에서 풀어낸 블록은 블록마다 다르다."""
    op = b.get("op")
    if op in F.FAMILIES:
        return F.caption(b, SPECS)
    if op == "src_call":
        return (b.get("label") or "직접 호출") + "".join(f"  {s['name']} {{{s['key']}}}" for s in b.get("slots", []))
    if op == "src_loop":
        return "직접 반복 {head}" if (b.get("args") or {}).get("head") else "묶음 { }"
    if op == "source_amount":
        return b.get("label", "효과") + " {amount}"
    return SPECS[op]["ko"]


def arg_kind(b, key):
    if b.get("op") == "src_call":
        s = next((s for s in b.get("slots", []) if s["key"] == key), None)
        return s["kind"] if s else "code"
    return block_spec(b)["args"][key][0]


def slot_info(b, key):
    return next((s for s in b.get("slots", []) if s["key"] == key), {}) if b.get("op") == "src_call" else {}


_ITEM_HINT = {}


def set_item_hint(item):
    """원본 변수 (DynamicVars) 이름표에 현재 수치를 보여 주려고 편집 중인 항목을 기억한다."""
    _ITEM_HINT["i"] = item


def _short_code(code, n=34):
    t = " ".join(str(code or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def walk(blocks):
    for b in blocks or []:
        yield b
        for k in BODY_KEYS:
            yield from walk(b.get(k))


def _label_text(v, lang):
    if isinstance(v, dict):
        order = (lang, "en", "ko") if lang == "zh" else (lang, "ko", "en")   # 중국어가 비면 영어 (이름 규칙과 같게)
        return next((v[l].strip() for l in order if (v.get(l) or "").strip()), "")
    return str(v or "").strip()


def _j(word, a, b):
    import modgen as M
    return M.josa(word, a, b)


def _describe_class(b, op, a, project, lang, V, W):
    import gimmick as G
    ko = lang == "ko"
    if op == "channel":
        om = G.orb_meta(project, a.get("orb")) or {"ko": "?", "en": "?"}
        n = om["ko"] if ko else om["en"]
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} {V('count')}번 [gold]영창[/gold]합니다." if ko else \
            f"[gold]Channel[/gold] {V('count')} [gold]{n}[/gold]."
    if op == "evoke":
        front = a.get("which", "front") == "front"
        cnt = V("count")
        if ko:
            return f"{'맨 앞' if front else '맨 뒤'} 구체를 {cnt}번 [gold]발현[/gold]합니다."
        return f"[gold]Evoke[/gold] your {'next' if front else 'last'} Orb{'' if cnt == '1' else f' {cnt} times'}."
    if op == "orb_passive_all":
        return "모든 구체의 지속 효과를 발동합니다." if ko else "Trigger the passive of all your Orbs."
    if op == "orb_slots":
        return f"구체 슬롯을 {V('amount')}개 얻습니다." if ko else f"Gain {V('amount')} Orb Slot(s)."
    if op == "orb_grow":
        return f"이 구체의 발현 수치가 {V('amount')} 증가합니다." if ko else f"Increase this Orb's Evoke amount by {V('amount')}."
    if op == "stars":
        return f"[gold]별[/gold]을 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Stars[/gold]."
    if op == "forge":
        return f"[gold]단조[/gold] {V('amount')}." if ko else f"[gold]Forge[/gold] {V('amount')}."
    if op == "osty_summon":
        return f"[gold]소환[/gold] {V('amount')}." if ko else f"[gold]Summon[/gold] {V('amount')}."
    if op == "osty_attack":
        hits = int(a.get("hits", 1) or 1)
        times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
        if ko:
            who = "" if a.get("who") == "target" else f"{W('who')}에게 "
            return f"[gold]골골이[/gold]가 {who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다."
        return f"[gold]Osty[/gold] deals {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
    if op == "osty_kill":
        return "[gold]골골이[/gold]를 희생합니다." if ko else "Sacrifice [gold]Osty[/gold]."
    return ""


def _pet_name(project, pid, lang):
    import pets as PT
    p = PT.find_pet(project or {}, pid)
    return PT._txt(p, "name", lang) if p else str(pid or "?")


def _summon_name(project, sid, lang):
    if sid == "*":
        return "모든 소환수" if lang == "ko" else "all summons"
    import gimmick as G
    s = G.find_summon(project or {}, sid)
    return G._txt(s, "name", lang) if s else str(sid)


# ---------------------------------------------------------------------------
# 값 / 조건 설명 (화면 표시용 짧은 글)
# ---------------------------------------------------------------------------
def _pname(project, key, lang="ko"):
    import modgen as M
    pm = M.power_meta(project, key)
    return (pm["ko"] if lang == "ko" else pm["en"]) if pm else str(key)


def value_label(v, project=None, lang="ko", card=False):
    if not isinstance(v, dict):
        return str(v)
    t = v.get("t")
    if t == "num":
        n = _fmt(v.get("v", 0))
        up = v.get("up") or 0
        if up and card:
            return "{IfUpgraded:show:%s|%s}" % (_fmt(float(v.get("v", 0)) + float(up)), n)
        return n + (f"(+{_fmt(up)})" if up and project is None else "")
    if t == "stack":
        who = (WHO if lang == "ko" else WHO_EN).get(v.get("who", "self"), "")
        p = _pname(project, v.get("power"), lang) if project else v.get("power")
        return f"{who}의 [gold]{p}[/gold]" if lang == "ko" else f"{_poss(v.get('who'))} [gold]{p}[/gold]"
    if t == "stat":
        who = (WHO if lang == "ko" else WHO_EN).get(v.get("who", "self"), "")
        s = dict(STATS).get(v.get("stat"), "")
        if lang == "en":
            s = {"hp": "current HP", "maxhp": "Max HP", "block": "Block"}.get(v.get("stat"), "")
        return f"{who}의 {s}" if lang == "ko" else f"{_poss(v.get('who'))} {s}"
    if t == "count":
        if lang == "ko":
            return dict(COUNTS).get(v.get("what"), "")
        return {"hand": "cards in your hand", "draw": "cards in your draw pile", "discard": "cards in your discard pile",
                "exhaust": "exhausted cards", "enemies": "enemies"}.get(v.get("what"), "")
    if t == "energy":
        return "남은 에너지" if lang == "ko" else "your Energy"
    if t == "amount":
        return "[blue]{Amount}[/blue]"
    if t == "round":
        return "현재 턴 수" if lang == "ko" else "the turn number"
    if t == "rand":
        return f"{value_label(v.get('min'), project, lang, card)}~{value_label(v.get('max'), project, lang, card)}"
    if t == "var":
        return str(v.get("name", "a"))
    if t == "card_state":
        k = str(v.get("key") or "count")
        if lang == "ko":
            return f"{ref_word(v, 'ko')}의 {k}"
        return f"{ref_word(v, 'en')}'s {k}"
    if t == "played":
        import gimmick as G
        f = v.get("filter", "Any")
        if lang == "ko":
            what = G.filter_word(project or {"gimmicks": {}}, f, "ko") if project else "카드"
            return f"{dict(PLAYED_SCOPES).get(v.get('scope'), '')} 사용한 {what} 수"
        what = G.filter_word(project or {"gimmicks": {}}, f, "en", plural=True) if project else "cards"
        return f"the number of {what} played {'this turn' if v.get('scope') == 'turn' else 'this combat'}"
    if t == "summons":
        return "소환수 수" if lang == "ko" else "your number of summons"
    if t == "orb_passive":
        return "[blue]{Passive}[/blue]"
    if t == "orb_evoke":
        return "[blue]{Evoke}[/blue]"
    if t == "orbs":
        import gimmick as G
        w = v.get("what", "count")
        om = G.orb_meta(project or {}, v.get("orb")) if v.get("orb") and w == "count" else None
        if lang == "ko":
            base = dict(ORB_COUNTS).get(w, "구체 수")
            return f"[gold]{om['ko']}[/gold] 구체 수" if om else base
        if om:
            return f"your [gold]{om['en']}[/gold] Orbs"
        return {"count": "your Orbs", "slots": "your Orb Slots", "empty": "your empty Orb Slots"}.get(w, "your Orbs")
    if t == "stars":
        return "[gold]별[/gold] 수" if lang == "ko" else "your [gold]Stars[/gold]"
    if t == "pet":
        n = _pet_name(project, v.get("pet"), lang)
        if lang == "ko":
            return f"[gold]{n}[/gold] {'최대 체력' if v.get('what') == 'maxhp' else '체력'}"
        return f"[gold]{n}'s[/gold] {'Max HP' if v.get('what') == 'maxhp' else 'HP'}"
    if t in ("star_x", "energy_x"):
        return "X"
    if t == "osty":
        if lang == "ko":
            return dict(OSTY_STATS).get(v.get("what"), "골골이 체력").replace("골골이", "[gold]골골이[/gold]")
        return "[gold]Osty's[/gold] " + ("Max HP" if v.get("what") == "maxhp" else "HP")
    if t == "event":
        return "그 수치" if lang == "ko" else "that amount"
    if t == "op":
        sym = dict(ARITH).get(v.get("op"), v.get("op"))
        return f"({value_label(v.get('a'), project, lang, card)} {sym} {value_label(v.get('b'), project, lang, card)})"
    if t == "dynvar":
        item = _ITEM_HINT.get("i") or {}
        rv = next((x for x in item.get("raw_vars", []) if x.get("name") == v.get("name")), None)
        if rv is None:
            return f"원본 변수 {v.get('name')}"
        up = rv.get("upgrade") or 0
        num = _fmt(rv.get("value", 0))
        if card and up:
            num = "{IfUpgraded:show:%s|%s}" % (_fmt(float(rv.get("value") or 0) + float(up)), num)
        elif up:
            num += f"(+{_fmt(up)})"
        return f"{v.get('name')}={num}" if lang == "ko" else num
    if t == "src":
        return "직접 수식 " + _short_code(v.get("code"))
    return "?"


def _visible(text):
    """조사 판단용: [태그] 를 빼고, {IfUpgraded:show:A|B} 는 B(강화 전)로."""
    import re
    t = re.sub(r"\{IfUpgraded:show:[^|}]*\|([^}]*)\}", r"\1", str(text))
    t = re.sub(r"\[/?[a-z]+\]", "", t)
    t = re.sub(r"\{[^}]*\}", "0", t)
    return t.strip().rstrip(")").strip()


_DIGIT_JONG = {"0": "ㅇ", "1": "ㄹ", "3": "ㅁ", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ"}   # 영 일 삼 육 칠 팔


def _jong(word):
    """마지막 글자의 받침 ('' = 없음). 숫자·영어는 읽는 소리로."""
    t = _visible(word)
    if not t:
        return ""
    ch = t[-1]
    if "가" <= ch <= "힣":
        j = (ord(ch) - 0xAC00) % 28
        return "" if j == 0 else ("ㄹ" if j == 8 else "x")
    if ch.isdigit():
        return _DIGIT_JONG.get(ch, "")
    if ch.upper() in "LMNR":          # 엘 엠 엔 알
        return "ㄹ" if ch.upper() in "LR" else "x"
    return ""


def _jj(word, a, b):
    """받침 있으면 a(이/을/과), 없으면 b(가/를/와)."""
    return a if _jong(word) else b


def _ro(word):
    j = _jong(word)
    return "으로" if j and j != "ㄹ" else "로"


def cmp_text(c, project, lang, card, conditional=False):
    """비교 조건을 말로: '별 수가 3 이상' / 조건문이면 '별 수가 3 이상이면'."""
    A = value_label(c.get("a"), project, lang, card)
    Bv = value_label(c.get("b"), project, lang, card)
    op = c.get("op", ">=")
    if lang == "ko":
        subj = f"{A}{_jj(A, '이', '가')}"
        stem, tail = {
            ">=": (f"{subj} {Bv} 이상", "이면"),
            "<=": (f"{subj} {Bv} 이하", "이면"),
            ">": (f"{subj} {Bv}{_jj(Bv, '을', '를')} 초과", "하면"),
            "<": (f"{subj} {Bv} 미만", "이면"),
            "==": (f"{subj} {Bv}{_jj(Bv, '과', '와')} 같", "으면"),
            "!=": (f"{subj} {Bv}{_jj(Bv, '과', '와')} 다르", "면"),
        }.get(op, (f"{A} {op} {Bv}", "이면"))
        if conditional:
            return stem + tail
        return stem + {"==": "음", "!=": "다"}.get(op, "")
    return {">=": f"{A} is {Bv} or more", "<=": f"{A} is {Bv} or less", ">": f"{A} is more than {Bv}",
            "<": f"{A} is less than {Bv}", "==": f"{A} is {Bv}", "!=": f"{A} is not {Bv}"}.get(op, f"{A} {op} {Bv}")


def _poss(who):
    return {"self": "your", "target": "the target's", "it": "that enemy's"}.get(who or "self", "your")


def selection_condition(b):
    """Seed the compound editor from older single-condition enemy blocks."""
    a = b.get("args", {})
    group = a.get("conditions")
    if group and (group.get("t") != "group" or group.get("items")):
        return copy.deepcopy(group) if group.get("t") == "group" else {"t":"group", "mode":"all", "items":[copy.deepcopy(group)]}
    condition = a.get("enemy_filter", "all")
    items = []
    if condition in ("power", "no_power"):
        item = {"t":"has", "who":"it", "power":a.get("power","Weak")}
        items = [{"t":"not", "a":item} if condition == "no_power" else item]
    elif condition in ("hp_below", "hp_above"):
        items = [{"t":"hp_percent", "who":"it", "op":"<=" if condition == "hp_below" else ">=",
                  "value":copy.deepcopy(a.get("limit", {"t":"num","v":30}))}]
    return {"t":"group", "mode":"all", "items":items}


def cond_label(c, project=None, lang="ko", card=False):
    if not isinstance(c, dict):
        return "?"
    t = c.get("t")
    V = lambda x: value_label(x, project, lang, card)  # noqa: E731
    if t == "group":
        items = c.get("items", [])
        if not items:
            return "조건 없음" if lang == "ko" else "No conditions"
        joiner = " 그리고 " if c.get("mode", "all") == "all" else " 또는 "
        if lang != "ko":
            joiner = " AND " if c.get("mode", "all") == "all" else " OR "
        return "(" + joiner.join(cond_label(x, project, lang, card) for x in items) + ")"
    if t == "hp_percent":
        who = (WHO if lang == "ko" else WHO_EN).get(c.get("who","it"), "")
        return f"{who} 체력 {c.get('op','<=')} {V(c.get('value'))}%" if lang == "ko" else f"{who} HP {c.get('op','<=')} {V(c.get('value'))}%"
    if t == "pile_count":
        import gimmick as G
        who = (WHO if lang == "ko" else WHO_EN).get(c.get("who","self"), "")
        pile = dict(PILES + [("Deck","전체 덱")]).get(c.get("pile","Deck"), c.get("pile"))
        cid = c.get("card_id")
        name = next((x.get('name_'+lang) or x['id'] for x in (project or {}).get('cards',[]) if x['id']==cid), cid) if cid else G.filter_word(project, c.get("filter","Any"),lang)
        return f"{who}의 {pile}에 {name} {c.get('op','>=')} {V(c.get('count'))}장" if lang == "ko" else f"{who}'s {c.get('pile','Deck')}: {name} {c.get('op','>=')} {V(c.get('count'))} cards"
    if t == "card_identity":
        cid = c.get("card_id", "")
        return f"고른 카드가 {cid}" if lang == "ko" else f"Chosen card is {cid}"
    if t == "cmp":
        return cmp_text(c, project, lang, card)
    if t == "chance":
        return f"{V(c.get('pct'))}% 확률" if lang == "ko" else f"a {V(c.get('pct'))}% chance"
    if t == "has":
        who = (WHO if lang == "ko" else WHO_EN).get(c.get("who", "self"), "")
        p = _pname(project, c.get("power"), lang) if project else c.get("power")
        return f"{who}에게 [gold]{p}[/gold]이(가) 있음" if lang == "ko" else f"{who} {'have' if c.get('who') == 'self' else 'has'} [gold]{p}[/gold]"
    if t in ("and", "or"):
        j = {"and": "그리고", "or": "또는"}[t] if lang == "ko" else t
        return f"({cond_label(c.get('a'), project, lang, card)} {j} {cond_label(c.get('b'), project, lang, card)})"
    if t == "not":
        return f"({cond_label(c.get('a'), project, lang, card)})이 아님" if lang == "ko" else f"not ({cond_label(c.get('a'), project, lang, card)})"
    if t == "osty_alive":
        return "[gold]골골이[/gold]가 살아 있음" if lang == "ko" else "[gold]Osty[/gold] is alive"
    if t == "pet_alive":
        n = _pet_name(project, c.get("pet"), lang)
        return f"[gold]{n}[/gold]{_j(n, '이', '가')} 살아 있음" if lang == "ko" else f"[gold]{n}[/gold] is alive"
    if t == "card_var_has":
        k = str(c.get("key") or "count")
        if lang == "ko":
            return f"{ref_word(c, 'ko')}에 변수 {k}{_jj(k, '이', '가')} 있음"
        return f"{ref_word(c, 'en')} has {k}"
    if t == "card_is":
        who = ref_word(c, lang)
        return _card_is_word(project or {"gimmicks": {}, "mod": {"id": "M"}}, who, c.get("filter"), lang)
    if t == "src":
        return "직접 조건 " + _short_code(c.get("code"), 48)
    return "?"


_ACT_KO = {"hand": "손으로 가져옵니다", "draw_at": "뽑을 카드 더미 {n}에 놓습니다",
           "exhaust": "소멸시킵니다", "discard": "버립니다", "upgrade": "강화합니다", "random_transform": "무작위 카드로 변화시킵니다"}
_ACT_EN = {"hand": "Put {w} into your hand.", "draw_at": "Put {w} {n} of your draw pile.", "exhaust": "Exhaust {w}.", "discard": "Discard {w}.",
           "upgrade": "Upgrade {w}.", "random_transform": "Transform {w} into a random card."}


def _pos_value(v):
    """위치 칸 값 (예전 'Bottom' 같은 글자도 받음) -> 값 dict."""
    if isinstance(v, dict):
        return v
    if v in OLD_POS:
        return {"t": "num", "v": OLD_POS[v]}
    return {"t": "num", "v": -1}


def _pos_word(v, project, lang, card):
    v = _pos_value(v)
    if v.get("t") == "num":
        return nth_word(int(float(v.get("v", 0) or 0)), lang)
    lab = value_label(v, project, lang, card)
    return f"{lab}번째" if lang == "ko" else f"position {lab}"


def _describe_cardref(b, op, a, project, lang, card, V):
    """카드 인스턴스 블록 설명."""
    import modgen as M
    import gimmick as G
    ko = lang == "ko"
    ref = a.get("card", "this")
    who = ref_word(a, lang)
    k = str(a.get("key") or "count")
    if op == "card_var_new":
        return f"{who}에 {k}{_jj(k, '을', '를')} 만듭니다 (처음 값 {V('amount')})." if ko else f"Give {who} {k} ({V('amount')})."
    if op == "card_var_remove":
        return f"{who}의 {k}{_jj(k, '을', '를')} 지웁니다." if ko else f"Remove {k} from {who}."
    if op in ("card_number_edit", "card_cost_edit", "card_damage_edit"):
        cost = a.get("stat", "cost") == "cost" if op == "card_number_edit" else op == "card_cost_edit"
        stat = a.get("stat", "cost") if op == "card_number_edit" else ("cost" if cost else "damage")
        name = dict(CARD_STATS).get(stat, stat) if ko else CARD_STAT_EN.get(stat, stat)
        duration = a.get("duration", "combat") if op == "card_number_edit" else (a.get("cost_duration", "combat") if cost else "combat")
        when = dict(COST_DURATIONS).get(duration, "이번 전투") if ko else {"combat": "this combat", "turn": "this turn", "played": "until played"}.get(duration, "this combat")
        mode = a.get("edit_mode", "add")
        if ko:
            verb = "으로 설정합니다" if mode == "set" else "만큼 변경합니다"
            return f"{when} {who}의 {name}{_jj(name, '을', '를')} {V('amount')}{verb}."
        return f"{'Set' if mode == 'set' else 'Change'} {who}'s {name} {'to' if mode == 'set' else 'by'} {V('amount')} {when}."
    if op == "card_do":
        act, n = pos_n(a.get("action"), a.get("action_n"))
        if ko:
            return f"{who}{_jj(who, '을', '를')} {_ACT_KO.get(act, '').replace('{n}', nth_word(n, 'ko'))}."
        return _ACT_EN.get(act, "").replace("{w}", who).replace("{n}", nth_word(n, "en"))
    if op == "card_ref_keyword":
        kn = M.KEYWORD_NAMES.get(lang, M.KEYWORD_NAMES["en"]).get(a.get("keyword"), str(a.get("keyword")))
        add = a.get("action", "add") == "add"
        if ko:
            return f"{who}에 [gold]{kn}[/gold]{_jj(kn, '을', '를')} {'부여합니다' if add else '제거합니다'}."
        return f"{who[0].upper() + who[1:]} {'gains' if add else 'loses'} [gold]{kn}[/gold]."
    if op == "card_tag":
        t = G.find_tag(project, a.get("tag") or "") if project else None
        tn = G._txt(t, "name", lang) if t else str(a.get("tag") or "?")
        add = a.get("action", "add") == "add"
        if ko:
            return f"{who}{_jj(who, '이', '가')} [gold]{tn}[/gold] 카드가 {'됩니다' if add else '아니게 됩니다'}."
        return f"{who[0].upper() + who[1:]} {'becomes' if add else 'is no longer'} a [gold]{tn}[/gold] card."
    if op == "card_enchant":
        en = a.get("enchant") or "Inky"
        return f"{who}에 [gold]{en}[/gold] {V('amount')}{_jj(V('amount'), '을', '를')} 인챈트합니다." if ko else             f"Enchant {who} with [gold]{en}[/gold] {V('amount')}."
    if op == "card_enchant_clear":
        return f"{who}의 인챈트를 없앱니다." if ko else f"Remove the enchantment from {who}."
    if op == "add_card_pos":
        if a.get("card") == "this":
            nm = "이 카드의 복사본" if ko else "a copy of this card"
        else:
            c = next((x for x in project.get("cards", []) if x["id"] == a.get("card")), None)
            nm = f"[gold]{M.text(c, 'name', lang)}[/gold]" if c else str(a.get("card"))
        where = _pos_word(a.get("pos"), project, lang, card)
        if ko:
            return f"{nm} {V('count')}장을 뽑을 카드 더미 {where}에 넣습니다."
        return f"Put {V('count')} {nm} into your draw pile ({where})."
    if op == "draw_bottom":
        where = _pos_word(a.get("pos"), project, lang, card)
        return f"뽑을 카드 더미 {where} 카드부터 {V('count')}장을 뽑습니다." if ko else \
            f"Draw {V('count')} card(s) starting {where} of your draw pile."
    return ""


def _fmt(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return str(int(f)) if f.is_integer() else str(f)


# ---------------------------------------------------------------------------
# 설명문 자동 생성
# ---------------------------------------------------------------------------
def describe(blocks, project, owner_kind, lang="ko", item=None):
    if lang == "zh":
        from card_zh import blocks_text
        return blocks_text(blocks, project, owner_kind == "card")
    card = owner_kind == "card"
    out = []
    for b in blocks or []:
        s = _describe_one(b, project, owner_kind, lang, card, item)
        if s:
            out.append(s)
    return " ".join(out)


def _describe_one(b, project, owner_kind, lang, card, item):
    b = expand_compact(b)
    a = b.get("args", {})
    V = lambda k: value_label(a.get(k), project, lang, card)  # noqa: E731
    W = lambda k: (WHO if lang == "ko" else WHO_EN).get(a.get(k, "self"), "")  # noqa: E731
    op = b["op"]
    ko = lang == "ko"
    import modgen as M
    damage_name = M.block_number_name(item, b) if owner_kind == "card" else None
    if damage_name:
        original_v = V
        V = lambda k: "{" + damage_name + ":diff()}" if k == "amount" else original_v(k)
    if op == "aura_power_amount":
        meta=M.power_meta(project,a.get("power_filter")) if a.get("power_filter") not in (None,"Any") else None
        name=(meta or {}).get("ko", "모든 파워")
        return f"조건에 맞는 다른 카드가 부여하는 {name}의 중첩을 {V('amount')}만큼 보정합니다. 이미 부여한 파워는 유지됩니다." if ko else f"Modify matching cards' applied power stacks by {V('amount')}."
    if op == "aura_card_effect":
        import gimmick as G
        source = dict(PILES).get(a.get("active_pile", "Hand"), "손패")
        target = dict([("Any", "모든 더미")] + PILES).get(a.get("target_pile", "Any"), "모든 더미")
        match = dict(G.tag_play_filters(project or {})).get(a.get("filter", "Any"), "아무 카드")
        body = describe(b.get("body") or [], project, owner_kind, lang)
        return f"이 카드가 {source}에 있을 때 {target}의 다른 {match} 카드를 사용하면: {body}" if ko else f"While in {a.get('active_pile','Hand')}, when another matching card is played: {body}"
    if op == "hand_aura_stat":
        import gimmick as G
        label = dict(G.tag_play_filters(project or {})).get(a.get("filter", "Any"), a.get("filter", "Any"))
        stat = {"cost":"비용", "damage":"피해량", "block":"방어도"}.get(a.get("stat", "cost"), "수치")
        if ko:
            target_pile = dict([("Any", "모든 더미")] + PILES).get(a.get("target_pile", "Any"), "선택한 더미")
            return f"이 카드가 {dict(PILES).get(a.get('active_pile', 'Hand'), '선택한 더미')}에 있는 동안 {target_pile}에 있는 다른 카드의 {stat}을 {V('amount')}만큼 보정합니다 ({label}). 해당 더미를 떠나면 해제됩니다."
        return f"While in {a.get('active_pile', 'Hand')}, modify other cards' {a.get('stat', 'cost')} by {V('amount')} ({a.get('filter', 'Any')})."
    if op == "damage":
        hits = int(a.get("hits", 1) or 1)
        times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
        who = "" if a.get("who") == "target" else (f"{W('who')}에게 " if ko else "")
        return f"{who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다." if ko else \
            f"Deal {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
    if op == "card_attack":
        return f"{W('who')}에게 공격 피해 {V('amount')}를 {value_label(a.get('hits'), project, lang, card)}회 줍니다." if ko else \
            f"Attack {W('who')} for {V('amount')} damage {value_label(a.get('hits'), project, lang, card)} time(s)."
    if op == "damage_to":
        return f"생물 {a.get('creature', '')}에게 피해 {V('amount')}를 줍니다." if ko else \
            f"Deal {V('amount')} damage to {a.get('creature', '')}."
    if op == "block_to":
        return f"생물 {a.get('creature', '')}에게 방어도 {V('amount')}를 줍니다." if ko else \
            f"Give {a.get('creature', '')} {V('amount')} Block."
    if op == "heal_to":
        return f"생물 {a.get('creature', '')}의 체력을 {V('amount')} 회복합니다." if ko else \
            f"Heal {a.get('creature', '')} for {V('amount')} HP."
    if op == "block":
        return f"[gold]방어도[/gold]를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Block[/gold]."
    if op == "lose_block":
        return f"{W('who')}의 [gold]방어도[/gold]를 {V('amount')} 없앱니다." if ko else f"Remove {V('amount')} [gold]Block[/gold] from {W('who')}."
    if op == "draw":
        return f"카드를 {V('amount')}장 뽑습니다." if ko else f"Draw {V('amount')} card(s)."
    if op == "energy":
        return f"에너지를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} Energy."
    if op == "energy_to":
        return f"{a.get('player', '')}에게 에너지 {V('amount')}를 줍니다." if ko else f"Give {a.get('player', '')} {V('amount')} Energy."
    if op == "gold_to":
        return f"플레이어 {a.get('player', '')}에게 골드 {V('amount')}를 줍니다." if ko else \
            f"Give player {a.get('player', '')} {V('amount')} Gold."
    if op == "lose_block_to":
        return f"생물 {a.get('creature', '')}의 방어도 {V('amount')}를 없앱니다." if ko else \
            f"Remove {V('amount')} Block from {a.get('creature', '')}."
    if op == "kill_creature":
        return f"생물 {a.get('creature', '')}를 처치합니다." if ko else f"Kill {a.get('creature', '')}."
    if op == "add_pet_model":
        return f"생물 {a.get('pet', '')}를 동료로 추가합니다." if ko else f"Add {a.get('pet', '')} as a pet."
    if op == "lose_gold":
        return f"{a.get('player', '')}가 골드 {V('amount')}를 잃습니다." if ko else f"{a.get('player', '')} loses {V('amount')} Gold."
    if op == "end_turn":
        return f"{a.get('player', '')}의 턴을 끝냅니다." if ko else f"End {a.get('player', '')}'s turn."
    if op == "heal":
        return (f"{'' if a.get('who') == 'self' else W('who') + '의 '}체력을 {V('amount')} 회복합니다." if ko
                else f"Heal {V('amount')} HP.")
    if op == "lose_hp":
        return (f"{'' if a.get('who') == 'self' else W('who') + '이(가) '}체력을 {V('amount')} 잃습니다." if ko
                else f"Lose {V('amount')} HP.")
    if op == "max_hp":
        return f"최대 체력이 {V('amount')} 증가합니다." if ko else f"Raise your Max HP by {V('amount')}."
    if op == "gold":
        return f"골드를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Gold[/gold]."
    if op in ("apply_power", "remove_power"):
        p = _pname(project, a.get("power"), lang)
        allp = op == "remove_power" and value_label(a.get("amount"), project, lang, card) == "0"
        if op == "apply_power":
            if a.get("who") == "self":
                return f"[gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]{p}[/gold]."
            return f"{W('who')}에게 [gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 부여합니다." if ko else \
                f"Apply {V('amount')} [gold]{p}[/gold] to {W('who')}."
        amt = ("모두" if ko else "all") if allp else V("amount")
        return f"{W('who')}의 [gold]{p}[/gold]{_j(p, '을', '를')} {amt} 제거합니다." if ko else f"Remove {amt} [gold]{p}[/gold] from {W('who')}."
    if op == "remove_power_model":
        return f"파워 모델 {a.get('power', '')}를 제거합니다." if ko else f"Remove power {a.get('power', '')}."
    if op == "apply_power_to":
        p = _pname(project, a.get("power"), lang)
        return f"생물 {a.get('creature', '')}에게 [gold]{p}[/gold] {V('amount')}를 부여합니다." if ko else \
            f"Apply {V('amount')} [gold]{p}[/gold] to {a.get('creature', '')}."
    if op in ("apply_power_type", "power_apply_type"):
        return f"생물 {a.get('creature', '')}에게 파워 {a.get('power_type', '')} {V('amount')}를 부여합니다." if ko else \
            f"Apply {V('amount')} {a.get('power_type', '')} to {a.get('creature', '')}."
    if op == "power_apply_model":
        return f"파워 {a.get('power', '')} 모델을 {a.get('creature', '')}에게 {V('amount')} 적용합니다." if ko else \
            f"Apply {V('amount')} from {a.get('power', '')} to {a.get('creature', '')}."
    if op == "flash":
        return ""
    if op == "wait":
        return f"{V('duration')}초 기다립니다." if ko else f"Wait {V('duration')} seconds."
    if op == "wait_scaled":
        return f"게임 속도에 맞춰 {a.get('minimum', '')}~{a.get('maximum', '')}초 기다립니다." if ko else \
            f"Wait from {a.get('minimum', '')} to {a.get('maximum', '')} seconds, scaled to game speed."
    if op == "trigger_creature_anim":
        return f"생물 {a.get('creature', '')}의 {a.get('animation', '')} 동작을 재생합니다." if ko else \
            f"Play {a.get('animation', '')} on {a.get('creature', '')}."
    if op == "play_vfx_on_creature":
        return f"생물 {a.get('creature', '')}에 이펙트 {a.get('vfx', '')}를 재생합니다." if ko else \
            f"Play VFX {a.get('vfx', '')} on {a.get('creature', '')}."
    if op == "doom_kill":
        return f"Doom 방식으로 {a.get('creatures', '')}를 처치합니다." if ko else \
            f"Kill {a.get('creatures', '')} with Doom."
    if op == "sfx":
        return f"소리 {a.get('path', '')}를 재생합니다." if ko else f"Play sound {a.get('path', '')}."
    if op in ("card_exhaust", "card_upgrade", "card_autoplay", "card_discard", "card_add_generated"):
        card_expr = a.get("cards") if op == "card_discard" else a.get("card", "")
        action = {"card_exhaust": "소멸", "card_upgrade": "강화", "card_autoplay": "자동 사용",
                  "card_discard": "버리기", "card_add_generated": "생성"}[op]
        if op == "card_add_generated":
            action += f" → {dict(PILES).get(a.get('pile'), a.get('pile'))}"
        return f"카드 {card_expr} {action}합니다." if ko else f"{action.title()} {card_expr}."
    if op == "card_add_keyword_model":
        return f"카드 모델 {a.get('card', '')}에 키워드 {a.get('keyword', '')}를 추가합니다." if ko else \
            f"Add keyword {a.get('keyword', '')} to card model {a.get('card', '')}."
    if op == "card_preview_cards":
        return f"카드 {a.get('cards', '')}를 미리 보기합니다." if ko else f"Preview {a.get('cards', '')}."
    if op == "card_remove_combat":
        return f"카드 {a.get('cards', '')}를 전투에서 제거합니다." if ko else f"Remove {a.get('cards', '')} from combat."
    if op == "draw_to":
        return f"플레이어 {a.get('player', '')}가 카드 {V('amount')}장을 뽑습니다." if ko else \
            f"Player {a.get('player', '')} draws {V('amount')} card(s)."
    if op == "shuffle_draw_pile":
        return f"플레이어 {a.get('player', '')}의 뽑을 카드 더미를 섞습니다." if ko else \
            f"Shuffle {a.get('player', '')}'s draw pile."
    if op == "autoplay_draw_pile":
        return f"플레이어 {a.get('player', '')}의 뽑을 카드 더미에서 자동 사용합니다." if ko else \
            f"Autoplay from {a.get('player', '')}'s draw pile."
    if op == "potion_add_type":
        return f"물약 {a.get('potion_type', '')}를 지급합니다." if ko else f"Procure potion {a.get('potion_type', '')}."
    if op == "potion_add_model":
        return f"물약 모델 {a.get('potion', '')}을 지급합니다." if ko else f"Procure potion model {a.get('potion', '')}."
    if op == "potion_add_model_at":
        return f"물약 모델 {a.get('potion', '')}을 {a.get('player', '')}의 슬롯 {a.get('slot', '')}에 넣습니다." if ko else \
            f"Put potion model {a.get('potion', '')} into slot {a.get('slot', '')} for {a.get('player', '')}."
    if op == "potion_discard":
        return f"물약 {a.get('potion', '')}을 버립니다." if ko else f"Discard potion {a.get('potion', '')}."
    if op == "card_set_cost_until_played":
        return f"카드 {a.get('card', '')}의 비용을 {V('amount')}(으)로 설정해 사용 시까지 유지합니다." if ko else \
            f"Set {a.get('card', '')}'s cost to {V('amount')} until played."
    if op == "card_free_this_turn":
        return f"카드 {a.get('card', '')}를 이번 턴에 무료로 만듭니다." if ko else \
            f"Make {a.get('card', '')} free this turn."
    if op == "card_notify_cost_changed":
        return f"카드 {a.get('card', '')}의 비용 변경을 알립니다." if ko else \
            f"Notify cost change for {a.get('card', '')}."
    if op == "card_upgrade_internal":
        return f"카드 {a.get('card', '')}의 내부 강화를 적용합니다." if ko else \
            f"Apply the internal upgrade to {a.get('card', '')}."
    if op == "card_finalize_upgrade_internal":
        return f"카드 {a.get('card', '')}의 내부 강화를 완료합니다." if ko else \
            f"Finalize the internal upgrade for {a.get('card', '')}."
    if op == "card_transform_to":
        return f"카드 {a.get('card', '')}를 {a.get('card_type', '')}(으)로 변환합니다." if ko else \
            f"Transform {a.get('card', '')} into {a.get('card_type', '')}."
    if op == "stun":
        return f"{a.get('creature', '')}을(를) 기절시킵니다." if ko else f"Stun {a.get('creature', '')}."
    if op == "card_keyword":
        import modgen as M
        keyword = M.KEYWORD_NAMES["ko" if ko else "en"].get(a.get("keyword"), a.get("keyword"))
        verb = "부여" if a.get("action") == "add" else "제거"
        return f"카드 {a.get('card', '')}에 {keyword}를 {verb}합니다." if ko else \
            f"{verb.title()} {keyword} on {a.get('card', '')}."
    if op == "card_add_pile":
        return f"카드 식 {a.get('cards', '')}를 {a.get('pile', '')}에 추가합니다." if ko else \
            f"Add {a.get('cards', '')} to {a.get('pile', '')}."
    if op == "card_add_generated_many":
        return f"생성 카드 목록을 {a.get('pile', '')}에 넣습니다." if ko else f"Add generated cards to {a.get('pile', '')}."
    if op == "card_preview":
        return "카드 미리보기를 표시합니다." if ko else "Preview the cards."
    if op == "modify_power_amount":
        return f"파워 {a.get('power', '')} 수치를 {V('amount')}만큼 변경합니다." if ko else \
            f"Modify {a.get('power', '')} by {V('amount')}."
    if op == "set_current_hp":
        return f"{a.get('creature', '')}의 현재 체력을 {V('amount')}로 설정합니다." if ko else \
            f"Set {a.get('creature', '')} HP to {V('amount')}."
    if op == "orb_channel_model":
        return f"구체 모델 {a.get('orb', '')}를 영창합니다." if ko else f"Channel orb {a.get('orb', '')}."
    if op == "orb_channel_type":
        return f"구체 유형 {a.get('orb_type', '')}를 영창합니다." if ko else f"Channel orb type {a.get('orb_type', '')}."
    if op == "orb_passive_model":
        return f"구체 모델 {a.get('orb', '')}의 지속 효과를 발동합니다." if ko else f"Trigger passive of orb {a.get('orb', '')}."
    if op == "orb_slots_to":
        return f"플레이어 {a.get('player', '')}의 구체 슬롯을 {V('amount')}개 추가합니다." if ko else \
            f"Add {V('amount')} orb slot(s) to player {a.get('player', '')}."
    if op == "hand":
        import gimmick as G
        act = dict(HAND_ACTIONS).get(a.get("action"), "")
        ctype = a.get("ctype") or "Any"
        if ko:
            what = G.filter_word(project, ctype, "ko")
            if a.get("which") == "all":
                return f"손패의 모든 {what}를 {act}합니다." if act != "버리기" else f"손패의 모든 {what}를 버립니다."
            return f"손패의 무작위 {what} {V('count')}장을 {act if act != '버리기' else '버립'}{'합니다' if act != '버리기' else '니다'}."
        acte = {"upgrade": "Upgrade", "exhaust": "Exhaust", "discard": "Discard"}.get(a.get("action"))
        cte = G.filter_word(project, ctype, "en", plural=True)
        return f"{acte} all {cte} in your hand." if a.get("which") == "all" else \
            f"{acte} {V('count')} random {cte} in your hand."
    if op in ("keyword_this", "keyword_cards"):
        import modgen as M
        import gimmick as G
        kn = M.KEYWORD_NAMES["ko" if ko else "en"].get(a.get("keyword"), a.get("keyword"))
        add = a.get("action", "add") == "add"
        if op == "keyword_this":
            if ko:
                return (f"이 카드에 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 부여합니다." if add else
                        f"이 카드의 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 제거합니다.")
            return f"This card gains [gold]{kn}[/gold]." if add else f"This card loses [gold]{kn}[/gold]."
        ctype = a.get("ctype") or "Any"
        if ko:
            where = dict(KW_WHERE).get(a.get("where"), "손패")
            what = G.filter_word(project, ctype, "ko")
            whom = f"{where}의 모든 {what}" if a.get("which") == "all" else f"{where}의 무작위 {what} {V('count')}장"
            return (f"{whom}에 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 부여합니다." if add else
                    f"{whom}에서 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 제거합니다.")
        where = {"hand": "your hand", "draw": "your draw pile", "discard": "your discard pile",
                 "all": "all your piles"}.get(a.get("where"), "your hand")
        cte = G.filter_word(project, ctype, "en", plural=True)
        whom = f"all {cte} in {where}" if a.get("which") == "all" else f"{V('count')} random {cte} in {where}"
        return f"Give {whom} [gold]{kn}[/gold]." if add else f"Remove [gold]{kn}[/gold] from {whom}."
    if op in ("set_var", "change_var"):
        n = str(a.get("name", "a"))
        amt = a.get("amount") or {}
        neg = op == "change_var" and amt.get("t") == "num" and float(amt.get("v", 0) or 0) < 0
        val = value_label(dict(amt, v=-float(amt.get("v", 0))) if neg else amt, project, lang, card)
        if op == "set_var":
            return f"{n}{_jj(n, '을', '를')} {val}{_ro(val)} 정합니다." if ko else f"Set {n} to {val}."
        if neg:
            return f"{n}에서 {val}{_jj(val, '을', '를')} 뺍니다." if ko else f"Subtract {val} from {n}."
        return f"{n}에 {val}{_jj(val, '을', '를')} 더합니다." if ko else f"Add {val} to {n}."
    if op in ("card_var_new", "card_var_remove", "card_number_edit", "card_cost_edit", "card_damage_edit", "card_do", "card_ref_keyword", "card_tag", "card_enchant",
              "card_enchant_clear", "add_card_pos", "draw_bottom"):
        return _describe_cardref(b, op, a, project, lang, card, V)
    if op in ("card_state_set", "card_state_change"):
        k = str(a.get("key") or "count")
        who = ref_word(a, lang)
        amt = a.get("amount") or {}
        neg = op == "card_state_change" and amt.get("t") == "num" and float(amt.get("v", 0) or 0) < 0
        val = value_label(dict(amt, v=-float(amt.get("v", 0))) if neg else amt, project, lang, card)
        if op == "card_state_set":
            return f"{who}의 {k}{_jj(k, '을', '를')} {val}{_ro(val)} 정합니다." if ko else f"Set {who}'s {k} to {val}."
        if neg:
            return f"{who}의 {k}에서 {val}{_jj(val, '을', '를')} 뺍니다." if ko else f"Subtract {val} from {who}'s {k}."
        return f"{who}의 {k}에 {val}{_jj(val, '을', '를')} 더합니다." if ko else f"Add {val} to {who}'s {k}."
    if op == "add_card":
        import modgen as M
        if a.get("card") == "this":
            nm = "이 카드의 복사본" if ko else "a copy of this card"
        else:
            c = next((x for x in project.get("cards", []) if x["id"] == a.get("card")), None)
            nm = f"[gold]{M.text(c, 'name', lang)}[/gold]" if c else a.get("card")
        pile = dict(PILES).get(a.get("pile"), "") if ko else {"Hand": "your hand", "Draw": "your draw pile",
                                                              "Discard": "your discard pile"}.get(a.get("pile"))
        return f"{nm} {V('count')}장을 {pile}에 넣습니다." if ko else f"Add {V('count')} {nm} into {pile}."
    if op in ("if", "if_else"):
        c = a.get("cond") or {}
        cond = cond_label(c, project, lang, card)
        body = describe(b.get("body"), project, owner_kind, lang, item)
        if ko and c.get("t") == "cmp":
            s = f"{cmp_text(c, project, lang, card, conditional=True)} {body}"   # '3 이상이면', '3을 초과하면', '3과 같으면'
        elif ko and cond.endswith("있음"):
            s = f"{cond[:-2]}있으면 {body}"       # '살아 있음' → '살아 있으면'
        elif ko and cond.endswith("확률"):
            s = f"{cond}로 {body}"                # '50% 확률로'
        else:
            s = f"{cond}이면 {body}" if ko else f"If {cond}: {body}"
        if op == "if_else" and b.get("else"):
            s += (" 아니면 " if ko else " Otherwise: ") + describe(b.get("else"), project, owner_kind, lang, item)
        return s
    if op == "repeat":
        return (f"{V('times')}번: " if ko else f"{V('times')} times: ") + describe(b.get("body"), project, owner_kind, lang, item)
    if op == "each_enemy":
        return ("모든 적에게 각각: " if ko else "For each enemy: ") + describe(b.get("body"), project, owner_kind, lang, item)
    if op == "random_enemy":
        return ("무작위 적 1명에게: " if ko else "To a random enemy: ") + describe(b.get("body"), project, owner_kind, lang, item)
    if op in ("filtered_enemies", "filtered_players"):
        condition = a.get("enemy_filter", "power")
        power = M.power_meta(project, a.get("power", "Weak"))
        name = (power or {}).get(lang, a.get("power", "Weak"))
        label = {"all": "모든 적", "power": f"{name} 보유 적", "no_power": f"{name} 미보유 적",
                 "hp_below": f"체력 {V('limit')}% 이하인 적", "hp_above": f"체력 {V('limit')}% 이상인 적"}.get(condition, "조건에 맞는 적")
        mode = {"random": "무작위", "choose": "직접 선택", "all": "모두"}.get(a.get("enemy_mode"), "무작위")
        selection = "모두" if a.get("enemy_mode") == "all" else f"{mode} 최대 {V('count')}명"
        group = a.get("conditions")
        if op == "filtered_players" or (group and (group.get("t") != "group" or group.get("items"))):
            label = "플레이어" if op == "filtered_players" else "적"
            detail = cond_label(group, project, lang, card) if group else "조건 없음"
            if not ko:
                label = "players" if op == "filtered_players" else "enemies"
                selection = "all" if a.get("enemy_mode") == "all" else ("randomly select" if a.get("enemy_mode","random") == "random" else "choose") + f" up to {V('count')}"
                return f"From {label} matching {detail}, {selection}; for each: " + describe(b.get("body"), project, owner_kind, lang, item)
            return f"{detail} 조건을 만족한 {label} 중 {selection}에게 각각: " + describe(b.get("body"), project, owner_kind, lang, item)
        if not ko:
            label = {"all": "enemies", "power": f"enemies with {name}", "no_power": f"enemies without {name}",
                     "hp_below": f"enemies at {V('limit')}% HP or less", "hp_above": f"enemies at {V('limit')}% HP or more"}.get(condition, "matching enemies")
            selection = "all" if a.get("enemy_mode") == "all" else ("randomly select" if a.get("enemy_mode", "random") == "random" else "choose") + f" up to {V('count')}"
            return f"From {label}, {selection}; for each: " + describe(b.get("body"), project, owner_kind, lang, item)
        return f"{label} 중 {selection}에게 각각: " + describe(b.get("body"), project, owner_kind, lang, item)
    # ---- 기믹 ----
    if op == "summon":
        n = _summon_name(project, a.get("summon"), lang)
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} 소환합니다." if ko else f"Summon [gold]{n}[/gold]."
    if op == "command":
        n = _summon_name(project, a.get("summon"), lang)
        if a.get("summon") == "*":
            return "모든 소환수가 즉시 행동합니다." if ko else "All your summons act immediately."
        return f"[gold]{n}[/gold]{_j(n, '이', '가')} 즉시 행동합니다." if ko else f"[gold]{n}[/gold] acts immediately."
    if op == "unsummon":
        n = _summon_name(project, a.get("summon"), lang)
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} 돌려보냅니다." if ko else f"Dismiss [gold]{n}[/gold]."
    if op == "pay":
        p = _pname(project, a.get("power"), lang)
        body = describe(b.get("body"), project, owner_kind, lang, item)
        els = describe(b.get("else"), project, owner_kind, lang, item)
        s = f"[gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 소모할 수 있으면 소모하고 {body}" if ko else \
            f"If you can, spend {V('amount')} [gold]{p}[/gold] to: {body}"
        if els:
            s += (f" 아니면 {els}" if ko else f" Otherwise: {els}")
        return s
    if op == "choice":
        opts = [(_label_text(a.get(k), lang), b.get(bk)) for k, bk in (("opt1", "body"), ("opt2", "else"), ("opt3", "third"))]
        opts = [(n, body) for n, body in opts if n]
        if ko:
            return "하나를 고릅니다: " + " / ".join(
                f"[gold]{n}[/gold]({describe(body, project, owner_kind, lang, item).rstrip('.')})" for n, body in opts) + "."
        return "Choose one: " + " / ".join(
            f"[gold]{n}[/gold] ({describe(body, project, owner_kind, lang, item).rstrip('.')})" for n, body in opts) + "."
    if op == "picked_action":
        action, act_n = pos_n(a.get("action"), a.get("action_n"))
        if action == "draw_at":
            return f"고른 카드를 뽑을 카드 더미 {nth_word(act_n, 'ko')}에 놓습니다." if ko else \
                f"Put it {nth_word(act_n, 'en')} of your draw pile."
        if ko:
            return f"고른 카드에 {dict(PICK_ACTIONS).get(action, '')}."
        return {"hand": "Move it to your hand.",
                "exhaust": "Exhaust it.", "discard": "Discard it.", "upgrade": "Upgrade it.",
                "random_transform": "Transform it into a random card."}.get(action, "")
    if op in ("pick", "random_transform", "pick_transform", "pick_each", "random_each"):
        import gimmick as G
        pile_ko = dict(PICK_PILES).get(a.get("pile"), "")
        pile_en = {"Hand": "your hand", "Draw": "your draw pile", "Discard": "your discard pile",
                   "Exhaust": "your exhaust pile"}.get(a.get("pile"), "")
        if op == "random_transform":
            import modgen as M
            result = a.get("result_filter", "Any")
            if result.startswith("kw:"):
                kw = result[3:]
                name = dict(M.CARD_KEYWORDS).get(kw, kw) if ko else kw
                pool = f"{name} 키워드가 있는 카드" if ko else f"cards with {name}"
            else:
                pool = G.filter_word(project, result, lang, plural=True)
            selected = M.transform_pools(project).get(a.get("result_pool"))
            if a.get("result_pool") and selected:
                pool = selected[0] + " " + pool
            if ko:
                return f"{pile_ko}의 {G.filter_word(project, a.get('ctype'), 'ko')} 중 무작위 {V('count')}장을 {pool} 중 한 장으로 변화시킵니다."
            return f"Transform {V('count')} random {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en} into random {pool}."
        if op == "random_each":
            detail = describe(b.get("body"), project, owner_kind, lang, item)
            if (a.get("conditions") or {}).get("items"):
                detail = ("선택 조건: " if ko else "Selection conditions: ") + cond_label(a['conditions'], project, lang, card) + ". " + detail
            return (f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} 무작위 {V('count')}장을 골라 한 장마다 실행합니다. {detail}" if ko else
                    f"Choose {V('count')} random {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en}. For each chosen card: {detail}")
        if op == "pick_each":
            detail = describe(b.get("body"), project, owner_kind, lang, item)
            if (a.get("conditions") or {}).get("items"):
                detail = ("선택 조건: " if ko else "Selection conditions: ") + cond_label(a['conditions'], project, lang, card) + ". " + detail
            return (f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} {V('count')}장을 골라 한 장마다 실행합니다. {detail}" if ko else
                    f"Choose {V('count')} {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en}. For each chosen card: {detail}")
        if op == "pick_transform":
            import modgen as M
            target = next((c for c in project.get("cards", []) if c["id"] == a.get("card")), None)
            name = M.text(target, "name", lang) if target else ("이 카드" if ko else "this card")
            if ko:
                return f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} {V('count')}장을 골라 {name}(으)로 변화시킵니다."
            return f"Choose {V('count')} {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en} and transform them into {name}."
        if ko:
            act_key, act_n = pos_n(a.get("action"), a.get("action_n"))
            act = {"hand": "손으로 가져옵니다", "draw_at": f"뽑을 카드 더미 {nth_word(act_n, 'ko')}에 놓습니다", "exhaust": "소멸시킵니다",
                   "discard": "버립니다", "random_transform": "무작위 카드로 변화시킵니다", "upgrade": "강화합니다"}.get(act_key, "")
            return f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} {V('count')}장을 골라 {act}."
        act_key, act_n = pos_n(a.get("action"), a.get("action_n"))
        act = {"hand": "put it into your hand", "draw_at": f"put it {nth_word(act_n, 'en')} of your draw pile", "exhaust": "Exhaust it",
               "discard": "discard it", "random_transform": "transform it into a random card", "upgrade": "Upgrade it"}.get(act_key, "")
        return f"Choose {V('count')} {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en} and {act}."
    if op in ("channel", "evoke", "orb_passive_all", "orb_slots", "orb_grow", "stars", "forge",
              "osty_summon", "osty_attack", "osty_kill"):
        return _describe_class(b, op, a, project, lang, V, W)
    if op.startswith("pet_"):
        n = _pet_name(project, a.get("pet"), lang)
        if op == "pet_summon":
            return (f"[gold]{n}[/gold]{_j(n, '을', '를')} [gold]소환[/gold]합니다 ({V('amount')})." if ko else
                    f"[gold]Summon[/gold] {V('amount')} [gold]{n}[/gold].")
        if op == "pet_attack":
            hits = int(a.get("hits", 1) or 1)
            times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
            if ko:
                who = "" if a.get("who") == "target" else f"{W('who')}에게 "
                return f"[gold]{n}[/gold]{_j(n, '이', '가')} {who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다."
            return f"[gold]{n}[/gold] deals {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
        if op == "pet_act":
            return f"[gold]{n}[/gold]{_j(n, '이', '가')} 즉시 행동합니다." if ko else f"[gold]{n}[/gold] acts immediately."
        if op == "pet_kill":
            return f"[gold]{n}[/gold]{_j(n, '을', '를')} 희생합니다." if ko else f"Sacrifice [gold]{n}[/gold]."
    if op == "fx":
        return ""  # 보이기만 하는 연출이라 설명에는 넣지 않음
    if op in ("button_on", "button_off"):
        import fxbtn
        bt = fxbtn.find_button(project, a.get("button")) or {}
        n = (bt.get(f"label_{lang}") or bt.get("label_ko") or a.get("button") or "?")
        if op == "button_on":
            return f"[gold]{n}[/gold] 버튼이 생깁니다." if ko else f"Gain the [gold]{n}[/gold] button."
        return f"[gold]{n}[/gold] 버튼이 사라집니다." if ko else f"Lose the [gold]{n}[/gold] button."
    if op == "delayed":
        body = describe(b.get("body"), project, owner_kind, lang, item)
        tv = V("times")
        rep = "" if tv == "1" else (f" ({tv}번)" if ko else f" ({tv} times)")
        if a.get("when") == "end":
            return (f"이번 턴이 끝날 때{rep}: {body}" if ko else f"At the end of this turn{rep}: {body}")
        return (f"다음 턴 시작 시{rep}: {body}" if ko else f"At the start of your next turn{rep}: {body}")
    return ""


# ---------------------------------------------------------------------------
# C# 로 변환
# ---------------------------------------------------------------------------
class _Gen:
    def __init__(self, project, C, prefix="Blk", extras=None, allow_event=False):
        self.project = project
        self.C = C
        self.n = 0
        self.selected_cards = []
        self.its = []        # 반복 안의 '그 적' 변수 이름 스택
        self.errors = []
        self.prefix = prefix          # 블록이 만드는 클래스(선택지 카드·예약 파워) 이름 앞부분
        self.extras = extras          # 그 클래스들을 모을 목록 (None 이면 버림)
        self.allow_event = allow_event
        self.no_vars = False          # 사용 조건처럼 변수를 쓸 수 없는 곳
        self.k = 0

    def uid(self, base):
        self.n += 1
        return f"{base}{self.n}"

    def cls_name(self, kind):
        import gimmick as G
        name = f"{self.prefix}{kind}{G.letters(self.k).capitalize()}"  # 대문자가 연달아 오지 않게 (게임 ID 규칙)
        self.k += 1
        return name

    def helper(self):
        import gimmick as G
        return G.helper(self.project)

    # ---- 생물 ----
    def creature(self, who):
        C = self.C
        if who == "self":
            return C.me
        if who == "target":
            if C.kind == "relic" or not C.other:
                self.errors.append("모든 적의 수치·조건은 '모든 적 각각에게' 안에서 '그 적'을 선택하세요." if getattr(C, "event_target", None) == "all" else "이 시점에는 지정된 대상이 없습니다. 자신·모든 적·무작위 적을 선택하세요.")
                return "null"
            return C.other
        if who == "it":
            if not self.its:
                self.errors.append("'그 적'은 '모든 적 각각에게' / '무작위 적 1명에게' 블록 안에서만 쓸 수 있습니다.")
                return "null"
            return self.its[-1]
        return "null"

    def card_ref(self, ref, n=None):
        """카드 인스턴스 참조 -> C# 식 (CardModel). 같은 카드가 여러 장이어도 그 한 장.
        뽑을 더미 맨 위/아래는 없을 수 있다 (null)."""
        ref, n = pos_n(ref, n)
        if ref == "draw_at":
            if n == 0:
                self.errors.append("뽑을 카드 더미 N번째: N 은 1(맨 위)부터, 아래에서 셀 때는 -1(맨 아래)부터입니다.")
                return "null"
            return f"{self.helper()}.DrawPileAt({self.player()}, {n})"
        if ref == "picked":
            if self.selected_cards:
                return self.selected_cards[-1]
            if getattr(self, "_replacement", None):
                return self._replacement
            self.errors.append("'고른 카드'는 '골라 한 장마다 실행' 블록 안에서만 쓸 수 있습니다.")
            return "null"
        if self.C.kind != "card":
            self.errors.append("'이 카드'는 카드의 블록에서만 쓸 수 있습니다. 다른 곳에서는 '고른 카드'를 쓰세요.")
            return "null"
        return "this"

    def with_card(self, ref, ind, fn):
        """카드 참조를 확인하고 (null 이면 건너뜀) fn(변수, 들여쓰기) 줄을 감싼다."""
        expr = self.card_ref(*ref) if isinstance(ref, tuple) else self.card_ref(ref)
        if expr == "null":
            return []
        if expr == "this" or expr.isidentifier():
            return fn(expr, ind)
        cv = self.uid("cr")
        return [f"{ind}if ({expr} is {{ }} {cv})", f"{ind}{{"] + fn(cv, ind + "    ") + [f"{ind}}}"]

    def card_is(self, cv, f):
        import gimmick as G
        f = f or "Any"
        if f.startswith("kw:"):
            return f"{cv}.Keywords.Contains(CardKeyword.{f[3:]})"
        if f == "enchanted":
            return f"({cv}.Enchantment != null)"
        if f == "upgraded":
            return f"{cv}.IsUpgraded"
        return G.filter_expr(self.project, f, cv)

    def enemies(self):
        C = self.C
        return "OwnerEnemies()" if C.kind == "power" else f"{C.me}.CombatState!.HittableEnemies"

    def rng(self):
        C = self.C
        return f"{C.me}.CombatState!.RunState.Rng.CombatTargets"

    def player(self):
        return self.C.player

    # ---- 값 ----
    def val(self, v):
        if not isinstance(v, dict):
            return "0m"
        t = v.get("t")
        if t == "num":
            base = _dec(v.get("v", 0))
            up = v.get("up") or 0
            if up and self.C.kind == "card":
                return f"(IsUpgraded ? {_dec(float(v.get('v', 0)) + float(up))} : {base})"
            return base
        if t == "stack":
            import modgen as M
            pm = M.power_meta(self.project, v.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {v.get('power')}")
                return "0m"
            cr = self.creature(v.get("who", "self"))
            return f"(decimal)({cr}?.GetPowerAmount<{pm['cls']}>() ?? 0)" if cr != self.C.me else \
                f"(decimal){cr}.GetPowerAmount<{pm['cls']}>()"
        if t == "stat":
            cr = self.creature(v.get("who", "self"))
            prop = {"hp": "CurrentHp", "maxhp": "MaxHp", "block": "Block"}.get(v.get("stat"), "CurrentHp")
            return f"(decimal)({cr}?.{prop} ?? 0)"
        if t == "count":
            w = v.get("what")
            if w == "enemies":
                return f"(decimal){self.enemies()}.Count"
            pile = {"hand": "Hand", "draw": "DrawPile", "discard": "DiscardPile", "exhaust": "ExhaustPile"}.get(w, "Hand")
            return f"(decimal)({self.player()}?.PlayerCombatState?.{pile}.Cards.Count ?? 0)"
        if t == "energy":
            return f"(decimal)({self.player()}?.PlayerCombatState?.Energy ?? 0)"
        if t == "amount":
            if self.C.kind != "power":
                self.errors.append("'이 파워의 스택 수'는 파워에서만 쓸 수 있습니다.")
                return "0m"
            return "(decimal)Amount"
        if t == "round":
            return f"(decimal)({self.C.me}.CombatState?.RoundNumber ?? 0)"
        if t == "rand":
            lo, hi = self.val(v.get("min")), self.val(v.get("max"))
            return f"(decimal){self.rng()}.NextInt((int)({lo}), (int)({hi}) + 1)"
        if t == "var":
            if self.no_vars:
                self.errors.append("여기서는 변수를 쓸 수 없습니다.")
                return "0m"
            return "v_" + _ident(v.get("name", "a"))
        if t == "card_state":
            ref = self.card_ref(v.get("card", "this"), v.get("card_n"))
            return f"{self.helper()}.CardState({ref}, {_cs_str(v.get('key'))})" if ref != "null" else "0m"
        if t == "played":
            import gimmick as G
            f = G.filter_expr(self.project, v.get("filter", "Any"), "c_")
            return f"(decimal){self.helper()}.Played({self.player()}, {'true' if v.get('scope', 'turn') == 'turn' else 'false'}, c_ => {f})"
        if t == "summons":
            return f"(decimal){self.helper()}.SummonCount({self.C.me})"
        if t in ("orb_passive", "orb_evoke"):
            if self.C.kind != "orb":
                self.errors.append("'이 구체의 지속/발현 수치'는 구체 블록에서만 쓸 수 있습니다.")
                return "0m"
            return "PassiveVal" if t == "orb_passive" else "EvokeVal"
        if t == "orbs":
            import gimmick as G
            q = f"{self.player()}?.PlayerCombatState?.OrbQueue"
            w = v.get("what", "count")
            if w == "slots":
                return f"(decimal)({q}?.Capacity ?? 0)"
            if w == "empty":
                return f"(decimal)(({q}?.Capacity ?? 0) - ({q}?.Orbs.Count ?? 0))"
            om = G.orb_meta(self.project, v.get("orb")) if v.get("orb") else None
            if om:
                return f"(decimal)({q}?.Orbs.Count(o_ => o_ is {om['cls']}) ?? 0)"
            return f"(decimal)({q}?.Orbs.Count ?? 0)"
        if t == "stars":
            return f"(decimal)({self.player()}?.PlayerCombatState?.Stars ?? 0)"
        if t == "pet":
            import pets as PT
            if not PT.find_pet(self.project, v.get("pet")):
                self.errors.append(f"없는 동료: {v.get('pet')}")
                return "0m"
            H, cls = PT.helper(self.project), PT.pet_cls(self.project, v.get("pet"))
            prop = "MaxHp" if v.get("what") == "maxhp" else "CurrentHp"
            return f"(decimal)({H}.Alive<{cls}>({self.player()}) ? {H}.Find<{cls}>({self.player()})!.{prop} : 0)"
        if t == "dynvar":
            if self.C.kind != "card" or not any(x.get("name") == v.get("name") for x in self.C.item.get("raw_vars", [])):
                self.errors.append(f"원본 변수 {v.get('name')} 이(가) 이 카드에 없습니다.")
                return "0m"
            prop = v.get("prop") or "BaseValue"
            cast = "(decimal)" if prop == "IntValue" else ""
            return f'{cast}DynamicVars["{v.get("name")}"].{prop}'
        if t == "src":
            code = str(v.get("code") or "").strip()
            if not code:
                self.errors.append("직접 수식 칸이 비어 있습니다.")
                return "0m"
            return f"(decimal)({code})"
        if t == "star_x":
            if self.C.kind != "card":
                self.errors.append("'X (쓴 별)'은 카드에서만 쓸 수 있습니다.")
                return "0m"
            return "(decimal)ResolveStarXValue()"
        if t == "energy_x":
            if self.C.kind != "card" or not (self.C.item or {}).get("x_cost"):
                self.errors.append("'X (쓴 에너지)'는 'X 비용' 카드에서만 쓸 수 있습니다 (카드 탭에서 X 비용을 켜세요).")
                return "0m"
            return "(decimal)XCount"
        if t == "osty":
            pl = self.player()
            prop = "MaxHp" if v.get("what") == "maxhp" else "CurrentHp"
            return f"(decimal)(({pl}?.IsOstyAlive ?? false) ? {pl}!.Osty!.{prop} : 0)"
        if t == "event":
            if not self.allow_event:
                self.errors.append("'그 수치'는 파워의 '넘칠 때' / '기준치 도달 시' 블록에서만 쓸 수 있습니다.")
                return "0m"
            return "ev_"
        if t == "op":
            o = v.get("op", "+")
            a, b = self.val(v.get("a")), self.val(v.get("b"))
            if o == "/":
                return f"({b} == 0m ? 0m : Math.Floor({a} / {b}))"
            return f"({a} {o} {b})"
        return "0m"

    def cond(self, c):
        if not isinstance(c, dict):
            return "false"
        t = c.get("t")
        if t == "group":
            mode = c.get("mode", "all")
            if mode not in ("all", "any"):
                self.errors.append("조건 묶음의 모두/하나 이상을 다시 선택하세요.")
                return "false"
            items = c.get("items", [])
            return "(" + (" && " if mode == "all" else " || ").join(self.cond(x) for x in items) + ")" if items else "true"
        if t == "hp_percent":
            cr = self.creature(c.get("who", "it"))
            op = c.get("op", "<=")
            if op not in dict(CMP_OPS):
                self.errors.append("체력 비율의 비교 방식을 다시 선택하세요.")
                return "false"
            return f"({cr} != null && {cr}.MaxHp > 0 && (decimal){cr}.CurrentHp * 100m {op} (decimal){cr}.MaxHp * Math.Clamp({self.val(c.get('value'))}, 0m, 100m))"
        if t in ("pile_count", "card_identity"):
            import modgen as M
            cid = c.get("card_id")
            cv = self.uid("conditionCard")
            if cid and not any(x['id'] == cid for x in self.project.get('cards', [])):
                self.errors.append(f"조건에서 지정한 카드가 없습니다: {cid}")
                return "false"
            match = f"{cv} is {M.item_cls(self.project, 'card', cid)}" if cid else self.card_is(cv, c.get('filter','Any'))
            if t == "card_identity":
                if not cid:
                    self.errors.append("조건에 사용할 카드를 고르세요.")
                    return "false"
                ref = self.card_ref("picked")
                return f"({ref} is {{ }} {cv} && {match})"
            pile = c.get("pile", "Deck")
            op = c.get("op", ">=")
            if pile not in {"Deck","Hand","Draw","Discard","Exhaust"} or op not in dict(CMP_OPS):
                self.errors.append("카드 보유 조건의 더미와 비교 방식을 다시 선택하세요.")
                return "false"
            who = c.get("who", "self")
            player = self.C.player if who == "self" else f"({self.creature(who)})?.Player"
            pv = self.uid("conditionPlayer")
            return f"({player} is {{ }} {pv} && PileType.{pile}.GetPile({pv}).Cards.Count({cv} => {match}) {op} {self.val(c.get('count'))})"
        if t == "cmp":
            return f"({self.val(c.get('a'))} {c.get('op', '>=')} {self.val(c.get('b'))})"
        if t == "chance":
            return f"({self.rng()}.NextInt(100) < (int)({self.val(c.get('pct'))}))"
        if t == "has":
            import modgen as M
            pm = M.power_meta(self.project, c.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {c.get('power')}")
                return "false"
            cr = self.creature(c.get("who", "self"))
            return f"(({cr}?.GetPowerAmount<{pm['cls']}>() ?? 0) > 0)"
        if t in ("and", "or"):
            j = "&&" if t == "and" else "||"
            return f"({self.cond(c.get('a'))} {j} {self.cond(c.get('b'))})"
        if t == "not":
            return f"(!{self.cond(c.get('a'))})"
        if t == "osty_alive":
            return f"({self.player()}?.IsOstyAlive ?? false)"
        if t == "pet_alive":
            import pets as PT
            if not PT.find_pet(self.project, c.get("pet")):
                self.errors.append(f"없는 동료: {c.get('pet')}")
                return "false"
            return f"{PT.helper(self.project)}.Alive<{PT.pet_cls(self.project, c.get('pet'))}>({self.player()})"
        if t in ("card_var_has", "card_is"):
            expr = self.card_ref(c.get("card", "this"), c.get("card_n"))
            if expr == "null":
                return "false"
            cv = self.uid("cq")
            inner = f"{self.helper()}.HasCardVar({cv}, {_cs_str(c.get('key'))})" if t == "card_var_has" else                 self.card_is(cv, c.get("filter"))
            return f"({expr} is {{ }} {cv} && {inner})"
        if t == "src":
            code = str(c.get("code") or "").strip()
            if not code:
                self.errors.append("직접 조건 칸이 비어 있습니다.")
                return "false"
            return f"({code})"
        return "false"

    def src_slot(self, s, cur):
        """직접 호출 블록의 칸 하나 -> 코드 글자. 바꾸지 않았으면 입력했던 글자 그대로."""
        kind = s.get("kind")
        if kind == "value":
            if cur == s.get("v0"):
                return "" if s.get("absent") else s.get("orig", "")
            if s.get("type") == "DynamicVar":
                if isinstance(cur, dict) and cur.get("t") == "dynvar":
                    return f'DynamicVars["{cur.get("name")}"]'
                self.errors.append(f"'{s.get('name')}' 칸은 원본 변수(DynamicVar)만 받습니다. 수치는 그 변수의 값을 바꾸세요.")
                return s.get("orig", "")
            code = self.val(cur)
            if s.get("type") == "int":
                code = f"(int)({code})"
            return s["wrap"].replace("{}", code) if s.get("absent") else code
        text = str(cur if cur is not None else "").strip()
        return text or s.get("orig", "")

    # ---- 문장 ----
    def stmts(self, blocks, ind):
        out = []
        for b in blocks or []:
            out += self.stmt(b, ind)
        return out

    def each_target(self, who, ind, body_fn):
        """who 가 모든 적/무작위 적이면 반복으로 감싼다."""
        if who == "all":
            v = self.uid("e")
            return [f"{ind}foreach (var {v} in {self.enemies()}.ToList())", f"{ind}{{"] + \
                body_fn(v, ind + "    ") + [f"{ind}}}"]
        if who == "random":
            v = self.uid("r")
            candidates = self.uid("enemies")
            return [f"{ind}{{", f"{ind}    var {candidates} = {self.enemies()}.ToList();",
                    f"{ind}    if ({candidates}.Count > 0)", f"{ind}    {{",
                    f"{ind}        var {v} = {self.rng()}.NextItem({candidates});"] + body_fn(v, ind + "        ") + [f"{ind}    }}", f"{ind}}}"]
        cr = self.creature(who)
        if cr == self.C.me:
            return body_fn(cr, ind)
        return [f"{ind}if ({cr} != null)", f"{ind}{{"] + body_fn(cr, ind + "    ") + [f"{ind}}}"]

    def block_amount(self, b):
        import modgen as M
        if not hasattr(self, "_number_names"):
            self._number_names = {id(block): name for block,name,_ in M.block_number_vars(self.C.item or {})} if self.C.kind == "card" else {}
        name = self._number_names.get(id(b.get("_compact_origin", b)))
        return f'DynamicVars["{name}"].BaseValue' if name else self.val(b.get("args", {}).get("amount"))

    def stmt(self, b, ind, event_bound=False):
        if b.get("op") in ("hand_aura_stat", "aura_power_amount", "aura_card_effect"):
            if not getattr(self.C, "hand_aura", False):
                self.errors.append("손패 지속 보정 블록은 키워드의 ‘더미에 있는 동안 지속 보정’에서 사용하세요.")
            return []
        if b.get("op") in F.FAMILIES:
            options = dict(F.FAMILIES[b["op"]][1])
            mode = b.get("args", {}).get("mode", next(iter(options)))
            if not isinstance(mode, str) or mode not in options:
                self.errors.append("목록에서 실행 방식을 다시 선택하세요.")
                return []
        if F.variant(b, SPECS) in ("edit_var", "card_state_edit") and b.get("args", {}).get("edit_mode", "add") not in ("set", "add"):
            self.errors.append("수치 변경 방법을 다시 선택하세요.")
            return []
        if b.get("op") == "button_switch" and b.get("args", {}).get("switch", "on") not in ("on", "off"):
            self.errors.append("버튼의 켜기/끄기를 다시 선택하세요.")
            return []
        b = expand_compact(b)
        import modgen as M
        C, a, op = self.C, b.get("args", {}), b.get("op")
        event_target = getattr(C, "event_target", None)
        if event_target == "choose":
            schema = SPECS.get(op, {}).get("args", {})
            fields = [key for key, value in a.items() if value == "target" and schema.get(key, (None,))[0] in ("who_multi", "who_one")]
            if fields and not event_bound:
                selected = self.uid("eventSelected")
                old_other, old_single = C.other, C.single
                self.its.append(selected)
                C.other = C.single = selected
                try:
                    body = self.stmt(b, ind + "    ", event_bound=True)
                finally:
                    C.other, C.single = old_other, old_single
                    self.its.pop()
                return [f"{ind}foreach (var {selected} in eventTargets.Where(enemy => enemy.IsHittable).ToList())", f"{ind}{{", *body, f"{ind}}}"]
            if fields:
                a = dict(a)
                for key in fields:
                    a[key] = "it"

        if event_target in ("all", "self"):
            schema = SPECS.get(op, {}).get("args", {})
            a = dict(a)
            for key, value in a.items():
                if value == "target" and schema.get(key, (None,))[0] in ("who_multi", "who_one"):
                    a[key] = event_target

        for key, value in a.items():
            if isinstance(value, str) and value in ("@selected_creature", "@selected_player"):
                cr = self.creature("it")
                if cr == "null":
                    return []
                if value == "@selected_creature":
                    return self.stmt({**b, "args":{**a, key:cr}}, ind)
                pv = self.uid("selectedPlayer")
                return [f"{ind}if ({cr}?.Player is {{ }} {pv})", f"{ind}{{", *self.stmt({**b, "args":{**a,key:pv}}, ind + "    "), f"{ind}}}"]
            if value in ("@picked_card", "@picked_cards"):
                card = self.card_ref("picked")
                if card == "null":
                    return []
                expression = f"new[] {{ {card} }}" if value == "@picked_cards" else card
                return self.stmt({**b, "args": {**a, key: expression}}, ind)
            if isinstance(value, str) and value.startswith(("@own_power:", "@target_power:")):
                meta = M.power_meta(self.project, value.split(":", 1)[1])
                if not meta:
                    self.errors.append("선택한 파워를 찾을 수 없습니다.")
                    return []
                creature = C.single if value.startswith("@target_power:") else C.me
                if not creature:
                    self.errors.append("이 위치에는 선택한 대상이 없습니다.")
                    return []
                power = self.uid("chosenPower")
                return [f"{ind}var {power} = ({creature})?.GetPower<{meta['cls']}>();",
                        f"{ind}if ({power} != null)", ind + "{",
                        *self.stmt({**b, "args": {**a, key: power}}, ind + "    "), ind + "}"]
        for key, value in a.items():
            if key in ("creature", "target", "attacker", "applier") and value == "@random_enemy":
                return self.each_target("random", ind, lambda enemy, indent:
                    self.stmt({**b, "args": {**a, key: enemy}}, indent))
            if key == "card" and value == "@random_hand":
                hand, card = self.uid("hand"), self.uid("card")
                lines = [f"{ind}var {hand} = {C.player}?.PlayerCombatState?.Hand.Cards.ToList();",
                         f"{ind}if ({hand} != null && {hand}.Count > 0)", f"{ind}{{",
                         f"{ind}    var {card} = {C.me}.CombatState!.RunState.Rng.CombatCardSelection.NextItem({hand});"]
                return lines + self.stmt({**b, "args": {**a, key: card}}, ind + "    ") + [ind + "}"]
        if op == "no_effect":
            return [ind + "await Task.CompletedTask;"]
        if op == "shared_call":
            name = a.get("name", "")
            definitions = self.project.get("shared_blocks", {})
            active = getattr(self, "_active_shared", ())
            if name not in definitions or name in active:
                self.errors.append(f"내 블록을 찾지 못했거나 순환 호출합니다: {name}")
                return []
            def expand(node):
                if isinstance(node, list):
                    return [expand(v) for v in node]
                if isinstance(node, dict):
                    if node.get("t") == "var" and node.get("name") in ("input1", "input2"):
                        return a["first" if node["name"] == "input1" else "second"]
                    return {k: expand(v) for k,v in node.items()}
                return node
            self._active_shared = (*active, name)
            try:
                return self.stmts(expand(definitions[name]), ind)
            finally:
                self._active_shared = active
        if a.get("card") == "@replacement":
            replacement = getattr(self, "_replacement", None)
            if not replacement:
                self.errors.append("방금 변화한 카드는 변화 블록 안에서 사용하세요.")
                return []
            return self.stmt({**b, "args":{**a,"card":replacement}}, ind)
        if op in ("src_call", "src_loop"):
            if C.kind != "card" or not C.item.get("clone"):
                self.errors.append("직접 코드 블록은 복제 카드에서만 사용할 수 있습니다.")
                return []
            if op == "src_loop":
                head = str(a.get("head") or "").strip()
                return ([ind + head] if head else []) + [f"{ind}{{"] + self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            slots = {s["key"]: s for s in b.get("slots", [])}
            out = []
            for i, part in enumerate(b.get("parts") or []):
                out.append(part if i % 2 == 0 else self.src_slot(slots.get(part, {}), a.get(part)))
            return [ind + line for line in "".join(out).splitlines()]
        if op in ("source_step", "source_hit", "source_amount"):
            if C.kind != "card" or not C.item.get("clone"):
                self.errors.append("직접 코드 블록은 복제 카드에서만 사용할 수 있습니다.")
                return []
            if op == "source_amount":
                suffix = b["suffix"]
                if suffix.startswith(("m", "M")):
                    suffix = suffix[1:]
                amount = self.block_amount(b)
                if b.get("label") == "드로우":
                    amount = f"(int)({amount})"
                return [ind + b["prefix"] + amount + suffix]
            if op == "source_step":
                return [ind + line for line in a.get("source", "").splitlines()]
            stat = a.get("stat")
            if not any(v["name"] == stat for v in C.item.get("raw_vars", [])) or not str(stat).isidentifier():
                self.errors.append("원본 피해 변수 참조가 없습니다.")
                return []
            who = "(cardPlay.Target ?? Me)" if a.get("target") == "target" else self.creature(a.get("target"))
            return [f'{ind}await Hit(choiceContext, {who}, DynamicVars["{stat}"].IntValue, {max(1,int(a.get("hits",1)))});']
        if op == "original_play":
            if C.kind == "card" and (C.item.get("clone") or {}).get("editable_play"):
                return [ind + "await OriginalOnPlay(choiceContext, cardPlay);"]
            self.errors.append("원본 실행 블록은 원본 사용 효과가 있는 복제 카드에서만 사용할 수 있습니다.")
            return []
        cc, me = C.cc, C.me
        need_player = C.kind == "power"

        def with_player(lines):
            if need_player:
                return [f"{ind}if ({C.player} != null)", f"{ind}{{"] + ["    " + x for x in lines] + [f"{ind}}}"]
            return lines

        if op == "card_attack":
            if C.kind != "card":
                self.errors.append("공격 블록은 카드 효과에서만 쓸 수 있습니다.")
                return []
            amt = self.block_amount(b)
            name = M.block_damage_name(C.item, b)
            if name:
                amt = f'DynamicVars["{name}"].BaseValue'
            hval = a.get("hits", {"t": "num", "v": 1})
            hits = self.val(hval)
            chain = f"DamageCmd.Attack({amt})"
            if hval != {"t": "num", "v": 1}:
                chain += f".WithHitCount((int)({hits}))"
            vfx = str(a.get("vfx") or "").strip()
            sfx = str(a.get("sfx") or "").strip()
            fx_extra = str(a.get("fx_extra") or "").strip()
            if vfx:
                fx_args = [vfx]
                if sfx:
                    fx_args.append(sfx)
                if fx_extra:
                    fx_args.append(fx_extra)
                chain += f".WithHitFx({', '.join(fx_args)})"
            elif sfx or fx_extra:
                self.errors.append("공격 효과음을 입력하려면 먼저 이펙트 값을 지정하세요.")
            guard_target = None
            who = a.get("who", "target")
            if who == "all":
                chain += ".TargetingAllOpponents(CombatState!)"
            elif who == "random":
                chain += ".TargetingRandomOpponents(CombatState!)"
            else:
                target = self.creature(who)
                if target == "null":
                    return []
                chain += f".Targeting({target})"
                if target != me:
                    guard_target = target
            chain += f".FromCard((CardModel)this).Execute({cc});"
            if guard_target:
                return [f"{ind}if ({guard_target} != null)", f"{ind}{{", f"{ind}    await {chain}", f"{ind}}}"]
            return [f"{ind}await {chain}"]
        if op == "damage":
            amt = self.block_amount(b)
            name = M.block_damage_name(C.item, b) if C.kind == "card" else None
            if name:
                amt = f'DynamicVars["{name}"].BaseValue'
            hits = max(1, int(a.get("hits", 1) or 1))
            props = "ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered"

            def body(t, i2):
                line = f"{i2}await CreatureCmd.Damage({cc}, {t}, {amt}, {props}, {me}, {C.src}, {C.play});"
                return [line] if hits == 1 else [f"{i2}for (var h_ = 0; h_ < {hits}; h_++)", "    " + line]
            return self.each_target(a.get("who", "target"), ind, body)
        if op == "damage_to":
            creature = str(a.get("creature") or "target").strip()
            if not creature:
                self.errors.append("피해를 줄 생물 식을 입력하세요.")
                return []
            props = ("ValueProp.Unblockable | " + ("ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered")) \
                if a.get("unblockable") else ("ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered")
            context = str(a.get("context") or cc).strip()
            args = [context, creature, self.block_amount(b), props, str(a.get("attacker") or me).strip()]
            if str(a.get("source_card") or "").strip():
                args.append(str(a.get("source_card")).strip())
            if str(a.get("card_play") or "").strip():
                if len(args) == 5:
                    args.append("null")
                args.append(str(a.get("card_play")).strip())
            return [f"{ind}await CreatureCmd.Damage({', '.join(args)});"]
        if op == "apply_power_type":
            creature = str(a.get("creature") or "target").strip()
            power_type = str(a.get("power_type") or "").replace("global::", "").strip()
            source = str(a.get("source") or "null").strip()
            if not creature or not power_type:
                self.errors.append("파워 유형과 대상 생물을 입력하세요.")
                return []
            if not power_type.startswith("global::"):
                power_type = "global::" + power_type
            silent = ", silent: true" if a.get("silent") else ""
            return [f"{ind}await CommonActions.Apply<{power_type}>({cc}, {creature}, {source}, "
                    f"{self.block_amount(b)}{silent});"]
        if op == "power_apply_type":
            creature = str(a.get("creature") or "target").strip()
            power_type = str(a.get("power_type") or "").strip()
            if not creature or not power_type:
                self.errors.append("파워 유형과 대상 생물을 입력하세요.")
                return []
            if not power_type.startswith("global::"):
                power_type = "global::" + power_type
            return [f"{ind}await PowerCmd.Apply<{power_type}>({cc}, {creature}, {self.block_amount(b)}, "
                    f"{a.get('applier') or me}, {a.get('source') or C.src});"]
        if op == "power_apply_model":
            return [f"{ind}await PowerCmd.Apply({cc}, {a.get('power') or 'powerModel'}, {a.get('creature') or 'target'}, "
                    f"{self.block_amount(b)}, {a.get('applier') or me}, {a.get('source') or C.src});"]
        if op == "block_to":
            creature = str(a.get("creature") or "target").strip()
            if not creature:
                self.errors.append("방어도를 받을 생물 식을 입력하세요.")
                return []
            prop = "ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered"
            play = C.play if a.get("card_play", True) and C.kind == "card" else "null"
            return [f"{ind}await CreatureCmd.GainBlock({creature}, {self.block_amount(b)}, {prop}, {play});"]
        if op == "heal_to":
            creature = str(a.get("creature") or "target").strip()
            if not creature:
                self.errors.append("회복할 생물 식을 입력하세요.")
                return []
            return [f"{ind}await CreatureCmd.Heal({creature}, {self.block_amount(b)});"]
        if op == "block":
            return [f"{ind}await CreatureCmd.GainBlock({me}, {self.block_amount(b)}, "
                    f"{'ValueProp.Move' if C.kind == 'card' else 'ValueProp.Unpowered'}, {C.play});"]
        if op == "lose_block":
            amt = self.block_amount(b)
            return self.each_target(a.get("who", "target"), ind,
                                    lambda t, i2: [f"{i2}await CreatureCmd.LoseBlock({cc}, {t}, {amt}, {me});"])
        if op == "lose_block_to":
            return [f"{ind}await CreatureCmd.LoseBlock({a.get('creature') or 'target'}, {self.block_amount(b)});"]
        if op == "kill_creature":
            return [f"{ind}await CreatureCmd.Kill({a.get('creature') or 'target'});"]
        if op == "draw":
            return with_player([f"{ind}await CardPileCmd.Draw({cc}, {self.block_amount(b)}, {C.player});"])
        if op == "energy":
            return with_player([f"{ind}await PlayerCmd.GainEnergy({self.block_amount(b)}, {C.player});"])
        if op == "energy_to":
            return [f"{ind}await PlayerCmd.GainEnergy({self.block_amount(b)}, {a.get('player') or C.player});"]
        if op == "gold_to":
            return [f"{ind}await PlayerCmd.GainGold({self.block_amount(b)}, {a.get('player') or C.player});"]
        if op == "gold":
            return with_player([f"{ind}await PlayerCmd.GainGold({self.block_amount(b)}, {C.player});"])
        if op == "lose_gold":
            return [f"{ind}await PlayerCmd.LoseGold({self.block_amount(b)}, {a.get('player') or C.player}, "
                    f"{a.get('loss_type') or 'GoldLossType.Spent'});"]
        if op == "end_turn":
            return [f"{ind}PlayerCmd.EndTurn({a.get('player') or C.player}, canBackOut: {a.get('can_back_out') or 'false'});"]
        if op == "card_exhaust":
            return [f"{ind}await CardCmd.Exhaust({cc}, {a.get('card') or 'cardModel'}, "
                    f"{'true' if a.get('played') else 'false'}, {'true' if a.get('triggered') else 'false'});"]
        if op == "card_upgrade":
            style = preview_style_expr(a.get("style"))
            tail = f", {style}" if style else ""
            return [f"{ind}CardCmd.Upgrade({a.get('card') or 'cardModel'}{tail});"]
        if op == "card_autoplay":
            return [f"{ind}await CardCmd.AutoPlay({cc}, {a.get('card') or 'cardModel'}, {a.get('target') or 'target'}, "
                    f"{a.get('type') or 'AutoPlayType.Default'}, skipXCapture: {a.get('skip_x') or 'false'}, "
                    f"skipCardPileVisuals: {a.get('skip_visuals') or 'false'});"]
        if op == "card_discard":
            return [f"{ind}await CardCmd.Discard({cc}, {a.get('cards') or 'cards'});"]
        if op == "card_keyword":
            card = a.get("card") or "cardModel"
            method = "ApplyKeyword" if a.get("action", "add") == "add" else "RemoveKeyword"
            return [f"{ind}CardCmd.{method}({card}, CardKeyword.{a.get('keyword', 'Exhaust')});"]
        if op == "card_add_keyword_model":
            return [f"{ind}{a.get('card') or 'cardModel'}.AddKeyword({a.get('keyword') or 'CardKeyword.Exhaust'});"]
        if op == "draw_to":
            return [f"{ind}await CardPileCmd.Draw({cc}, {self.block_amount(b)}, {a.get('player') or C.player});"]
        if op == "card_add_generated":
            line = f"{ind}await CardPileCmd.AddGeneratedCardToCombat({a.get('card') or 'cardModel'}, PileType.{a.get('pile', 'Hand')}, {C.player});"
            return with_player([line])
        if op == "card_add_pile":
            extra = str(a.get("extra") or "").strip()
            args = f"{a.get('cards') or 'cardModel'}, {a.get('pile') or 'PileType.Hand'}"
            if extra:
                args += ", " + extra
            return [f"{ind}await CardPileCmd.Add({args});"]
        if op == "card_add_generated_many":
            return [f"{ind}await CardPileCmd.AddGeneratedCardsToCombat({a.get('cards') or 'cards'}, "
                    f"{a.get('pile') or 'PileType.Hand'}, {a.get('player') or C.player}, "
                    f"{a.get('position') or 'CardPilePosition.Random'});"]
        if op == "card_preview":
            if preview_style_expr(a.get("style")).endswith("CardPreviewStyle.None"):
                return []
            return [f"{ind}CardCmd.PreviewCardPileAdd({a.get('cards') or 'cards'}, "
                    f"(float)({self.val(a.get('scale'))}), {preview_style_expr(a.get('style')) or 'global::MegaCrit.Sts2.Core.Nodes.CommonUi.CardPreviewStyle.HorizontalLayout'});"]
        if op == "card_preview_cards":
            scale = str(a.get("scale") or "").strip()
            args = str(a.get("cards") or "cardModel")
            if scale:
                args += f", (float)({scale})"
            return [f"{ind}CardCmd.Preview({args});"]
        if op == "card_remove_combat":
            return [f"{ind}await CardPileCmd.RemoveFromCombat({a.get('cards') or 'cardModel'});"]
        if op == "shuffle_draw_pile":
            return [f"{ind}await CardPileCmd.Shuffle({cc}, {a.get('player') or C.player});"]
        if op == "stun":
            return [f"{ind}await CreatureCmd.Stun({a.get('creature') or 'target'});"]
        if op == "autoplay_draw_pile":
            return [f"{ind}await CardPileCmd.AutoPlayFromDrawPile({cc}, {a.get('player') or C.player}, "
                    f"{self.val(a.get('count'))}, {a.get('position') or 'CardPilePosition.Top'}, "
                    f"forceExhaust: {a.get('force_exhaust') or 'false'});"]
        if op == "potion_add_type":
            potion_type = str(a.get("potion_type") or "").replace("global::", "").strip()
            if not potion_type:
                self.errors.append("지급할 물약 종류를 입력하세요.")
                return []
            return [f"{ind}await PotionCmd.TryToProcure<{potion_type}>({a.get('player') or C.player});"]
        if op == "potion_add_model":
            return [f"{ind}await PotionCmd.TryToProcure({a.get('potion') or 'potionModel'}, {a.get('player') or C.player});"]
        if op == "potion_add_model_at":
            return [f"{ind}{a.get('player') or C.player}.AddPotionInternal({a.get('potion') or 'potionModel'}, {a.get('slot') or 'potionSlotIndex'});"]
        if op == "potion_discard":
            return [f"{ind}{a.get('potion') or 'potionModel'}.Discard();"]
        if op == "card_set_cost_until_played":
            return [f"{ind}{a.get('card') or 'cardModel'}.EnergyCost.SetThisTurnOrUntilPlayed({self.block_amount(b)});"]
        if op == "card_free_this_turn":
            return [f"{ind}{a.get('card') or 'cardModel'}.SetToFreeThisTurn();"]
        if op == "card_notify_cost_changed":
            return [f"{ind}{a.get('card') or 'cardModel'}.InvokeEnergyCostChanged();"]
        if op == "card_upgrade_internal":
            return [f"{ind}{a.get('card') or 'cardModel'}.UpgradeInternal();"]
        if op == "card_finalize_upgrade_internal":
            return [f"{ind}{a.get('card') or 'cardModel'}.FinalizeUpgradeInternal();"]
        if op == "card_transform_to":
            card_type = str(a.get("card_type") or "").replace("global::", "").strip()
            if not card_type:
                self.errors.append("변환할 카드 종류를 입력하세요.")
                return []
            return [f"{ind}await CardCmd.TransformTo<{card_type}>({a.get('card') or 'cardModel'});"]
        if op == "modify_power_amount":
            return [f"{ind}await PowerCmd.ModifyAmount({cc}, {a.get('power') or 'powerModel'}, "
                    f"{self.block_amount(b)}, {me}, {C.src});"]
        if op == "remove_power_model":
            return [f"{ind}await PowerCmd.Remove({a.get('power') or 'powerModel'});"]
        if op == "set_current_hp":
            return [f"{ind}await CreatureCmd.SetCurrentHp({a.get('creature') or me}, {self.block_amount(b)});"]
        if op == "orb_channel_model":
            return with_player([f"{ind}await OrbCmd.Channel({cc}, {a.get('orb') or 'orbModel.ToMutable()'}, {C.player});"])
        if op == "orb_channel_type":
            orb_type = str(a.get("orb_type") or "").replace("global::", "").strip()
            if not orb_type:
                self.errors.append("영창할 구체 종류를 입력하세요.")
                return []
            return [f"{ind}await OrbCmd.Channel<{orb_type}>({cc}, {a.get('player') or C.player});"]
        if op == "orb_passive_model":
            return [f"{ind}await OrbCmd.Passive({cc}, {a.get('orb') or 'orbModel'}, {a.get('target') or 'null'});"]
        if op == "orb_slots_to":
            n = self.uid("n")
            player = a.get("player") or C.player
            return [f"{ind}var {n} = (int)({self.block_amount(b)});",
                    f"{ind}if ({n} > 0) await OrbCmd.AddSlots({player}, {n});",
                    f"{ind}else if ({n} < 0) OrbCmd.RemoveSlots({player}, -{n});"]
        if op == "add_pet_model":
            return [f"{ind}await PlayerCmd.AddPet({a.get('pet') or 'petCreature'}, {a.get('player') or C.player});"]
        if op == "wait":
            return [f"{ind}await Cmd.Wait((float)({self.val(a.get('duration'))}));"]
        if op == "wait_scaled":
            return [f"{ind}await Cmd.CustomScaledWait({a.get('minimum') or '0.1f'}, {a.get('maximum') or '0.25f'});"]
        if op == "trigger_creature_anim":
            return [f"{ind}await CreatureCmd.TriggerAnim({a.get('creature') or 'target'}, "
                    f"{a.get('animation') or '"Attack"'}, {a.get('delay') or '0.15f'});"]
        if op == "play_vfx_on_creature":
            return [f"{ind}VfxCmd.PlayOnCreature({a.get('creature') or 'target'}, {a.get('vfx') or '"vfx/vfx_attack_slash"'});"]
        if op == "doom_kill":
            return [f"{ind}await DoomPower.DoomKill({a.get('creatures') or 'creatures'});"]
        if op == "max_hp":
            return [f"{ind}await CreatureCmd.GainMaxHp({me}, {self.block_amount(b)});"]
        if op == "heal":
            amt = self.block_amount(b)
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f"{i2}await CreatureCmd.Heal({t}, {amt});"])
        if op == "lose_hp":
            amt = self.block_amount(b)
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [
                f"{i2}await CreatureCmd.Damage({cc}, {t}, {amt}, ValueProp.Unblockable | ValueProp.Unpowered, {me}, {C.src}, {C.play});"])
        if op in ("apply_power", "apply_power_to", "remove_power"):
            pm = M.power_meta(self.project, a.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {a.get('power')}")
                return []
            amt = self.block_amount(b)
            if op == "apply_power_to":
                creature = str(a.get("creature") or "target").strip()
                if not creature:
                    self.errors.append("파워를 받을 생물 식을 입력하세요.")
                    return []
                silent = ", silent: true" if a.get("silent") else ""
                return [f"{ind}await CommonActions.Apply<{pm['cls']}>({cc}, {creature}, {C.src}, {amt}{silent});"]
            if op == "apply_power":
                return self.each_target(a.get("who", "target"), ind, lambda t, i2: [
                    f"{i2}await CommonActions.Apply<{pm['cls']}>({cc}, {t}, {C.src}, {amt}"
                    f"{', silent: true' if a.get('silent') else ''});"])
            pv = self.uid("pw")

            def rm(t, i2):
                return [f"{i2}{{", f"{i2}    var {pv} = {t}.GetPower<{pm['cls']}>();",
                        f"{i2}    if ({pv} != null)", f"{i2}    {{",
                        f"{i2}        if ({amt} <= 0m) await PowerCmd.Remove({pv});",
                        f"{i2}        else await PowerCmd.ModifyAmount({cc}, {pv}, -({amt}), {me}, {C.src});",
                        f"{i2}    }}", f"{i2}}}"]
            return self.each_target(a.get("who", "target"), ind, rm)
        if op == "flash":
            if C.kind in ("relic", "power"):
                return [f"{ind}Flash();"]
            return []
        if op == "hand":
            import gimmick as G
            lst, cv, i_ = self.uid("cards"), self.uid("c"), self.uid("i")
            ct = a.get("ctype", "Any") or "Any"
            cond = ["true"]
            if C.kind == "card":
                cond.append(f"{cv} != this")
            if ct != "Any":
                cond.append(G.filter_expr(self.project, ct, cv))
            if a.get("action") == "upgrade":
                cond.append(f"{cv}.IsUpgradable")
            act = {"upgrade": f"CardCmd.Upgrade({cv});", "exhaust": f"await CardCmd.Exhaust({cc}, {cv});",
                   "discard": f"await CardCmd.Discard({cc}, {cv});"}[a.get("action", "upgrade")]
            lines = [f"{ind}{{",
                     f"{ind}    var {lst} = ({C.player}?.PlayerCombatState?.Hand.Cards ?? System.Array.Empty<CardModel>()).Where({cv} => {' && '.join(cond)}).ToList();"]
            if a.get("which") == "all":
                lines += [f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", f"{ind}        {act}", f"{ind}    }}"]
            else:
                lines += [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}) && {lst}.Count > 0; {i_}++)",
                          f"{ind}    {{", f"{ind}        var {cv} = {self.rng()}.NextItem({lst});",
                          f"{ind}        {lst}.Remove({cv});", f"{ind}        {act}", f"{ind}    }}"]
            return lines + [f"{ind}}}"]
        if op in ("keyword_this", "keyword_cards"):
            import gimmick as G
            kw = a.get("keyword") or "Retain"
            verb = "ApplyKeyword" if a.get("action", "add") == "add" else "RemoveKeyword"
            if op == "keyword_this":
                if C.kind != "card":
                    self.errors.append("'이 카드에 키워드'는 카드에서만 쓸 수 있습니다 (다른 곳은 '카드들에 키워드').")
                    return []
                return [f"{ind}CardCmd.{verb}(this, CardKeyword.{kw});"]
            lst, cv, i_, pcs = self.uid("cards"), self.uid("c"), self.uid("i"), self.uid("pcs")
            piles = {"hand": ["Hand"], "draw": ["DrawPile"], "discard": ["DiscardPile"],
                     "all": ["Hand", "DrawPile", "DiscardPile"]}.get(a.get("where"), ["Hand"])
            src = ".Concat".join(f"({pcs}.{x}.Cards)" for x in piles)
            ct = a.get("ctype", "Any") or "Any"
            has = f"{cv}.Keywords.Contains(CardKeyword.{kw})"
            cond = [f"!{has}" if verb == "ApplyKeyword" else has]
            if C.kind == "card":
                cond.append(f"{cv} != this")
            if ct != "Any":
                cond.append(G.filter_expr(self.project, ct, cv))
            act = f"CardCmd.{verb}({cv}, CardKeyword.{kw});"
            lines = [f"{ind}{{", f"{ind}    var {pcs} = {C.player}?.PlayerCombatState;",
                     f"{ind}    var {lst} = {pcs} == null ? new List<CardModel>() : "
                     f"{src}.Where({cv} => {' && '.join(cond)}).ToList();"]
            if a.get("which") == "all":
                lines += [f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", f"{ind}        {act}", f"{ind}    }}"]
            else:
                lines += [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}) && {lst}.Count > 0; {i_}++)",
                          f"{ind}    {{", f"{ind}        var {cv} = {self.rng()}.NextItem({lst});",
                          f"{ind}        {lst}.Remove({cv});", f"{ind}        {act}", f"{ind}    }}"]
            return lines + [f"{ind}}}"]
        if op == "add_card":
            mid = self.project["mod"]["id"]
            i_, nc = self.uid("i"), self.uid("nc")
            card = a.get("card", "this")
            if card == "this":
                if C.kind != "card":
                    self.errors.append("'이 카드의 복사본'은 카드에서만 쓸 수 있습니다.")
                    return []
                make = f"{me}.CombatState!.CreateCard(CanonicalInstance, {C.player})"
            else:
                if not any(x["id"] == card for x in self.project.get("cards", [])):
                    self.errors.append(f"없는 카드: {card}")
                    return []
                make = f"{me}.CombatState!.CreateCard<{M.item_cls(self.project, 'card', card)}>({C.player})"
            inner = [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}); {i_}++)", f"{ind}    {{",
                     f"{ind}        var {nc} = {make};"]
            if card == "this":
                inner.append(f"{ind}        if (IsUpgraded) CardCmd.Upgrade({nc});")
            inner += [f"{ind}        await CardPileCmd.AddGeneratedCardToCombat({nc}, PileType.{a.get('pile', 'Hand')}, {C.player});",
                      f"{ind}    }}"]
            if need_player:
                return [f"{ind}if ({C.player} != null)", f"{ind}{{"] + inner + [f"{ind}}}"]
            return [f"{ind}{{"] + inner + [f"{ind}}}"]
        if op in ("if", "if_else"):
            lines = [f"{ind}if ({self.cond(a.get('cond'))})", f"{ind}{{"] + self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            if op == "if_else":
                lines += [f"{ind}else", f"{ind}{{"] + self.stmts(b.get("else"), ind + "    ") + [f"{ind}}}"]
            return lines
        if op == "repeat":
            i_ = self.uid("k")
            return [f"{ind}for (var {i_} = 0; {i_} < (int)({self.val(a.get('times'))}); {i_}++)", f"{ind}{{"] + \
                self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
        if op in ("filtered_enemies", "filtered_players"):
            import modgen as M
            import re
            from types import SimpleNamespace
            pool, selected, v = self.uid("enemyPool"), self.uid("enemySelection"), self.uid("it")
            players = op == "filtered_players"
            condition = a.get("enemy_filter", "power")
            group = a.get("conditions")
            if players or (group and (group.get("t") != "group" or group.get("items"))):
                condition = "all"
            predicate = "true"
            if condition in ("power", "no_power"):
                pm = M.power_meta(self.project, a.get("power", "Weak"))
                if not pm:
                    self.errors.append("대상 조건에 사용할 파워를 고르세요.")
                    return []
                predicate = f"enemy.GetPowerAmount<{pm['cls']}>() {'>' if condition == 'power' else '<='} 0"
            elif condition in ("hp_below", "hp_above"):
                predicate = f"enemy.MaxHp > 0 && (decimal)enemy.CurrentHp * 100m {'<=' if condition == 'hp_below' else '>='} (decimal)enemy.MaxHp * Math.Clamp({self.val(a.get('limit'))}, 0m, 100m)"
            elif condition != "all":
                self.errors.append("적 대상 조건을 다시 선택하세요.")
                return []
            if group and (group.get("t") != "group" or group.get("items")):
                self.its.append("enemy")
                try:
                    predicate = self.cond(group)
                finally:
                    self.its.pop()
            mode = a.get("enemy_mode", "random")
            count = f"Math.Clamp((int)({self.val(a.get('count'))}), 0, {pool}.Count)"
            source = f"{C.me}.CombatState!.PlayerCreatures" if players else self.enemies()
            alive = "IsAlive" if players else "IsHittable"
            lines = [f"{ind}{{", f"{ind}    var {pool} = {source}.Where(enemy => enemy.{alive} && ({predicate})).ToList();"]
            if mode == "choose":
                ctx = SimpleNamespace(event_target="choose", event_target_count=count, player=C.player, me=C.me, cc=C.cc)
                setup = event_target_setup(ctx, [], self.project, enemy_expr=pool, force=True)
                if players:
                    setup = [line.replace("TargetType.AnyEnemy", "TargetType.AnyAlly").replace(".IsHittable", ".IsAlive") for line in setup]
                names = set(re.findall(r"\bevent[A-Z]\w*", "\n".join(setup)))
                mapping = {name: self.uid(name) for name in sorted(names)}
                for line in setup:
                    line = re.sub(r"\bevent[A-Z]\w*", lambda m: mapping[m.group()], line)
                    lines.append(ind + "    " + line)
                lines.append(f"{ind}    var {selected} = {mapping['eventTargets']};")
            elif mode in ("random", "all"):
                lines.append(f"{ind}    var {selected} = new global::System.Collections.Generic.List<global::MegaCrit.Sts2.Core.Entities.Creatures.Creature>();")
                if mode == "all":
                    lines.append(f"{ind}    {selected}.AddRange({pool});")
                else:
                    n, pick = self.uid("enemyCount"), self.uid("enemyPick")
                    lines += [f"{ind}    var {n} = {count};", f"{ind}    while ({selected}.Count < {n} && {pool}.Count > 0)", f"{ind}    {{",
                              f"{ind}        var {pick} = {self.rng()}.NextItem({pool});", f"{ind}        if ({pick} == null) break;", f"{ind}        {selected}.Add({pick});", f"{ind}        {pool}.Remove({pick});", f"{ind}    }}"]
            else:
                self.errors.append("적 선택 방식을 다시 고르세요.")
                return []
            self.its.append(v)
            try:
                body = self.stmts(b.get("body"), ind + "        ")
            finally:
                self.its.pop()
            return lines + [f"{ind}    foreach (var {v} in {selected}.Where(enemy => enemy.{alive}))", f"{ind}    {{", *body, f"{ind}    }}", f"{ind}}}"]
        if op in ("each_enemy", "random_enemy"):
            v = self.uid("it")
            self.its.append(v)
            try:
                body = self.stmts(b.get("body"), ind + ("    " if op == "each_enemy" else "        "))
            finally:
                self.its.pop()
            if op == "each_enemy":
                return [f"{ind}foreach (var {v} in {self.enemies()}.ToList())", f"{ind}{{"] + body + [f"{ind}}}"]
            return [f"{ind}{{", f"{ind}    var {v} = {self.rng()}.NextItem({self.enemies()}.ToList());",
                    f"{ind}    if ({v} != null)", f"{ind}    {{"] + body + [f"{ind}    }}", f"{ind}}}"]
        if op == "set_var":
            return [f"{ind}v_{_ident(a.get('name', 'a'))} = {self.block_amount(b)};"]
        if op == "change_var":
            return [f"{ind}v_{_ident(a.get('name', 'a'))} += {self.block_amount(b)};"]
        if op in ("card_state_set", "card_state_change"):
            ref = self.card_ref(a.get("card", "this"), a.get("card_n"))
            if ref == "null":
                return []
            fn = "SetCardState" if op == "card_state_set" else "AddCardState"
            return [f"{ind}{self.helper()}.{fn}({ref}, {_cs_str(a.get('key'))}, {self.block_amount(b)});"]
        if op in ("card_var_new", "card_var_remove", "card_number_edit", "card_cost_edit", "card_damage_edit", "card_do", "card_ref_keyword", "card_tag", "card_enchant",
                  "card_enchant_clear", "add_card_pos", "draw_bottom"):
            return self.cardref_stmt(b, op, a, ind)
        if op in ("summon", "command", "unsummon", "pay", "choice", "pick", "random_transform", "pick_transform", "pick_each", "random_each", "picked_action", "delayed"):
            return self.gimmick_stmt(b, op, a, ind)
        if op in SPECS and SPECS[op]["cat"] == "class":
            return self.class_stmt(b, op, a, ind)
        if op.startswith("pet_"):
            import pets as PT
            pid = a.get("pet") or ""
            p = PT.find_pet(self.project, pid)
            if not p:
                self.errors.append("동료를 고르세요 ('기믹' 탭에서 먼저 만드세요)." if not pid else f"없는 동료: {pid}")
                return []
            H, cls, act = PT.helper(self.project), PT.pet_cls(self.project, pid), PT.act_cls(self.project, pid)
            pl = C.player
            if op == "pet_summon":
                return [f"{ind}await {H}.Summon<{cls}, {act}>({C.cc}, {pl}, {self.block_amount(b)}, this, "
                        f"{'true' if p.get('guard', True) else 'false'});"]
            if op == "pet_act":
                return [f"{ind}await {H}.Act<{cls}, {act}>({C.cc}, {pl});"]
            if op == "pet_kill":
                return [f"{ind}await {H}.Kill<{cls}>({pl});"]
            amt = self.block_amount(b)
            hits = max(1, int(a.get("hits", 1) or 1))
            return self.each_target(a.get("who", "target"), ind,
                                    lambda t, i2: [f"{i2}await {H}.Attack<{cls}>({C.cc}, {pl}, {t}, {amt}, {hits});"])
        if op in ("fx", "button_on", "button_off"):
            import fxbtn
            mid = self.project["mod"]["id"]
            nsp = f"global::{mid}.{mid}Code.Gimmicks"
            if op == "fx":
                fid = a.get("fx") or ""
                if not fxbtn.find_effect(self.project, fid):
                    self.errors.append("이펙트를 고르세요 ('이펙트·버튼' 탭에서 먼저 그리세요)." if not fid else f"없는 이펙트: {fid}")
                    return []
                return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f'{i2}{nsp}.{mid}Fx.Play("{fid}", {t});'])
            bid = a.get("button") or ""
            if not fxbtn.find_button(self.project, bid):
                self.errors.append("버튼을 고르세요 ('이펙트·버튼' 탭에서 먼저 만드세요)." if not bid else f"없는 버튼: {bid}")
                return []
            if op == "button_on":
                return [f'{ind}await {nsp}.{mid}Buttons.On("{bid}", {self.C.me}, {self.C.cc});']
            return [f'{ind}await {nsp}.{mid}Buttons.Off("{bid}", {self.C.me});']
        if op == "sfx":
            path = str(a.get("path") or '"event:/sfx"').strip()
            return [f"{ind}SfxCmd.Play({path}, (float)({self.val(a.get('volume'))}));"]
        return [f"{ind}// 알 수 없는 블록: {op}"]

    # ---- 직업 시스템 블록 ----
    def cardref_stmt(self, b, op, a, ind):
        import modgen as M
        C, cc, H = self.C, self.C.cc, self.helper()
        key = _cs_str(a.get("key"))
        if op == "card_var_new":
            amt = self.val(a.get("amount"))
            copy_ = "true" if a.get("on_clone", "copy") == "copy" else "false"
            keep = "true" if a.get("on_end", "drop") == "keep" else "false"
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [
                f"{i}{H}.NewCardVar({cv}, {key}, {amt}, {copy_}, {keep});"])
        if op == "card_var_remove":
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [f"{i}{H}.RemoveCardVar({cv}, {key});"])
        if op in ("card_number_edit", "card_cost_edit", "card_damage_edit"):
            mode = a.get("edit_mode", "add")
            if mode not in ("add", "set"):
                self.errors.append("수치 변경 방법을 다시 선택하세요.")
                return []
            amount = self.val(a.get("amount"))
            def change(cv, i):
                stat = a.get("stat", "cost") if op == "card_number_edit" else ("cost" if op == "card_cost_edit" else "damage")
                duration = a.get("duration", "combat") if op == "card_number_edit" else a.get("cost_duration", "combat")
                if stat not in dict(CARD_STATS) or duration not in dict(COST_DURATIONS):
                    self.errors.append("변경할 수치와 적용 기간을 다시 선택하세요.")
                    return []
                if stat != "cost" and op == "card_number_edit":
                    method = "EditCardDamage" if stat == "damage" else "EditCardNumber"
                    stat_arg = "" if stat == "damage" else _cs_str(stat) + ", "
                    return [f"{i}{H}.{method}({cv}, {stat_arg}{amount}, {'true' if mode == 'set' else 'false'}, {_cs_str(duration)});"]
                if stat == "cost":
                    suffix = {"combat": "ThisCombat", "turn": "ThisTurn", "played": "UntilPlayed"}.get(duration)
                    if suffix is None:
                        self.errors.append("비용 변경 기간을 다시 선택하세요.")
                        return []
                    value = f"(int)({amount})"
                    if mode == "set":
                        value = f"System.Math.Max(0, {value})"
                    method = ("Set" if mode == "set" else "Add") + suffix
                    return [f"{i}if (!{cv}.EnergyCost.CostsX && {cv}.EnergyCost.Canonical >= 0)",
                            f"{i}{{", f"{i}    {cv}.EnergyCost.{method}({value});",
                            f"{i}    {cv}.InvokeEnergyCostChanged();", f"{i}}}"]
                var = self.uid("damage")
                value = amount if mode == "set" else f"{var}.BaseValue + ({amount})"
                return [f"{i}foreach (var {var} in {cv}.DynamicVars.Values.OfType<global::MegaCrit.Sts2.Core.Localization.DynamicVars.DamageVar>())",
                        f"{i}{{", f"{i}    {var}.BaseValue = System.Math.Max(0m, {value});", f"{i}}}"]
            return self.with_card((a.get("card", "picked"), a.get("card_n")), ind, change)
        if op == "card_do":
            act = a.get("action", "draw_at")
            if act == "hand" and a.get("card") == "this":
                self.errors.append("'이 카드'를 손으로 가져오기는 사용 중에는 할 수 없습니다.")
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind,
                                  lambda cv, i: [i + _card_action(act, cv, cc, H, a.get("action_n"))])
        if op == "card_ref_keyword":
            verb = "ApplyKeyword" if a.get("action", "add") == "add" else "RemoveKeyword"
            kw = a.get("keyword") or "Retain"
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [f"{i}CardCmd.{verb}({cv}, CardKeyword.{kw});"])
        if op == "card_tag":
            import gimmick as G
            tag = a.get("tag") or ""
            if not G.find_tag(self.project, tag):
                self.errors.append("기믹 태그를 고르세요 ('기믹' 탭에서 먼저 만드세요)." if not tag else f"없는 태그: {tag}")
                return []
            fn = "AddCardTag" if a.get("action", "add") == "add" else "RemoveCardTag"
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [f'{i}{H}.{fn}({cv}, {_cs_str(tag)});'])
        if op == "card_enchant":
            en = a.get("enchant") or "Inky"
            if en not in dict(ENCHANTS):
                self.errors.append(f"없는 인챈트: {en}")
                return []
            T = f"global::MegaCrit.Sts2.Core.Models.Enchantments.{en}"
            amt = self.val(a.get("amount"))
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [
                f"{i}if (({cv}.Enchantment == null || {cv}.Enchantment is {T}) && ModelDb.Enchantment<{T}>().CanEnchant({cv})) CardCmd.Enchant<{T}>({cv}, {amt});"])
        if op == "card_enchant_clear":
            return self.with_card((a.get("card", "this"), a.get("card_n")), ind, lambda cv, i: [
                f"{i}if ({cv}.Enchantment != null) CardCmd.ClearEnchantment({cv});"])
        if op == "draw_bottom":
            pos = self.val(_pos_value(a.get("pos")))
            return [f"{ind}await {H}.DrawFromPosition({C.player}, (int)({pos}), (int)({self.val(a.get('count'))}));"]
        if op == "add_card_pos":
            i_, nc = self.uid("i"), self.uid("nc")
            card = a.get("card", "this")
            if card == "this":
                if C.kind != "card":
                    self.errors.append("'이 카드의 복사본'은 카드에서만 쓸 수 있습니다.")
                    return []
                make = f"{C.me}.CombatState!.CreateCard(CanonicalInstance, {C.player})"
            else:
                if not any(x["id"] == card for x in self.project.get("cards", [])):
                    self.errors.append(f"없는 카드: {card}")
                    return []
                make = f"{C.me}.CombatState!.CreateCard<{M.item_cls(self.project, 'card', card)}>({C.player})"
            pos = self.val(_pos_value(a.get("pos")))
            lines = [f"{ind}if ({C.player} != null)", f"{ind}{{",
                     f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}); {i_}++)", f"{ind}    {{",
                     f"{ind}        var {nc} = {make};"]
            if card == "this":
                lines.append(f"{ind}        if (IsUpgraded) CardCmd.Upgrade({nc});")
            return lines + [f"{ind}        await {H}.AddGeneratedToDrawPile({nc}, {C.player}, (int)({pos}));",
                            f"{ind}    }}", f"{ind}}}"]
        return []

    def class_stmt(self, b, op, a, ind):
        import gimmick as G
        C, cc = self.C, self.C.cc
        pl = self.uid("pl")
        src = "this"

        def wrap(lines):
            return [f"{ind}{{", f"{ind}    var {pl} = {C.player};", f"{ind}    if ({pl} != null)", f"{ind}    {{"] + \
                [f"{ind}        {x}" for x in lines] + [f"{ind}    }}", f"{ind}}}"]
        if op == "channel":
            om = G.orb_meta(self.project, a.get("orb"))
            if not om:
                self.errors.append(f"없는 구체: {a.get('orb')}")
                return []
            k = self.uid("k")
            return wrap([f"for (var {k} = 0; {k} < (int)({self.val(a.get('count'))}); {k}++)",
                         f"    await OrbCmd.Channel<{om['cls']}>({cc}, {pl});"])
        if op == "evoke":
            k = self.uid("k")
            fn = "EvokeNext" if a.get("which", "front") == "front" else "EvokeLast"
            return wrap([f"for (var {k} = 0; {k} < (int)({self.val(a.get('count'))}) && {pl}.PlayerCombatState.OrbQueue.Orbs.Count > 0; {k}++)",
                         f"    await OrbCmd.{fn}({cc}, {pl});"])
        if op == "orb_passive_all":
            o = self.uid("o")
            return wrap([f"foreach (var {o} in {pl}.PlayerCombatState.OrbQueue.Orbs.ToList())",
                         f"    await OrbCmd.Passive({cc}, {o}, null);"])
        if op == "orb_slots":
            n = self.uid("n")
            return wrap([f"var {n} = (int)({self.val(a.get('amount'))});",
                         f"if ({n} > 0) await OrbCmd.AddSlots({pl}, {n});",
                         f"else if ({n} < 0) OrbCmd.RemoveSlots({pl}, -{n});"])
        if op == "orb_grow":
            if C.kind != "orb":
                self.errors.append("'이 구체의 발현 수치 +'는 구체 블록에서만 쓸 수 있습니다.")
                return []
            return [f"{ind}_grow += {self.val(a.get('amount'))};"]
        if op == "stars":
            n = self.uid("n")
            return wrap([f"var {n} = {self.val(a.get('amount'))};",
                         f"if ({n} > 0m) await PlayerCmd.GainStars({n}, {pl});",
                         f"else if ({n} < 0m) await PlayerCmd.LoseStars(-{n}, {pl});"])
        if op == "forge":
            return wrap([f"await ForgeCmd.Forge({self.val(a.get('amount'))}, {pl}, {src});"])
        if op == "osty_summon":
            return wrap([f"await OstyCmd.Summon({cc}, {pl}, {self.val(a.get('amount'))}, {src});"])
        if op == "osty_kill":
            return wrap([f"if ({pl}.IsOstyAlive) await CreatureCmd.Kill({pl}.Osty!);"])
        if op == "osty_attack":
            amt = self.val(a.get("amount"))
            hits = max(1, int(a.get("hits", 1) or 1))
            if C.kind == "card":
                check = "global::MegaCrit.Sts2.Core.Models.Monsters.Osty.CheckMissingWithAnim(Owner)"

                def body(t, i2):
                    return [f"{i2}if (!{check})",
                            f"{i2}    await DamageCmd.Attack({amt}).FromOsty(Owner.Osty!, this, cardPlay).Targeting({t})"
                            f".WithHitCount({hits}).Execute({cc});"]
            else:
                def body(t, i2):
                    return [f"{i2}if ({C.player}?.IsOstyAlive ?? false)",
                            f"{i2}    for (var h_ = 0; h_ < {hits}; h_++)",
                            f"{i2}        await CreatureCmd.Damage({cc}, {t}, {amt}, ValueProp.Move, {C.player}!.Osty!, null, null);"]
            return self.each_target(a.get("who", "target"), ind, body)
        return []

    # ---- 기믹 블록 ----
    def gimmick_stmt(self, b, op, a, ind):
        import gimmick as G
        import modgen as M
        C, cc, me = self.C, self.C.cc, self.C.me
        H = self.helper()
        if op in ("summon", "command", "unsummon"):
            sid = a.get("summon") or ""
            if op == "command" and sid == "*":
                return [f"{ind}await {H}.CommandAll({cc}, {me});"]
            if not G.find_summon(self.project, sid):
                self.errors.append("소환수를 고르세요 ('기믹' 탭에서 먼저 만드세요)." if not sid else f"없는 소환수: {sid}")
                return []
            cls = G.summon_cls(self.project, sid)
            if op == "summon":
                return [f"{ind}await {H}.Summon<{cls}>({cc}, {me}, {C.src});"]
            if op == "command":
                return [f"{ind}await {H}.Command<{cls}>({cc}, {me});"]
            return [f"{ind}await {H}.Unsummon<{cls}>({me});"]
        if op == "pay":
            pm = M.power_meta(self.project, a.get("power"))
            if not pm:
                self.errors.append(f"'낼 수 있으면' 블록: 자원 파워를 고르세요 ({a.get('power') or '없음'}).")
                return []
            lines = [f"{ind}if (await {H}.Pay<{pm['cls']}>({cc}, {me}, {self.val(a.get('amount'))}, {C.src}))", f"{ind}{{"] + \
                self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            if b.get("else"):
                lines += [f"{ind}else", f"{ind}{{"] + self.stmts(b.get("else"), ind + "    ") + [f"{ind}}}"]
            return lines
        if op == "choice":
            opts = []
            for k, bk in (("opt1", "body"), ("opt2", "else"), ("opt3", "third")):
                lab = a.get(k)
                if _label_text(lab, "ko") or _label_text(lab, "en"):
                    opts.append((lab, b.get(bk) or []))
            if len(opts) < 2:
                self.errors.append("'하나 고르기'에는 이름이 있는 선택지가 2개 이상 필요합니다.")
                return []
            names = []
            for lab, body in opts:
                cls = self.cls_name("Choice")
                names.append(cls)
                if self.extras is not None:
                    owner = "card" if C.kind == "card" else "power"
                    self.extras.append({
                        "kind": "choice", "cls": cls,
                        "title": {"ko": _label_text(lab, "ko"), "en": _label_text(lab, "en"), "zh": _label_text(lab, "zh")},
                        "desc": {"ko": describe(body, self.project, owner, "ko"), "en": describe(body, self.project, owner, "en"),
                                 "zh": describe(body, self.project, owner, "zh")}})
            pv, iv = self.uid("pl"), self.uid("pick")
            mid = self.project["mod"]["id"]
            opt_list = ", ".join(f"{H}.Option<global::{mid}.{mid}Code.Gimmicks.{n}>({pv})" for n in names)
            lines = [f"{ind}{{", f"{ind}    var {pv} = {C.player};", f"{ind}    if ({pv} != null)", f"{ind}    {{",
                     f"{ind}        var {iv} = await {H}.Choose({cc}, {pv}, {opt_list});"]
            for i, (_lab, body) in enumerate(opts):
                lines += [f"{ind}        {'if' if i == 0 else 'else if'} ({iv} == {i})", f"{ind}        {{"] + \
                    self.stmts(body, ind + "            ") + [f"{ind}        }}"]
            return lines + [f"{ind}    }}", f"{ind}}}"]
        def picked_action(cv):
            return _card_action(a.get("action", "hand"), cv, cc, H, a.get("action_n"))
        if op == "picked_action":
            if not self.selected_cards:
                self.errors.append("‘고른 카드에 실행’은 ‘한 장마다 실행’ 안에 넣으세요.")
                return []
            return [ind + picked_action(self.selected_cards[-1])]
        if op in ("pick", "random_transform", "pick_transform", "pick_each", "random_each"):
            pile = a.get("pile", "Discard")
            cv, lst, pv = self.uid("c"), self.uid("picked"), self.uid("pl")
            conds = [G.filter_expr(self.project, a.get("ctype") or "Any", cv)]
            group = a.get("conditions")
            if group and (group.get("t") != "group" or group.get("items")):
                self.selected_cards.append(cv)
                try:
                    conds.append(self.cond(a["conditions"]))
                finally:
                    self.selected_cards.pop()
            if C.kind == "card":
                conds.append(f"{cv} != this")
            if a.get("action") == "upgrade":
                conds.append(f"{cv}.IsUpgradable")
            if op == "random_each":
                pool, remaining = self.uid("candidates"), self.uid("remaining")
                self.selected_cards.append(cv)
                try:
                    commands = self.stmts(b.get("body"), ind + "        ")
                finally:
                    self.selected_cards.pop()
                # Select the complete, distinct set before any action changes
                # a pile. Added/moved cards cannot enter this selection later.
                return [f"{ind}if ({C.player} is {{ }} {pv})", f"{ind}{{",
                        f"{ind}    var {pool} = PileType.{pile}.GetPile({pv}).Cards.Where({cv} => {' && '.join(conds)}).ToList();",
                        f"{ind}    var {lst} = new System.Collections.Generic.List<CardModel>();",
                        f"{ind}    var {remaining} = (int)({self.val(a.get('count'))});",
                        f"{ind}    while ({remaining}-- > 0 && {pool}.Count > 0)", f"{ind}    {{",
                        f"{ind}        var {cv} = {pv}.RunState.Rng.CombatCardSelection.NextItem({pool});",
                        f"{ind}        if ({cv} == null) break;",
                        f"{ind}        {pool}.Remove({cv});", f"{ind}        {lst}.Add({cv});", f"{ind}    }}",
                        f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", *commands,
                        f"{ind}    }}", f"{ind}}}"]
            if op == "random_transform":
                remaining = self.uid("remaining")
                result = a.get("result_filter", "Any")
                setup = []
                guard = ""
                change = f"await CardCmd.TransformToRandom({cv}, {pv}.PlayerRng.Transformations);"
                pool_key = a.get("result_pool", "")
                source = "ModelDb.AllCards"
                if pool_key:
                    selected = M.transform_pools(self.project).get(pool_key)
                    if not selected:
                        self.errors.append("변화 결과 캐릭터의 카드 풀을 다시 선택하세요.")
                        return []
                    source = f"ModelDb.CardPool<{selected[1]}>().AllCards"
                if result != "Any" or pool_key:
                    if result.startswith("kw:") and result[3:] in dict(M.CARD_KEYWORDS):
                        match = f"model.Keywords.Contains(CardKeyword.{result[3:]})"
                    elif result in dict(G.card_filters(self.project)):
                        tag = G.find_tag(self.project, result[4:]) if result.startswith("tag:") else None
                        match = G.filter_expr(self.project, result, "model")
                        if tag and tag.get("keyword_member"):
                            match = f"({match} || model.Keywords.Contains({tag['keyword_member']}))"
                    else:
                        self.errors.append("변화 결과에 사용할 키워드 또는 태그를 다시 선택하세요.")
                        return []
                    pool = self.uid("results")
                    setup = [f"{ind}    var {pool} = {source}.Where(model => {match}).ToList();"]
                    guard = f" && {pool}.Count > 0"
                    chosen = f"{pv}.PlayerRng.Transformations.NextItem({pool})"
                    change = f"await CardCmd.Transform({cv}, {C.me}.CombatState!.CreateCard({chosen}, {pv}));"
                after = []
                if b.get("body"):
                    previous = getattr(self, "_replacement", None)
                    self._replacement = self.uid("replacement")
                    change = f"var {self._replacement} = " + change
                    try:
                        after = self.stmts(b["body"], ind + "        ")
                    finally:
                        self._replacement = previous
                return [f"{ind}if ({C.player} is {{ }} {pv})", f"{ind}{{",
                        f"{ind}    var {lst} = PileType.{pile}.GetPile({pv}).Cards.Where({cv} => {' && '.join(conds)}).ToList();",
                        f"{ind}    var {remaining} = (int)({self.val(a.get('count'))});",
                        *setup, f"{ind}    while ({remaining}-- > 0 && {lst}.Count > 0{guard})", f"{ind}    {{",
                        f"{ind}        var {cv} = {pv}.RunState.Rng.CombatCardSelection.NextItem({lst});",
                        f"{ind}        {lst}.Remove({cv});",
                        f"{ind}        {change}", *after,
                        f"{ind}    }}", f"{ind}}}"]
            act = picked_action(cv)
            if op == "pick_transform":
                target = a.get("card", "this")
                if target == "this" and C.kind == "card":
                    target_type = M.item_cls(self.project, "card", C.item["id"])
                elif any(c["id"] == target for c in self.project.get("cards", [])):
                    target_type = M.item_cls(self.project, "card", target)
                else:
                    self.errors.append("변화 결과로 사용할 카드를 선택하세요.")
                    return []
                act = f"await CardCmd.TransformTo<{target_type}>({cv});"
            if pile == "Hand" and a.get("action") == "hand":
                self.errors.append("손패에서 골라 손으로 가져올 수는 없습니다.")
            if op == "pick_each":
                self.selected_cards.append(cv)
                commands = self.stmts(b.get("body"), ind + "        ")
                self.selected_cards.pop()
            else:
                commands = [f"{ind}        {act}"]
            return [f"{ind}{{", f"{ind}    var {pv} = {C.player};",
                    f"{ind}    var {lst} = await {H}.Pick({cc}, {pv}, PileType.{pile}, (int)({self.val(a.get('count'))}), "
                    f"{cv} => {' && '.join(conds)}, this);",
                    f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", *commands, f"{ind}    }}", f"{ind}}}"]
        if op == "delayed":
            cls = self.cls_name("Later")
            mid = self.project["mod"]["id"]
            if self.extras is not None:
                owner = "card" if C.kind == "card" else "power"
                d_ko = describe(b.get("body"), self.project, "power", "ko")
                d_en = describe(b.get("body"), self.project, "power", "en")
                d_zh = describe(b.get("body"), self.project, "power", "zh")
                when = a.get("when", "start")
                self.extras.append({
                    "kind": "delayed", "cls": cls, "when": when, "blocks": copy.deepcopy(b.get("body") or []),
                    "title": {"ko": "예약: 다음 턴" if when == "start" else "예약: 턴 종료",
                              "en": "Next Turn" if when == "start" else "End of Turn",
                              "zh": "预约：下回合" if when == "start" else "预约：回合结束"},
                    "desc": {"ko": (f"다음 턴 시작 시 ([blue]{{Amount}}[/blue]번): " if when == "start" else
                                    "이번 턴이 끝날 때 ([blue]{Amount}[/blue]번): ") + d_ko,
                             "en": ("At the start of your next turn ([blue]{Amount}[/blue] times): " if when == "start" else
                                    "At the end of this turn ([blue]{Amount}[/blue] times): ") + d_en,
                             "zh": ("下回合开始时（[blue]{Amount}[/blue]次）：" if when == "start" else
                                    "本回合结束时（[blue]{Amount}[/blue]次）：") + d_zh}})
                del owner
            # 본문도 미리 검사 (오류를 바로 보여 주려고)
            sub = _Gen(self.project, _power_ctx(), prefix=cls)
            sub.stmts(b.get("body"), ind)
            self.errors += sub.errors
            return [f"{ind}await PowerCmd.Apply<global::{mid}.{mid}Code.Gimmicks.{cls}>({cc}, {me}, {self.val(a.get('times'))}, {me}, {C.src});"]
        return []


def _dec(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        f = 0.0
    return (str(int(f)) if f.is_integer() else repr(f)) + "m"


def _card_action(action, cv, cc, H=None, n=None):
    """카드 한 장에 하는 행동 (고르기 블록·카드 참조 블록이 같이 씀). 'draw_at' 은 뽑을 더미 N번째."""
    action, n = pos_n(action, n)
    if action == "draw_at":
        return f"await {H}.PutInDrawPile({cv}, {n});"
    return {"hand": f"await CardPileCmd.Add({cv}, PileType.Hand);",
            "exhaust": f"await CardCmd.Exhaust({cc}, {cv});",
            "discard": f"await CardCmd.Discard({cc}, {cv});",
            "random_transform": f"await CardCmd.TransformToRandom({cv}, {cv}.Owner.PlayerRng.Transformations);",
            "upgrade": f"if ({cv}.IsUpgradable) CardCmd.Upgrade({cv});"}.get(action or "hand", "")


def _cs_str(text):
    """C# 문자열 리터럴 (카드 상태 이름)."""
    import json
    return json.dumps(str(text or "count").strip() or "count", ensure_ascii=False)


def _ident(name):
    import re
    s = re.sub(r"[^0-9A-Za-z_가-힣]", "_", str(name or "a"))
    return s if s and not s[0].isdigit() else "_" + s


def _used_vars(blocks):
    names = set()

    def scan_val(v):
        if isinstance(v, dict):
            if v.get("t") == "var":
                names.add(v.get("name", "a"))
            for child in v.values():
                scan_val(child)
        elif isinstance(v, list):
            for child in v:
                scan_val(child)
    for b in walk(blocks):
        a = b.get("args", {})
        if b["op"] in ("edit_var", "set_var", "change_var"):
            names.add(a.get("name", "a"))
        for v in a.values():
            scan_val(v)
            if isinstance(v, dict):
                for k in ("a", "b"):
                    scan_val(v.get(k)) if isinstance(v.get(k), dict) else None
    return sorted(names)


def _power_ctx():
    import modgen as M
    return M._Ctx("power", {"id": "x", "trigger": "none", "enemy_mode": "all"})


def uses_event_target(blocks, project):
    visited = set()
    def scan(node):
        if isinstance(node, list):
            return any(scan(child) for child in node)
        if not isinstance(node, dict):
            return False
        if any(node.get(key) == "target" for key in ("who", "target", "creature")):
            return True
        if node.get("op") == "shared_call":
            name = node.get("args", {}).get("name", "")
            if name not in visited:
                visited.add(name)
                if scan(project.get("shared_blocks", {}).get(name, [])):
                    return True
        return any(scan(value) for value in node.values())
    return scan(blocks)


def event_target_setup(C, blocks, project, enemy_expr=None, force=False):
    mode = getattr(C, "event_target", None)
    if mode not in ("random", "choose") or not (force or uses_event_target(blocks, project)):
        return []
    player, creature, context = C.player, C.me, C.cc
    lines = [f"var eventEnemies = {enemy_expr or f'{creature}.CombatState?.HittableEnemies.ToList()'};"]
    if mode == "random":
        return lines + [f"var eventTarget = eventEnemies != null && eventEnemies.Count > 0 ? {player}.RunState.Rng.CombatTargets.NextItem(eventEnemies) : null;"]
    count = getattr(C, "event_target_count", 1)
    lines += [
        "var eventTargets = new global::System.Collections.Generic.List<global::MegaCrit.Sts2.Core.Entities.Creatures.Creature>();",
        "global::MegaCrit.Sts2.Core.Entities.Creatures.Creature? eventTarget = null;",
        "if (eventEnemies != null && eventEnemies.Count > 0 && !global::MegaCrit.Sts2.Core.Combat.CombatManager.Instance.IsOverOrEnding)",
        "{",
        f"    var eventMaxTargets = global::System.Math.Min({count}, eventEnemies.Count);",
        "    var eventRun = global::MegaCrit.Sts2.Core.Runs.RunManager.Instance;",
        "    var eventChoices = eventRun.PlayerChoiceSynchronizer;",
        f"    var eventChoiceId = eventChoices.ReserveChoiceId({player});",
        f"    await {context}.SignalPlayerChoiceBegun({player}, global::MegaCrit.Sts2.Core.Entities.Multiplayer.PlayerChoiceOptions.CancelPlayCardActions);",
        "    var eventSelectedIndexes = new global::System.Collections.Generic.List<int>();",
        "    var eventMarkedNodes = new global::System.Collections.Generic.List<global::MegaCrit.Sts2.Core.Nodes.Combat.NCreature>();",
        "    try",
        "    {",
        f"        if (global::MegaCrit.Sts2.Core.Context.LocalContext.IsMe({player}) && eventRun.NetService.Type != global::MegaCrit.Sts2.Core.Multiplayer.Game.NetGameType.Replay)",
        "        {",
        "            try",
        "            {",
        "                var eventRoom = global::MegaCrit.Sts2.Core.Nodes.Rooms.NCombatRoom.Instance;",
        "                if (eventRoom != null)",
        "                {",
        "                    global::MegaCrit.Sts2.Core.Nodes.Combat.NPlayerHand.Instance?.CancelAllCardPlay();",
        "                    var eventManager = global::MegaCrit.Sts2.Core.Nodes.Combat.NTargetManager.Instance;",
        f"                    var eventOrigin = eventRoom.GetCreatureNode({creature});",
        "                    var eventPosition = eventOrigin != null ? eventOrigin.GlobalPosition + eventOrigin.Size / 2 : Godot.Vector2.Zero;",
        "                    while (eventSelectedIndexes.Count < eventMaxTargets && !global::MegaCrit.Sts2.Core.Combat.CombatManager.Instance.IsOverOrEnding",
        "                        && eventEnemies.Any(enemy => enemy.IsHittable && !eventSelectedIndexes.Contains(eventEnemies.IndexOf(enemy))))",
        "                    {",
        "                        var eventMode = global::MegaCrit.Sts2.Core.Nodes.CommonUi.NControllerManager.Instance?.IsUsingDirectionalNavigation == true",
        "                            ? global::MegaCrit.Sts2.Core.Nodes.Combat.TargetMode.Controller : global::MegaCrit.Sts2.Core.Nodes.Combat.TargetMode.ClickMouseToTarget;",
        "                        eventManager.StartTargeting(TargetType.AnyEnemy, eventPosition, eventMode,",
        "                            () => global::MegaCrit.Sts2.Core.Combat.CombatManager.Instance.IsOverOrEnding || !eventEnemies.Any(enemy => enemy.IsHittable && !eventSelectedIndexes.Contains(eventEnemies.IndexOf(enemy))),",
        "                            node => node is global::MegaCrit.Sts2.Core.Nodes.Combat.NCreature targetNode && targetNode.Entity.IsHittable && eventEnemies.Contains(targetNode.Entity) && !eventSelectedIndexes.Contains(eventEnemies.IndexOf(targetNode.Entity)));",
        "                        var eventSelectionFinished = false;",
        "                        var eventSelectedIndex = -1;",
        "                        try",
        "                        {",
        "                            var eventSelectedNode = await eventManager.SelectionFinished();",
        "                            eventSelectionFinished = true;",
        "                            if (eventSelectedNode is global::MegaCrit.Sts2.Core.Nodes.Combat.NCreature eventNode)",
        "                                eventSelectedIndex = eventEnemies.IndexOf(eventNode.Entity);",
        "                        }",
        "                        finally",
        "                        {",
        "                            if (!eventSelectionFinished && eventManager.IsInSelection) eventManager.CancelTargeting();",
        "                        }",
        "                        if (eventSelectedIndex < 0 || eventSelectedIndexes.Contains(eventSelectedIndex)) break;",
        "                        eventSelectedIndexes.Add(eventSelectedIndex);",
        "                        var eventMarkedNode = eventRoom.GetCreatureNode(eventEnemies[eventSelectedIndex]);",
        "                        if (eventMarkedNode != null) eventMarkedNodes.Add(eventMarkedNode);",
        "                        if (eventSelectedIndexes.Count < eventMaxTargets)",
        "                        {",
        "                            await eventManager.ToSignal(eventManager.GetTree(), Godot.SceneTree.SignalName.ProcessFrame);",
        "                            foreach (var eventMarked in eventMarkedNodes)",
        "                                if (Godot.GodotObject.IsInstanceValid(eventMarked)) eventMarked.ShowMultiselectReticle();",
        "                        }",
        "                    }",
        "                }",
        "            }",
        "            finally",
        "            {",
        f"                eventChoices.SyncLocalChoice({player}, eventChoiceId, global::MegaCrit.Sts2.Core.GameActions.PlayerChoiceResult.FromIndexes(eventSelectedIndexes));",
        "            }",
        "        }",
        "        else",
        "        {",
        f"            eventSelectedIndexes = (await eventChoices.WaitForRemoteChoice({player}, eventChoiceId)).AsIndexes();",
        "        }",
        "    }",
        "    finally",
        "    {",
        "        foreach (var eventMarked in eventMarkedNodes)",
        "            if (Godot.GodotObject.IsInstanceValid(eventMarked)) eventMarked.HideMultiselectReticle();",
        f"        await {context}.SignalPlayerChoiceEnded();",
        "    }",
        "    foreach (var eventIndex in eventSelectedIndexes.Distinct().Take(eventMaxTargets))",
        "        if (!global::MegaCrit.Sts2.Core.Combat.CombatManager.Instance.IsOverOrEnding && eventIndex >= 0 && eventIndex < eventEnemies.Count && eventEnemies[eventIndex].IsHittable)",
        "            eventTargets.Add(eventEnemies[eventIndex]);",
        "    eventTarget = eventTargets.FirstOrDefault();",
        "}",
    ]
    return lines


def compile_blocks(blocks, project, C, ind="        ", prefix="Blk", extras=None, allow_event=False):
    """-> (C# 줄 목록, 오류 목록). extras 목록을 주면 블록이 만든 클래스(선택지 카드·예약 파워) 정보가 쌓인다."""
    g = _Gen(project, C, prefix=prefix, extras=extras, allow_event=allow_event)
    lines = [f"{ind}{{", f"{ind}    // --- 블록 코딩 ---"]
    lines += [ind + "    " + line for line in event_target_setup(C, blocks, project)]
    for n in _used_vars(blocks):
        lines.append(f"{ind}    decimal v_{_ident(n)} = 0m;")
    lines += g.stmts(blocks, ind + "    ")
    lines.append(f"{ind}}}")
    return lines, g.errors


# 값·조건 고르기 창의 종류 목록 (Tk 와 Qt 가 같이 쓴다)
VALUE_TYPES = [("num", "숫자"), ("stack", "파워가 쌓인 수치"), ("stat", "체력 / 방어도"), ("count", "카드 수 / 적 수"),
               ("energy", "남은 에너지"), ("amount", "이 파워가 쌓인 수치 (파워 전용)"), ("round", "현재 턴 수"),
               ("rand", "무작위 범위 (최소~최대)"), ("var", "변수에 저장한 숫자"), ("op", "계산 (값 ○ 값)"),
               ("played", "사용한 카드 수 (이번 턴/전투 · 종류·태그별) — 연계"), ("summons", "소환수 수"),
               ("event", "발동 당시 수치 (넘친 양 / 기준치 도달 시)"),
               ("orbs", "구체 수 / 구체 슬롯 수"), ("orb_passive", "이 구체의 지속 수치 (구체 전용, 밀집 적용)"),
               ("orb_evoke", "이 구체의 발현 수치 (구체 전용, 밀집 적용)"), ("stars", "별 수"),
               ("energy_x", "X (이 카드에 쓴 에너지, X 비용 카드 전용)"),
               ("star_x", "X (이 카드에 쓴 별, 별 X 카드 전용)"), ("osty", "골골이 체력"), ("pet", "동료(골골이형) 체력"),
               ("card_state", "카드에 저장한 숫자 (한 장마다 따로)")]
COND_TYPES = [("group", "조건 묶음 · 모두 / 하나 이상"), ("hp_percent", "체력 비율 비교 (%)"),
              ("pile_count", "덱·더미에 카드가 있음 / 장수 비교"), ("card_identity", "고른 카드가 지정 카드임"),
              ("cmp", "비교 (값 ○ 값)"), ("chance", "확률 %"), ("has", "파워를 가지고 있음"),
              ("and", "그리고 (둘 다)"), ("or", "또는 (하나라도)"), ("not", "아니다"),
              ("osty_alive", "골골이가 살아 있음"), ("pet_alive", "동료(골골이형)가 살아 있음"),
              ("card_var_has", "카드에 저장한 값이 있음 (그 한 장)"), ("card_is", "카드의 규칙·태그·종류·추가 능력 확인")]


# 팔레트에 보이는 이름과 검색 낱말 (Tk 와 Qt 가 같이 쓴다)
PALETTE_NAMES = {
    "damage": "피해 주기 · 대상과 횟수 선택",
    "block": "방어도 얻기", "draw": "카드 뽑기", "energy": "에너지 얻기",
    "apply_power": "파워 부여하기", "remove_power": "파워 제거하기",
    "heal": "체력 회복하기", "lose_hp": "방어도를 무시하고 체력 잃기",
    "pick": "카드 골라서 한 가지 동작 실행",
    "select_cards": "카드 고르기 · 직접 선택 / 무작위 선택",
    "select_enemies": "적에게 반복 · 모든 적 / 무작위 적",
    "pick_each": "카드 골라서 한 장마다 여러 동작 실행",
    "random_each": "무작위 카드 N장 선택 · 강화 / 버리기 / 소멸 등 여러 동작 실행",
    "card_number_edit": "카드 수치 바꾸기 · 비용·피해·방어 등",
    "hand_aura_stat": "더미 지속 보정 · 비용·피해·방어",
    "aura_card_effect": "조건에 맞는 카드 사용 시 · 저장한 효과 실행",
    "aura_power_amount": "다른 카드의 파워 부여 중첩 보정",
    "card_cost_edit": "고른 카드 비용 증가 감소 설정 · 이번 턴 전투 다음 사용까지",
    "card_damage_edit": "고른 카드 피해량 데미지 증가 감소 설정 · 이번 전투",
    "picked_action": "고른 카드에 동작 추가 · ‘한 장마다 실행’ 안에서 사용",
    "pick_transform": "고른 카드를 지정한 카드로 변화시키기",
    "if": "조건을 만족하면 실행", "if_else": "조건에 따라 두 갈래로 실행",
    "repeat": "안에 넣은 블록 반복하기",
}


PALETTE_KEYWORDS = {"hand_aura_stat": "손패 뽑을 카드 더미 버린 카드 더미 지속 보정 비용 피해량 방어도 키워드", "card_number_edit": "고른 카드 비용 피해량 방어도 카드 뽑기 장수 에너지 체력 회복 손실 최대 체력 골드 수치 증가 감소 설정 이번 턴 전투 다음 사용 시까지"}
