# Graph Report - scratch-2026-11-06-0b528d  (2026-11-11)

## Corpus Check
- 62 files · ~190,925 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 2, .sts2blocks 1, .zip 1)

## Summary
- 2518 nodes · 5976 edges · 123 communities (75 shown, 48 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 324 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Tab Docking & Notebook
- C# Item Code Generation
- Gimmick Runtime & Tags
- Game Scene Builder
- App Features (README)
- Mod Generator Core
- Block Editor UI
- Button Designer
- Effect Painter
- Docking Regression Tests
- Combat Button Runtime
- Card Library & Event Effects
- Block Descriptions
- Other Mods Tab
- Flicker-free Refresh Helpers
- Updater & Auto-update
- Card Frames & AI Prompt
- Item Tab Base
- Gimmick Tab & Pets
- Art Guide Builder
- Main App Dialogs
- Wheel, Scroll & Theme Kit
- App Shell Actions
- Localization & Images
- Simple Preview Renderer
- Block-to-C# Compiler
- Slot Dialogs
- C# Parser
- Search & Find Palette
- Release Signing & Stdlib
- Character Tab
- Card Tab
- Art Guide Dialogs
- Block Editor History
- Mod Import & Characters
- Frame Style Dialog
- Pets Generator
- Test Suite Wiring
- Feedback & Logs
- Chinese Card Text
- Call Signatures
- Power & Orb Metadata
- Decompiler Integration
- AI Paste Fixer
- Design Docs
- Labeled Combo & Effect Dialog
- Block Arg Widgets
- Native Block Mapping
- Description Editor
- Relic/Potion Forms
- Card List Drag
- C# Clone Cloning
- Project Save & Load
- Effect List & Clone Panel
- C# Decomposer
- Hand Aura Rules
- In-game Card Compositor
- Undo History & Zoom
- Auto Description
- Game Asset Reader
- Small: RandomCardBlockTests
- Small: TagBlockTests
- Small: RefreshTests
- Small: copy
- Small: validate
- Small: selftest
- Small: __init__
- Small: blockhelp.py
- Small: _inline
- Small: compose_power
- Small: CompoundConditionsTests
- Small: cardkind.py
- Small: tkinter
- Small: resolve
- Small: _find_image
- Small: ModTab
- Small: BlockFamilyTests
- Small: takeover
- Small: write_png
- Small: LabeledCombo
- Small: compile_blocks
- Small: ingame.py
- Small: AutoScroll
- Small: GuidePage
- Small: GameColorBar
- Small: fxui.py
- Small: Canvas
- Small: ResponsiveForm
- Small: Tooltip
- Small: UpgradeEffectTests
- Small: open_mod_as_project
- Small: CardKindTests
- Small: EnemySelectionTests
- Small: History
- Small: gimmick_stmt
- Small: json
- Small: image_file
- Small: ModifierList
- Small: CodeChoiceTests
- Small: open_recipes
- Small: save_settings
- Small: GalleryTab
- Small: insert_description_number
- Small: PowerTab
- Small: apply
- Small: ClassChain
- Small: test_no_cost.py
- Small: Style Reference 1 (Chibi Pirat
- Small: _resolve_preset
- Small: test_card_list_drag_selection_
- Small: missing_selections
- Small: new_block
- Small: block_description_values
- Small: show_usages
- Small: test_enemy_condition_fields_sw
- Small: compare
- Small: block_caption
- Small: card_is_filters
- Small: set_project_hint
- Small: set_item_hint
- Small: Pillow (optional dependency
- Small: fix

## God Nodes (most connected - your core abstractions)
1. `App` - 87 edges
2. `BlockEditor` - 82 edges
3. `ItemTab` - 53 edges
4. `Decomposer` - 45 edges
5. `DockingRegressionTests` - 44 edges
6. `EffectPainter` - 43 edges
7. `GimmickTab` - 43 edges
8. `StS2 Mod Maker app` - 43 edges
9. `ButtonDesigner` - 39 edges
10. `center_window()` - 39 edges

## Surprising Connections (you probably didn't know these)
- `RefreshTests` --uses--> `DescriptionText`  [INFERRED]
  tests/test_refresh.py → descriptionui.py
- `RefreshTests` --uses--> `AsyncTiles`  [INFERRED]
  tests/test_refresh.py → sts2_mod_maker.py
- `RefreshTests` --uses--> `App`  [INFERRED]
  tests/test_refresh.py → sts2_mod_maker.py
- `UI/UX Design Standard` --references--> `apply_theme()`  [EXTRACTED]
  docs/UI_DESIGN.md → uxkit.py
- `Scroll and widget reuse (no redundant configure)` --references--> `_set_if()`  [EXTRACTED]
  docs/UI_DESIGN.md → uxkit.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Mod build flow** — readme_build_pipeline, readme_prerequisites, readme_generated_project, readme_project_file [INFERRED 0.85]
- **AI art request round-trip** — readme_ai_art, ai_requests_mymod_그림요청_설명서_doc, ai_requests_mymod_그림요청_설명서_common_rules, ai_requests_mymod_그림요청_설명서_apply_steps [INFERRED 0.85]

## Communities (123 total, 48 thin omitted)

### Community 0 - "Tab Docking & Notebook"
Cohesion: 0.06
Nodes (15): listpane(), CheckedMenu, label(), update(), DockDrag, DockPanedWindow, forget_floating_window(), install_panel_menu() (+7 more)

### Community 1 - "C# Item Code Generation"
Cohesion: 0.07
Nodes (42): _cs_str(), power_members(), prog(), card_energy_cost(), card_pool_for_character(), _clone_head(), _Ctx, effective_card_pool() (+34 more)

### Community 2 - "Gimmick Runtime & Tags"
Cohesion: 0.07
Nodes (45): add_examples(), _all_blocks(), card_errors(), card_filters(), _card_kind_filter(), card_members(), card_play_prefix(), card_prefix_text() (+37 more)

### Community 3 - "Game Scene Builder"
Cohesion: 0.07
Nodes (34): background(), btn_text(), button_image(), draw_pets(), end_turn(), end_turn_rect(), energy(), figure() (+26 more)

### Community 4 - "App Features (README)"
Cohesion: 0.06
Nodes (57): After-generation apply steps, Card illustrations, Combat standing reference image, Character images (portrait/icon/map/energy), Common rules (file names, zip), Card composition design skill, Composition types A-F, MyMod art request brief (+49 more)

### Community 5 - "Mod Generator Core"
Cohesion: 0.07
Nodes (43): architect_from_loc(), block_damage_name(), block_damage_upgrades(), block_damage_vars(), block_number_name(), block_number_type(), block_number_vars(), canonical_keyword_terms() (+35 more)

### Community 6 - "Block Editor UI"
Cohesion: 0.10
Nodes (8): _advanced_palette_block(), _block_color(), BlockEditor, tint(), begin(), show(), _darker(), tip()

### Community 7 - "Button Designer"
Cohesion: 0.10
Nodes (5): ButtonDesigner, ent(), FxTab, _rename(), fix()

### Community 8 - "Effect Painter"
Cohesion: 0.14
Nodes (5): _bbox(), EffectPainter, _offset(), _simplify(), rdp()

### Community 9 - "Docking Regression Tests"
Cohesion: 0.08
Nodes (4): DockingRegressionTests, children(), children(), descend()

### Community 10 - "Combat Button Runtime"
Cohesion: 0.09
Nodes (32): add_examples(), _all_ops(), anchor_members(), anchor_options(), btn_text(), buttons(), _col(), copies_dirs() (+24 more)

### Community 11 - "Card Library & Event Effects"
Cohesion: 0.10
Nodes (12): CardLibrary, rename_self(), finish(), display(), finish(), import_project_card(), require(), scan() (+4 more)

### Community 12 - "Block Descriptions"
Cohesion: 0.10
Nodes (28): arg_kind(), block_spec(), _card_is_word(), cmp_text(), cond_label(), _dec(), _describe_cardref(), _describe_class() (+20 more)

### Community 13 - "Other Mods Tab"
Cohesion: 0.08
Nodes (5): AsyncTiles, ExternalTab, work(), go(), take()

### Community 14 - "Flicker-free Refresh Helpers"
Cohesion: 0.08
Nodes (14): AIGuideDialog(), AIPasteDialog(), AIWorkflow, PastePage, _text(), _open_folder(), quick_copy(), _requests_dir() (+6 more)

### Community 15 - "Updater & Auto-update"
Cohesion: 0.08
Nodes (22): check(), work(), _done(), download(), fetch_latest(), _get_json(), install_dir(), is_frozen() (+14 more)

### Community 16 - "Card Frames & AI Prompt"
Cohesion: 0.08
Nodes (27): _blocks_reference(), build_prompt(), fix_request(), _list(), _opts(), project_summary(), add_example(), base_rgb_from() (+19 more)

### Community 18 - "Gimmick Tab & Pets"
Cohesion: 0.14
Nodes (3): GimmickTab, rename_gimmick_ref(), stable_listbox()

### Community 19 - "Art Guide Builder"
Cohesion: 0.08
Nodes (22): apply(), build_guide(), card_composition(), chosen_slots(), composition_skill(), _desc(), extract_zip(), guide_options() (+14 more)

### Community 20 - "Main App Dialogs"
Cohesion: 0.09
Nodes (9): FeedbackDialog, proceed(), ArchitectDialog, RawVarDialog, render_preview(), show_code_window(), center_window(), _pos() (+1 more)

### Community 21 - "Wheel, Scroll & Theme Kit"
Cohesion: 0.08
Nodes (20): is_panel_window(), panel_groups(), pointer_in_workspace(), position_window(), prepare_float_window(), BulkEditDialog, getter(), _can_scroll() (+12 more)

### Community 23 - "Localization & Images"
Cohesion: 0.09
Nodes (25): card_characters(), character_description(), _cleanup_stale_image_outputs(), description(), description_gimmick_name(), description_reference_options(), _description_tip_key(), game_snake() (+17 more)

### Community 24 - "Simple Preview Renderer"
Cohesion: 0.13
Nodes (18): draw_rich(), fill_values(), _font(), ImageCache, _panel(), parse_bbcode(), _placeholder(), render_card() (+10 more)

### Community 25 - "Block-to-C# Compiler"
Cohesion: 0.16
Nodes (5): _cs_str(), _Gen, change(), body(), expand()

### Community 26 - "Slot Dialogs"
Cohesion: 0.11
Nodes (18): _Combo, _first_pet(), _plain(), SlotDialog, combo(), edit_item(), entry(), upd() (+10 more)

### Community 27 - "C# Parser"
Cohesion: 0.14
Nodes (20): _close(), decompose(), decompose_with_classes(), _embedded(), _global_index(), _map_interp(), members(), onplay_of() (+12 more)

### Community 28 - "Search & Find Palette"
Cohesion: 0.10
Nodes (15): dialogs(), all_entries(), delete(), FindPalette, item_icon(), SearchEntry, decorate(), refresh() (+7 more)

### Community 29 - "Release Signing & Stdlib"
Cohesion: 0.12
Nodes (9): read_original_code(), _copy_img(), _remove_decompiler_install(), _digest(), _powershell(), sign(), verify(), CardNumberRuntimeTests (+1 more)

### Community 30 - "Character Tab"
Cohesion: 0.17
Nodes (5): frame_ms(), CharacterTab, show(), ent(), pet_preview()

### Community 31 - "Card Tab"
Cohesion: 0.13
Nodes (3): CardTab, save(), GM_cond_label()

### Community 33 - "Block Editor History"
Cohesion: 0.11
Nodes (8): uses(), output_window(), show(), typed(), pick(), show(), typed(), bind_selection()

### Community 34 - "Mod Import & Characters"
Cohesion: 0.14
Nodes (18): dispatch(), fragment(), lower(), statements(), _enum(), external_keywords(), _extract_items(), fix_decompiled() (+10 more)

### Community 36 - "Pets Generator"
Cohesion: 0.14
Nodes (21): act_cls(), add_examples(), character_members(), find_pet(), gen_runtime(), helper(), localization(), motion_members() (+13 more)

### Community 37 - "Test Suite Wiring"
Cohesion: 0.11
Nodes (3): CallMappingDialog, LabelDialog, _source_call_slots()

### Community 38 - "Feedback & Logs"
Cohesion: 0.15
Nodes (15): _append(), append_app_log(), install_exception_hooks(), main_hook(), thread_hook(), log_dir(), _looks_like_error(), make_report() (+7 more)

### Community 39 - "Chinese Card Text"
Cohesion: 0.16
Nodes (17): block_text(), body(), blocks_text(), card_type(), condition(), effect(), modifier(), power_name() (+9 more)

### Community 40 - "Call Signatures"
Cohesion: 0.11
Nodes (12): _arg_labels(), _call_label(), call_signature(), _generic_end(), _looks_numeric(), one_line(), _param_label(), _short() (+4 more)

### Community 41 - "Power & Orb Metadata"
Cohesion: 0.11
Nodes (16): uid(), letters(), ns(), orb_meta(), _pascal(), summon_cls(), tag_cls(), _amount_expr() (+8 more)

### Community 42 - "Decompiler Integration"
Cohesion: 0.18
Nodes (15): cache_root(), _category(), decompile(), _dotnet_exe(), ensure_decompiler(), _fmt_num(), _ilspy_cmd(), _install_decompiler() (+7 more)

### Community 43 - "AI Paste Fixer"
Cohesion: 0.21
Nodes (16): _all_ids(), _enum(), extract(), _fix_blocks(), _fix_cond(), _fix_effects(), _fix_id(), _fix_item() (+8 more)

### Community 44 - "Design Docs"
Cohesion: 0.10
Nodes (16): Beginner Terms Guide, Card Stored Number, Enchant (Card Extra Ability), Hover Term Tooltips, Model vs Type distinction, My Blocks (reusable actions), Card Tag, Block Families Guide (+8 more)

### Community 46 - "Block Arg Widgets"
Cohesion: 0.18
Nodes (18): candidates(), choose_mode(), edit(), edit_code(), edit_label(), edit_source(), save(), label() (+10 more)

### Community 51 - "C# Clone Cloning"
Cohesion: 0.14
Nodes (12): clone_item(), _consts(), CsClass, eval_path(), _expr_end(), find_member(), match_bracket(), parse_cs() (+4 more)

### Community 52 - "Project Save & Load"
Cohesion: 0.16
Nodes (6): _project_data_for_save(), _project_image_paths(), visit(), _resolve_project_image_paths(), _transform_project_image_paths(), visit()

### Community 53 - "Effect List & Clone Panel"
Cohesion: 0.20
Nodes (3): ClonePanel, effect_summary(), EffectList

### Community 55 - "Hand Aura Rules"
Cohesion: 0.14
Nodes (7): blocks(), members(), play_effects(), rules(), stable(), visit(), HandAuraTests

### Community 56 - "In-game Card Compositor"
Cohesion: 0.14
Nodes (12): compose_card(), compose_hover_tip(), draw_label(), draw_rich(), layout(), energy_outline_color(), _hex(), _nine_patch_full() (+4 more)

### Community 58 - "Auto Description"
Cohesion: 0.18
Nodes (15): trigger_text(), filter_word(), modifier_sentence(), power_text(), _ref_name(), auto_description(), card_event_description(), _description() (+7 more)

### Community 59 - "Game Asset Reader"
Cohesion: 0.19
Nodes (5): default_cache_dir(), extract_sfnt(), GameAssets, parse_scene_rects(), Pck

### Community 63 - "Small: copy"
Cohesion: 0.21
Nodes (8): describe(), selection_condition(), block_spec(), caption(), install(), migrate(), switch(), variant()

### Community 64 - "Small: validate"
Cohesion: 0.14
Nodes (12): modifier_errors(), power_errors(), architect_dialogues(), architect_loc(), card_event_context(), card_event_target_count(), default_architect(), event_separate() (+4 more)

### Community 65 - "Small: selftest"
Cohesion: 0.15
Nodes (4): compose(), main(), selftest(), game()

### Community 67 - "Small: blockhelp.py"
Cohesion: 0.18
Nodes (4): block_help(), field_help(), legacy(), BeginnerHelpTests

### Community 68 - "Small: _inline"
Cohesion: 0.15
Nodes (9): assigns_any(), _blocks_text(), arm_body(), dedent(), idents(), _src(), _strip_local_fns(), select() (+1 more)

### Community 69 - "Small: compose_power"
Cohesion: 0.22
Nodes (10): _compose(), styled(), compose_potion(), compose_power(), compose_relic(), energy_icons(), _mod_placeholder(), _open_user_image() (+2 more)

### Community 71 - "Small: cardkind.py"
Cohesion: 0.22
Nodes (9): create(), defaults_for_type(), definition(), gen_runtime(), loc_key(), member(), options(), runtime_class() (+1 more)

### Community 72 - "Small: tkinter"
Cohesion: 0.26
Nodes (9): balance(), import_results(), choose(), open_row(), unresolved(), connect(), apply(), refresh() (+1 more)

### Community 73 - "Small: resolve"
Cohesion: 0.23
Nodes (4): map_idents(), _num(), rename(), fn()

### Community 74 - "Small: _find_image"
Cohesion: 0.19
Nodes (10): _base_item(), class_to_id(), _find_image(), _find_image_by_name(), game_snake(), _index_images(), add(), _loc_lookup() (+2 more)

### Community 75 - "Small: ModTab"
Cohesion: 0.18
Nodes (3): detect_sts2_path(), load_settings(), ModTab

### Community 77 - "Small: takeover"
Cohesion: 0.17
Nodes (6): _dep_entries(), fix_out_ref(), strip_comments(), takeover(), all_effect_blocks(), _top_level_types()

### Community 78 - "Small: write_png"
Cohesion: 0.26
Nodes (5): _mod_placeholder_art(), rscc_decompress(), _chunk(), hex_to_rgb(), write_png()

### Community 79 - "Small: LabeledCombo"
Cohesion: 0.23
Nodes (5): file_row(), browse(), LabeledCombo, lang_entry(), ScrollFrame

### Community 80 - "Small: compile_blocks"
Cohesion: 0.18
Nodes (9): compile_blocks(), event_target_setup(), _ident(), upgrade_numeric_blocks(), _used_vars(), scan_val(), uses_event_target(), scan() (+1 more)

### Community 81 - "Small: ingame.py"
Cohesion: 0.24
Nodes (6): apply_hsv(), decode_ctex(), get_assets(), _inv(), last_error(), _mul()

### Community 85 - "Small: fxui.py"
Cohesion: 0.22
Nodes (4): _assets(), _font_for(), _mix(), stage_image()

### Community 86 - "Small: Canvas"
Cohesion: 0.24
Nodes (3): Canvas, _resized(), poll()

### Community 90 - "Small: open_mod_as_project"
Cohesion: 0.25
Nodes (3): poll(), prog(), work()

### Community 94 - "Small: gimmick_stmt"
Cohesion: 0.25
Nodes (5): _card_action(), describe(), picked_action(), _label_text(), _power_ctx()

### Community 95 - "Small: json"
Cohesion: 0.39
Nodes (5): _is_manifest(), _items_from_loc(), _load_loc(), load_mod(), _read_json()

### Community 99 - "Small: open_recipes"
Cohesion: 0.33
Nodes (3): choice(), insert(), value()

### Community 100 - "Small: save_settings"
Cohesion: 0.29
Nodes (3): _atomic_write_json(), save_settings(), auto_check()

### Community 104 - "Small: apply"
Cohesion: 0.40
Nodes (3): apply(), check(), _rename_refs()

### Community 107 - "Small: Style Reference 1 (Chibi Pirat"
Cohesion: 0.50
Nodes (4): Chibi Anime Art Style, Style Reference 1 (Chibi Pirate Gunner Card Art), Ornate Gold Card Frame with Red Gems, Pirate Girl Firing Flintlock (Water Splash)

### Community 111 - "Small: new_block"
Cohesion: 0.67
Nodes (3): _first_custom_power(), _first_summon(), new_block()

## Knowledge Gaps
- **24 isolated node(s):** `Card Tag`, `Model vs Type distinction`, `My Blocks (reusable actions)`, `Card Select Block (direct/random)`, `Repeat For Enemies Block` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 610 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **48 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BlockEditor` connect `Block Editor UI` to `Block Editor History`, `Small: open_recipes`, `Test Suite Wiring`, `Docking Regression Tests`, `Small: _resolve_preset`, `Block Arg Widgets`, `Description Editor`, `Small: AutoScroll`, `Small: test_enemy_condition_fields_sw`, `Small: GameColorBar`, `Small: Tooltip`, `Slot Dialogs`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `App` (e.g. with `CardLibrary` and `FeedbackDialog`) actually correct?**
  _`App` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Card Tag`, `Model vs Type distinction`, `My Blocks (reusable actions)` to the rest of the system?**
  _24 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Tab Docking & Notebook` be split into smaller, more focused modules?**
  _Cohesion score 0.05661005661005661 - nodes in this community are weakly interconnected._
- **Why does `center_window()` connect `Main App Dialogs` to `Art Guide Dialogs`, `Block Editor History`, `Small: __init__`, `Small: open_recipes`, `Frame Style Dialog`, `Test Suite Wiring`, `Small: open_mod_as_project`, `Small: insert_description_number`, `Small: _resolve_preset`, `Labeled Combo & Effect Dialog`, `Flicker-free Refresh Helpers`, `Other Mods Tab`, `Wheel, Scroll & Theme Kit`, `App Shell Actions`, `Slot Dialogs`, `Search & Find Palette`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `BlockEditor` (e.g. with `DescriptionText` and `GameColorBar`) actually correct?**
  _`BlockEditor` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Should `C# Item Code Generation` be split into smaller, more focused modules?**
  _Cohesion score 0.06610169491525424 - nodes in this community are weakly interconnected._