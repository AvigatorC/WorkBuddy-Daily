"""验证 _needs_do 逻辑：对着真实接口，确认已下架/已完成任务都判为「不用做」。"""
import sys

sys.path.insert(0, "/app/Dumb-Panel/scripts")
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

import workbuddy_daily as w

# 这三类是重点验证对象
CASES = [
    ("Model_chat_GLM5.2", "已下架 -> 必须 False（原先会白跑对话烧积分）"),
    ("Buddy_App_QQ", "已下架 -> 必须 False"),
    ("create_canvas", "已下架 -> 必须 False（原先会白跑对话）"),
    ("black_cat", "已下架 -> 必须 False"),
    ("chat_5", "已完成 -> 必须 False"),
    ("Hp_Appearance", "已完成 -> 必须 False"),
    ("Sequential_Tasks_7", "未完成 -> 应为 True"),
]

print("=" * 84)
print("%-24s %-10s %-10s %s" % ("task_code", "st", "_needs_do", "预期/说明"))
print("=" * 84)
all_ok = True
for code, note in CASES:
    st, cur, tgt = w.prog(s, code)
    nd = w._needs_do(s, code)
    expect_false = "必须 False" in note
    ok = (not nd) if expect_false else nd
    if not ok:
        all_ok = False
    print("%-24s %-10s %-10s %s %s" % (code, st, nd, "OK " if ok else "FAIL", note[:44]))

print()
print("结论:", "全部符合预期，不会再有已完成/已下架任务被重复执行" if all_ok else "存在不符预期项")
