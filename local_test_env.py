# -*- coding: utf-8 -*-
"""本地校验用的环境搭手。

本机（Windows 沙箱）缺两样东西，都不影响被测逻辑：
  1. 没有第三方 `requests` —— 上游测试只把它当命名空间用，真正的 HTTP
     会话都在测试内注入 FakeSession，所以给个最小桩即可。
  2. tempfile 会以 0o700 建目录，沙箱 ACL 下建出来的目录不可写、也删不掉，
     换成用 os.makedirs 建目录、清理时忽略错误。
"""

import os
import shutil
import sys
import tempfile
import types
import uuid
from urllib.parse import quote as _url_quote


def install_requests_stub():
    if "requests" in sys.modules:
        return
    stub = types.ModuleType("requests")
    stub.Session = type("Session", (), {})
    stub.exceptions = types.SimpleNamespace(
        RequestException=type("RequestException", (Exception,), {}))
    stub.utils = types.SimpleNamespace(quote=_url_quote)
    stub.packages = types.SimpleNamespace(
        urllib3=types.SimpleNamespace(
            exceptions=types.SimpleNamespace(InsecureRequestWarning=Warning),
            disable_warnings=lambda *a, **k: None,
        ))
    sys.modules["requests"] = stub


def install_sandbox_friendly_tempdir(base):
    os.makedirs(base, exist_ok=True)

    def _mkdtemp(suffix=None, prefix=None, dir=None):
        root = dir or base
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, (prefix or "tmp") + uuid.uuid4().hex[:10] + (suffix or ""))
        os.makedirs(path, exist_ok=True)
        return path

    tempfile.mkdtemp = _mkdtemp
    tempfile.TemporaryDirectory._rmtree = classmethod(
        lambda cls, name, ignore_errors=False: shutil.rmtree(name, ignore_errors=True))
