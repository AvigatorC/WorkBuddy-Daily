import json
import urllib3

urllib3.disable_warnings()
import requests

BASE = "https://www.codebuddy.cn"
tok = ""
for line in open("/app/Dumb-Panel/data/WORKBUDDY_ACCESS_TOKEN.txt", encoding="utf-8").read().strip().splitlines():
    p = line.strip().split("@")
    if len(p) >= 2 and p[1].startswith("eyJ"):
        tok = p[1]
        break
    if line.startswith("eyJ"):
        tok = line.strip()
        break

s = requests.Session()
s.trust_env = False
s.headers.update({"Authorization": "Bearer " + tok})

# 桌面口径
desk = s.get(BASE + "/v2/activity/growth/tasks", timeout=25, verify=False).json()
dtasks = (desk.get("data") or {}).get("tasks") or []
dmap = {}
for t in dtasks:
    dmap[t.get("task_code")] = t

# 小程序口径
h = {"X-Client-Platform": "miniprogram"}
mpr = s.get(BASE + "/v2/activity/growth/tasks", headers=h, timeout=25, verify=False).json()
mtasks = (mpr.get("data") or {}).get("tasks") or []
mmap = {}
for t in mtasks:
    mmap[t.get("task_code")] = t

# 脚本里所有 _run 声明的 task code
SCRIPT_CODES = [
    "checkin", "Expert_team_use_3", "Buddy_App", "Buddy_App_QQ",
    "Hp_Appearance", "Library_read", "create_canvas", "automation_1", "playbook_prompt",
    "expert_5", "template_5", "Model_chat_GLM5.2", "chat_5", "black_cat",
    "Expert_lighthouse", "WorkBuddy_Valorant",
    "expert_use_maidehao", "expert_use_douyinyin",
    "expert_use_shangjia_xuanchuan", "expert_use_bowangwang",
    "Sequential_Tasks_1", "Sequential_Tasks_2", "Sequential_Tasks_3", "Sequential_Tasks_4",
    "Sequential_Tasks_5", "Sequential_Tasks_6", "Sequential_Tasks_7",
    "badges", "blindbox", "buddy_info", "travel", "makeup", "redeem", "lottery", "gift",
    "workstation_expert",
]

print("=" * 92)
print("桌面口径任务: %d 项 | 小程序口径: %d 项 | 脚本声明: %d 项" % (len(dtasks), len(mtasks), len(SCRIPT_CODES)))
print("=" * 92)
print("%-32s %-14s %-14s %s" % ("task_code", "桌面状态", "小程序状态", "诊断"))
print("-" * 92)

missing, done, todo = [], [], []
for code in SCRIPT_CODES:
    d = dmap.get(code)
    m = mmap.get(code)
    ds = d.get("accept_status") if d else None
    ms = m.get("accept_status") if m else None
    if d is None and m is None:
        diag = "!! 接口无此任务（脚本仍会跑）"
        missing.append(code)
    elif (ds in ("completed", "claimed")) or (ms in ("completed", "claimed")):
        diag = "已完成"
        done.append((code, ds or ms))
    else:
        diag = "未完成"
        todo.append((code, ds, ms))
    print("%-32s %-14s %-14s %s" % (code, ds or "-", ms or "-", diag))

print()
print("=" * 92)
print("A. 接口里不存在、但脚本还会去跑（会白扣积分）: %d 项" % len(missing))
for c in missing:
    print("   -", c)
print()
print("B. 已完成（应跳过）: %d 项" % len(done))
print()
print("C. 真正未完成: %d 项" % len(todo))
for c, ds, ms in todo:
    print("   - %-32s 桌面=%s 小程序=%s" % (c, ds or "-", ms or "-"))
