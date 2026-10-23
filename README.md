# VoyagerPhone · 远航浏览器版 0.5

[打开游戏](https://bradlytomsett.github.io/VoyagerPhone/)

VOYAGER V14.66 的单人星际沙盒。网页、Python 引擎和运行资源全部由 GitHub Pages 的 `docs/` 提供；引擎在浏览器 Web Worker 内通过 Pyodide 运行，无需游戏服务器、Codespaces 或 Docker。原始 `seed/` 保持不变。

## 开始游玩

1. 用新版 Chrome 打开游戏。首次加载约 20 MB，请等待“本机存档已就绪”。手机和电脑均可使用。
2. 打开“游戏设置”，填写自己的 API Key，并核对服务商当前可用的模型名称。预设地址为 `https://api.deepseek.com`，协议为 Chat Completions，预填模型为 `deepseek-flash`；也可填写兼容的 HTTPS 接口。
3. 保存设置，先用“问询”查看舰队、任务和账户。保存设置本身不会发起模型调用；“测试 API 连接”和发送指令会产生服务商费用。
4. 原存档没有开放场景和玩家视角。选择视角人物与开场地点，点击“建立新的游玩场景”，补充 AI 需要的信息。查看草案，点击“执行这一回合”后才正式保存。
5. 此后的“行动”先生成草案，再进行独立复核，由原引擎校验，最后等你确认。问询不推进游戏时间。

人物与地点可以按名称选择，指挥官位于人物列表首位。选择人物本身不会改变存档；指挥官首次建立场景时，必要的身份登记与视角绑定随草案一起等待确认。

## 原始资料与游戏记忆

“资料库”直接读取当前存档、任务、世界设定、规则与事件记录，按人物、店铺、地区和关键词检索；每条保留原文位置与日期。余火、正式员工、雷托、熄炉-9、韩默、伊沃和马洛有可直接查看的摘要。查看资料无需 API Key，不推进时间，也不改写账户或资产。

22 份原始冷归档可勾选“包含历史归档”后按需解码搜索。旧状态、未确认草案与经营模拟保留原始性质，不当作已发生的交易。AI 每轮根据问题检索相关原文，同时遵守现有视角与知情限制；指挥官资料不会自动成为 NPC 的记忆。检索受上下文大小限制，没有命中不等于原始存档不存在该信息。

## 进度、密钥与备份

- 进度自动保存在当前浏览器的 IndexedDB，包含网页回合航志和校验值；存储事务完成后才报告保存成功。
- 同一存档只允许一个标签页写入。出现“游戏已在另一个标签页打开”时，关闭另一个游戏页再刷新。
- 定期点击“导出当前存档”。换设备时使用“导入游戏存档”；导入会替换当前进度，请先导出备份。清除网站数据、移除浏览器配置或丢失设备可能丢失本机进度。
- API Key 默认只保留在本次标签页会话中；只有主动勾选才在本机长期记住。导出文件不含密钥。不要把密钥提交到仓库。
- AI 请求从浏览器直接发送到设置中的服务商，包含本轮玩家可见上下文与指令。接口必须允许来自 Pages 网站的跨域请求；不支持时需换用兼容接口。
- 生成中关闭页面不会自动重发模型请求。确认提交前先保存原回合意图，重开后沿用相同编号恢复，避免重复行动。
- 本版本没有游戏账号、多人联机和跨设备同步。每个浏览器拥有独立进度，关闭页面不会按现实时间自动推进游戏。

真实模型可用性需用自己的密钥在设置中测试。固定响应测试验证请求格式和异常处理，不代表真实 AI 的剧情质量或服务商账户权限。

## 构建与发布

`browser/` 是源码，`docs/` 是可直接发布的完整静态站点。固定 Pyodide 0.27.7 的运行时、SQLite/LZMA 包与许可证已放在 `docs/vendor/pyodide/`，运行时不依赖外部 CDN。

```bash
python scripts/build_browser.py
node tests/browser_model.mjs
node tests/browser_storage.mjs
python -m unittest tests.test_source_library -v
node tests/browser_sources.mjs
node tests/browser_commander.mjs
node tests/browser_wasm.mjs
```

WASM 测试在隔离副本中创建明确标为 SYNTHETIC 的场景，验证真实原生回合、确认、关闭后恢复、重复提交去重、快照、导出和导入；支持 Windows，不依赖本机 Linux `fcntl`。原有服务器测试可在 Linux 运行：`python -m unittest discover -s tests -v`。

发布设置：仓库 Settings → Pages → Deploy from a branch → `main` → `/docs`。必须提交完整 `docs/`，包括 `.nojekyll`、`engine-bundle.zip`、`python_stdlib.zip`、WASM 和两个扩展 wheel。`asset-manifest.json` 记录构建资源校验值。

## 代码布局

| 路径 | 内容 |
| --- | --- |
| `browser/` | 中文手机界面、Worker、模型直连、本机存储与 Python 适配器 |
| `docs/` | GitHub Pages 发布资源 |
| `backend/` | 复用的引擎桥接、回合与模型契约；Pages 无需运行服务器 |
| `seed/` | 原始引擎、Guard、规则与初始存档 |
| `tests/` | 固定模型报文、WASM 集成和原有服务端测试 |

复杂战斗、多存档、语音和原舰队图包尚未接入网页。未接入的机制不会由 AI 伪造为已执行。
