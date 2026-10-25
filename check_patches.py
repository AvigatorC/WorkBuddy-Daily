# -*- coding: utf-8 -*-
"""校验呆呆面板补丁是否完整、行为是否与旧版 v3.17 一致。

这些是上游没有的本地定制，升级后必须逐条确认，否则面板集成会悄悄失配。

用法：python check_patches.py <被打过补丁的脚本>
"""

import contextlib
import json
import io
import os
import shutil
import sys
import uuid

import local_test_env

TARGET = sys.argv[1] if len(sys.argv) > 1 else "workbuddy_daily.py"
SOURCE = io.open(TARGET, encoding="utf-8").read()


@contextlib.contextmanager
def _scratch_dir():
    """自建临时目录，避开 Windows 沙箱对 tempfile 0o700 目录的限制。"""
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".verify")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "scratch-" + uuid.uuid4().hex[:10])
    os.makedirs(path, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))


# ---- 1. 静态检查：四处补丁都在 ----
check("状态目录函数 _resolve_state_dir 存在", "def _resolve_state_dir()" in SOURCE)
check("REFRESH_STORE 走 _STATE_DIR",
      'REFRESH_STORE = os.path.join(_STATE_DIR, "wb_refresh_tokens.json")' in SOURCE)
check("TOKEN_FILE 走 _STATE_DIR",
      'TOKEN_FILE = os.path.join(_STATE_DIR, "WORKBUDDY_ACCESS_TOKEN.txt")' in SOURCE)
check("BENEFIT_STATE_FILE 走 _STATE_DIR",
      'BENEFIT_STATE_FILE = os.path.join(_STATE_DIR, "workbuddy_benefit_state.json")' in SOURCE)
check("活跃状态走 _STATE_DIR",
      'state_file = os.getenv("WORKBUDDY_ACTIVITY_STATE", "").strip() or os.path.join(\n        _STATE_DIR, "workbuddy_activity_state.json")' in SOURCE)
check("脚本目录不再直接放状态文件",
      'os.path.dirname(os.path.abspath(__file__)), "wb_refresh_tokens.json"' not in SOURCE)

check("t_sign 接受 status_out", "def t_sign(s, uid, nick, log, status_out=None):" in SOURCE)
check("4 处签到成功都回传 checked_in",
      SOURCE.count('status_out["checked_in"] = True') == 4,
      "实际 %d 处" % SOURCE.count('status_out["checked_in"] = True'))
check("run_account 传入 _checkin_state",
      "t_sign(s, uid, nick, log, _checkin_state)" in SOURCE)
check("白名单排除签到时记录 skipped", '_checkin_state["skipped"] = True' in SOURCE)
check("summary 带 checked_in", 'summary["checked_in"] = bool(_checkin_state.get("checked_in"))' in SOURCE)
check("summary 带 checkin_skipped", 'summary["checkin_skipped"] = bool(' in SOURCE)

check("WORKBUDDY_NOTIFY 文档存在", "WORKBUDDY_NOTIFY" in SOURCE)
check("推送默认 fail 静默", 'notify_mode = (os.environ.get("WORKBUDDY_NOTIFY") or "fail")' in SOURCE)
check("失败推送标题", 'send_notify_all("❌ WorkBuddy 签到失败"' in SOURCE)
check("--query 直接返回 0", "    if QUERY_ONLY:\n        return 0\n" in SOURCE)
check("签到失败 return 1", "        return 1\n    return 0\n" in SOURCE)
check("入口用 sys.exit(main())", 'if __name__ == "__main__":\n    sys.exit(main())' in SOURCE)

# ---- 2. 动态检查：真的按面板布局解析状态目录 ----
local_test_env.install_requests_stub()
sys.path.insert(0, os.path.dirname(os.path.abspath(TARGET)) or ".")
os.environ.pop("WORKBUDDY_STATE_DIR", None)
os.environ.pop("WORKBUDDY_REFRESH_TOKEN", None)
os.environ.pop("WORKBUDDY_SKIP_TASKS", None)
os.environ.pop("WORKBUDDY_TASKS", None)

with _scratch_dir() as temp:
    scripts = os.path.join(temp, "scripts")
    data = os.path.join(temp, "data")
    os.makedirs(scripts)
    os.makedirs(data)
    open(os.path.join(data, "wb_refresh_tokens.json"), "w").write(
        '{"18600000000": {"refresh_token": "RT", "access_token": "AT", "updated": 1}}')

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "wb_under_test", os.path.join(scripts, "workbuddy_daily.py"))
    module = importlib.util.module_from_spec(spec)
    # 把被测脚本复制到面板式布局里再导入，才能验证 __file__ 推导
    source = io.open(TARGET, encoding="utf-8").read()
    io.open(os.path.join(scripts, "workbuddy_daily.py"), "w", encoding="utf-8").write(source)
    spec.loader.exec_module(module)

    check("状态目录解析到 data/",
          os.path.normcase(module._STATE_DIR) == os.path.normcase(data),
          module._STATE_DIR)
    check("REFRESH_STORE 指向 data/",
          os.path.normcase(module.REFRESH_STORE) ==
          os.path.normcase(os.path.join(data, "wb_refresh_tokens.json")))
    check("不会把状态写到 scripts/",
          not os.path.exists(os.path.join(scripts, "wb_refresh_tokens.json")))

    # 脚本必须从 data/ 读取令牌库（而不是 scripts/ 下的空库，
    # 否则会回落到环境变量里那份「没轮换过」的旧 RT，有掉登录风险）
    store_on_disk = json.load(io.open(module.REFRESH_STORE, encoding="utf-8"))
    check("从 data/ 读到已轮换的令牌库",
          store_on_disk.get("18600000000", {}).get("refresh_token") == "RT",
          "keys=%s" % list(store_on_disk))
    check("导入后仍不在 scripts/ 生成状态文件",
          not os.path.exists(os.path.join(scripts, "wb_refresh_tokens.json")))

    # WORKBUDDY_STATE_DIR 覆盖优先级
    override = os.path.join(temp, "custom")
    os.environ["WORKBUDDY_STATE_DIR"] = override
    resolved = module._resolve_state_dir()
    check("WORKBUDDY_STATE_DIR 可覆盖", os.path.normcase(resolved) == os.path.normcase(override), resolved)
    os.environ.pop("WORKBUDDY_STATE_DIR", None)

# ---- 3. 退出码语义：签到失败返回 1，--query 返回 0 ----
check("main() 有返回值路径", SOURCE.count("return 0") >= 2 and "return 1" in SOURCE)

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
