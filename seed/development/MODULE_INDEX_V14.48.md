# V14.48 当前构建模块清单

共39个模块；加载顺序与契约以devsrc/SOURCE_MANIFEST.json为准。本批所有devsrc、runtime加载器、构建器与发布engine保持V14.47字节。

| 顺序 | 文件 | 名称 | 导入/导出数量 |
|---|---|---|---|
| 1 | devsrc/00_prelude.py | prelude | 0/113 |
| 2 | devsrc/01_text_policy_core.py | text_policy_core | 28/42 |
| 3 | devsrc/02_authority_storage.py | authority_storage | 139/181 |
| 4 | devsrc/03_turn_session_runtime.py | turn_session_runtime | 61/24 |
| 5 | devsrc/04_delivery_packaging.py | delivery_packaging | 42/18 |
| 6 | devsrc/05_simulation_runtime.py | simulation_runtime | 63/69 |
| 7 | devsrc/06_query_layer.py | query_layer | 53/37 |
| 8 | devsrc/07_combat_core.py | combat_core | 47/12 |
| 9 | devsrc/08_save_transactions.py | save_transactions | 96/31 |
| 10 | devsrc/09_development_tooling.py | development_tooling | 14/7 |
| 11 | devsrc/10_selftest_and_diagnostics.py | selftest_and_diagnostics | 207/12 |
| 12 | devsrc/11_mechanics_hazards.py | mechanics_hazards | 56/57 |
| 13 | devsrc/12_scheduler.py | scheduler | 18/5 |
| 14 | devsrc/13_migrations.py | migrations | 104/68 |
| 15 | devsrc/14_health_and_upgrade.py | health_and_upgrade | 54/23 |
| 16 | devsrc/15_battle_transaction.py | battle_transaction | 47/28 |
| 17 | devsrc/16_finance_domain.py | finance_domain | 13/13 |
| 18 | devsrc/16a_pricing_domain.py | pricing_domain | 29/57 |
| 19 | devsrc/17_domain_commands.py | domain_commands | 62/32 |
| 20 | devsrc/18_legacy_migration.py | legacy_migration | 35/5 |
| 21 | devsrc/19_p2_contracts.py | p2_contracts | 22/13 |
| 22 | devsrc/19a_authorization_service.py | authorization_service | 23/6 |
| 23 | devsrc/19b_transaction_service.py | transaction_service | 20/11 |
| 24 | devsrc/20_cli.py | cli | 195/172 |
| 25 | devsrc/21_mobile_read_cache.py | mobile_read_cache | 52/36 |
| 26 | devsrc/22_scene_visibility.py | scene_visibility | 35/12 |
| 27 | devsrc/23_scene_commands.py | scene_commands | 37/12 |
| 28 | devsrc/24_bootstrap.py | bootstrap | 12/2 |
| 29 | devsrc/25_consistency_repair.py | consistency_repair | 56/31 |
| 30 | devsrc/26_reliable_runtime.py | reliable_runtime | 60/38 |
| 31 | devsrc/27_accounts_games.py | accounts_games | 19/18 |
| 32 | devsrc/28_snapshot_service.py | snapshot_service | 27/15 |
| 33 | devsrc/29_memory_content.py | memory_content | 14/11 |
| 34 | devsrc/30_runtime_services.py | runtime_services | 53/47 |
| 35 | devsrc/31_story_scenes.py | story_scenes | 22/15 |
| 36 | devsrc/32_knowledge_policy.py | knowledge_policy | 24/18 |
| 37 | devsrc/33_narrative_director.py | narrative_director | 31/7 |
| 38 | devsrc/34_experience.py | experience | 19/7 |
| 39 | devsrc/35_story_services.py | story_services | 44/28 |

19a负责可信意图授权，19b负责统一事务；27独立账户，28验证快照，29记忆/内容，30查询服务，31—35人物场景/知识/导演/经验/故事服务。跨模块全局绑定与captures仍有耦合，不把清单当作已完全解耦的证明。
修改运行代码先编辑devsrc，再refresh_manifest.py与build.py；确定性构建后走完整引擎/Guard绑定与授权升级。本批不进行运行代码升级。
