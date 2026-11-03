# 部署、更新与维护手册 — WorkBuddy 每日脚本

本文件是给**接手这个仓库的人（或 agent）**看的操作手册：它部署在哪、怎么改、怎么验证、哪些坑踩过。
上游通用文档见 `README.md`；这里只写**这个 fork + 这台服务器**特有的事实。

---

## 1. 一句话定位

`workbuddy_daily.py` 是 WorkBuddy 的自动签到/刷任务脚本。本仓库（AvigatorC 的 fork）的 `prod` 分支
= **上游 v3.36 + 呆呆面板定制**，部署在 10.100.100.179 的 Dumb-Panel 面板里，每天 00:10 / 18:10 各跑一次。

同机还跑两个**不在本仓库**的任务：国际版每日活跃（§11）和极氪签到（§12）。

---

## 2. 部署拓扑

| 项 | 值 |
|:--|:--|
| 服务器 | `10.100.100.179`（SSH alias `kyptserver`，Debian 13，root） |
| 面板 | `/opt/daidai/Dumb-Panel`（容器 `daidai-panel`，宿主目录 bind mount 到 `/app/Dumb-Panel`） |
| 运行文件 | `/opt/daidai/Dumb-Panel/scripts/workbuddy_daily.py`（`-rwx------ root:root`） |
| 调度 | 面板内置 cron，任务 id=16「WorkBuddy 每日」，`10 00,18 * * *`（Asia/Shanghai） |
| 运行命令 | 面板里配的是 `python /app/Dumb-Panel/scripts/workbuddy_daily.py` |
| 日志 | `/opt/daidai/Dumb-Panel/logs/task_16_WorkBuddy_每日/<时间戳>.log` |
| 备份 | `/opt/daidai/Dumb-Panel/backups/workbuddy_daily.py.<tag>.<时间戳>` |
| 状态文件 | `/opt/daidai/Dumb-Panel/data/`（`wb_refresh_tokens.json`、`WORKBUDDY_ACCESS_TOKEN.txt` 等） |

面板任务的环境变量（存在 `daidai.db` 的 `env_vars` 表，**不在脚本里**）：

| 变量 | 值/作用 |
|:--|:--|
| `WORKBUDDY_STATE_DIR` | `/app/Dumb-Panel/data`（**必需**，上游 v3.23 起不再按 `__file__` 推导状态目录） |
| `WORKBUDDY_REFRESH_TOKEN` | 账号刷新令牌（首次自举用，轮换后以 data 目录里的 store 为准） |
| `SERVERCHAN_SENDKEY` | Server酱 推送（免费版每天 5 条，所以默认只在失败时推） |
| `WORKBUDDY_NOTIFY` | **没有设**。不设时走代码里的默认值 `fail`——这条默认值是面板定制的关键，不要改回上游的 `always` |

账号：1 个（手机号 18666513162）。

---

## 3. 分支与版本

| 分支 | 用途 | 当前 |
|:--|:--|:--|
| `prod` | **部署分支**，唯一需要打补丁的分支 | `3adc4d8`（上游 **v3.36** + 面板定制） |
| `main` | 跟上游（**本地没有这个分支**，只有 `upstream/main` 跟踪 ref，且是陈旧的 v3.25） | — |
| `feat/notify-policy` | PR #38 的历史分支，已合并 | `47bbbb7` |

远端：

- `upstream` → `L0NE-6/WorkBuddy-Daily`（SSH）
- `fork` → `AvigatorC/WorkBuddy-Daily`（SSH）

⚠️ **`prod` 领先 `fork/prod` 3 个提交**（`5d6860b`、`e41c5ca`、`3adc4d8`）。本机沙箱里 SSH/HTTPS 都推不了（见 §9），
需要在正常终端里 `git push fork prod`。

线上文件与仓库 `prod` **字节一致**：
`workbuddy_daily.py` sha256 `a5ff8eeb192d8b2eeb16e60dccc23d12a8a4a4bc8b85b44ce664400d568b85eb`（242297 字节）。

---

## 4. 面板定制清单（相对上游，只有这些）

改 `workbuddy_daily.py` 时只允许在这几条上偏离上游，其余一律跟上游走：

| # | 位置 | 定制 |
|:--|:--|:--|
| 1 | 文件头 | 版本行后缀「（呆呆面板定制）」 |
| 2 | 头部注释 | `WORKBUDDY_NOTIFY` 文档改成默认 `fail` |
| 3 | `_notify_ok()` | `checkin_skipped` / `enterprise` 的账号**不算异常**（否则企业号每天误推） |
| 4 | `_notify_or_skip()` | 默认 `fail`；正常推 `🌱 WorkBuddy 签到报告`，异常推 `❌ WorkBuddy 签到失败` |
| 5 | `main()` 尾部 | `--query` 早退 `return 0`；正常走 `_notify_or_skip()` 后 `return _exit_code(summaries)` |
| 6 | `_exit_code()` | 新增函数：有账号签到未确认 → 退出码 1（面板据此告警） |
| 7 | `run_account()` | 签到受 `want("checkin")` 白名单控制，跳过时记 `_checkin_state["skipped"]` |
| 8 | `summary` | 多写一个 `checkin_skipped` 字段 |
| 9 | 入口 | `sys.exit(main())`（否则退出码恒为 0，面板告警失效） |
| 10 | `t_sign()` 文档 | `status_out` 说明改成「退出码与通知策略判定」 |

---

## 5. 任务守卫（重要，别再踩）

### 事故复盘（issue #39）

上游对「服务端不再下发的任务」`prog()` 返回 `(None, None, None)`。旧判断
`st not in ("completed", "claimed")` 对 `None` **恒为真** → 脚本对已下线的任务照发真实对话、照扣积分。

2026-10-27 12:30 起 `create_canvas`（设计创意画布）下线，但面板分支还在每天 00:10 / 18:10
各发一次「帮我在设计创意画布里做一张活动海报」，每次真扣 **0.05–0.24 积分**，连跑 7 次。

**更坑的是根因**：面板分支当时用 `patch_panel.py` 给上游打补丁，那个补丁只插入了 `_needs_do()`
函数的**定义**，从来没插入过任何**调用点**（`grep -c "_needs_do(" = 1`）。所以每次"同步上游 + 打补丁"
都得到一个有守卫函数但没人调用的脚本。

### 现行机制（v3.26 起）

守卫**完全由上游承载**，prod 不再自造 helper。`patch_panel.py` 会逐个断言这 6 个锚点存在：

| 任务 | 守卫写法（源码片段） |
|:--|:--|
| `t_chat_n`（chat_5 / GLM5.2） | `if st is None:` + 注释 `# 任务未下发`，然后 `return` |
| `create_canvas` | `canvas_st = prog(...)[0]` → `if canvas_st is None: …跳过` |
| `automation_1` | `if st is None:` → `log("   自动化任务: …")` |
| `playbook_prompt` | `playbook_st = prog(...)[0]` → `if playbook_st is None: …跳过` |
| `RichMeow_Chat` | `need_rich = rich_st is not None and rich_st not in ("completed", "claimed")` |
| `skill_1` | `need_skill = skill_st is not None and skill_st not in ("completed", "claimed")` |

**如果上游哪天把守卫删了，`patch_panel.py` 会直接报错退出**，不会静默部署。

### 语义边界（要知道的副作用）

守卫把「读不到」等同于「已下线」跳过。接口抖动时（`prog()` 内部 `except: pass` 吞掉异常），
那一轮会少做几个任务，日志显示「不在任务列表，跳过」。这是上游的设计选择，
好处是绝不再盲目发对话扣费。

---

## 6. 工具链

| 工具 | 用途 | 命令 | 期望 |
|:--|:--|:--|:--|
| `patch_panel.py` | 把上游脚本转成面板版（不碰守卫，只校验） | `python patch_panel.py <上游脚本> <输出> [<上游测试> <测试输出>]` | 打印「已应用 14 个补丁」 |
| `check_patches.py` | 静态校验面板定制 + 守卫（25 项） | `python check_patches.py workbuddy_daily.py` | `25/25 通过` |
| `check_exit_codes.py` | 退出码/推送语义（12 项，stub 掉网络） | `python check_exit_codes.py workbuddy_daily.py` | `12/12 通过` |
| `run_tests_offline.py` | 没有 `requests`、tempfile 受限时跑上游测试 | `python run_tests_offline.py tests/test_workbuddy_core.py` | `43 tests OK` |
| `local_test_env.py` | 上面两个的桩（requests 命名空间 + 沙箱友好临时目录） | 被 import | — |

测试三件套：

```bash
python run_tests_offline.py tests/test_workbuddy_core.py   # 上游 43 项
python run_tests_offline.py tests/test_panel_guards.py     # 面板 8 项（退出码 + 守卫不变量）
python run_tests_offline.py tests/test_credits_report.py   # 积分报告 7 项
```

> `tests/test_workbuddy_intl.py` 本地跑不了（缺 `urllib3`），国际版也没部署在这台面板上，可以忽略。

**核心不变量**：`patch_panel.py(上游) == 仓库里的 workbuddy_daily.py`（字节一致）。
改完补丁后一定要验证这条，否则说明手改和补丁脚本已经漂了。

---

## 7. 同步上游的标准流程

```bash
# 1. 取上游（本机 SSH 不通，用 HTTPS；见 §9）
git fetch https://github.com/L0NE-6/WorkBuddy-Daily.git main
git merge FETCH_HEAD            # 在 prod 分支上；冲突基本只在 main() 尾部
#    冲突处理原则：功能修复取上游；面板定制（notify/退出码）保留自己的

# 2. 重打补丁并校验
python patch_panel.py <上游的 workbuddy_daily.py> /tmp/patched.py \
                      <上游的 tests/test_workbuddy_core.py> /tmp/patched_tests.py
git diff --no-index /tmp/patched.py workbuddy_daily.py     # 必须无输出

# 3. 三道校验
python check_patches.py workbuddy_daily.py        # 25/25
python check_exit_codes.py workbuddy_daily.py     # 12/12
python run_tests_offline.py tests/test_workbuddy_core.py
python run_tests_offline.py tests/test_panel_guards.py

# 4. 提交 + 部署（见 §8）
```

---

## 8. 部署流程

```bash
# 0. 备份
cd /opt/daidai/Dumb-Panel
cp -p scripts/workbuddy_daily.py backups/workbuddy_daily.py.pre-<tag>.$(date +%Y%m%d-%H%M%S)

# 1. 上传到 .new（不要直接覆盖运行文件）
#    本地: ssh_upload / scp → /opt/daidai/Dumb-Panel/scripts/workbuddy_daily.py.new

# 2. 校验哈希（本地 sha256 必须等于远端）
sha256sum scripts/workbuddy_daily.py.new

# 3. 容器内语法自检（⚠️ 不要用 py_compile，它会往 __pycache__ 写文件）
docker exec daidai-panel python3 -c "import io;p='/app/Dumb-Panel/scripts/workbuddy_daily.py.new';compile(io.open(p,encoding='utf-8').read(),p,'exec');print('OK')"

# 4. 落位
chmod 700 scripts/workbuddy_daily.py.new
mv scripts/workbuddy_daily.py.new scripts/workbuddy_daily.py
sha256sum scripts/workbuddy_daily.py

# 5. 验证（二选一）
#    a) 等 18:10 定时跑，看日志
#    b) 手动跑一次（会走真实接口，但任务都 claimed，代价≈0）
docker exec -e WORKBUDDY_STATE_DIR=/app/Dumb-Panel/data -e WORKBUDDY_NOTIFY=0 \
  daidai-panel python3 /app/Dumb-Panel/scripts/workbuddy_daily.py
```

部署成功的判据：日志出现 `设计创意画布: 当前任务列表未下发（可能已下线），跳过`，
且**会话列表没有新增 `canvas-*` 会话**、耗时从 ~58s 降到 ~17s。

当前线上版本：`sha256 a5ff8eeb192d8b2eeb16e60dccc23d12a8a4a4bc8b85b44ce664400d568b85eb`（242297 字节，v3.36）。

---

## 9. 排障手册

### 9.1 某个任务到底还下不下发（只读）

```bash
AT=$(cat /opt/daidai/Dumb-Panel/data/WORKBUDDY_ACCESS_TOKEN.txt | tr -d '\r\n')
curl -s -H "Authorization: Bearer $AT" \
  'https://www.workbuddy.cn/v2/activity/growth/tasks' | python3 -c "
import json,sys
d=json.load(sys.stdin); ts=(d.get('data') or {}).get('tasks') or []
print('count=',len(ts))
for t in ts: print(' ', t.get('task_code'), t.get('accept_status'))"
```

小程序口径加请求头 `X-Client-Platform: miniprogram`（数量不同，18 项左右）。

### 9.2 有没有真的发对话、扣积分（只读）

```bash
curl -s -H "Authorization: Bearer $AT" \
  'https://www.workbuddy.cn/console/webchat/conversations?page=1&pageSize=30'
```

按 `createdAt` 和运行时间对齐；脚本发起的画布会话前缀 `canvas-`。

### 9.3 日志里的关键行

| 日志 | 含义 |
|:--|:--|
| `设计/自动化/灵感: None / claimed / claimed` | 三个值分别是 `create_canvas` / `automation_1` / `playbook_prompt` 的状态；`None` = 未下发 |
| `xxx: 当前任务列表未下发（可能已下线），跳过` | 守卫生效，**没有**发请求 |
| `🏁 完成20/20` | 任务全清；`完成0/0` 通常是那一瞬间接口抖动，全部读不到 |
| `ℹ️ 签到正常，静默不推送` | 默认 `fail` 策略下的正常表现，不是故障 |

### 9.4 本机（Windows）环境的坑

- **SSH 推送不可用**：沙箱里 `ssh.exe` 报 `couldn't create signal pipe, Win32 error 5`，
  `git push` / `git fetch`（SSH 远端）都会失败；HTTPS 推送需要凭据，GCM 也会被拦。
  → **推送必须在本机正常终端里做**。
- **HTTPS 读可以用**：`git -c http.sslBackend=openssl fetch https://...`（默认 schannel 会报 `SEC_E_NO_CREDENTIALS`）。
- 容器里**没有 `python`**，只有 `python3`（面板任务配的 `python` 由面板自己的 PATH 解析）。

---

## 10. 禁忌清单

1. **不要**再引入「只定义不调用」的守卫 helper（`_needs_do()` 就是这么翻车的）。守卫只跟上游。
2. **不要**在服务器上直接手改 `workbuddy_daily.py`——改了要同步回 `patch_panel.py`，否则下次同步必丢。
3. **不要**把 `WORKBUDDY_NOTIFY` 的默认值改回 `always`（Server酱 每天只有 5 条额度）。
4. **不要**用 `py_compile` 做部署前检查（会往 `__pycache__` 写文件，污染脚本目录）。
5. **不要**在 `prog()` 外面用 `not in ("completed", "claimed")` 当闸门——`None` 恒真。
6. **不要**把 `data/` 目录里的令牌文件提交进仓库（`.gitignore` 已覆盖，别绕过）。

---

## 11. 国际版每日任务（独立 cron）

国内版（`workbuddy_daily.py`）和国际版（`workbuddy_intl_daily.py`）是**两套完全不同的东西**，
不要按国内版的预期去理解国际版。

### 11.1 国际版到底有什么

`BASE = https://www.workbuddy.ai`。国内版那 20 项日常任务（签到、画布、专家团、模板、小程序链……）
在国际版**一项都没有**，实测可用的只有三样：

| 体系 | 端点 | 状态（2026-10-30 实测） |
|:--|:--|:--|
| 每日签到活动（100 分/天） | `POST /billing/meter/checkin-activity-status` | `active: false`，`activity_name`/`start_time`/`end_time` 全空 ⇒ **后端没下发活动配置**，领不到 |
| 连登 streak | `GET /activity/growth/streak` | ✅ 活的，`days` 会随活跃上报 +1，满 7 天/14 天可兑换 |
| 等级任务（5 个） | `GET /v2/activity/growth/tasks` | `first_chat` / `skill_installed` / `wechat_linked` / `expert_summoned` / `template_used` |

实测结论（别重复踩）：**发一条对话 + 上报 `chat_request_send` 不会点亮 `first_chat`**——
HTTP 200、`code:0`，但任务状态仍是 `available`、profile 仍是 `completed:0 / level:0`、额度一分没少。
说明等级任务不认这条链路，大概率要真实客户端事件；`wechat_linked` 更是必须真人绑微信。

> 注意：`dsh-providers-hub` 的文档（`jet-hub.js:261`）写「国际版根本没有成长中心」是**过时/错误**的，
> 实测 `/v2/activity/growth/tasks` 返回 200 且有 5 个等级任务——只是没有日常任务口径。

### 11.2 部署

| 项 | 值 |
|:--|:--|
| 调度 | **面板任务 id=17「WorkBuddy 国际版」**（`daidai.db` 的 `tasks` 表），cron 见面板；不要用宿主 crontab |
| 入口 | `/opt/daidai/Dumb-Panel/scripts/workbuddy_intl_run.py`（700，python 包装，注入环境变量后 runpy 跑主脚本） |
| 主脚本 | `/opt/daidai/Dumb-Panel/scripts/workbuddy_intl_daily.py`（700） |
| 令牌 | `/opt/daidai/Dumb-Panel/data/wb_intl_token.txt`（600），格式 `备注\|token\|uid\|refresh_token` |
| 日志 | `/opt/daidai/Dumb-Panel/logs/task_17_WorkBuddy_国际版/<时间戳>.log`（面板按任务名建目录） |
| 运行身份 | 面板容器 `daidai-panel`，托管 python `deps/python/3.12/bin/python`（自带 requests 2.34） |
| 失败通知 | 面板 `notify_on_failure=0` |

> ⚠️ **面板只接受 `python` / `node` 开头的命令**。写成 `sh xxx.sh` 会报
> 「找不到托管依赖命令 sh，请先在依赖页面安装对应 Python/Node 依赖」并立即退出码 1。
> 所以入口必须是 `.py`，环境变量在 python 里用 `os.environ` 注入。

### 11.3 为什么不会天天提醒

两层都堵死了：

1. 入口脚本里 `os.environ["NO_NOTIFY"] = "1"` —— 主脚本第 625 行的判据是
   `if os.getenv("NO_NOTIFY","").strip() != "1" and lines:`，推送整段被短路，企业微信 / PushPlus 都不会发。
2. 面板任务的 `notify_on_failure=0`（失败也不发面板通知）。

脚本仍会打印摘要（`账号1 avigatorc：活动未开启…`），但**只进面板日志**。别把 `NO_NOTIFY=1` 删掉。

### 11.4 日常操作

```bash
# 手动跑一次（会真实调用，但国际版当前几乎零成本）
docker exec daidai-panel /app/Dumb-Panel/deps/python/3.12/bin/python \
    /app/Dumb-Panel/scripts/workbuddy_intl_run.py
# 或者直接在面板上点这条任务的「运行」

# 看日志
ls -t /opt/daidai/Dumb-Panel/logs/task_17_WorkBuddy_国际版/ | head -3

# 换令牌：覆盖四段格式文件即可，不用改任务
printf '%s\n' 'avigatorc|<AT>|<uid>|<RT>' > /opt/daidai/Dumb-Panel/data/wb_intl_token.txt
chmod 600 /opt/daidai/Dumb-Panel/data/wb_intl_token.txt

# 改时间 / 停掉：面板 UI 里改 cron 或把 status 置 0
```

### 11.5 已知噪音与限制

- 每天固定一行 `⚠️ 令牌续期失败: HTTP 401（改用现有令牌）`——**不是故障**：AT 的 `exp` 是
  **2027-10-29**，脚本回落到现有令牌继续跑。真过期了再换 token。
- 活动没开时，每天只做三件事：探测（关闭）、上报活跃（连登 +1）、保活对话 + 网页会话。
  等 `active` 翻成 `true` 才会自动领那 100 分——这才是挂着它的意义。
- 国际版**没有可持续的每日收益**，别指望它像国内版那样每天清 20 项。

### 11.6 只读探测（排查用，不发对话不领奖）

```bash
AT=$(cut -d'|' -f2 /opt/daidai/Dumb-Panel/data/wb_intl_token.txt)
UID=$(cut -d'|' -f3 /opt/daidai/Dumb-Panel/data/wb_intl_token.txt)
curl -s -X POST -H "Authorization: Bearer $AT" -H "X-User-Id: $UID" \
     -H "Content-Type: application/json" -d '{}' \
     https://www.workbuddy.ai/billing/meter/checkin-activity-status
```

---

## 12. 极氪签到（zeekr.js，不在本仓库）

### 12.1 定位

`/opt/daidai/Dumb-Panel/scripts/zeekr.js`，面板任务 **id=14「极氪签到」**，cron `10 0,21 * * *`，
命令 `node /app/Dumb-Panel/scripts/zeekr.js`，`success_exit_codes=0`，`notify_on_failure=1`。
环境变量只有 `ZEEKR_TOKEN`（存在面板 `env_vars`）。

上游是 [m20104600/zeekr-checkin](https://github.com/m20104600/zeekr-checkin)，青龙入口：
`https://raw.githubusercontent.com/m20104600/zeekr-checkin/main/dist/zeekr.qinglong.js`。

### 12.2 当前版本与定制

线上 `zeekr.js` = **上游 v3.3.0 + 4 处面板定制**，sha256 `fffddf3c…3ec35ce66`（73853 字节）。

| # | 定制 | 为什么 |
|:--|:--|:--|
| 1 | `zeekrPushServerChan()` + `zeekrQLNotify()` 优先走 Server酱 | 本部署没有青龙 `sendNotify.js` 的 `DAIDAI_NOTIFY_*` 渠道；面板 `env_vars` 里有 `SERVERCHAN_SENDKEY` |
| 2 | `ctx.reportedSteps` / `ctx.lastSteps` | 记录本次上报的步数 |
| 3 | 同值不补报 + 补报后复查任务 | 接口回 `000000` 但任务不计入时，重复上报只会白等一轮（实测「步行3000步」一直 `cur=0/1`） |
| 4 | 奖励领完但任务未达标 → `⚠️ 奖励已领完，但任务未全部达标` | 不再假报 `🎉 全部完成！` |

步数分档（`zeekrResolveStepCounts`，未设 `ZEEKR_STEPS` 时）：

```
< 12 点  → 500~1500      凌晨/上午
< 19 点  → 3000~10000    白天（面板定制，上游默认 10000~20000）
>= 19 点 → 15000~25000   晚间
```

### 12.3 升级步骤

```bash
cd /tmp
curl -sS -o zk_new.js https://raw.githubusercontent.com/m20104600/zeekr-checkin/main/dist/zeekr.qinglong.js
grep -n ZEEKR_PORT_VERSION zk_new.js          # 确认版本
# 1) 先打 Server酱 定制（插入 zeekrServerChanKey / zeekrPushServerChan，并在 zeekrQLNotify 里优先调用）
# 2) 部署后打「步数/任务结论」定制（reportedSteps / lastSteps / walkPending）
cp -p /opt/daidai/Dumb-Panel/scripts/zeekr.js /opt/daidai/Dumb-Panel/backups/zeekr.js.pre-<tag>.<时间戳>
cp /tmp/zk_patched.js /opt/daidai/Dumb-Panel/scripts/zeekr.js.new && chmod 600 .../zeekr.js.new
mv .../zeekr.js.new .../zeekr.js
docker exec daidai-panel node --check /app/Dumb-Panel/scripts/zeekr.js
```

> `node --check` 只认 `.js` 后缀，检查 `.new` 文件要先复制成 `/tmp/x.js`。

### 12.4 已知问题：「步行3000步 / 减碳2000g」永远 0/1

**这是服务端问题，不是脚本问题。** 已穷尽的排查（2026-11-03）：

| 变量 | 试过 | 结果 |
|:--|:--|:--|
| `sourceType` | 1 / 2 / 10 / 20 / 21 / 22 / 30 | 全 `000000`，任务不动 |
| `app_code` | `toc_h5_office_zeekrapp` / `toc_h5_green_zeekrapp` | 一样 |
| `app_type` / `platform_h5` / `risk_platform` | `web`↔`h5` / `""`↔`IOS` / `web`↔`h5` | 一样 |
| Origin / Referer | `www.zeekrlife.com` / `activity-h5.zeekrlife.com` | 一样 |
| `device_id` | `"0"` / 空 | 一样 |
| `accountId` | 带 / 不带 | 带错值才 `999999`，正确值也是 `000000` |

关键信号：`initDayWalkData` **永远返回 `data: null`**（对比 `taskMsg` / `uncollected` 都有完整回包），
且 `/zeekrlife-mp-val/**` 下只有这一个端点（其余全 404）。判断是接口已空壳化，或 `WEB_PC` Token 被该端点拒绝。
**下一步需要真机抓包**（App 里点「步行3000步」，看 `walkData` 请求的完整头 + 体）。

### 12.5 排障

```bash
# 只读：查任务进度（不写任何数据）
# 见 §12.4 的探针脚本思路：拿 ZEEKR_TOKEN 打 taskMsg，看 taskTakeDTO.currentStep / currentComplete
# 看日志
ls -t /opt/daidai/Dumb-Panel/logs/task_14_极氪签到/ | head -3

# 手动跑（必须注入 TOKEN，容器里没有面板环境变量）
TOKEN=$(python3 -c "import sqlite3;print(sqlite3.connect('file:/opt/daidai/Dumb-Panel/daidai.db?mode=ro',uri=True).execute(\"select value from env_vars where name='ZEEKR_TOKEN'\").fetchone()[0])")
docker exec -e ZEEKR_TOKEN="$TOKEN" -e ZEEKR_NOTIFY=0 daidai-panel node /app/Dumb-Panel/scripts/zeekr.js
```

---

## 13. 变更记录

| 日期 | 内容 |
|:--|:--|
| 2026-11-03 | 极氪 `zeekr.js` 升到上游 **v3.3.0**，移植 4 处面板定制（Server酱 通知 / 步数同值不补报 / 补报后复查 / 不假报完成）；耗时 221s→114s。穷尽排查「步行3000步」不达标：`sourceType`、`app_code`、身份头、`device_id`、`accountId` 全部无效，`initDayWalkData` 恒回 `data:null`，判定为服务端/Token 平台问题，待真机抓包 |
| 2026-11-03 | 合并上游 **v3.29–v3.36**（续期 `uid_of` NameError、5.9.3 指纹、专家任务先 accept、专家任务回落 MP、盲盒结算时序、积分差值）；`patch_panel.py` 14 补丁重打、输出与合并结果字节一致 |
| 2026-10-30 | 新增国际版每日任务：面板任务 id=17「WorkBuddy 国际版」，入口 `workbuddy_intl_run.py`（面板只认 python/node，`sh` 会被拒），`NO_NOTIFY=1` + `notify_on_failure=0` 双静默；实测国际版无日常任务、签到活动 `active=false`、等级任务不认 `chat_request_send` |
| 2026-10-30 | 合并上游 v3.26–v3.28；守卫改由上游承载、删除自造 `_needs_do()`；`patch_panel.py` 改为「不碰守卫只校验」；`check_patches.py`/`check_exit_codes.py` 重写；新增 `tests/test_panel_guards.py`；部署到面板并验证不再空跑画布对话 |
| 2026-10-28 | （上游）v3.26 修复 issue #39；面板分支被 v3.25 覆盖导致守卫丢失 |
| 2026-10-27 | `create_canvas` 下线，脚本开始空跑扣费 |
