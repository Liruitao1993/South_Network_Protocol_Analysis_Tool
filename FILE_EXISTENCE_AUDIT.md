# File Existence Audit Report
## AGENTS.md §3 Architecture Tree Verification
**Date:** 2026-07-18

---

## MISSING FILES (1 total)

### Data Files
| File | Status | Severity |
|------|--------|----------|
| `dlt645_di_custom.json` | **MISSING** | CRITICAL — AGENTS.md §3 lists this file in the data files section, but it does not exist on disk. All other data files exist. |

---

## VERIFIED EXISTING FILES (All pass ✅)

### Parser Files (15/15)
protocol_parser.py, protocol_tool.py, gdw10376_parser.py, gdw10376_tool.py, plc_rf_parser.py, dlms_parser.py, hdlc_parser.py, dlms_deep_parser.py, dlt645_parser.py, dl_t698_45_parser.py, dl_t698_45_apdu_parser.py, dl_t698_45_axdr.py, dl_t698_45_oi_lookup.py, csg_new_gen_parser.py, csg_new_gen_cmd_payloads.py

### Lookup Files (4/4)
obis_lookup.py, command_lookup.py, dlt645_di_lookup.py, gdw_afn_lookup.py

### Frame Gen Files (6/6)
send_frame_lib.py, gdw_send_frame_lib.py, dl_t698_45_frame_gen.py, dl_t698_45_frame_schema.py, frame_generator_schema.py, gdw_frame_generator_schema.py

### GUI Components (8/8)
frame_gen_widget.py, preset_buttons.py, test_plan_widget.py, serial_worker.py, gui_utils.py, archive_widget.py, topology_widget.py, diff_widget.py

### Web Files (21/21)
- Entry: streamlit_app.py, web_app.py
- Core: web/main_page.py, web/protocol_registry.py, web/frame_extractor.py, web/__init__.py
- Adapters: web/adapters/serial_adapter.py, web/adapters/__init__.py
- Components: web/components/hex_input.py, web/components/parse_table.py, web/components/protocol_selector.py, web/components/byte_highlighter.py, web/components/serial_panel.py, web/components/__init__.py
- Tabs: web/tabs/single_parse.py, web/tabs/batch_parse.py, web/tabs/diff.py, web/tabs/lookup.py, web/tabs/frame_gen.py, web/tabs/preset_cmd.py, web/tabs/test_plan.py, web/tabs/archive.py, web/tabs/topology.py, web/tabs/__init__.py
- Styles: web/styles/custom.css

### TUI (2/2)
tui_app.py, tui_app.tcss

### Validator Files (10/10 including gw_new_gen_validator.py)
validator/__init__.py, validator/base.py, validator/nw_validator.py, validator/gdw_validator.py, validator/hdlc_validator.py, validator/plc_rf_validator.py, validator/dlt645_validator.py, validator/dl_t698_45_validator.py, validator/csg_new_gen_validator.py

### Other Modules (7/7)
frame_diff_engine.py, enhanced_export.py, lua_script_engine.py, monitor/frame_monitor.py, report/excel_reporter.py, templates/test_templates.py, visual_editor/test_item_editor.py

### Data Files (13/14 — 1 missing listed above)
custom_di.json, gdw_custom_afn.json, dlt645_di.json, NW_command.json, GW_command.json, command.json, config.json, test_plan.json, archive_data.json, lme_all_tables.json, lme_info_entries.json, oi_to_class.json, extracted_classes.json

### Test Files (12/12)
test_dlms.py, test_hdlc.py, test_plc_rf.py, test_ber_tlv.py, test_actual_hdlc.py, test_special_frame.py, test_snrm_frame.py, test_dl_t698_45.py, test_oad_enrichment.py, test_csg_new_gen.py, test_diff_engine.py, test_plan_widget.py

### Spec Files (2/2)
协议解析工具.spec, 南网协议解析工具.spec

### Scripts (15/15)
generate_dlt645_di.py, generate_oi_lookup.py, extract_69845_classes.py, extract_oi_to_class.py, convert_docx_to_md.py, extract_pdf.py, extract_doc_fields.py, extract_di_definitions.py, analyze_frame.py, analyze_fields.py, analyze_lme_ids.py, gap_analysis.py, create_work_list.py, search_di.py, lme_info_entry_parser.py

### Doc Files (11/11)
docs/Lua脚本使用说明.md, QWEN.md, README.md, CLAUDE.md, work_list.md, docs/superpowers/specs/2026-05-12-dl-t698-45-parser-design.md, docs/superpowers/plans/2026-05-12-dl-t698-45-parser.md, docs/superpowers/specs/2026-05-09-topology-formation-timing-design.md, docs/superpowers/specs/2026-07-15-nicegui-web-version-design.md, docs/superpowers/plans/2026-07-15-nicegui-web-version-plan.md, .sisyphus/plans/csg_new_gen_parser.md

---

## UNDOCUMENTED ROOT .py FILES (exist on disk, NOT in AGENTS.md §3)

### Significant (functional code, not just tests/tmp)
| File | Notes |
|------|-------|
| `gw_new_gen_parser.py` | **CRITICAL** — A parser for 国网新一代 protocol. Present in the `# 国网新一代协议/` subdirectory marker in directory listing, plus exists at root. AGENTS.md only documents `csg_new_gen_parser.py` (南网). |
| `topology_graph.py` | Standalone topology graph module — may be referenced by topology_widget.py but not in architecture tree |
| `Lib.py` | Library/utility file — not documented |
| `lookup_pages.py` | Lookup page module — not documented |
| `lookup_pages_simple.py` | Simplified lookup pages — not documented |

### Generated/Auto Files
| File | Notes |
|------|-------|
| `_generated_mapping.py` | Auto-generated mapping file (leading underscore) |
| `_generated_mapping_v2.py` | Auto-generated mapping file v2 |

### Export/Integration Scripts
| File | Notes |
|------|-------|
| `enhanced_batch_export.py` | Batch export variant — not documented |
| `integrate_enhanced_export.py` | Integration script for enhanced export |
| `integration_script.py` | Generic integration script |

### Ad-hoc Scripts (tmp/test)
| File | Notes |
|------|-------|
| `gen_test_frames.py` | Frame generation test helper |
| `_tui_smoke_test.py` | TUI smoke test (leading underscore) |
| `tmp_fix.py`, `tmp_fix2.py`, `tmp_screenshot.py` | Temporary/debug files |
| `topology_networkx_demo.py` | Demo script |

### Additional Test Files (not in AGENTS.md §7)
| File |
|------|
| test_bplc_deep.py |
| test_cmd_test_frame.py |
| test_config_run_params.py |
| test_csg_batch_prefix.py |
| test_csg_summary.py |
| test_efc.py |
| test_full_debug.py |
| test_full_push.py |
| test_gw_new_gen.py |
| test_len_debug.py |
| test_lua_engine.py |
| test_mac_data.py |
| test_mac_debug.py |
| test_mac_detailed.py |
| test_mac_frame_debug.py |
| test_mac_offset.py |
| test_meter_id.py |
| test_msdu_debug.py |
| test_plc_rf_fix.py |
| test_push_frame.py |
| test_run_params.py |
| test_sack_fix.py |
| test_user_frame.py |
| test_user_input.py |

### Other Non-.py Undocumented Files
| File | Notes |
|------|-------|
| `extract_lme_entries.py` | Script for extracting LME entries — not in §6 scripts list |
| `南网解析工具.iss` | Inno Setup installer script — not documented |
| `2222.iss` | Another Inno Setup script — not documented |

---

## Summary

| Category | Listed in AGENTS.md | Exist on Disk | Missing | Undocumented (on disk but not in AGENTS.md) |
|----------|---------------------|---------------|---------|----------------------------------------------|
| Parser files | 15 | 15 | 0 | 1 (gw_new_gen_parser.py) |
| Lookup files | 4 | 4 | 0 | 0 |
| Frame gen files | 6 | 6 | 0 | 0 |
| GUI components | 8 | 8 | 0 | 0 |
| Web files | 21 | 21 | 0 | 0 |
| TUI files | 2 | 2 | 0 | 0 |
| Validator files | 9 | 10 | 0 | 1 (gw_new_gen_validator.py) |
| Other modules | 7 | 7 | 0 | 0 |
| Data files | 14 | 13 | 1 (dlt645_di_custom.json) | 0 |
| Test files | 12 | 12 | 0 | 24 |
| Spec files | 2 | 2 | 0 | 0 |
| Scripts | 15 | 15 | 0 | 1 (extract_lme_entries.py) |
| Doc files | 11 | 11 | 0 | 0 |
| **TOTAL** | **126** | **125+** | **1** | **~30** |

### Critical Findings
1. **`dlt645_di_custom.json`** — Listed in AGENTS.md architecture tree but does not exist on disk
2. **`gw_new_gen_parser.py`** — Exists on disk but is completely undocumented in AGENTS.md (it's a full parser for the 国网新一代 protocol, not a trivial file)
3. **~24 test files** exist on disk but are not listed in AGENTS.md §7
4. **`gw_new_gen_validator.py`** exists in `validator/` but was not in the original audit checklist — AGENTS.md may or may not list it
5. **`extract_lme_entries.py`** — A script file not documented in §6
