# -*- coding: utf-8 -*-
"""把「呆呆面板」定制补丁打到上游 workbuddy_daily.py 上，并校验守卫没被同步冲掉。

适用基线：上游 v3.28 及以上。

上游 v3.26 起已经自带「任务未下发就不发请求」的守卫（issue #39），所以本脚本
**不再插入 `_needs_do()` 之类的守卫代码**——只在末尾用 verify_guards() 断言它们
还在。历史上正是「插入 helper 但调用点没跟上」导致画布对话空跑扣费，这里改成
「不碰守卫，只校验」。

上游不含、必须重新应用的定制只有两条：
  1. 通知策略  WORKBUDDY_NOTIFY 默认 fail（Server酱 免费版每天仅 5 条）
  2. 退出码    main() 返回 0/1，签到失败时让面板判定任务失败并告警

用法：
    python patch_panel.py <上游脚本> <输出文件> [上游测试文件 <测试输出文件>]
"""

import io
import re
import sys

if len(sys.argv) < 3:
    raise SystemExit("用法: python patch_panel.py <上游脚本> <输出文件> "
                     "[上游测试文件 <测试输出文件>]")

SRC, DST = sys.argv[1], sys.argv[2]
TEST_SRC = sys.argv[3] if len(sys.argv) > 3 else None
TEST_DST = sys.argv[4] if len(sys.argv) > 4 else None

applied = []


def _read(path):
    text = io.open(path, encoding="utf-8", newline="").read()
    return text.replace("\r\n", "\n"), "\r\n" in text


def _write(path, text, had_crlf):
    out = text.replace("\n", "\r\n") if had_crlf else text
    io.open(path, "w", encoding="utf-8", newline="").write(out)


def sub(old, new, label, text):
    n = text.count(old)
    if n != 1:
        raise SystemExit("补丁失败 [%s]：期望命中 1 处，实际 %d 处" % (label, n))
    applied.append(label)
    return text.replace(old, new, 1)


text, had_crlf = _read(SRC)

# ------------------------------------------------- 0 版本头标注面板定制
text, n = re.subn(r"(🌱 WorkBuddy Daily - 全能签到脚本 v[\d.]+)\n",
                  r"\1（呆呆面板定制）\n", text, count=1)
if n != 1:
    raise SystemExit("补丁失败 [0-header]：版本行未命中")
applied.append("0-header")

# ------------------------------------------------- 1 通知策略：默认 fail
text = sub(
    '   WORKBUDDY_NOTIFY          【可选】推送策略，默认 always（每次运行都推，与原行为一致）\n'
    '                             always → 每次都推\n'
    '                             fail   → 仅本轮有异常时推（签到未确认、账号异常中断）\n'
    '                             0      → 完全关闭推送\n',
    '   WORKBUDDY_NOTIFY          【可选】推送策略，默认 fail（仅失败推，省额度）\n'
    '                              fail / 未设 → 仅签到失败时推\n'
    '                              always     → 每次都推（调试用）\n'
    '                              0          → 完全关闭\n',
    "1-doc-notify", text)

text = sub(
    '    """按 WORKBUDDY_NOTIFY 策略决定是否推送。\n'
    '\n'
    '    always（默认，保持原行为）  每次运行都推\n'
    '    fail                        仅本轮不「一切正常」时推\n'
    '    0 / off / none              完全不推\n'
    '    """\n'
    '    mode = (os.environ.get("WORKBUDDY_NOTIFY") or "always").strip().lower()\n',
    '    """按 WORKBUDDY_NOTIFY 策略决定是否推送。\n'
    '\n'
    '    fail（默认，省 Server酱 额度）  仅本轮不「一切正常」时推\n'
    '    always                          每次运行都推（调试用）\n'
    '    0 / off / none                  完全不推\n'
    '    """\n'
    '    mode = (os.environ.get("WORKBUDDY_NOTIFY") or "fail").strip().lower()\n',
    "2-notify-default-fail", text)

# ------------------------------------------------- 2 退出码：main() 返回 0/1
text = sub(
    '    # 推送摘要（完整日志见青龙日志/控制台）\n'
    '    _notify_or_skip(summaries)\n',    '    # 推送摘要（完整日志见青龙日志/控制台）\n'
    '    if QUERY_ONLY:\n'
    '        # 只查不做的模式不该推送，也不该被面板判失败\n'
    '        return 0\n'
    '    _notify_or_skip(summaries)\n'
    '    return _exit_code(summaries)\n',
    "3-main-exit-code-call", text)

text = sub(
    '    send_notify_all("🌱 WorkBuddy 签到报告", build_summary(summaries))\n',
    '    send_notify_all("🌱 WorkBuddy 签到报告", build_summary(summaries))\n'
    '\n'
    '\n'
    'def _exit_code(summaries):\n'
    '    """面板按退出码判定任务成败：有账号签到未确认 → 1。\n'
    '\n'
    '    企业版 / 用户用白名单显式跳过签到的账号不算失败，否则每天都会误报。\n'
    '    """\n'
    '    for sm in summaries:\n'
    '        if sm.get("checked_in"):\n'
    '            continue\n'
    '        if sm.get("checkin_skipped") or sm.get("enterprise"):\n'
    '            continue\n'
    '        print("❌ 签到未成功确认: 账号%s（详见上方输出）" % sm.get("idx"))\n'
    '        print("   退出码 1 —— 调度器会据此判定本次任务失败并告警")\n'
    '        return 1\n'
    '    return 0\n',
    "4-exit-code-func", text)

text = sub(
    'if __name__ == "__main__":\n'
    '    main()\n',
    'if __name__ == "__main__":\n'
    '    sys.exit(main())\n',
    "5-entry-sys-exit", text)

# ------------------------------------------------- 2b 签到结论回传（退出码依赖）
text = sub(
    '    `status_out` 为调用方传入的 dict，用于回传签到结论供通知策略判断：\n',
    '    `status_out` 是调用方传入的 dict，用于回传签到结论，供退出码与通知策略判定：\n',
    "2b-status-doc", text)

text = sub(
    '    _checkin_state = {}\n'
    '    _run("每日签到", ["checkin"], lambda: t_sign(s, uid, nick, log, _checkin_state))\n',
    '    _checkin_state = {}\n'
    '    if want("checkin"):\n'
    '        _run("每日签到", ["checkin"], lambda: t_sign(s, uid, nick, log, _checkin_state))\n'
    '    else:\n'
    '        # 用户用 WORKBUDDY_TASKS / WORKBUDDY_SKIP_TASKS 显式排除了签到：\n'
    '        # 这是他自己的选择，不应被判为失败（否则每天都会误报退出码 1）。\n'
    '        log("   ⏭️ 每日签到: 按配置跳过（不在本次任务白名单内）")\n'
    '        _checkin_state["skipped"] = True\n',
    "2c-checkin-wiring", text)

text = sub(
    '    # 签到结论：供 WORKBUDDY_NOTIFY 判断本轮是否「正常」\n'
    '    summary["checked_in"] = bool(_checkin_state.get("checked_in"))\n',
    '    # 签到结论（供退出码与 WORKBUDDY_NOTIFY 判定；未执行/未确认一律 False）\n'
    '    summary["checked_in"] = bool(_checkin_state.get("checked_in"))\n'
    '    summary["checkin_skipped"] = bool(summary.get("enterprise") or _checkin_state.get("skipped"))\n',
    "2d-summary-checkin-skipped", text)

# ------------------------------------------------- 3 守卫必须还在（不插入，只校验）
GUARD_ANCHORS = (
    ("t_chat_n 未下发守卫", 'if st is None:\n            # 任务未下发'),
    ("create_canvas 未下发守卫", "canvas_st is None"),
    ("playbook_prompt 未下发守卫", "playbook_st is None"),
    ("RichMeow_Chat 未下发守卫", "need_rich = rich_st is not None"),
    ("skill_1 未下发守卫", "need_skill = skill_st is not None"),
)


def verify_guards(source):
    """上游一旦把守卫删掉，这里必须炸——否则画布/聊天会重新空跑扣费。"""
    missing = [label for label, anchor in GUARD_ANCHORS if anchor not in source]
    if missing:
        raise SystemExit(
            "守卫校验失败：上游这次同步缺少 %s。\n"
            "请先按 issue #39 的做法补回 `st is None` 守卫，再部署；"
            "否则已下线的任务会继续真发对话、真扣积分。" % "、".join(missing))


verify_guards(text)
applied.append("6-verify-guards")

_write(DST, text, had_crlf)

# ------------------------------------------------- 4 测试里的默认策略断言
if TEST_SRC and TEST_DST:
    ttext, t_crlf = _read(TEST_SRC)
    ttext = sub(
        '    def test_notify_policy_always_is_default(self):\n'
        '        """不设 WORKBUDDY_NOTIFY 时必须每次推送，保持原行为。"""\n',
        '    def test_notify_policy_fail_is_default(self):\n'
        '        """呆呆面板定制：不设 WORKBUDDY_NOTIFY 时默认 fail（Server酱 免费版每天仅 5 条）。"""\n',
        "7-test-name", ttext)
    ttext = sub(
        '            module["_notify_or_skip"]([{"idx": 1, "checked_in": True}])\n'
        '            self.assertEqual(1, len(sent))\n'
        '            module["_notify_or_skip"]([{"idx": 1, "checked_in": False}])\n'
        '            self.assertEqual(2, len(sent))\n',
        '            module["_notify_or_skip"]([{"idx": 1, "checked_in": True}])\n'
        '            self.assertEqual(0, len(sent))\n'
        '            module["_notify_or_skip"]([{"idx": 1, "checked_in": False}])\n'
        '            self.assertEqual(1, len(sent))\n',
        "8-test-assert", ttext)
    _write(TEST_DST, ttext, t_crlf)

print("已应用 %d 个补丁：%s" % (len(applied), ", ".join(applied)))
