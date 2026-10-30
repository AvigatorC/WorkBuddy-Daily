# -*- coding: utf-8 -*-
"""校验「呆呆面板」定制补丁与「未下发任务守卫」是否都还在。

这些是上游没有、或上游曾经丢过的关键行为，每次同步上游后都要跑一遍：
守卫一旦缺失，已下线的任务（如 create_canvas）就会继续真发对话、真扣积分。

本脚本只做静态检查，不导入被测脚本（导入会执行 load_accounts 并因缺凭据退出）。

用法：python check_patches.py [workbuddy_daily.py]
"""

import io
import sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "workbuddy_daily.py"
SOURCE = io.open(TARGET, encoding="utf-8").read()

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))


# ---- 1. 未下发任务守卫（issue #39：丢了就会空跑扣积分）----
GUARDS = (
    ("t_chat_n 未下发守卫", 'if st is None:\n            # 任务未下发'),
    ("create_canvas 未下发守卫", "canvas_st is None"),
    ("automation_1 未下发守卫", 'if st is None:\n        log("   自动化任务'),
    ("playbook_prompt 未下发守卫", "playbook_st is None"),
    ("RichMeow_Chat 未下发守卫", "need_rich = rich_st is not None"),
    ("skill_1 未下发守卫", "need_skill = skill_st is not None"),
)
for label, anchor in GUARDS:
    check(label, anchor in SOURCE)

bare_gates = [
    line.strip() for line in SOURCE.splitlines()
    if line.strip().startswith(("if prog(s,", "elif prog(s,"))
    and 'not in ("completed", "claimed")' in line
]
check("没有裸 prog() 闸门（None 恒真）", not bare_gates, "; ".join(bare_gates[:3]))

# ---- 2. 面板定制：通知策略 ----
check("WORKBUDDY_NOTIFY 文档存在", "WORKBUDDY_NOTIFY" in SOURCE)
check("推送默认 fail", 'or "fail").strip().lower()' in SOURCE)
check("fail 策略仍然静默成功轮", 'if mode == "fail" and _notify_ok(summaries):' in SOURCE)

# ---- 3. 面板定制：退出码 ----
check("存在 _exit_code", "def _exit_code(summaries):" in SOURCE)
check("main() 返回 _exit_code", "    return _exit_code(summaries)\n" in SOURCE)
check("--query 直接返回 0",
      "    if QUERY_ONLY:\n        # 只查不做的模式不该推送，也不该被面板判失败\n        return 0\n" in SOURCE)
check("入口用 sys.exit(main())", 'if __name__ == "__main__":\n    sys.exit(main())' in SOURCE)

# ---- 4. 面板定制：签到结论回传 ----
check("t_sign 接受 status_out", "def t_sign(s, uid, nick, log, status_out=None):" in SOURCE)
check("4 处签到成功都回传 checked_in",
      SOURCE.count('status_out["checked_in"] = True') == 4,
      "实际 %d 处" % SOURCE.count('status_out["checked_in"] = True'))
check("run_account 传入 _checkin_state",
      "t_sign(s, uid, nick, log, _checkin_state)" in SOURCE)
check("白名单排除签到时记录 skipped", '_checkin_state["skipped"] = True' in SOURCE)
check("summary 带 checked_in", 'summary["checked_in"] = bool(_checkin_state.get("checked_in"))' in SOURCE)
check("summary 带 checkin_skipped", 'summary["checkin_skipped"] = bool(' in SOURCE)

# ---- 5. 状态目录仍走 STATE_DIR（面板把 data/ 挂给 WORKBUDDY_STATE_DIR）----
check("有 STATE_DIR 定义", "STATE_DIR = _state_dir()" in SOURCE)
check("REFRESH_STORE 走 STATE_DIR",
      'REFRESH_STORE = os.path.join(STATE_DIR, "wb_refresh_tokens.json")' in SOURCE)
check("TOKEN_FILE 走 STATE_DIR",
      'TOKEN_FILE = os.path.join(STATE_DIR, "WORKBUDDY_ACCESS_TOKEN.txt")' in SOURCE)

print("=" * 68)
failed = 0
for name, ok, detail in results:
    if ok:
        print("  ok   %s" % name)
    else:
        failed += 1
        print("  FAIL %s %s" % (name, ("(%s)" % detail) if detail else ""))
print("=" * 68)
print("%d/%d 通过" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
