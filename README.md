# VoyagerPhone · VOYAGER 手机网页游戏 0.3

这一版把 V14.66 的 Python 引擎接到手机网页与模型 API。原始引擎、Guard、规则和存档文件保存在 `seed/`，保持上传包的原始字节。第一次启动时复制到独立的持久目录，此后只修改这份游戏副本。

## 目前能做什么

- 手机竖屏与电脑界面：指挥台、三支舰队、五个独立账户、任务、网页回合航志。
- 从原引擎读取经过校验的玩家可见数据，金额按原十进制字符串显示；店铺的模拟账目标记保留。
- 自由文字问询、行动草案、独立 AI 剧情复核、明确确认后的原生事务提交。
- 没有开放场景时先准备新场景，不复活历史封存事件。
- 持久回合编号、重复请求去重、切后台后轮询恢复、提交结果不确定时沿用原命令核对。
- 自动保存、导出完整游戏包；API 密钥仅在服务器。

本项目包含完整网页与 Python 后端。推荐通过下方 Codespaces 入口启动，在网页填写模型 API。也可使用后面的 Docker 方案部署到自己的服务器。GitHub Pages 无法运行这个依赖 Linux 文件与 `fcntl` 的原生引擎。

## 手机上启动：公开地址 + 游戏账号登录

[**创建或恢复 VoyagerPhone**](https://codespaces.new/BradlyTomsett/VoyagerPhone?quickstart=1)

首次创建会自动安装依赖、初始化单人游戏账号并启动后端。启动命令：

```bash
python scripts/start_codespaces.py --public
```

启动输出中会显示游戏地址、用户名 `commander` 和随机初始密码。**初始密码只显示一次，请自行保存。** 登录信息、模型密钥和存档都不会提交到 GitHub。服务器只保存密码的随机盐和 scrypt 散列；登录会话保存在服务器，浏览器使用有效期七天的 HttpOnly、Secure、SameSite Cookie。

公开的 8000 端口只免去访客的 GitHub 登录步骤。访客首先看到游戏自己的用户名、密码登录页；全部游戏数据、API 设置和导出仍需游戏账号授权。旧的 `#access=...` 链接不再能够绕过游戏登录。账号初始化只在服务器执行，公众不能注册或抢先认领账号。

新建环境会在验证密码认证已启用后尝试设置端口为 Public。如果 GitHub 不允许启动脚本管理端口，在 Codespaces 的 **Ports → 8000 → Port Visibility → Public** 中设置即可。不要在旧版没有账号登录的服务器上开放端口。

已有 0.2 环境升级时，先完成或放弃待确认回合，执行 `git pull --ff-only`，停止旧的游戏服务再运行上面的启动命令。保留同一个 Codespace 和 `.voyager-runtime/data`，舰队、任务、历史、API 配置与已保存回合继续沿用。新的登录凭据独立保存于该数据目录。

第一次进入游戏设置，已经预填 DeepSeek：

| 设置 | 内容 |
| --- | --- |
| API 基础地址 | `https://api.deepseek.com` |
| 模型名称 | `deepseek-flash` |
| 接口协议 | `Responses` |
| API Key | 在登录后的设置页填入自己的密钥 |
| 复核模型 | 留空，使用同型号的独立请求 |

保存设置不会发起模型调用。真实模型调用需要你的 API Key；先使用“问询”检查连接。展开剧情前仍需选定视角人物和地点，建立新场景。退出登录会立即撤销当前会话；不要向他人提供你的游戏密码。

密码丢失可在 Codespaces 终端运行 `python scripts/reset_login.py`，按隐藏输入提示重设，再重启游戏。该操作保留游戏和模型配置，撤销所有旧会话。

Codespaces 闲置后会自动暂停，使用与存储受 GitHub 额度约束。恢复同一个环境后账号与存档继续使用；删除环境可能丢失本地数据，请定期导出存档。

## 部署到自己的 Linux 服务器

准备 Docker Compose、可访问的域名和 HTTPS 反向代理。模型服务必须能从该服务器正常访问。

```bash
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

把生成的随机口令填入 `.env` 的 `VOYAGER_ACCESS_TOKEN`。它是游戏访问口令，与模型 API 密钥不同。然后在服务器本地编辑这些配置：

| 配置 | 填什么 |
| --- | --- |
| `MODEL_API_KEY` | 提供商的真实 API 密钥，不能放入网页或 Git |
| `MODEL_ID` | 该账户实际可调用的 API 模型 ID |
| `REVIEW_MODEL_ID` | 独立复核使用的模型 ID；留空表示同一型号的另一次独立请求 |
| `MODEL_BASE_URL` | 默认 `https://api.openai.com/v1`；可换为支持相应协议的提供商地址 |
| `MODEL_PROTOCOL` | `responses`，或兼容严格 JSON Schema 的 `chat_completions` |
| `VOYAGER_ALLOWED_ORIGINS` | 允许连接的网页完整源地址，多个用逗号分开 |

不同服务商对模型参数、结构化输出和拒绝响应的约定可能不同。DeepSeek 官方域名使用上文的专用适配；其他提供商使用所选协议的标准 JSON Schema 报文，接入前需确认兼容性。所有提供商的输出都经过本地检查。

```bash
docker compose up -d --build
docker compose logs --tail 80
```

默认只把后端绑定在服务器的 `127.0.0.1:8000`。用 HTTPS 反向代理指向它，例如已有 Caddy 时：

```caddyfile
game.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

把 `game.example.com` 换成你自己的已解析域名。不要直接把无 TLS 的服务端口暴露为手机入口。

浏览器打开 `https://game.example.com`，或打开已发布的手机界面。在“连接设置”填写：

1. 游戏服务器根地址，例如 `https://game.example.com`。网页由后端直接提供时可以留空。
2. `VOYAGER_ACCESS_TOKEN` 对应的游戏访问口令。
3. 行动时的视角人物 ID，例如明确选择霍克·马伦时填写 `PER-HAWK-MALEN-01`。示例 ID 不等于已经授权玩家控制该角色。
4. 场景 ID 可留空，使用引擎的当前场景。

访问口令只在当前标签页会话中保存。模型密钥始终留在服务器。关闭标签页会话后可能需要重新输入游戏口令；已保存回合仍在服务器。

### 第一次游玩

原存档没有开放场景，也没有绑定玩家视角，生活化人物/环境档案仍有未补全项目。这是原存档状态，网页不会擅自补写。

先选择“问询”查看舰队近况。然后选“行动”，明确给出视角人物、已存在的地点 ID、想开始的事情。缺少条件时 AI 会询问；补充信息后继续。

建立新场景可能需要本次创作的人物档案、环境设定与视角控制。模型生成的内容会作为草案供你查看，点击“执行这一回合”才会提交。已有非零版本的人物背景在这一版的初始化入口中禁止覆盖。没有证据的既往经历不能冒充已核实历史。

场景准备完成后再次下达行动。剧情模型提出 V3 回合，另一次独立模型请求复核，原引擎校验；确认后引擎一次提交时间、机械效果与剧情，页面以提交报告呈现结果。问询不推进时间。

## 保存、升级和恢复

- 正式游戏副本与网页回合数据库放在 Docker 持久卷 `voyager_data`，更新镜像不会重新导入初始存档。
- 不要运行 `docker compose down -v`，这会删除该卷。
- 同一份游戏只运行一个 Web worker；允许多线程读取，回合写入排队。不要给 Gunicorn 增加 worker 数量或同时启动第二个副本使用同一个目录。
- 生成期间重启会标记为中断，不会自动重复消费模型调用；玩家可以重新提出请求。
- 已确认、正在提交的回合会保存完整 envelope。重启先走原 Guard 恢复，然后按同一命令编号核对。未知提交结果会阻止新行动，使用页面的“核对并恢复”。
- 如出现 `COMMITTED_REPORT_REQUIRES_REREAD`，继续恢复原回合，不能换编号重做效果。
- “导出当前存档”导出的是当前正式游戏组件、开发代码与冷归档，可继续交给匹配 Guard。访问口令、模型密钥、网页数据库不进入游戏导出包。
- 服务器级备份应覆盖整个持久卷；导出游戏包用于保留游戏事实，网页回合航志另外保存在 SQLite。

## 本地开发与验证

`ci-example/test.yml` 是可选的 GitHub Actions 测试模板，默认不启用。需要自动 CI 时，可由有工作流管理权限的仓库维护者放入 `.github/workflows/`。

正式托管使用 Gunicorn。后端主要业务代码只使用 Python 标准库，便于在受限环境验证。

```bash
python -m unittest discover -s tests -v
node --check dist/app.js
node --check dist/sw.js
```

测试会在临时目录构建明确标为 SYNTHETIC 的副本，不修改 `seed/`。模型报文测试使用固定响应，不消耗真实模型 API。

## 第一版范围与限制

目前是单人、单存档版本。网页覆盖问询、场景准备和现有 V3 故事回合支持的七类机械效果。网页现在也可以在通过游戏访问口令认证后保存或更换模型 API 配置。复杂战斗指挥、任意维护命令、多存档、多人联机、语音、原舰队图包和离线后台模拟尚未接入网页。原生引擎的这些能力没有被删除；未接线机制必须明确停止，不能由模型伪造执行。

这一版不自动为每项任务调用独立后台 AI，也不在关闭网页时按现实时间推进游戏。回合最多推进一天，原引擎的风险、到期结算与语义屏障继续生效。

AI 的自然语言质量仍需真实模型试运行评估。结构化 JSON 不保证剧情事实正确；本版保留独立复核、知识隔离、用户确认和机械校验。费用取决于生成、复核的实际 token 用量，响应 usage 保存在网页回合中。

## 源码布局

| 路径 | 内容 |
| --- | --- |
| `dist/` | 手机网页、PWA 元数据、原存档只读状态快照 |
| `backend/app.py` | WSGI API、SQLite 回合、授权、后台调度和恢复 |
| `backend/engine.py` | 原生引擎适配与玩家视图 |
| `backend/model.py` | 模型 API 生成与独立复核 |
| `seed/` | 原始 V14.66 完整组件包，保持原始内容 |
| `tests/` | 请求去重、权限、恢复、原生真实事务等测试 |

实现参考：[OpenAI Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)。
