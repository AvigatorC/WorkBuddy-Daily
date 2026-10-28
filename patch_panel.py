# -*- coding: utf-8 -*-
"""把「呆呆面板」定制补丁打到上游 workbuddy_daily.py 上。

适用基线：上游 v3.25 及以上（已含 WORKBUDDY_STATE_DIR / _state_dir）。

上游不含、必须重新应用的定制：
  1. 下架任务守卫    _needs_do()：已下架(st=None)/已完成任务不再重复执行
  2. 签到结论回传    t_sign 通过 status_out 回传 checked_in，供退出码判定
  3. 通知策略        WORKBUDDY_NOTIFY=fail（默认，仅失败推）/ always / 0
  4. 退出码          main() 返回 0/1，签到失败时让面板判定任务失败并告警

注意：状态目录(_state_dir)已由上游 v3.23 合入（PR #35），本脚本不再重复打补丁。

用法：
    python patch_panel.py <上游脚本> <输出文件>
"""

import io
import sys

SRC, DST = sys.argv[1], sys.argv[2]
text = io.open(SRC, encoding="utf-8", newline="").read()
had_crlf = "\r\n" in text
text = text.replace("\r\n", "\n")

applied = []


def sub(old, new, label):
    global text
    n = text.count(old)
    if n != 1:
        raise SystemExit("补丁失败 [%s]：期望命中 1 处，实际 %d 处" % (label, n))
    text = text.replace(old, new, 1)
    applied.append(label)


def sub_any(pairs, label):
    """多形态匹配：上游不同版本措辞可能微调，命中其一即可。"""
    global text
    for old, new in pairs:
        if text.count(old) == 1:
            text = text.replace(old, new, 1)
            applied.append(label)
            return
    raise SystemExit("补丁失败 [%s]：所有候选形态都未唯一命中" % label)


# ------------------------------------------------------- 1 _needs_do 守卫
# 锚点必须从 `def prog(s, code):` 起算：_mp_prog() 的结尾与 prog() 完全相同，
# 仅靠函数尾部的 return 会命中 2 处。
sub(
    'def prog(s, code):\n'
    '    try:\n'
    '        r = s.get(BASE + "/v2/activity/growth/tasks", timeout=25, verify=False).json()\n'
    '        for t in r.get("data", {}).get("tasks", []):\n'
    '            if t.get("task_code") == code:\n'
    '                pr = t.get("progress") or {}\n'
    '                return t.get("accept_status", ""), pr.get("current"), pr.get("target")\n'
    '    except Exception:\n'
    '        pass\n'
    '    return None, None, None\n',
    'def prog(s, code):\n'
    '    try:\n'
    '        r = s.get(BASE + "/v2/activity/growth/tasks", timeout=25, verify=False).json()\n'
    '        for t in r.get("data", {}).get("tasks", []):\n'
    '            if t.get("task_code") == code:\n'
    '                pr = t.get("progress") or {}\n'
    '                return t.get("accept_status", ""), pr.get("current"), pr.get("target")\n'
    '    except Exception:\n'
    '        pass\n'
    '    return None, None, None\n'
    '\n'
    '\n'
    'def _needs_do(s, code):\n'
    '    """任务是否真的还需要做：只有「明确存在于列表且未完成」才返回 True。\n'
    '\n'
    '    关键点：`prog()` 读不到任务时返回 st=None。若把它当成「未完成」继续执行，\n'
    '    轻则白发一轮上报，重则真发对话、真扣积分（实测 Model_chat_GLM5.2 已下架，\n'
    '    每次仍跑一次 GLM-5.2 对话）。所以 None 一律视为「不要做」。\n'
    '    """\n'
    '    st, cur, tgt = prog(s, code)\n'
    '    return st is not None and st not in ("completed", "claimed")\n',
    "1-needs-do",
)

# ------------------------------------------------------- 2 t_sign status_out
sub(
    'def t_sign(s, uid, nick, log):\n'
    '    """每日签到 + 签到活动读数（连签天数 / 累计积分 / 连签奖励日）\n'
    '\n'
    '    先查活动状态，确认在活动期且今天未签才 POST。daily-checkin 对瞬时错误\n'
    '    （网络/5xx）有界重试，但空 200、业务失败或没有 credit 的响应不再写成成功。\n'
    '    """\n',
    'def t_sign(s, uid, nick, log, status_out=None):\n'
    '    """每日签到 + 签到活动读数（连签天数 / 累计积分 / 连签奖励日）\n'
    '\n'
    '    先查活动状态，确认在活动期且今天未签才 POST。daily-checkin 对瞬时错误\n'
    '    （网络/5xx）有界重试，但空 200、业务失败或没有 credit 的响应不再写成成功。\n'
    '\n'
    '    `status_out` 是调用方传入的 dict，用于回传签到结论，供进程退出码判定：\n'
    '      checked_in   True=今天确实已签（含幂等命中）\n'
    '    """\n',
    "2a-t_sign-signature",
)

# 各「签到成功」分支标记 checked_in
for label, old, new in [
    (
        "2b-sign-already",
        '    if status_data.get("today_checked_in") in (True, 1):\n'
        '        log("   ✅签到: 今天已签到%s" % _checkin_tail(s))\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
        '    if status_data.get("today_checked_in") in (True, 1):\n'
        '        log("   ✅签到: 今天已签到%s" % _checkin_tail(s))\n'
        '        if status_out is not None:\n'
        '            status_out["checked_in"] = True\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
    ),
    (
        "2c-sign-credit",
        '        log("   ✅签到成功 +%s积分%s%s" % (\n'
        '            claim_data.get("credit"), _checkin_tail(s),\n'
        '            "（状态稍后刷新）" if pending else ""))\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
        '        log("   ✅签到成功 +%s积分%s%s" % (\n'
        '            claim_data.get("credit"), _checkin_tail(s),\n'
        '            "（状态稍后刷新）" if pending else ""))\n'
        '        if status_out is not None:\n'
        '            status_out["checked_in"] = True\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
    ),
    (
        "2d-sign-already-claimed",
        '        log("   ✅签到: %s%s" % (message, _checkin_tail(s)))\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
        '        log("   ✅签到: %s%s" % (message, _checkin_tail(s)))\n'
        '        if status_out is not None:\n'
        '            status_out["checked_in"] = True\n'
        '        t_daily_activity(s, uid, nick, log)\n'
        '        return\n',
    ),
    (
        "2e-sign-code10001",
        '            log("   ✅签到: 状态回读确认今日已签%s" % _checkin_tail(s))\n'
        '            t_daily_activity(s, uid, nick, log)\n'
        '            return\n',
        '            log("   ✅签到: 状态回读确认今日已签%s" % _checkin_tail(s))\n'
        '            if status_out is not None:\n'
        '                status_out["checked_in"] = True\n'
        '            t_daily_activity(s, uid, nick, log)\n'
        '            return\n',
    ),
]:
    sub(old, new, label)

# ------------------------------------------------------- 3 聊天任务下架守卫
sub(
    'def t_chat_n(s, uid, nick, log, code, n, prompts):\n'
    '    """通用聊天任务: chat_5 / Model_chat_GLM5.2"""\n'
    '    for i in range(n):\n',
    'def t_chat_n(s, uid, nick, log, code, n, prompts):\n'
    '    """通用聊天任务: chat_5 / Model_chat_GLM5.2\n'
    '\n'
    '    ⚠️ 上游会随时下架任务。`prog()` 读不到时返回 st=None，若此时仍发对话，\n'
    '    会真实调用模型、真实扣积分（实测 Model_chat_GLM5.2 已下架）。\n'
    '    """\n'
    '    st, cur, tgt = prog(s, code)\n'
    '    if st is None:\n'
    '        log("   %s: 不在当前任务列表（已下架/改名），跳过，不发对话" % code)\n'
    '        return\n'
    '    for i in range(n):\n',
    "3-chat-n-guard",
)

# ------------------------------------------------------- 4 run_account 接线
sub(
    '    _run("每日签到", ["checkin"], lambda: t_sign(s, uid, nick, log))\n',
    '    _checkin_state = {}\n'
    '    if want("checkin"):\n'
    '        _run("每日签到", ["checkin"], lambda: t_sign(s, uid, nick, log, _checkin_state))\n'
    '    else:\n'
    '        # 用户用 WORKBUDDY_TASKS / WORKBUDDY_SKIP_TASKS 显式排除了签到：\n'
    '        # 这是他自己的选择，不应被判为失败（否则每天都会误报退出码 1）。\n'
    '        log("   ⏭️ 每日签到: 按配置跳过（不在本次任务白名单内）")\n'
    '        _checkin_state["skipped"] = True\n',
    "4-run-account-wiring",
)

sub(
    '    summary.update({"done": done, "total": len(st_all), "rest": rest,\n'
    '                    "level": prof2.get("level", "?"), "energy": energy})\n',
    '    summary.update({"done": done, "total": len(st_all), "rest": rest,\n'
    '                    "level": prof2.get("level", "?"), "energy": energy})\n'
    '    # 签到结论（供进程退出码判定；未执行/未确认一律 False）\n'
    '    summary["checked_in"] = bool(_checkin_state.get("checked_in"))\n'
    '    summary["checkin_skipped"] = bool(summary.get("enterprise") or _checkin_state.get("skipped"))\n',
    "5-summary-checkin",
)

# ------------------------------------------------------- 5 main 退出码 + 推送
sub_any([
    (
        '    # 推送摘要（完整日志见青龙日志/控制台）\n'
        '    send_notify_all("🌱 WorkBuddy 签到报告", build_summary(summaries))\n'
        '\n'
        '\n'
        'from concurrent.futures import ThreadPoolExecutor, as_completed\n'
        '\n'
        'if __name__ == "__main__":\n'
        '    main()\n',
        '    # ---- 退出码与推送 ----\n'
        '    # ⚠️ Server酱 免费版每天只有 5 条额度，所以**成功必须静默**。\n'
        '    # WORKBUDDY_NOTIFY 取值：fail（默认，仅失败推）/ always（调试用）/ 0（关闭）\n'
        '    if QUERY_ONLY:\n'
        '        return 0\n'
        '    failed_accounts = []\n'
        '    for sm in summaries:\n'
        '        if sm.get("checked_in"):\n'
        '            continue\n'
        '        # 企业版/无个人成长体系：上游本就不支持签到，不算失败\n'
        '        if sm.get("checkin_skipped") or sm.get("enterprise"):\n'
        '            continue\n'
        '        failed_accounts.append(sm.get("idx"))\n'
        '\n'
        '    notify_mode = (os.environ.get("WORKBUDDY_NOTIFY") or "fail").strip().lower()\n'
        '    if notify_mode != "0":\n'
        '        if failed_accounts:\n'
        '            print("")\n'
        '            print("❌ 签到未成功确认的账号: %s（详见上方各账号输出）"\n'
        '                  % "、".join("账号%d" % i for i in failed_accounts))\n'
        '            send_notify_all("❌ WorkBuddy 签到失败", build_summary(summaries))\n'
        '        elif notify_mode == "always":\n'
        '            send_notify_all("🌱 WorkBuddy 签到报告", build_summary(summaries))\n'
        '        else:\n'
        '            print("ℹ️ 签到正常，静默不推送（节省 Server酱 额度）")\n'
        '\n'
        '    if failed_accounts:\n'
        '        print("   退出码 1 —— 调度器会据此判定本次任务失败并告警")\n'
        '        return 1\n'
        '    return 0\n'
        '\n'
        '\n'
        'from concurrent.futures import ThreadPoolExecutor, as_completed\n'
        '\n'
        'if __name__ == "__main__":\n'
        '    sys.exit(main())\n',
    ),
], "6-main-exit-code")

# ------------------------------------------------------- 6 文档补充
sub_any([
    (
        '   SERVERCHAN_SENDKEY        【可选】Server酱 微信推送（免费每天 5 条）：https://sct.ftqq.com\n'
        '                             sctp 开头的是「方糖」专属通道，脚本会自动走对应域名\n',
        '   SERVERCHAN_SENDKEY        【可选】Server酱 微信推送（免费每天 5 条）：https://sct.ftqq.com\n'
        '                             sctp 开头的是「方糖」专属通道，脚本会自动走对应域名\n'
        '   WORKBUDDY_NOTIFY          【可选】推送策略，默认 fail（仅失败推，省额度）\n'
        '                              fail / 未设 → 仅签到失败时推\n'
        '                              always     → 每次都推（调试用）\n'
        '                              0          → 完全关闭\n',
    ),
], "7-doc-notify")

out = text.replace("\n", "\r\n") if had_crlf else text
io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("已应用 %d 个补丁：%s" % (len(applied), ", ".join(applied)))
