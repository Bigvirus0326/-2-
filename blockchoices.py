"""블록 칸의 선택지 (Tk · Qt 공용, 화면과 무관): 코드 칸에 들어갈 대상·카드·파워·구체 등의 목록."""
import blockcode as B
import modgen as M


def code_choices(project, owner_kind, item, op, key):
    if op not in B.SPECS or op in ("src_call", "src_loop"):
        return {}
    ctx = M._Ctx(owner_kind, item)
    if key in ("creature", "target", "attacker", "applier"):
        choices = {"자신": ctx.me, "무작위 적 한 명": "@random_enemy"}
        choices["조건으로 고른 적/플레이어 (반복 안에서)"] = "@selected_creature"
        if ctx.single:
            choices["선택한 대상"] = ctx.single
        return choices
    if key == "orb_type":
        import gimmick as G
        return {label: meta["cls"] for ident, label in G.orb_options(project)
                if (meta := G.orb_meta(project, ident))}
    if key == "potion_type":
        return {f"{M.text(c, 'name', 'ko')} ({c['id']})": M.item_cls(project, "potion", c)
                for c in project.get("potions", [])}
    if key == "card_type":
        return {f"{M.text(c, 'name', 'ko')} ({c['id']})": M.item_cls(project, "card", c)
                for c in project.get("cards", [])}
    if key == "card":
        choices = {"고른 카드 (카드 고르기 안에서)": "@picked_card", "방금 변화한 카드":"@replacement", "손패에서 무작위 한 장": "@random_hand"}
        if owner_kind == "card":
            choices["이 카드"] = "this"
        return choices
    if key == "cards" and op in ("card_discard", "card_remove_combat", "card_preview_cards", "card_add_pile"):
        choices = {"고른 카드 (카드 고르기 안에서)": "@picked_card"}
        if owner_kind == "card":
            choices["이 카드"] = "this"
        return choices
    if key == "cards" and op == "card_add_generated_many":
        return {"고른 카드 한 장": "@picked_cards"}
    if key == "power":
        choices = {f"자신에게 걸린 {label}": "@own_power:" + pid
                   for pid, label in M.power_options(project)}
        if ctx.single:
            choices.update({f"선택한 대상에게 걸린 {label}": "@target_power:" + pid
                            for pid, label in M.power_options(project)})
        return choices
    if key == "potion" and op in ("potion_add_model", "potion_add_model_at"):
        return {f"{M.text(c, 'name', 'ko')}의 새 물약 ({c['id']})":
                f"ModelDb.Potion<{M.item_cls(project, 'potion', c)}>().ToMutable()"
                for c in project.get("potions", [])}
    if key == "orb":
        import gimmick as G
        return {label + "의 새 구체": f"ModelDb.Orb<{meta['cls']}>().ToMutable()"
                for ident, label in G.orb_options(project)
                if (meta := G.orb_meta(project, ident))}
    if key in ("source", "source_card"):
        return {"이 카드": "this", "출처 카드 없음": "null"} if owner_kind == "card" else {"출처 카드 없음": "null"}
    if key == "context":
        return {"현재 선택 상황": ctx.cc} if hasattr(ctx, "cc") else {"현재 선택 상황": "choiceContext"}
    if key == "power_type":
        return {label: meta["cls"] for pid, label in M.power_options(project)
                if (meta := M.power_meta(project, pid))}
    if key == "player":
        return {"소유 플레이어": ctx.player, "조건으로 고른 플레이어 (반복 안에서)":"@selected_player"}
    if key == "pile":
        return {label: "PileType." + pile for pile, label in B.PILES}
    if key == "position" and B.SPECS[op]["args"][key][1].startswith("CardPilePosition."):
        return {"맨 위": "CardPilePosition.Top", "맨 아래": "CardPilePosition.Bottom", "무작위 위치": "CardPilePosition.Random"}
    if key == "animation":
        return {"공격 동작": '\"Attack\"', "피격 동작": '\"Hurt\"', "기본 동작": '\"Idle\"'}
    if key in ("skip_x", "skip_visuals", "can_back_out", "force_exhaust"):
        return {"예": "true", "아니오": "false"}
    if key == "keyword":
        return {label: "CardKeyword." + code for code, label in M.CARD_KEYWORDS}
    return {}
