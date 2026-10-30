# -*- coding: utf-8 -*-
"""呆呆面板定制的回归：退出码语义 + 「未下发任务守卫」不变量。

独立成文件（不改上游 tests/test_workbuddy_core.py），这样每次同步上游都只需
重跑 patch_panel.py，测试文件保持上游原样、不会产生合并冲突。

用法：python run_tests_offline.py tests/test_panel_guards.py
"""

import ast
import unittest
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parents[1] / "workbuddy_daily.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = {
    node.name: node
    for node in TREE.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def load_functions(*names, **globals_):
    namespace = {"__builtins__": __builtins__, **globals_}
    module = ast.Module(body=[FUNCTIONS[name] for name in names], type_ignores=[])
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace


class PanelExitCodeTests(unittest.TestCase):
    """main() 的退出码要让调度器能把「签到失败」判成任务失败。

    企业号 / 用户用白名单显式跳过签到的账号不算失败，否则每天都会误报退出码 1。
    """

    def _module(self):
        return load_functions("_exit_code", print=lambda *a, **k: None)

    def test_all_accounts_checked_in_returns_zero(self):
        module = self._module()
        self.assertEqual(0, module["_exit_code"]([{"idx": 1, "checked_in": True},
                                                  {"idx": 2, "checked_in": True}]))

    def test_unconfirmed_account_returns_one(self):
        module = self._module()
        self.assertEqual(1, module["_exit_code"]([{"idx": 1, "checked_in": True},
                                                  {"idx": 2, "checked_in": False}]))

    def test_enterprise_or_skipped_accounts_are_not_failures(self):
        module = self._module()
        self.assertEqual(0, module["_exit_code"]([
            {"idx": 1, "checked_in": True},
            {"idx": 2, "checked_in": False, "enterprise": True},
            {"idx": 3, "checked_in": False, "checkin_skipped": True},
        ]))

    def test_no_accounts_returns_zero(self):
        module = self._module()
        self.assertEqual(0, module["_exit_code"]([]))

    def test_entry_point_uses_sys_exit(self):
        """入口必须 sys.exit(main())，否则退出码永远是 0，面板告警失效。"""
        self.assertIn('if __name__ == "__main__":\n    sys.exit(main())', SOURCE)

    def test_query_only_returns_zero(self):
        """--query 只查不做，不该推送也不该被判定失败。"""
        self.assertIn("    if QUERY_ONLY:\n        # 只查不做的模式不该推送", SOURCE)


class GuardCoverageTests(unittest.TestCase):
    """静态不变量：会真发对话的任务闸门必须显式处理 st=None。

    issue #39 的根因是 `prog()[0] not in ("completed", "claimed")` 对 None 恒真；
    每次上游同步都可能把守卫冲掉（v3.25 那次就冲掉过），所以这里钉死源码形状。
    """

    ANCHORS = (
        ("t_chat_n", "if st is None:\n            # 任务未下发"),
        ("create_canvas", "canvas_st is None"),
        ("automation_1", 'if st is None:\n        log("   自动化任务'),
        ("playbook_prompt", "playbook_st is None"),
        ("RichMeow_Chat", "need_rich = rich_st is not None"),
        ("skill_1", "need_skill = skill_st is not None"),
    )

    def test_every_gate_handles_none(self):
        for name, anchor in self.ANCHORS:
            self.assertIn(anchor, SOURCE, "守卫丢失：%s" % name)

    def test_no_bare_prog_gate_remains(self):
        """禁止 `if prog(s, ...)[0] not in ("completed", "claimed")` 这种 None 恒真闸门。

        只查「作为 if/elif 首条件」的写法；`... or prog(...) not in (...)` 是真发过
        请求之后的回落判断，None 时多走一次兜底上报，不产生对话、不扣费。
        """
        offenders = [
            line.strip() for line in SOURCE.splitlines()
            if line.strip().startswith(("if prog(s,", "elif prog(s,"))
            and 'not in ("completed", "claimed")' in line
        ]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
