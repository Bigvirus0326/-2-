"""
블록 코딩 -> C# 변환.

프로그램 = 블록 목록. 블록 = {"op": 이름, "args": {...}, "body": [...], "else": [...]}
값(value) = {"t": "num"|"stack"|"stat"|"count"|"energy"|"amount"|"round"|"rand"|"var"|"op", ...}
조건(cond) = {"t": "cmp"|"chance"|"has"|"and"|"or"|"not", ...}

같은 블록이 카드 / 유물 / 물약 / 파워 어디에 있든 그 자리에 맞는 C# 를 만든다 (modgen._Ctx 이름 사용).
"""
from __future__ import annotations

import copy

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
    "mod_api": ("Manosaba 전용", "#a14bc5"),
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
    "block_to": {"cat": "action", "ko": "생물 {creature}에게 방어도 {amount} · 힘 적용 {powered}",
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
    "card_upgrade": {"cat": "card", "ko": "카드 {card} 강화 · 미리보기 방식 {style}",
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
    "card_preview": {"cat": "card", "ko": "카드 미리보기 {cards} · 크기 {scale} · 방식 {style}",
                     "args": {"cards": ("code", "cards"), "scale": ("value", {"t": "num", "v": 1}),
                              "style": ("code", "CardPreviewStyle.Default")}},
    "card_preview_cards": {"cat": "card", "ko": "카드 {cards} 미리보기 · 크기 {scale}",
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
    "card_upgrade_internal": {"cat": "card", "ko": "카드 {card} 내부 강화 적용",
                               "args": {"card": ("code", "cardModel")}},
    "card_finalize_upgrade_internal": {"cat": "card", "ko": "카드 {card} 내부 강화 완료",
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
    "set_var": {"cat": "var", "ko": "변수 {name} 을(를) {amount}(으)로 정하기",
                "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 0})}},
    "change_var": {"cat": "var", "ko": "변수 {name} 에 {amount} 더하기",
                   "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 1})}},
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
                           "count": ("value", {"t": "num", "v": 1})}, "body": True},
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
    "button_on": {"cat": "fx", "ko": "버튼 {button} 켜기", "args": {"button": ("button", "")}},
    "button_off": {"cat": "fx", "ko": "버튼 {button} 끄기", "args": {"button": ("button", "")}},
    "sfx": {"cat": "fx", "ko": "소리 {path} 재생 · 음량 {volume}",
            "args": {"path": ("code", '"event:/sfx"'), "volume": ("value", {"t": "num", "v": 1})}},
    "kotodama_gain": {"cat": "mod_api", "ko": "언령 에너지 {amount} 얻기",
                       "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "manosaba_ema_summon": {"cat": "mod_api", "ko": "에마 소환 · 체력 {amount}",
                             "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "manosaba_novel_summon": {"cat": "mod_api", "ko": "소설 속 몬스터 {monster} 소환 · 체력 {amount}",
                               "args": {"monster": ("manosaba_monster", ""),
                                        "amount": ("value", {"t": "num", "v": 5})}},
    "manosaba_ignite": {"cat": "mod_api", "ko": "카드 {card}의 점화 {amount} 낮추기",
                         "args": {"card": ("code", "cardModel"), "amount": ("value", {"t": "num", "v": 1})}},
    "manosaba_attach_combust": {"cat": "mod_api", "ko": "카드 {card}에 연소 {amount} 부여",
                                 "args": {"card": ("code", "cardModel"), "amount": ("value", {"t": "num", "v": 1})}},
    "manosaba_gun_attack": {"cat": "mod_api", "ko": "총격 {target}에게 피해 {amount}",
                             "args": {"target": ("code", "target"), "amount": ("value", {"t": "num", "v": 6})}},
    "manosaba_scene_vfx": {"cat": "mod_api", "ko": "Manosaba 장면 이펙트 {mode} · 장면 {scene} · 화면 좌표 {x}, {y} · 맞춤 {fit_cover} · 스프라이트 {sprite_nodes}",
                            "args": {"mode": ("code", "PlaySceneAtCombatCenterAndWait"), "scene": ("code", '"res://Manosaba/scenes/"'),
                                     "x": ("code", "0.5f"), "y": ("code", "0.5f"), "offset_x": ("code", "0f"),
                                     "offset_y": ("code", "0f"), "fit_cover": ("code", "false"),
                                     "sprite_nodes": ("code", "null"), "timeout": ("value", {"t": "num", "v": 30})}},
    "manosaba_video": {"cat": "mod_api", "ko": "Manosaba 영상 {video} 재생 · 초록색 키 {chroma_key}",
                       "args": {"video": ("code", '"res://Manosaba/video/"'), "chroma_key": ("code", "false")}},
    "manosaba_force_win": {"cat": "mod_api", "ko": "전투 즉시 승리 · 전투 상태 {combat_state}",
                            "args": {"combat_state": ("code", "CombatState")}},
    "manosaba_resolve_stance": {"cat": "mod_api", "ko": "Manosaba 태세 {stance} 적용 · 생물 {owner} · 적용자 {applier} · 카드 {source}",
                                 "args": {"stance": ("code", "Low"), "owner": ("code", "Owner.Creature"),
                                          "applier": ("code", "Owner.Creature"), "source": ("code", "this")}},
    "manosaba_novel_friends_sfx": {"cat": "mod_api", "ko": "Manosaba 소설 친구 효과음 재생", "args": {}},
    "manosaba_add_layers": {"cat": "mod_api", "ko": "혈액 구체 {orb} 층 {amount} 추가",
                             "args": {"orb": ("code", "bloodOrb"), "amount": ("value", {"t": "num", "v": 1})}},
    "manosaba_add_firepower": {"cat": "mod_api", "ko": "화력 유물 {relic}에 {amount} 추가",
                                "args": {"relic": ("code", "relic"), "amount": ("value", {"t": "num", "v": 1})}},
    "manosaba_maximize_firepower": {"cat": "mod_api", "ko": "화력 유물 {relic}의 화력 최대로 만들기 · null 허용 {null_safe}",
                                     "args": {"relic": ("code", "relic"), "null_safe": ("bool", True)}},
    "manosaba_ignore_next_instance": {"cat": "mod_api", "ko": "파워 {power} 다음 적용 한 번 무시",
                                       "args": {"power": ("code", "temporaryPower"), "null_safe": ("bool", False)}},
    "manosaba_set_partner": {"cat": "mod_api", "ko": "파워 {power} 동료 대상 {partner}로 설정",
                              "args": {"power": ("code", "power"), "partner": ("code", "target"), "null_safe": ("bool", False)}},
    "manosaba_set_applier": {"cat": "mod_api", "ko": "파워 {power} 적용자 {applier}로 설정",
                              "args": {"power": ("code", "power"), "applier": ("code", "Owner.Creature"), "null_safe": ("bool", False)}},
    "manosaba_set_target": {"cat": "mod_api", "ko": "파워 {power} 대상 {target}로 설정",
                             "args": {"power": ("code", "power"), "target": ("code", "target"), "null_safe": ("bool", False)}},
    "manosaba_set_source_card": {"cat": "mod_api", "ko": "파워 {power} 출처 카드 {source}로 설정",
                                  "args": {"power": ("code", "power"), "source": ("code", "this"), "null_safe": ("bool", False)}},
    "manosaba_set_upgraded": {"cat": "mod_api", "ko": "파워 {power} 강화 상태 {upgraded}로 설정",
                               "args": {"power": ("code", "power"), "upgraded": ("code", "IsUpgraded"), "null_safe": ("bool", False)}},
    "manosaba_channel_orb_at": {"cat": "mod_api", "ko": "혈액 구체 {orb}를 플레이어 {player}의 구체 슬롯 {insert_index} 위치에 영창",
                                 "args": {"orb": ("code", "orbModel.ToMutable()"), "player": ("code", "Owner"),
                                          "insert_index": ("value", {"t": "num", "v": 0})}},
    "manosaba_evoke_blood_orb": {"cat": "mod_api", "ko": "혈액 구체 발현 · 결과 변수 {result} · 플레이어 {player}",
                                  "args": {"result": ("code", "num"), "player": ("code", "Owner")}},
    "manosaba_remove_main_piles": {"cat": "mod_api", "ko": "손패·뽑기·버리기 더미 카드를 전투에서 제거 · 플레이어 {player}",
                                    "args": {"player": ("code", "Owner")}},
    "manosaba_owner_attack_anim": {"cat": "mod_api", "ko": "Manosaba 카드 소유자 공격 동작 재생", "args": {}},
    "manosaba_show_button": {"cat": "mod_api", "ko": "Manosaba 전투 버튼 {button} 표시 · 플레이어 {player}",
                              "args": {"button": ("code", "FanService"), "player": ("code", "Owner")}},
    "manosaba_power_duplicate_callback": {"cat": "mod_api", "ko": "파워 {power} 복제 카드 효과 호출",
                                          "args": {"power": ("code", "power")}},
    "manosaba_pet_ai_assign": {"cat": "mod_api", "ko": "동료 {pet}의 적 행동 슬롯을 {copy_from} 기준으로 지정",
                                "args": {"pet": ("code", "pet"), "copy_from": ("code", "null")}},
    "manosaba_pet_ai_advance": {"cat": "mod_api", "ko": "동료 {pet}의 다음 적 행동 선택 · 대상 목록 {targets}",
                                 "args": {"pet": ("code", "pet"), "targets": ("code", "targets")}},
    "manosaba_toggle_creature_node": {"cat": "mod_api", "ko": "전투 생물 노드 {node} 상호작용 가능 {interactable}",
                                       "args": {"node": ("code", "nCreature"), "interactable": ("code", "true")}},
    "manosaba_dying_message_upgrade": {"cat": "mod_api", "ko": "파워 {power} 사망 메시지 강화 · null 허용 {null_safe}",
                                        "args": {"power": ("code", "dyingMessagePower"), "null_safe": ("bool", True)}},
    "manosaba_run_side_turn_effect": {"cat": "mod_api", "ko": "파워 {power}의 {side} 턴 시작 효과 실행 · 생물 {creatures} · 전투 상태 {state}",
                                       "args": {"power": ("code", "power"), "side": ("code", "enemy.Side"),
                                                "creatures": ("code", "creatures"), "state": ("code", "state")}},
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
               "card_finalize_upgrade_internal", "card_transform_to", "keyword_this", "keyword_cards"]),
    ("flow", ["shared_call", "if", "if_else", "repeat", "each_enemy", "random_enemy", "wait", "wait_scaled"]),
    ("var", ["set_var", "change_var"]),
    ("gimmick", ["pay", "summon", "command", "unsummon", "choice", "pick", "random_transform", "pick_transform", "pick_each", "picked_action", "delayed"]),
    ("class", ["channel", "orb_channel_model", "orb_channel_type", "orb_passive_model", "evoke", "orb_passive_all", "orb_slots", "orb_slots_to", "orb_grow", "stars", "forge",
               "osty_summon", "osty_attack", "osty_kill", "pet_summon", "pet_attack", "pet_act", "pet_kill", "add_pet_model"]),
    ("mod_api", ["kotodama_gain", "manosaba_ema_summon", "manosaba_novel_summon", "manosaba_ignite", "manosaba_attach_combust",
                 "manosaba_gun_attack", "manosaba_scene_vfx", "manosaba_video", "manosaba_force_win",
                 "manosaba_resolve_stance", "manosaba_novel_friends_sfx", "manosaba_add_layers", "manosaba_add_firepower",
                 "manosaba_maximize_firepower", "manosaba_ignore_next_instance", "manosaba_set_partner",
                 "manosaba_set_applier", "manosaba_set_target", "manosaba_set_source_card", "manosaba_set_upgraded",
                 "manosaba_channel_orb_at", "manosaba_evoke_blood_orb", "manosaba_remove_main_piles",
                 "manosaba_owner_attack_anim", "manosaba_show_button", "manosaba_power_duplicate_callback",
                 "manosaba_pet_ai_assign", "manosaba_pet_ai_advance", "manosaba_toggle_creature_node",
                 "manosaba_dying_message_upgrade", "manosaba_run_side_turn_effect"]),
    ("fx", ["fx", "button_on", "button_off", "sfx", "play_vfx_on_creature"]),
]
BODY_KEYS = ("body", "else", "third")
PICK_PILES = [("Hand", "손패"), ("Draw", "뽑을 카드 더미"), ("Discard", "버린 카드 더미"), ("Exhaust", "소멸한 카드 더미")]
PICK_ACTIONS = [("hand", "손으로 가져오기"), ("top", "뽑을 더미 맨 위에 놓기"), ("exhaust", "소멸"), ("discard", "버리기"),
                ("upgrade", "강화 (이번 전투)"), ("random_transform", "무작위 카드로 변화")]
DELAY_WHEN = [("start", "다음 내 턴 시작에"), ("end", "이번 턴이 끝날 때")]
PLAYED_SCOPES = [("turn", "이번 턴에"), ("combat", "이번 전투에서")]

WHO = {"self": "나", "target": "대상", "it": "그 적", "all": "모든 적", "random": "무작위 적"}
WHO_EN = {"self": "you", "target": "the target", "it": "that enemy", "all": "ALL enemies", "random": "a random enemy"}
CARD_TYPES = [("Any", "아무"), ("Attack", "공격"), ("Skill", "스킬"), ("Power", "파워")]
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
    opts.append(("it", "그 적 (반복 안)"))
    if multi:
        opts += [("all", "모든 적"), ("random", "무작위 적")]
    return opts


def new_block(op):
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
    if op in ("button_on", "button_off"):
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


def block_caption(b):
    """블록에 보일 글 ({칸} 자리 포함). 원본에서 풀어낸 블록은 블록마다 다르다."""
    op = b.get("op")
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
    return SPECS[b["op"]]["args"][key][0]


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


def cond_label(c, project=None, lang="ko", card=False):
    if not isinstance(c, dict):
        return "?"
    t = c.get("t")
    V = lambda x: value_label(x, project, lang, card)  # noqa: E731
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
    if t == "src":
        return "직접 조건 " + _short_code(c.get("code"), 48)
    return "?"


def _fmt(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return str(int(f)) if f.is_integer() else str(f)


# ---------------------------------------------------------------------------
# 설명문 자동 생성
# ---------------------------------------------------------------------------
def describe(blocks, project, owner_kind, lang="ko"):
    if lang == "zh":
        from card_zh import blocks_text
        return blocks_text(blocks, project, owner_kind == "card")
    card = owner_kind == "card"
    out = []
    for b in blocks or []:
        s = _describe_one(b, project, owner_kind, lang, card)
        if s:
            out.append(s)
    return " ".join(out)


def _describe_one(b, project, owner_kind, lang, card):
    a = b.get("args", {})
    V = lambda k: value_label(a.get(k), project, lang, card)  # noqa: E731
    W = lambda k: (WHO if lang == "ko" else WHO_EN).get(a.get(k, "self"), "")  # noqa: E731
    op = b["op"]
    ko = lang == "ko"
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
    if op == "kotodama_gain":
        return f"언령 에너지를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} Kotodama energy."
    if op == "manosaba_ema_summon":
        return f"에마를 소환하거나 체력을 {V('amount')}만큼 늘립니다." if ko else f"Summon Ema or raise her HP by {V('amount')}."
    if op == "manosaba_novel_summon":
        n = str(a.get("monster", "")).split(".")[-1]
        return f"{n}을(를) 소환합니다 (체력 {V('amount')})." if ko else f"Summon {n} with {V('amount')} HP."
    if op == "manosaba_ignite":
        return f"고른 카드의 점화를 {V('amount')} 낮춥니다." if ko else f"Reduce the selected card's Ignite by {V('amount')}."
    if op == "manosaba_attach_combust":
        return f"고른 카드에 연소 {V('amount')}를 부여합니다." if ko else f"Attach {V('amount')} Combust to the selected card."
    if op == "manosaba_gun_attack":
        return f"총격으로 {a.get('target', '')}에게 피해 {V('amount')}를 줍니다." if ko else \
            f"Fire a gun attack at {a.get('target', '')} for {V('amount')} damage."
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
    if op == "manosaba_scene_vfx":
        return f"전투 장면 이펙트 {a.get('scene', '')}를 재생합니다." if ko else \
            f"Play combat scene effect {a.get('scene', '')}."
    if op == "manosaba_video":
        return f"영상 {a.get('video', '')}를 재생합니다." if ko else f"Play video {a.get('video', '')}."
    if op == "manosaba_force_win":
        return "Manosaba 전투를 승리로 끝냅니다." if ko else "End the Manosaba combat in victory."
    if op == "manosaba_resolve_stance":
        return f"{a.get('stance', '')} 태세를 {a.get('owner', '')}에게 적용합니다." if ko else \
            f"Resolve {a.get('stance', '')} stance for {a.get('owner', '')}."
    if op == "manosaba_novel_friends_sfx":
        return "Manosaba 소설 친구 효과음을 재생합니다." if ko else "Play the Manosaba novel friends sound."
    if op == "manosaba_add_layers":
        return f"혈액 구체 {a.get('orb', '')}에 층 {V('amount')}을 추가합니다." if ko else \
            f"Add {V('amount')} layers to BloodOrb {a.get('orb', '')}."
    if op == "manosaba_add_firepower":
        return f"화력 유물 {a.get('relic', '')}에 {V('amount')} 화력을 추가합니다." if ko else \
            f"Add {V('amount')} firepower to {a.get('relic', '')}."
    if op == "manosaba_maximize_firepower":
        return f"화력 유물 {a.get('relic', '')}의 화력을 최대로 만듭니다." if ko else \
            f"Maximize firepower on {a.get('relic', '')}."
    if op == "manosaba_channel_orb_at":
        return f"혈액 구체 {a.get('orb', '')}를 {a.get('player', '')}의 {V('insert_index')}번 위치에 영창합니다." if ko else \
            f"Channel {a.get('orb', '')} into slot {V('insert_index')} for {a.get('player', '')}."
    if op == "manosaba_evoke_blood_orb":
        return f"혈액 구체를 발현해 결과를 {a.get('result', '')}에 저장합니다." if ko else \
            f"Evoke a Blood Orb and store the result in {a.get('result', '')}."
    if op == "manosaba_remove_main_piles":
        return f"{a.get('player', '')}의 손패·뽑기·버리기 더미 카드를 전투에서 제거합니다." if ko else \
            f"Remove {a.get('player', '')}'s hand, draw, and discard cards from combat."
    if op == "manosaba_owner_attack_anim":
        return "Manosaba 카드 소유자의 공격 동작을 재생합니다." if ko else "Play the card owner's Manosaba attack animation."
    if op == "manosaba_show_button":
        return f"Manosaba 전투 버튼 {a.get('button', '')}를 표시합니다." if ko else \
            f"Show Manosaba combat button {a.get('button', '')}."
    if op == "manosaba_power_duplicate_callback":
        return f"파워 {a.get('power', '')}의 복제 카드 효과를 실행합니다." if ko else \
            f"Run the duplicate card callback on {a.get('power', '')}."
    if op == "manosaba_pet_ai_assign":
        return f"동료 {a.get('pet', '')}의 행동 슬롯을 {a.get('copy_from', '')} 기준으로 지정합니다." if ko else \
            f"Assign the pet {a.get('pet', '')}'s AI slot from {a.get('copy_from', '')}."
    if op == "manosaba_pet_ai_advance":
        return f"동료 {a.get('pet', '')}의 적 행동을 다음 유효한 동작으로 넘깁니다." if ko else \
            f"Advance {a.get('pet', '')} to its next valid enemy move."
    if op == "manosaba_toggle_creature_node":
        return f"전투 생물 노드 {a.get('node', '')}의 상호작용 가능 상태를 {a.get('interactable', '')}(으)로 합니다." if ko else \
            f"Set interaction on creature node {a.get('node', '')} to {a.get('interactable', '')}."
    if op == "manosaba_dying_message_upgrade":
        return f"파워 {a.get('power', '')}의 사망 메시지를 강화합니다." if ko else \
            f"Upgrade the dying message on power {a.get('power', '')}."
    if op == "manosaba_run_side_turn_effect":
        return f"파워 {a.get('power', '')}의 {a.get('side', '')} 턴 시작 효과를 실행합니다." if ko else \
            f"Run the turn-start effect on {a.get('power', '')} for {a.get('side', '')}."
    if op == "manosaba_ignore_next_instance":
        return f"파워 {a.get('power', '')}의 다음 적용을 한 번 무시합니다." if ko else \
            f"Ignore the next instance on power {a.get('power', '')}."
    setter_labels = {"manosaba_set_partner": ("동료", "partner", "partner"),
                     "manosaba_set_applier": ("적용자", "applier", "applier"),
                     "manosaba_set_target": ("대상", "target", "target"),
                     "manosaba_set_source_card": ("출처 카드", "source", "source card"),
                     "manosaba_set_upgraded": ("강화 상태", "upgraded", "upgraded state")}
    if op in setter_labels:
        label, key, en_label = setter_labels[op]
        return f"파워 {a.get('power', '')}의 {label}을(를) {a.get(key, '')}(으)로 설정합니다." if ko else \
            f"Set power {a.get('power', '')} {en_label} to {a.get(key, '')}."
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
        body = describe(b.get("body"), project, owner_kind, lang)
        if ko and c.get("t") == "cmp":
            s = f"{cmp_text(c, project, lang, card, conditional=True)} {body}"   # '3 이상이면', '3을 초과하면', '3과 같으면'
        elif ko and cond.endswith("있음"):
            s = f"{cond[:-2]}있으면 {body}"       # '살아 있음' → '살아 있으면'
        elif ko and cond.endswith("확률"):
            s = f"{cond}로 {body}"                # '50% 확률로'
        else:
            s = f"{cond}이면 {body}" if ko else f"If {cond}: {body}"
        if op == "if_else" and b.get("else"):
            s += (" 아니면 " if ko else " Otherwise: ") + describe(b.get("else"), project, owner_kind, lang)
        return s
    if op == "repeat":
        return (f"{V('times')}번: " if ko else f"{V('times')} times: ") + describe(b.get("body"), project, owner_kind, lang)
    if op == "each_enemy":
        return ("모든 적에게 각각: " if ko else "For each enemy: ") + describe(b.get("body"), project, owner_kind, lang)
    if op == "random_enemy":
        return ("무작위 적 1명에게: " if ko else "To a random enemy: ") + describe(b.get("body"), project, owner_kind, lang)
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
        body = describe(b.get("body"), project, owner_kind, lang)
        els = describe(b.get("else"), project, owner_kind, lang)
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
                f"[gold]{n}[/gold]({describe(body, project, owner_kind, lang).rstrip('.')})" for n, body in opts) + "."
        return "Choose one: " + " / ".join(
            f"[gold]{n}[/gold] ({describe(body, project, owner_kind, lang).rstrip('.')})" for n, body in opts) + "."
    if op == "picked_action":
        action = a.get("action")
        if ko:
            return f"고른 카드에 {dict(PICK_ACTIONS).get(action, '')}."
        return {"hand": "Move it to your hand.", "top": "Put it on top of your draw pile.",
                "exhaust": "Exhaust it.", "discard": "Discard it.", "upgrade": "Upgrade it.",
                "random_transform": "Transform it into a random card."}.get(action, "")
    if op in ("pick", "random_transform", "pick_transform", "pick_each"):
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
        if op == "pick_each":
            detail = describe(b.get("body"), project, owner_kind, lang)
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
            act = {"hand": "손으로 가져옵니다", "top": "뽑을 카드 더미 맨 위에 놓습니다", "exhaust": "소멸시킵니다",
                   "discard": "버립니다", "random_transform": "무작위 카드로 변화시킵니다", "upgrade": "강화합니다"}.get(a.get("action"), "")
            return f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} {V('count')}장을 골라 {act}."
        act = {"hand": "put it into your hand", "top": "put it on top of your draw pile", "exhaust": "Exhaust it",
               "discard": "discard it", "random_transform": "transform it into a random card", "upgrade": "Upgrade it"}.get(a.get("action"), "")
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
        body = describe(b.get("body"), project, owner_kind, lang)
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
                self.errors.append("유물에는 '대상'이 없습니다 ('그 적'이나 '모든 적'을 쓰세요).")
                return "null"
            return C.other
        if who == "it":
            if not self.its:
                self.errors.append("'그 적'은 '모든 적 각각에게' / '무작위 적 1명에게' 블록 안에서만 쓸 수 있습니다.")
                return "null"
            return self.its[-1]
        return "null"

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
            return [f"{ind}{{", f"{ind}    var {v} = {self.rng()}.NextItem({self.enemies()}.ToList());",
                    f"{ind}    if ({v} != null)", f"{ind}    {{"] + body_fn(v, ind + "        ") + [f"{ind}    }}", f"{ind}}}"]
        cr = self.creature(who)
        if cr == self.C.me:
            return body_fn(cr, ind)
        return [f"{ind}if ({cr} != null)", f"{ind}{{"] + body_fn(cr, ind + "    ") + [f"{ind}}}"]

    def stmt(self, b, ind):
        import modgen as M
        C, a, op = self.C, b.get("args", {}), b.get("op")
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
                amount = self.val(a.get("amount"))
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
            amt = self.val(a.get("amount"))
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
            chain += f".FromCard((CardModel)this).Execute({cc});"
            return [f"{ind}await {chain}"]
        if op == "damage":
            amt = self.val(a.get("amount"))
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
            args = [context, creature, self.val(a.get("amount")), props, str(a.get("attacker") or me).strip()]
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
                    f"{self.val(a.get('amount'))}{silent});"]
        if op == "power_apply_type":
            creature = str(a.get("creature") or "target").strip()
            power_type = str(a.get("power_type") or "").strip()
            if not creature or not power_type:
                self.errors.append("파워 유형과 대상 생물을 입력하세요.")
                return []
            if not power_type.startswith("global::"):
                power_type = "global::" + power_type
            return [f"{ind}await PowerCmd.Apply<{power_type}>({cc}, {creature}, {self.val(a.get('amount'))}, "
                    f"{a.get('applier') or me}, {a.get('source') or C.src});"]
        if op == "power_apply_model":
            return [f"{ind}await PowerCmd.Apply({cc}, {a.get('power') or 'powerModel'}, {a.get('creature') or 'target'}, "
                    f"{self.val(a.get('amount'))}, {a.get('applier') or me}, {a.get('source') or C.src});"]
        if op == "block_to":
            creature = str(a.get("creature") or "target").strip()
            if not creature:
                self.errors.append("방어도를 받을 생물 식을 입력하세요.")
                return []
            prop = "ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered"
            play = C.play if a.get("card_play", True) and C.kind == "card" else "null"
            return [f"{ind}await CreatureCmd.GainBlock({creature}, {self.val(a.get('amount'))}, {prop}, {play});"]
        if op == "heal_to":
            creature = str(a.get("creature") or "target").strip()
            if not creature:
                self.errors.append("회복할 생물 식을 입력하세요.")
                return []
            return [f"{ind}await CreatureCmd.Heal({creature}, {self.val(a.get('amount'))});"]
        if op == "block":
            return [f"{ind}await CreatureCmd.GainBlock({me}, {self.val(a.get('amount'))}, "
                    f"{'ValueProp.Move' if C.kind == 'card' else 'ValueProp.Unpowered'}, {C.play});"]
        if op == "lose_block":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "target"), ind,
                                    lambda t, i2: [f"{i2}await CreatureCmd.LoseBlock({cc}, {t}, {amt}, {me});"])
        if op == "lose_block_to":
            return [f"{ind}await CreatureCmd.LoseBlock({a.get('creature') or 'target'}, {self.val(a.get('amount'))});"]
        if op == "kill_creature":
            return [f"{ind}await CreatureCmd.Kill({a.get('creature') or 'target'});"]
        if op == "draw":
            return with_player([f"{ind}await CardPileCmd.Draw({cc}, {self.val(a.get('amount'))}, {C.player});"])
        if op == "energy":
            return with_player([f"{ind}await PlayerCmd.GainEnergy({self.val(a.get('amount'))}, {C.player});"])
        if op == "energy_to":
            return [f"{ind}await PlayerCmd.GainEnergy({self.val(a.get('amount'))}, {a.get('player') or C.player});"]
        if op == "gold_to":
            return [f"{ind}await PlayerCmd.GainGold({self.val(a.get('amount'))}, {a.get('player') or C.player});"]
        if op == "gold":
            return with_player([f"{ind}await PlayerCmd.GainGold({self.val(a.get('amount'))}, {C.player});"])
        if op == "lose_gold":
            return [f"{ind}await PlayerCmd.LoseGold({self.val(a.get('amount'))}, {a.get('player') or C.player}, "
                    f"{a.get('loss_type') or 'GoldLossType.Spent'});"]
        if op == "end_turn":
            return [f"{ind}PlayerCmd.EndTurn({a.get('player') or C.player}, canBackOut: {a.get('can_back_out') or 'false'});"]
        if op == "card_exhaust":
            return [f"{ind}await CardCmd.Exhaust({cc}, {a.get('card') or 'cardModel'}, "
                    f"{'true' if a.get('played') else 'false'}, {'true' if a.get('triggered') else 'false'});"]
        if op == "card_upgrade":
            style = str(a.get("style") or "").strip()
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
            return [f"{ind}await CardPileCmd.Draw({cc}, {self.val(a.get('amount'))}, {a.get('player') or C.player});"]
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
            return [f"{ind}CardCmd.PreviewCardPileAdd({a.get('cards') or 'cards'}, "
                    f"(float)({self.val(a.get('scale'))}), {a.get('style') or 'CardPreviewStyle.Default'});"]
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
            return [f"{ind}{a.get('card') or 'cardModel'}.EnergyCost.SetThisTurnOrUntilPlayed({self.val(a.get('amount'))});"]
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
                    f"{self.val(a.get('amount'))}, {me}, {C.src});"]
        if op == "remove_power_model":
            return [f"{ind}await PowerCmd.Remove({a.get('power') or 'powerModel'});"]
        if op == "set_current_hp":
            return [f"{ind}await CreatureCmd.SetCurrentHp({a.get('creature') or me}, {self.val(a.get('amount'))});"]
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
            return [f"{ind}var {n} = (int)({self.val(a.get('amount'))});",
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
        if op in ("kotodama_gain", "manosaba_ema_summon", "manosaba_novel_summon",
                  "manosaba_ignite", "manosaba_attach_combust", "manosaba_scene_vfx",
                  "manosaba_video", "manosaba_force_win", "manosaba_resolve_stance",
                  "manosaba_novel_friends_sfx", "manosaba_add_layers", "manosaba_add_firepower",
                  "manosaba_maximize_firepower", "manosaba_ignore_next_instance", "manosaba_set_partner",
                  "manosaba_set_applier", "manosaba_set_target", "manosaba_set_source_card", "manosaba_set_upgraded",
                  "manosaba_channel_orb_at", "manosaba_evoke_blood_orb", "manosaba_remove_main_piles",
                  "manosaba_owner_attack_anim", "manosaba_show_button", "manosaba_power_duplicate_callback",
                  "manosaba_pet_ai_assign", "manosaba_pet_ai_advance", "manosaba_toggle_creature_node",
                  "manosaba_dying_message_upgrade", "manosaba_run_side_turn_effect"):
            if (self.project.get("takeover") or {}).get("mod", "").casefold() != "manosaba":
                self.errors.append("Manosaba 전용 블록은 Manosaba 모드 프로젝트에서만 쓸 수 있습니다.")
                return []
            if op == "manosaba_channel_orb_at":
                player = str(a.get("player") or C.player).strip()
                orb = str(a.get("orb") or "orbModel.ToMutable()").strip()
                if not player or not orb:
                    self.errors.append("영창할 구체와 플레이어 식을 입력하세요.")
                    return []
                return [f"{ind}await global::Manosaba.Characters.JogasakiNoah.Cards.OrbGapChannelHelper."
                        f"ChannelAt({cc}, {orb}, {player}, (int)({self.val(a.get('insert_index'))}));"]
            if op == "manosaba_evoke_blood_orb":
                import re
                result_name = str(a.get("result") or "num").strip()
                player = str(a.get("player") or C.player).strip()
                if not re.fullmatch(r"[A-Za-z_]\w*", result_name) or not player:
                    self.errors.append("결과 변수 이름과 플레이어 식을 확인하세요.")
                    return []
                return [f"{ind}decimal {result_name} = await global::Manosaba.Characters.JogasakiNoah.Cards."
                        f"SekketsusoujitsuHelper.EvokeNextBloodOrb({cc}, {player});"]
            if op == "manosaba_remove_main_piles":
                player = str(a.get("player") or C.player).strip()
                if not player:
                    self.errors.append("플레이어 식을 입력하세요.")
                    return []
                cards = self.uid("removedCards")
                return [f"{ind}var {cards} = new global::System.Collections.Generic.List<global::MegaCrit.Sts2.Core.Entities.Cards.CardModel>();",
                        f"{ind}{cards}.AddRange(PileType.Draw.GetPile({player}).Cards);",
                        f"{ind}{cards}.AddRange(PileType.Hand.GetPile({player}).Cards);",
                        f"{ind}{cards}.AddRange(PileType.Discard.GetPile({player}).Cards);",
                        f"{ind}if ({cards}.Count > 0) await CardPileCmd.RemoveFromCombat({cards});"]
            if op == "manosaba_owner_attack_anim":
                if C.kind != "card":
                    self.errors.append("소유자 공격 동작 블록은 카드 효과에서만 쓸 수 있습니다.")
                    return []
                return [f"{ind}await PlayOwnerAttackAnimAsync();"]
            if op == "manosaba_show_button":
                button_paths = {
                    "FanService": "global::manosaba.Characters.SawatariCoco.Visuals.FanServiceSkillButtonUi",
                    "CouldItBeThatSkill": "global::Manosaba.Characters.TachibanaSherry.Visuals.CouldItBeThatSkillButtonUi",
                }
                button = button_paths.get(str(a.get("button") or "FanService").strip())
                if not button:
                    self.errors.append("표시할 버튼은 FanService 또는 CouldItBeThatSkill입니다.")
                    return []
                return [f"{ind}{button}.EnsureShown({a.get('player') or C.player});"]
            if op == "manosaba_power_duplicate_callback":
                return [f"{ind}{a.get('power') or 'power'}.OnDuplicateCardPlayed();"]
            if op == "manosaba_pet_ai_assign":
                pet = str(a.get("pet") or "pet").strip()
                copied = str(a.get("copy_from") or "null").strip()
                if not pet:
                    self.errors.append("동료 생물 식을 입력하세요.")
                    return []
                args = pet + (f", {copied}" if copied and copied != "null" else "")
                return [f"{ind}global::Manosaba.Characters.JogasakiNoah.Powers.PetEnemyAiPower.AssignAiSlot({args});"]
            if op == "manosaba_pet_ai_advance":
                pet = str(a.get("pet") or "pet").strip()
                targets = str(a.get("targets") or "targets").strip()
                if not pet or not targets:
                    self.errors.append("동료 생물과 대상 목록 식을 입력하세요.")
                    return []
                return [f"{ind}global::Manosaba.Characters.JogasakiNoah.Powers.PetEnemyAiPower.TryAdvanceToValidMove({pet}, {targets});"]
            if op == "manosaba_toggle_creature_node":
                node = str(a.get("node") or "nCreature").strip()
                interactable = str(a.get("interactable") or "true").strip()
                if not node or interactable not in ("true", "false"):
                    self.errors.append("전투 생물 노드 식과 상호작용 가능 값을 확인하세요.")
                    return []
                return [f"{ind}{node}.ToggleIsInteractable(on: {interactable});"]
            if op == "manosaba_dying_message_upgrade":
                power = str(a.get("power") or "dyingMessagePower").strip()
                if not power:
                    self.errors.append("사망 메시지 파워 식을 입력하세요.")
                    return []
                accessor = "?." if a.get("null_safe") else "."
                return [f"{ind}{power}{accessor}Upgrade();"]
            if op == "manosaba_run_side_turn_effect":
                power = str(a.get("power") or "power").strip()
                side = str(a.get("side") or "enemy.Side").strip()
                creatures = str(a.get("creatures") or "creatures").strip()
                state = str(a.get("state") or "state").strip()
                if not power or not side or not creatures or not state:
                    self.errors.append("파워, 턴 진영, 생물 목록, 전투 상태를 입력하세요.")
                    return []
                return [f"{ind}await {power}.AfterSideTurnStart({side}, {creatures}, {state});"]
            if op == "manosaba_resolve_stance":
                stance = str(a.get("stance") or "Low").strip().capitalize()
                if stance not in ("Low", "Mid", "High"):
                    self.errors.append("태세는 Low, Mid, High 중에서 선택하세요.")
                    return []
                return [f"{ind}await global::Manosaba.Characters.Common.Overrides.ManosabaKeywords."
                        f"Resolve{stance}Stance({a.get('owner') or 'Owner.Creature'}, "
                        f"{a.get('applier') or 'Owner.Creature'}, {a.get('source') or 'this'});"]
            if op == "manosaba_novel_friends_sfx":
                return [f"{ind}global::manosaba.Characters.NatsumeAnan.Cards.NovelSettingNoahFriendsSfx.TryPlay();"]
            if op == "manosaba_add_layers":
                orb = str(a.get("orb") or "bloodOrb").strip()
                if not orb:
                    self.errors.append("층을 추가할 혈액 구체 식을 입력하세요.")
                    return []
                return [f"{ind}{orb}.AddLayers({self.val(a.get('amount'))});"]
            if op == "manosaba_add_firepower":
                relic = str(a.get("relic") or "relic").strip()
                if not relic:
                    self.errors.append("화력을 추가할 유물 식을 입력하세요.")
                    return []
                return [f"{ind}{relic}.AddFirepower((int)({self.val(a.get('amount'))}));"]
            if op == "manosaba_maximize_firepower":
                relic = str(a.get("relic") or "relic").strip()
                if not relic:
                    self.errors.append("화력을 최대로 만들 유물 식을 입력하세요.")
                    return []
                accessor = "?." if a.get("null_safe") else "."
                return [f"{ind}{relic}{accessor}MaximizeFirepower();"]
            if op == "manosaba_ignore_next_instance":
                power = str(a.get("power") or "temporaryPower").strip()
                if not power:
                    self.errors.append("파워 식을 입력하세요.")
                    return []
                accessor = "?." if a.get("null_safe") else "."
                return [f"{ind}{power}{accessor}IgnoreNextInstance();"]
            setter_specs = {
                "manosaba_set_partner": ("partner", "SetPartner"),
                "manosaba_set_applier": ("applier", "SetApplier"),
                "manosaba_set_target": ("target", "SetTarget"),
                "manosaba_set_source_card": ("source", "SetSourceCard"),
                "manosaba_set_upgraded": ("upgraded", "SetUpgraded"),
            }
            if op in setter_specs:
                field, method = setter_specs[op]
                power = str(a.get("power") or "power").strip()
                value = str(a.get(field) or "").strip()
                if not power or not value:
                    self.errors.append("파워와 설정할 값을 입력하세요.")
                    return []
                accessor = "?." if a.get("null_safe") else "."
                return [f"{ind}{power}{accessor}{method}({value});"]
            if op == "manosaba_scene_vfx":
                mode = str(a.get("mode") or "PlaySceneAtCombatCenterAndWait").strip()
                methods = {"PlaySceneAtCombatCenter", "PlaySceneAtCombatCenterAndWait",
                           "PlaySceneAtCombatViewportPosition", "PlaySceneAtCombatViewportPositionAndWait"}
                scene = str(a.get("scene") or "").strip()
                if mode not in methods or not scene:
                    self.errors.append("Manosaba 장면 효과의 호출 방식과 장면 경로를 입력하세요.")
                    return []
                args = [scene]
                if "ViewportPosition" in mode:
                    args.extend([f"(float)({a.get('x') or '0.5f'})", f"(float)({a.get('y') or '0.5f'})",
                                 f"offsetX: (float)({a.get('offset_x') or '0f'})",
                                 f"offsetY: (float)({a.get('offset_y') or '0f'})"])
                args.extend([f"fitCoverViewport: {a.get('fit_cover') or 'false'}",
                             f"spriteNodeNames: {a.get('sprite_nodes') or 'null'}"])
                if mode.endswith("AndWait"):
                    args.append(f"timeoutSeconds: (float)({self.val(a.get('timeout'))})")
                prefix = "await " if mode.endswith("AndWait") else ""
                return [f"{ind}{prefix}global::Manosaba.Characters.Common.Commands.ManosabaVfxCmd.{mode}({', '.join(args)});"]
            if op == "manosaba_video":
                video = str(a.get("video") or "").strip()
                if not video:
                    self.errors.append("재생할 영상 경로를 입력하세요.")
                    return []
                return [f"{ind}global::Manosaba.Characters.Common.Commands.ManosabaVideoCmd."
                        f"PlayFullscreenOneShot({video}, chromaKeyGreen: {a.get('chroma_key') or 'false'});"]
            if op == "manosaba_force_win":
                return [f"{ind}await global::Manosaba.Characters.Common.Commands.ManosabaCombatCmd."
                        f"ForceWinWithoutDeathOrEscape({a.get('combat_state') or 'CombatState'});"]
            amount = self.val(a.get("amount"))
            if op == "kotodama_gain":
                return with_player([f"{ind}global::manosaba.Characters.NatsumeAnan.KotodamaEnergy."
                                    f"Gain({C.player}, (int)({amount}));"])
            if op == "manosaba_ema_summon":
                if C.kind != "card":
                    self.errors.append("에마 소환은 카드 효과에서만 쓸 수 있습니다.")
                    return []
                return [f"{ind}await global::Manosaba.Characters.Common.Monsters.SakurabaEmaDogCmd."
                        f"Summon({cc}, {C.player}, {amount}, {C.src});"]
            if op == "manosaba_novel_summon":
                if C.kind != "card":
                    self.errors.append("소설 속 몬스터 소환은 카드 효과에서만 쓸 수 있습니다.")
                    return []
                takeover = self.project.get("takeover") or {}
                monster = str(a.get("monster") or "").replace("global::", "").strip()
                if monster not in (takeover.get("novel_monsters") or []):
                    self.errors.append("소환할 Manosaba 몬스터를 선택하세요.")
                    return []
                return [f"{ind}await global::Manosaba.Characters.Common.Monsters.NovelSettingMonsterCmd."
                        f"Summon<global::{monster}>({cc}, {C.player}, {C.src}, {amount});"]
            if op in ("manosaba_ignite", "manosaba_attach_combust"):
                if C.kind != "card":
                    self.errors.append("점화·연소 블록은 카드 효과에서만 쓸 수 있습니다.")
                    return []
                card = str(a.get("card") or "").strip()
                if not card:
                    self.errors.append("대상 카드 식을 입력하세요.")
                    return []
                if op == "manosaba_ignite":
                    return [f"{ind}await global::manosaba.Characters.ShitoAlisa.ShitoCombustOperations."
                            f"ApplyIgniteToCard({cc}, {card}, {amount});"]
                return [f"{ind}global::manosaba.Characters.ShitoAlisa.ShitoCombustOperations."
                        f"AttachCombust({card}, (int)({amount}));"]
        if op == "manosaba_gun_attack":
            if (self.project.get("takeover") or {}).get("mod", "").casefold() != "manosaba" or C.kind != "card":
                self.errors.append("총격 블록은 Manosaba 카드 효과에서만 쓸 수 있습니다.")
                return []
            return [f"{ind}await ExecuteGunAttack({cc}, {a.get('target') or 'target'}, {self.val(a.get('amount'))});"]
        if op == "max_hp":
            return [f"{ind}await CreatureCmd.GainMaxHp({me}, {self.val(a.get('amount'))});"]
        if op == "heal":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f"{i2}await CreatureCmd.Heal({t}, {amt});"])
        if op == "lose_hp":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [
                f"{i2}await CreatureCmd.Damage({cc}, {t}, {amt}, ValueProp.Unblockable | ValueProp.Unpowered, {me}, {C.src}, {C.play});"])
        if op in ("apply_power", "apply_power_to", "remove_power"):
            pm = M.power_meta(self.project, a.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {a.get('power')}")
                return []
            amt = self.val(a.get("amount"))
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
            return [f"{ind}v_{_ident(a.get('name', 'a'))} = {self.val(a.get('amount'))};"]
        if op == "change_var":
            return [f"{ind}v_{_ident(a.get('name', 'a'))} += {self.val(a.get('amount'))};"]
        if op in ("summon", "command", "unsummon", "pay", "choice", "pick", "random_transform", "pick_transform", "pick_each", "picked_action", "delayed"):
            return self.gimmick_stmt(b, op, a, ind)
        if op in SPECS and SPECS[op]["cat"] == "class":
            return self.class_stmt(b, op, a, ind)
        if op.startswith("pet_"):
            import pets as PT
            pid = a.get("pet") or ""
            p = PT.find_pet(self.project, pid)
            if not p:
                self.errors.append("동료를 고르세요 ('🎲 기믹' 탭에서 먼저 만드세요)." if not pid else f"없는 동료: {pid}")
                return []
            H, cls, act = PT.helper(self.project), PT.pet_cls(self.project, pid), PT.act_cls(self.project, pid)
            pl = C.player
            if op == "pet_summon":
                return [f"{ind}await {H}.Summon<{cls}, {act}>({C.cc}, {pl}, {self.val(a.get('amount'))}, this, "
                        f"{'true' if p.get('guard', True) else 'false'});"]
            if op == "pet_act":
                return [f"{ind}await {H}.Act<{cls}, {act}>({C.cc}, {pl});"]
            if op == "pet_kill":
                return [f"{ind}await {H}.Kill<{cls}>({pl});"]
            amt = self.val(a.get("amount"))
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
                    self.errors.append("이펙트를 고르세요 ('🎨 이펙트·버튼' 탭에서 먼저 그리세요)." if not fid else f"없는 이펙트: {fid}")
                    return []
                return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f'{i2}{nsp}.{mid}Fx.Play("{fid}", {t});'])
            bid = a.get("button") or ""
            if not fxbtn.find_button(self.project, bid):
                self.errors.append("버튼을 고르세요 ('🎨 이펙트·버튼' 탭에서 먼저 만드세요)." if not bid else f"없는 버튼: {bid}")
                return []
            if op == "button_on":
                return [f'{ind}await {nsp}.{mid}Buttons.On("{bid}", {self.C.me}, {self.C.cc});']
            return [f'{ind}await {nsp}.{mid}Buttons.Off("{bid}", {self.C.me});']
        if op == "sfx":
            path = str(a.get("path") or '"event:/sfx"').strip()
            return [f"{ind}SfxCmd.Play({path}, (float)({self.val(a.get('volume'))}));"]
        return [f"{ind}// 알 수 없는 블록: {op}"]

    # ---- 직업 시스템 블록 ----
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
            return {"hand": f"await CardPileCmd.Add({cv}, PileType.Hand);",
                   "top": f"await CardPileCmd.Add({cv}, PileType.Draw, CardPilePosition.Top);",
                   "exhaust": f"await CardCmd.Exhaust({cc}, {cv});",
                   "discard": f"await CardCmd.Discard({cc}, {cv});",
                   "random_transform": f"await CardCmd.TransformToRandom({cv}, {cv}.Owner.PlayerRng.Transformations);",
                   "upgrade": f"if ({cv}.IsUpgradable) CardCmd.Upgrade({cv});"}.get(a.get("action", "hand"))
        if op == "picked_action":
            if not self.selected_cards:
                self.errors.append("‘고른 카드에 실행’은 ‘한 장마다 실행’ 안에 넣으세요.")
                return []
            return [ind + picked_action(self.selected_cards[-1])]
        if op in ("pick", "random_transform", "pick_transform", "pick_each"):
            pile = a.get("pile", "Discard")
            cv, lst, pv = self.uid("c"), self.uid("picked"), self.uid("pl")
            conds = [G.filter_expr(self.project, a.get("ctype") or "Any", cv)]
            if C.kind == "card":
                conds.append(f"{cv} != this")
            if a.get("action") == "upgrade":
                conds.append(f"{cv}.IsUpgradable")
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
            for k in ("a", "b", "min", "max", "pct"):
                scan_val(v.get(k))
    for b in walk(blocks):
        a = b.get("args", {})
        if b["op"] in ("set_var", "change_var"):
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


def compile_blocks(blocks, project, C, ind="        ", prefix="Blk", extras=None, allow_event=False):
    """-> (C# 줄 목록, 오류 목록). extras 목록을 주면 블록이 만든 클래스(선택지 카드·예약 파워) 정보가 쌓인다."""
    g = _Gen(project, C, prefix=prefix, extras=extras, allow_event=allow_event)
    lines = [f"{ind}{{", f"{ind}    // --- 블록 코딩 ---"]
    for n in _used_vars(blocks):
        lines.append(f"{ind}    decimal v_{_ident(n)} = 0m;")
    lines += g.stmts(blocks, ind + "    ")
    lines.append(f"{ind}}}")
    return lines, g.errors
