# -*- coding: utf-8 -*-
"""把「呆呆面板」定制补丁重新打到上游 workbuddy_daily.py 上。

上游 L0NE-6/WorkBuddy-Daily 不包含以下四处本地定制，升级时必须重新应用，
否则面板集成会被破坏：

  1. 状态文件目录    wb_refresh_tokens.json / WORKBUDDY_ACCESS_TOKEN.txt 等
                     落到面板 data/ 卷，而不是脚本同级 scripts/。
                     否则升级后 RT 状态文件读不到，会拿环境变量里的旧 RT 重新
                     自举，有掉登录的风险。
  2. 签到结论回传    t_sign 通过 status_out 回传 checked_in，供退出码判定。
  3. 通知策略        WORKBUDDY_NOTIFY=fail（默认，仅失败推）/ always / 0，
                     照顾 Server酱 免费版每天 5 条额度。
  4. 退出码          main() 返回 0/1，签到失败时让面板判定任务失败并告警。

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


# ---------------------------------------------------------------- 1 状态目录
sub(
    'REFRESH_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wb_refresh_tokens.json")\n'
    'TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WORKBUDDY_ACCESS_TOKEN.txt")\n'
    'BENEFIT_STATE_FILE = os.path.join(\n'
    '    os.path.dirname(os.path.abspath(__file__)), "workbuddy_benefit_state.json")\n',
    '''def _resolve_state_dir():
    """状态文件目录。

    优先 `WORKBUDDY_STATE_DIR`，其次脚本上级的 `data/`（呆呆里是
    /app/Dumb-Panel/data/，在数据卷内），最后退回脚本目录（青龙单文件部署）。

    这样与 qoder / trae 两个脚本的行为一致：状态统一落在 data/ 下，
    重装或更新脚本都不会碰到。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.environ.get("WORKBUDDY_STATE_DIR", "").strip(),
        os.path.join(os.path.dirname(here), "data"),
        here,
    ):
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".w")
            with open(probe, "w") as fh:
                fh.write("")
            os.remove(probe)
            return cand
        except Exception:
            continue
    return here


_STATE_DIR = _resolve_state_dir()

REFRESH_STORE = os.path.join(_STATE_DIR, "wb_refresh_tokens.json")
TOKEN_FILE = os.path.join(_STATE_DIR, "WORKBUDDY_ACCESS_TOKEN.txt")
BENEFIT_STATE_FILE = os.path.join(_STATE_DIR, "workbuddy_benefit_state.json")
''',
    "1-state-dir",
)

# ------------------------------------------------------- 2 活跃状态同一目录
sub(
    '    state_file = os.getenv("WORKBUDDY_ACTIVITY_STATE", "").strip() or os.path.join(\n'
    '        os.path.dirname(os.path.abspath(__file__)), "workbuddy_activity_state.json")',
    '    state_file = os.getenv("WORKBUDDY_ACTIVITY_STATE", "").strip() or os.path.join(\n'
    '        _STATE_DIR, "workbuddy_activity_state.json")',
    "2-activity-state",
)

# ------------------------------------------------------- 3 t_sign 回传结论
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
    '      checked_in   True=今天确实已签（含幂等命中）；False=未签成功\n'
    '      reason       未签成功的原因（简短中文）\n'
    '    """\n',
    "3a-t_sign-signature",
)

# 每个「签到成功」分支都标记 checked_in，两处企业版 deny 也标记以便豁免
for label, old, new in [
    (
        "3b-sign-already",
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
        "3c-sign-credit",
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
        "3d-sign-already-claimed",
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
        "3e-sign-code10001",
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

# ------------------------------------------------------- 6 main 退出码 + 推送
sub(
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
    "6-main-exit-code",
)

# ------------------------------------------------------- 7 文档补充
sub(
    '   SERVERCHAN_SENDKEY        【可选】Server酱 微信推送（免费每天 5 条）：https://sct.ftqq.com\n'
    '                             sctp 开头的是「方糖」专属通道，脚本会自动走对应域名\n',
    '   SERVERCHAN_SENDKEY        【可选】Server酱 微信推送（免费每天 5 条）：https://sct.ftqq.com\n'
    '                             sctp 开头的是「方糖」专属通道，脚本会自动走对应域名\n'
    '   WORKBUDDY_NOTIFY          【可选】推送策略，默认 fail（仅失败推，省额度）\n'
    '                              fail / 未设 → 仅签到失败时推\n'
    '                              always     → 每次都推（调试用）\n'
    '                              0          → 完全关闭\n',
    "7-doc-notify",
)

out = text.replace("\n", "\r\n") if had_crlf else text
io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("已应用 %d 个补丁：%s" % (len(applied), ", ".join(applied)))
