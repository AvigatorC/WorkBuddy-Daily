# -*- coding: utf-8 -*-
"""验证退出码与推送开关的真实运行语义（不发网络请求）。

面板任务配置 success_exit_codes='0'，所以退出码必须满足：
  · 签到成功            → 0（且默认静默，不推送）
  · 签到失败            → 1（告警）
  · 企业版账号（上游不支持签到） → 0（不算失败）
  · 白名单主动排除签到   → 0（用户自己的选择）
  · --query             → 0
  · WORKBUDDY_NOTIFY=0  → 即使失败也不推送，但退出码仍为 1

做法：加载被测脚本，把 main() 依赖的账号执行与推送函数替换成桩。
用法：python check_exit_codes.py <脚本>
"""

import io
import json
import os
import shutil
import sys
import uuid

import local_test_env

TARGET = sys.argv[1] if len(sys.argv) > 1 else "workbuddy_daily.py"
local_test_env.install_requests_stub()

# 被测脚本导入时就会解析账号，没有凭据会直接退出。
# 这里先造一个假的 data/ 布局 + 合法形态的 JWT 占位，导入后再替换 main() 的依赖。
_SCRATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".verify",
                        "exit-" + uuid.uuid4().hex[:10])
_SCRIPTS = os.path.join(_SCRATCH, "scripts")
_DATA = os.path.join(_SCRATCH, "data")
os.makedirs(_SCRIPTS)
os.makedirs(_DATA)

_FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjk5OTk5OTk5OTl9.c2lnbmF0dXJl"
json.dump({"13800000000": {"refresh_token": _FAKE_JWT, "access_token": _FAKE_JWT,
                           "updated": 9999999999}},
          io.open(os.path.join(_DATA, "wb_refresh_tokens.json"), "w", encoding="utf-8"))
shutil.copy(TARGET, os.path.join(_SCRIPTS, "workbuddy_daily.py"))

os.environ.pop("WORKBUDDY_REFRESH_TOKEN", None)
os.environ.pop("WORKBUDDY_STATE_DIR", None)
sys.path.insert(0, _SCRIPTS)

import importlib.util

spec = importlib.util.spec_from_file_location(
    "wb_exit_test", os.path.join(_SCRIPTS, "workbuddy_daily.py"))
wb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wb)

results = []
pushed = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))


def run_main(summaries, query_only=False, notify=None):
    """跑 main()，用给定 summaries 冒充各账号执行结果。"""
    pushed.clear()
    wb.QUERY_ONLY = query_only
    wb.ACCOUNTS = [{"note": "13800000000"}]
    seq = list(summaries)

    def fake_run_account(idx, acc, do_desktop):
        return ["[stub] account %d" % idx], seq.pop(0) if seq else summaries[-1]

    wb.run_account = fake_run_account
    wb.send_notify_all = lambda title, content: pushed.append(title)
    os.environ.pop("WORKBUDDY_NOTIFY", None)
    if notify is not None:
        os.environ["WORKBUDDY_NOTIFY"] = notify
    try:
        return wb.main()
    finally:
        os.environ.pop("WORKBUDDY_NOTIFY", None)
        wb.QUERY_ONLY = False


OK = {"idx": 1, "checked_in": True, "checkin_skipped": False, "done": 20, "total": 20,
      "rest": [], "level": 15, "energy": "?"}
FAIL = {"idx": 1, "checked_in": False, "checkin_skipped": False, "done": 19, "total": 20,
        "rest": ["checkin"], "level": 15, "energy": "?"}
ENT = {"idx": 1, "checked_in": False, "checkin_skipped": True, "enterprise": True,
       "done": 0, "total": 0, "rest": [], "level": "?", "energy": "?"}

code = run_main([OK])
check("签到成功 → 退出码 0", code == 0, str(code))
check("签到成功 → 默认不推送（省 Server酱 额度）", pushed == [], str(pushed))

code = run_main([FAIL])
check("签到失败 → 退出码 1", code == 1, str(code))
check("签到失败 → 推送告警", any("失败" in t for t in pushed), str(pushed))

code = run_main([ENT])
check("企业版账号 → 退出码 0（上游本就不支持签到）", code == 0, str(code))
check("企业版账号 → 不推送", pushed == [], str(pushed))

code = run_main([{"idx": 1, "checked_in": False, "checkin_skipped": True, "done": 19,
                  "total": 20, "rest": [], "level": 15, "energy": "?"}])
check("白名单排除签到 → 退出码 0", code == 0, str(code))

code = run_main([FAIL], query_only=True)
check("--query → 退出码 0", code == 0, str(code))
check("--query → 不推送", pushed == [], str(pushed))

code = run_main([FAIL], notify="0")
check("NOTIFY=0 且失败 → 仍不推送", pushed == [], str(pushed))
check("NOTIFY=0 且失败 → 退出码仍为 1", code == 1, str(code))

code = run_main([OK], notify="always")
check("NOTIFY=always 且成功 → 推送", len(pushed) == 1, str(pushed))

print("=" * 68)
failed = 0
for name, ok, detail in results:
    if ok:
        print("  ok   %s" % name)
    else:
        failed += 1
        print("  FAIL %s (%s)" % (name, detail))
print("=" * 68)
print("%d/%d 通过" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
