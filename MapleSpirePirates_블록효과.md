# MapleSpirePirates 블록 효과 패치

기도·포격·연계·승선·처치 조건처럼 기존 C# 상태 추적에 의존하는 동작은 범용 블록으로 완전히 재현할 수 없어, 대응하는 즉시 효과와 기존 파워로 근사했습니다. 소환·지휘 블록은 툴이 같은 패치의 소환수 정의를 찾지 못해 즉시 공격·방어도·드로우 효과로 근사했습니다. 시각 효과와 카드별 원본 비용·조건 판정은 포함하지 않았습니다.

카드의 기존 ID와 효과 블록만 담았습니다. 아래 JSON을 툴의 AI 결과 붙여넣기에 사용하세요.

```json
{
  "format": "sts2mod-patch",
  "cards": [
    {
      "id": "c_s01",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s02",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s03",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s04",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s05",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s06",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s07",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s08",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s09",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s10",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 9,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s11",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 2,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s12",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s13",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s14",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s15",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s16",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s17",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "lose_block",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 0
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s18",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 3,
                      "up": 2
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "c_s19",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Attack",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "hand"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s20",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s21",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_aim",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s22",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_tactics",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s23",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 4,
                      "up": 2
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s24",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s25",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 18,
                  "up": 6
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 12,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s26",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 1
                },
                "hits": 6,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s27",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 9,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s28",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 14,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 14,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s29",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 2
                },
                "hits": 2,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s30",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 26,
                  "up": 8
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s31",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s32",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 7,
                      "up": 3
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s33",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 11,
                  "up": 4
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Attack",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "hand"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s34",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s35",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "energy_action",
              "args": {
                "mode": "energy_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s36",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s37",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s38",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 15,
                  "up": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 12,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s39",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_damage",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s40",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_twins",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s41",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s42",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_tactics",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s43",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_guard",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s44",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_powder",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s45",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_reload",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s46",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s47",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s48",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Any",
                "count": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                },
                "action": "hand"
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s49",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_aim",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s50",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 14,
                  "up": 6
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s51",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 5,
                      "up": 2
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "c_s52",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "lose_block",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 0
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 16,
                  "up": 5
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s53",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "all",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s54",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 6,
                      "up": 3
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_refund",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s55",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 48,
                  "up": 16
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s56",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 48,
                  "up": 14
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "all",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "all",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s57",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s58",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_arsenal",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s59",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 66,
                  "up": 22
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 15,
                      "up": 7
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "c_s60",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 35,
                  "up": 10
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s61",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "random",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 2
                },
                "hits": 8,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s62",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_maker",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s63",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_flag",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s64",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_legion",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s65",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 28,
                      "up": 10
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s66",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_master",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s67",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "draw_action",
                  "args": {
                    "mode": "draw_to",
                    "player": "it.Player",
                    "amount": {
                      "t": "num",
                      "v": 2,
                      "up": 1
                    }
                  }
                }
              ]
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "energy_action",
                  "args": {
                    "mode": "energy_to",
                    "player": "it.Player",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s68",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 11,
                  "up": 4
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s69",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_thunder",
                "amount": {
                  "t": "num",
                  "v": 12,
                  "up": 6
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_s70",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 30,
                  "up": 10
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "energy_action",
                  "args": {
                    "mode": "energy_to",
                    "player": "it.Player",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 8,
                      "up": 4
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:cannon_shell",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t01",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t02",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t03",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "random",
                "amount": {
                  "t": "num",
                  "v": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t04",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t05",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "powered": true,
                "card_play": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t06",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 2,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t07",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 9,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t08",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t09",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t10",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t11",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t12",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t13",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t14",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_discipline",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t15",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 8
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "all",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t16",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t17",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t18",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t19",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t20",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 4
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t21",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "random",
                "amount": {
                  "t": "num",
                  "v": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t22",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_fire_control",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t23",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t24",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_discipline",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t25",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                },
                "hits": 4,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t26",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 2
                },
                "hits": 3,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t27",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 11,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t28",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t29",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t30",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "lose_block",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 0
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 22,
                  "up": 7
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t31",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 12,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t32",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t33",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_rank_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t34",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t35",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Any",
                "count": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                },
                "action": "hand"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t36",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t37",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t38",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 4
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t39",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 12,
                  "up": 6
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t40",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 4
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t41",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "powered": true,
                "card_play": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t42",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 5,
                      "up": 3
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t43",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "energy_action",
              "args": {
                "mode": "energy_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 4
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t44",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 3
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t45",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_boarding_bonus",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t46",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_supply_officer",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t47",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_quick_draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t48",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_dignity",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t49",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_reinforced_ammo",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t50",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_summon_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t51",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "energy_action",
              "args": {
                "mode": "energy_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t52",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t53",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 8
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t54",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_fire_control",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t55",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 32,
                  "up": 10
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t56",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 24,
                  "up": 8
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t57",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_fire_control",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t58",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "random",
                "amount": {
                  "t": "num",
                  "v": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t59",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 8
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_dominion",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t60",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t61",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_architect",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t62",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_bond",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t63",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 18,
                      "up": 7
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "energy_action",
                  "args": {
                    "mode": "energy_to",
                    "player": "it.Player",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_elite_squad",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t64",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_flagship",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t65",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 25,
                  "up": 8
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "c:captain_target_keyword",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t66",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 1
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_summon_keyword",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t67",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:captain_elite_squad",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t68",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 16,
                  "up": 6
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t69",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "c_t70",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 30,
                  "up": 10
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 15,
                      "up": 7
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p01",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p02",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p03",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p04",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:serpent",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p05",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 2,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p06",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p07",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                },
                "hits": 2,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p08",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p09",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p10",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 9,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p11",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p12",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p13",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p14",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p15",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p16",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p17",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p18",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "hand",
              "args": {
                "ctype": "Any",
                "which": "random",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "discard"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p19",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 14,
                      "up": 5
                    },
                    "hits": 1,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p20",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "all",
                    "amount": {
                      "t": "num",
                      "v": 8,
                      "up": 3
                    },
                    "hits": 1,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p21",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "cardPlay.Target ?? Me",
                    "amount": {
                      "t": "num",
                      "v": 13,
                      "up": 5
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p22",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "draw_action",
                  "args": {
                    "mode": "draw",
                    "amount": {
                      "t": "num",
                      "v": 2,
                      "up": 1
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p23",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "powered": true,
                "card_play": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p24",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 4,
                      "up": 2
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p25",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "block_action",
              "args": {
                "mode": "lose_block",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 0
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p26",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "all",
                "power": "Weak",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p27",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 2
                },
                "hits": 4,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p28",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p29",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 2
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p30",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "target",
                "power": "Vulnerable",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            },
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 18,
                  "up": 6
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p31",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "all",
                "amount": {
                  "t": "num",
                  "v": 13,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p32",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 1
                },
                "hits": 4,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p33",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 8,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p34",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 7,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:serpent_damage",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p35",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Attack",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "hand"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p36",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p37",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "all",
                    "amount": {
                      "t": "num",
                      "v": 17,
                      "up": 6
                    },
                    "hits": 1,
                    "powered": true
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "all",
                    "power": "Vulnerable",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p38",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block",
                    "amount": {
                      "t": "num",
                      "v": 7,
                      "up": 3
                    }
                  }
                },
                {
                  "op": "draw_action",
                  "args": {
                    "mode": "draw",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "self",
                    "power": "c:next_attack",
                    "amount": {
                      "t": "num",
                      "v": 3,
                      "up": 2
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p39",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              },
              "body": [
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "all",
                    "power": "Weak",
                    "amount": {
                      "t": "num",
                      "v": 2,
                      "up": 1
                    }
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "all",
                    "power": "Vulnerable",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p40",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 4
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 30,
                      "up": 10
                    },
                    "hits": 1,
                    "powered": true
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "self",
                    "power": "c:dragon_energy",
                    "amount": {
                      "t": "num",
                      "v": 4
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p41",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              },
              "body": [
                {
                  "op": "filtered_players",
                  "args": {
                    "conditions": {
                      "t": "group",
                      "mode": "all",
                      "items": []
                    },
                    "enemy_mode": "all",
                    "count": {
                      "t": "num",
                      "v": 99
                    }
                  },
                  "body": [
                    {
                      "op": "block_action",
                      "args": {
                        "mode": "block_to",
                        "creature": "it",
                        "amount": {
                          "t": "num",
                          "v": 13,
                          "up": 5
                        },
                        "powered": true,
                        "card_play": true
                      }
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p42",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3
                }
              },
              "body": [
                {
                  "op": "energy_action",
                  "args": {
                    "mode": "energy",
                    "amount": {
                      "t": "num",
                      "v": 1,
                      "up": 1
                    }
                  }
                },
                {
                  "op": "draw_action",
                  "args": {
                    "mode": "draw",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p43",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "pick_card_action",
                  "args": {
                    "mode": "pick",
                    "pile": "Discard",
                    "ctype": "Any",
                    "count": {
                      "t": "num",
                      "v": 1,
                      "up": 1
                    },
                    "action": "hand"
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p44",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 12,
                      "up": 4
                    },
                    "hits": 1,
                    "powered": true
                  }
                },
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 6,
                      "up": 3
                    },
                    "hits": 1,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p45",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:knuckle",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p46",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:rhythm",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p47",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:breath",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p48",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:serpent",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:serpent_damage",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p49",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:scales",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p50",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:refund",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p51",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:torrent",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p52",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw_to",
                "player": "cardPlay.Target.Player",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p53",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pick_card_action",
              "args": {
                "mode": "pick",
                "pile": "Discard",
                "ctype": "Any",
                "count": {
                  "t": "num",
                  "v": 1
                },
                "action": "hand"
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p54",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:wind",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "block_action",
              "args": {
                "mode": "block_to",
                "creature": "cardPlay.Target ?? Me",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 3
                },
                "powered": true,
                "card_play": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p55",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 4,
                  "up": 1
                },
                "hits": 10,
                "powered": true
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p56",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 10,
                  "up": 4
                },
                "hits": 1,
                "powered": true
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p57",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "damage_action",
              "args": {
                "mode": "damage",
                "who": "target",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                },
                "hits": 1,
                "powered": true
              }
            },
            {
              "op": "energy_action",
              "args": {
                "mode": "energy",
                "amount": {
                  "t": "num",
                  "v": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p58",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 6
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 42,
                      "up": 14
                    },
                    "hits": 1,
                    "powered": true
                  }
                },
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "all",
                    "amount": {
                      "t": "num",
                      "v": 14,
                      "up": 6
                    },
                    "hits": 1,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p59",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 4
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "random",
                    "amount": {
                      "t": "num",
                      "v": 9,
                      "up": 3
                    },
                    "hits": 4,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p60",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "stack",
                  "who": "self",
                  "power": "c:dragon_energy"
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "all",
                    "amount": {
                      "t": "num",
                      "v": 12,
                      "up": 6
                    },
                    "hits": 1,
                    "powered": true
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p61",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 5
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "cardPlay.Target ?? Me",
                    "amount": {
                      "t": "num",
                      "v": 30,
                      "up": 10
                    },
                    "powered": true,
                    "card_play": true
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "target",
                    "power": "c:keep_block",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p62",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "pay",
              "args": {
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 4
                }
              },
              "body": [
                {
                  "op": "damage_action",
                  "args": {
                    "mode": "damage",
                    "who": "target",
                    "amount": {
                      "t": "num",
                      "v": 15,
                      "up": 5
                    },
                    "hits": 2,
                    "powered": true
                  }
                },
                {
                  "op": "power_action",
                  "args": {
                    "mode": "apply_power",
                    "who": "self",
                    "power": "c:dragon_energy",
                    "amount": {
                      "t": "num",
                      "v": 2
                    }
                  }
                }
              ]
            }
          ]
        }
      ]
    },
    {
      "id": "v_p63",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:transform",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p64",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:awakening",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p65",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:serpent",
                "amount": {
                  "t": "num",
                  "v": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:resonance",
                "amount": {
                  "t": "num",
                  "v": 1,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p66",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:endless",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p67",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:overdrive",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "Strength",
                "amount": {
                  "t": "num",
                  "v": 6,
                  "up": 3
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p68",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "draw_action",
              "args": {
                "mode": "draw",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:lightning",
                "amount": {
                  "t": "num",
                  "v": 2,
                  "up": 1
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p69",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:protection",
                "amount": {
                  "t": "num",
                  "v": 5,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    },
    {
      "id": "v_p70",
      "effects": [
        {
          "kind": "code",
          "auto_text": true,
          "blocks": [
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "block_action",
                  "args": {
                    "mode": "block_to",
                    "creature": "it",
                    "amount": {
                      "t": "num",
                      "v": 6,
                      "up": 3
                    },
                    "powered": true,
                    "card_play": true
                  }
                }
              ]
            },
            {
              "op": "filtered_players",
              "args": {
                "conditions": {
                  "t": "group",
                  "mode": "all",
                  "items": []
                },
                "enemy_mode": "all",
                "count": {
                  "t": "num",
                  "v": 99
                }
              },
              "body": [
                {
                  "op": "energy_action",
                  "args": {
                    "mode": "energy_to",
                    "player": "it.Player",
                    "amount": {
                      "t": "num",
                      "v": 1
                    }
                  }
                }
              ]
            },
            {
              "op": "power_action",
              "args": {
                "mode": "apply_power",
                "who": "self",
                "power": "c:dragon_energy",
                "amount": {
                  "t": "num",
                  "v": 3,
                  "up": 2
                }
              }
            }
          ]
        }
      ]
    }
  ]
}
```

