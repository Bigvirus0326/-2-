"""Independent BaseLib CardType registration, retaining older project identities."""
import gimmick as G
import modgen as M


def options(project):
    return M.CARD_TYPES + [("kind:" + t["id"], t.get("name_ko") or t["id"])
                           for t in G.tags(project) if t.get("card_kind")]


def selected(project, card):
    return next(("kind:" + t["id"] for t in G.tags(project)
                 if t.get("card_kind") and t["id"] in card.get("gtags", [])), card.get("type", "Attack"))


def create(project, name, base, description=""):
    name = name.strip()
    if not name:
        raise ValueError("종류 이름을 입력하세요.")
    if base not in dict(M.CARD_TYPES):
        raise ValueError("기본 종류를 목록에서 선택하세요.")
    if name in dict(options(project)).values():
        raise ValueError("이미 있는 종류 이름입니다.")
    ids = {t["id"] for t in G.tags(project)}
    index = 1
    while "card_kind_" + str(index) in ids:
        index += 1
    tag = G.new_tag("card_kind_" + str(index))
    tag.update(card_kind=True, base_type=base, name_ko=name, name_en=name,
               desc_ko=description.strip() or name, desc_en=description.strip() or name)
    project.setdefault("gimmicks", {}).setdefault("tags", []).append(tag)
    return "kind:" + tag["id"]


def apply(project, card, value):
    tag = G.find_tag(project, value[5:]) if value.startswith("kind:") else None
    base = tag.get("base_type") if tag and tag.get("card_kind") else value
    if base not in dict(M.CARD_TYPES):
        raise ValueError("카드 종류를 다시 선택하세요.")
    custom_ids = {t["id"] for t in G.tags(project) if t.get("card_kind")}
    card["gtags"] = [tid for tid in card.get("gtags", []) if tid not in custom_ids]
    if tag:
        card["gtags"].append(tag["id"])
    card["type"] = base


def defaults_for_type(card):
    """Explicit type selection only; loading never changes existing card rules."""
    if card["type"] in ("Curse", "Status"):
        card.update(rarity=card["type"], cost=0, upgrade_cost=0, target="Self", x_cost=False)
        if "Unplayable" not in card.setdefault("keywords", []):
            card["keywords"].append("Unplayable")


def definition(project, card):
    key = selected(project, card)
    return G.find_tag(project, key[5:]) if key.startswith("kind:") else None


def runtime_class(project):
    mid = project["mod"]["id"]
    return f"global::{mid}.{mid}Code.Cards.{mid}CardKinds"


def member(project, card):
    tag = definition(project, card)
    return (f"    public override CardType Type => {runtime_class(project)}.{M.pascal(tag['id'])};"
            if tag else "")


def loc_key(project, tag):
    return project["mod"]["id"].upper() + ".CARD_TYPE." + tag["id"].upper()


def gen_runtime(project):
    kinds = [t for t in G.tags(project) if t.get("card_kind")]
    if not kinds:
        return "// No custom card types.\n"
    mid = project["mod"]["id"]
    lines = ["using BaseLib.Patches.Content;", "using HarmonyLib;",
             "using MegaCrit.Sts2.Core.Entities.Cards;", "using MegaCrit.Sts2.Core.Models;",
             "using MegaCrit.Sts2.Core.Localization;", "using MegaCrit.Sts2.Core.Helpers;",
             f"namespace {mid}.{mid}Code.Cards;", f"public static class {mid}CardKinds", "{"]
    for tag in kinds:
        lines += [f"    [CustomEnum] public static CardType {M.pascal(tag['id'])};"]
    lines += ["    public static bool TryVisualType(CardType type, out CardType visual)", "    {"]
    for tag in kinds:
        base = tag.get("base_type", "Skill")
        if base not in dict(M.CARD_TYPES):
            raise ValueError("카드 종류의 외형을 다시 선택하세요: " + tag["id"])
        lines.append(f"        if (type == {M.pascal(tag['id'])}) {{ visual = CardType.{base}; return true; }}")
    lines += ["        visual = type; return false;", "    }",
              '    [HarmonyPatch(typeof(CardTypeExtensions), nameof(CardTypeExtensions.ToLocString))]',
              "    private static class TypeNamePatch", "    {", "        [HarmonyPrefix]",
              "        private static bool Prefix(CardType __0, ref LocString __result)", "        {"]
    import json
    for tag in kinds:
        lines.append(f'            if (__0 == {M.pascal(tag["id"])}) {{ __result = new LocString("gameplay_ui", {json.dumps(loc_key(project, tag))}); return false; }}')
    lines += ["            return true;", "        }", "    }"]
    # These three private getters throw on unknown CardTypes in the native game.
    # Patch only our own registered values; other mods and vanilla remain untouched.
    for prop, part in (("FramePath", "frame"), ("PortraitBorderPath", "portrait_border"),
                       ("AncientTextBgPath", "ancient_text_bg")):
        lines += [f'    [HarmonyPatch(typeof(CardModel), "{prop}", MethodType.Getter)]',
                  f"    private static class {prop}Patch", "    {", "        [HarmonyPrefix]",
                  "        private static bool Prefix(CardModel __instance, ref string __result)", "        {",
                  "            if (!TryVisualType(__instance.Type, out var visual)) return true;"]
        native = "CardType.Attack or CardType.Skill or CardType.Power"
        if part != "portrait_border":
            native += " or CardType.Quest"
        lines += [f"            if (visual is not ({native})) visual = CardType.Skill;"]
        if part == "frame":
            lines += ['            if (__instance.Rarity == CardRarity.Ancient) { __result = CardModel.MissingPortraitPath; return false; }']
        path = ('"atlases/compressed_atlas.sprites/ancient_text_bg_" + visual.ToString().ToLowerInvariant() + ".png.tres"'
                if part == "ancient_text_bg" else
                f'"atlases/ui_atlas.sprites/card/card_{part}_" + visual.ToString().ToLowerInvariant() + "_s.tres"')
        lines += [f"            __result = ImageHelper.GetImagePath({path});",
                  "            return false;", "        }", "    }"]
    lines += ["}"]
    return "\n".join(lines) + "\n"
