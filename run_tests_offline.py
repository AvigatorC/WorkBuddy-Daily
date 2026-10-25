# -*- coding: utf-8 -*-
"""在缺少 requests 的本地环境里跑上游回归测试。

上游 tests/test_workbuddy_core.py 只把 `requests` 当作命名空间使用
（真正的 HTTP 会话都是测试内注入的 FakeSession / requests_module），
所以只用一个最小桩模块就能跑，被测逻辑完全不受影响。

用法：python run_tests_offline.py <tests/test_workbuddy_core.py>
"""

import os
import runpy
import sys

import local_test_env

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python run_tests_offline.py <测试文件>")
    test_file = sys.argv[1]
    local_test_env.install_requests_stub()
    local_test_env.install_sandbox_friendly_tempdir(os.path.join(HERE, ".verify"))
    sys.argv = [test_file]
    runpy.run_path(test_file, run_name="__main__")


if __name__ == "__main__":
    main()
