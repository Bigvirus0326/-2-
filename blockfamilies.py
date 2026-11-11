"""Compact block families. Keep legacy commands as the compilation format."""
import copy

# family, caption, [(legacy operation, menu label)]
GROUPS = [
 ("select_cards", "카드 고르기", [("pick_each","직접 선택"),("random_each","무작위 선택")]),
 ("select_enemies", "적에게 반복", [("each_enemy","모든 적"),("random_enemy","무작위 적 1명"),("filtered_enemies","조건으로 고르기")]),
 ("condition_branch", "조건", [("if","조건 만족 시"),("if_else","조건 만족 / 불만족 시")]),
 ("wait_action", "기다리기", [("wait","지정 시간"),("wait_scaled","게임 속도에 맞추기")]),
 ("damage_action", "피해 주기", [("damage","기본 피해"),("card_attack","카드 공격 · 연출"),("damage_to","생물 직접 지정")]),
 ("block_action", "방어도", [("block","자신이 얻기"),("lose_block","대상 방어도 제거"),("block_to","생물 지정 · 얻기"),("lose_block_to","생물 지정 · 제거")]),
 ("health_action", "체력", [("heal","회복"),("lose_hp","잃기"),("max_hp","최대 체력 증가"),("heal_to","생물 지정 · 회복"),("set_current_hp","현재 체력 설정")]),
 ("energy_action", "에너지", [("energy","자신이 얻기"),("energy_to","플레이어 지정 · 얻기")]),
 ("gold_action", "골드", [("gold","자신이 얻기"),("gold_to","플레이어 지정 · 얻기"),("lose_gold","잃기")]),
 ("draw_action", "카드 뽑기", [("draw","맨 위에서 뽑기"),("draw_to","플레이어 지정 · 뽑기"),("draw_bottom","지정 위치에서 뽑기")]),
 ("power_action", "파워", [("apply_power","부여"),("remove_power","제거"),("apply_power_to","생물 지정 · 부여")]),
 ("power_model_action", "파워 직접 지정", [("apply_power_type","유형 · 공통 부여"),("power_apply_type","유형 · 부여"),("power_apply_model","모델 · 부여"),("modify_power_amount","모델 · 수치 변경"),("remove_power_model","모델 · 제거")]),
 ("card_keyword_action", "카드 키워드", [("card_ref_keyword","카드 지정"),("keyword_this","이 카드"),("keyword_cards","여러 카드"),("card_keyword","카드 식 지정"),("card_add_keyword_model","키워드 식 지정")]),
 ("create_card_action", "카드 생성·추가", [("add_card","카드 생성"),("add_card_pos","생성 · 위치 지정"),("card_add_generated","생성된 카드 추가"),("card_add_generated_many","생성된 카드 목록 추가"),("card_add_pile","카드 식 추가")]),
 ("preview_card_action", "게임에서 카드 보여주기", [("card_preview","더미에 추가한 카드 표시"),("card_preview_cards","지정한 카드 표시")]),
 ("enchant_card_action", "카드 추가 능력 (인챈트)", [("card_enchant","부여"),("card_enchant_clear","제거")]),
 ("upgrade_card_action", "카드 강화 처리", [("card_upgrade","강화"),("card_upgrade_internal","강화 수치 직접 적용"),("card_finalize_upgrade_internal","강화 처리 마무리")]),
 ("cost_card_action", "카드 비용 처리", [("card_set_cost_until_played","사용 시까지 설정"),("card_free_this_turn","이번 턴 무료"),("card_notify_cost_changed","비용 변경 알림")]),
 ("potion_action", "물약", [("potion_add_type","유형으로 지급"),("potion_add_model","모델 지급"),("potion_add_model_at","슬롯에 지급"),("potion_discard","버리기")]),
 ("summon_action", "소환수", [("summon","소환 / 단계 상승"),("command","행동시키기"),("unsummon","돌려보내기")]),
 ("pet_action", "동료", [("pet_summon","소환"),("pet_attack","공격"),("pet_act","행동"),("pet_kill","희생"),("add_pet_model","모델 지정 · 추가")]),
 ("osty_action", "골골이", [("osty_summon","소환"),("osty_attack","공격"),("osty_kill","희생")]),
 ("channel_action", "구체 영창", [("channel","구체 선택"),("orb_channel_type","유형 지정"),("orb_channel_model","모델 지정")]),
 ("orb_trigger_action", "구체 발동", [("evoke","발현"),("orb_passive_all","모든 지속 효과"),("orb_passive_model","모델 지속 효과")]),
 ("orb_slot_action", "구체 슬롯", [("orb_slots","자신"),("orb_slots_to","플레이어 지정")]),
 ("card_var_action", "카드에 값 저장하기", [("card_var_new","만들기"),("card_state_edit","저장 값 설정 / 증감"),("card_var_remove","지우기")]),
 ("pick_card_action", "카드 선택·변화", [("pick","직접 선택 · 동작"),("pick_transform","직접 선택 · 지정 카드로 변화"),("random_transform","무작위 선택 · 무작위 카드로 변화")]),
 ("card_model_action", "카드 직접 조작", [("card_exhaust","소멸"),("card_discard","버리기"),("card_remove_combat","전투에서 제거"),("card_autoplay","자동 사용"),("card_transform_to","지정 유형으로 변화")]),
 ("kill_action", "처치", [("kill_creature","생물 처치"),("doom_kill","Doom 처치")]),
 ("visual_effect_action", "이펙트 재생", [("fx","만든 이펙트"),("play_vfx_on_creature","게임 이펙트 직접 지정")]),
 ("sound_action", "소리 재생", [("sfx","소리 경로 지정"),("manosaba_novel_friends_sfx","Manosaba 소설 친구 효과음")]),
 ("animation_action", "동작 재생", [("trigger_creature_anim","생물 지정"),("manosaba_owner_attack_anim","Manosaba 카드 소유자 공격")]),
 ("manosaba_summon_action", "Manosaba 소환", [("manosaba_ema_summon","에마"),("manosaba_novel_summon","소설 속 몬스터")]),
 ("manosaba_firepower_action", "Manosaba 화력", [("manosaba_add_firepower","더하기"),("manosaba_maximize_firepower","최대로 설정")]),
 ("manosaba_blood_orb_action", "혈액 구체", [("manosaba_add_layers","층 추가"),("manosaba_channel_orb_at","위치 지정 · 영창"),("manosaba_evoke_blood_orb","발현")]),
 ("manosaba_pet_ai_action", "동료 적 행동", [("manosaba_pet_ai_assign","행동 슬롯 지정"),("manosaba_pet_ai_advance","다음 행동 선택")]),
 ("manosaba_source_action", "Manosaba 출처 설정", [("manosaba_set_partner","동료"),("manosaba_set_applier","부여자"),("manosaba_set_target","대상"),("manosaba_set_source_card","출처 카드"),("manosaba_set_upgraded","강화 상태")]),
]
FAMILIES = {op: (title, variants) for op,title,variants in GROUPS}
LEGACY = {old: family for family,_,variants in GROUPS for old,_ in variants}


def install(specs, palette):
    for family,title,variants in GROUPS:
        first=specs[variants[0][0]]
        spec=copy.deepcopy(first)
        spec["ko"]=title + " {mode}"
        spec["args"]={"mode":("family_mode",variants[0][0]),**spec["args"]}
        specs[family]=spec
    seen=set()
    result=[]
    for cat,ops in palette:
        row=[]
        for op in ops:
            mapped=LEGACY.get(op,op)
            # Cross-category groups belong where their default action lived.
            if mapped in FAMILIES and op != FAMILIES[mapped][1][0][0]:
                continue
            if mapped not in seen:
                row.append(mapped); seen.add(mapped)
        if row:
            result.append((cat,row))
    return result


def variant(b, specs):
    family=b.get("op")
    if family not in FAMILIES:
        return family
    default=FAMILIES[family][1][0][0]
    mode=b.get("args",{}).get("mode",default)
    return mode if isinstance(mode,str) and mode in dict(FAMILIES[family][1]) else default


def block_spec(b,specs):
    family=b.get("op")
    if family not in FAMILIES:
        return specs.get(family)
    selected=copy.deepcopy(specs[variant(b,specs)])
    selected["args"]={"mode":("family_mode",variant(b,specs)),**selected["args"]}
    return selected


def caption(b,specs):
    family=b["op"]
    if family=="select_cards":
        return "{pile}에서 {ctype} · 조건 {conditions} · {count}장 · {mode} · 한 장마다 실행"
    if family=="select_enemies":
        if variant(b,specs)=="filtered_enemies":
            args=b.get("args",{})
            condition=args.get("enemy_filter","power")
            detail=" · {power}" if condition in ("power","no_power") else " · {limit}%" if condition in ("hp_below","hp_above") else ""
            count="" if args.get("enemy_mode","random")=="all" else " 최대 {count}명"
            if (args.get("conditions") or {}).get("items"):
                return "{mode} · {conditions} · {enemy_mode}"+count+"에게 각각 실행 (안에서 '그 적/플레이어')"
            return "{mode} · {enemy_filter}"+detail+" · 여러 조건 {conditions} · {enemy_mode}"+count+"에게 각각 실행 (안에서 '그 적/플레이어')"
        return "{mode}에게 각각 실행 (안에서 '그 적')"
    return FAMILIES[family][0] + " {mode} · " + specs[variant(b,specs)]["ko"]


def migrate(b,specs):
    old=b.get("op")
    if old not in LEGACY:
        return
    args=b.setdefault("args",{})
    for key,(_kind,value) in specs[old]["args"].items():
        args.setdefault(key,copy.deepcopy(value))
    args["mode"]=old
    b["op"]=LEGACY[old]


def switch(b,new_mode,specs):
    family=b["op"]
    if not isinstance(new_mode,str) or new_mode not in dict(FAMILIES[family][1]):
        raise ValueError("목록에서 실행 방식을 선택하세요.")
    old_mode=variant(b,specs)
    args=b.setdefault("args",{})
    saved=b.setdefault("mode_args",{})
    saved[old_mode]=copy.deepcopy({k:v for k,v in args.items() if k!="mode"})
    old_spec,new_spec=specs[old_mode],specs[new_mode]
    replacement={k:copy.deepcopy(v) for k,(_kind,v) in new_spec["args"].items()}
    replacement.update(copy.deepcopy(saved.get(new_mode,{})))
    for key,(kind,_value) in new_spec["args"].items():
        if key in args and old_spec["args"].get(key,(None,None))[0]==kind:
            replacement[key]=copy.deepcopy(args[key])
    args.clear(); args.update(replacement); args["mode"]=new_mode
    for field in ("body","else","third"):
        if new_spec.get(field):
            b.setdefault(field,[])


def modes(b,owner=None):
    card_only={"card_attack","manosaba_ema_summon","manosaba_novel_summon","manosaba_ignite","manosaba_attach_combust","manosaba_gun_attack","manosaba_owner_attack_anim"}
    return [(op,label) for op,label in FAMILIES[b["op"]][1]
            if (op not in card_only or owner in (None,"card")) and (op!="orb_grow" or owner in (None,"orb"))]


def keywords(op,specs):
    if op not in FAMILIES:
        return ""
    title,variants=FAMILIES[op]
    return " ".join([title,*(old+" "+label+" "+specs[old]["ko"] for old,label in variants)])
