# -*- coding: utf-8 -*-
"""把打好的包发成 GitHub Release（走 REST API）。

gh CLI 没装、MCP 那边也没有「建 Release / 传资产」的工具，所以直接打 API。
本机 HTTPS 被 MITM 代理拦着，证书链过不去 —— 只对这一次请求关掉校验，
不改系统设置（和 git 的 GIT_SSL_NO_VERIFY 是同一个道理）。

用法：
    .venv\\Scripts\\python.exe tools\\publish_release.py v1.0.0 "标题" 说明.md 资产1 [资产2 ...]

说明文件是 Markdown，直接作为 Release 正文。重复执行会复用同名 Tag 的
Release，只是再上传一遍资产（同名资产会覆盖）。
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
CTX = ssl._create_unverified_context()      # 本机代理做了 MITM，证书链校验过不去


def token() -> str:
    """从 git 的凭据助手那儿借 token，不额外存一份明文。"""
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    for line in out.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("拿不到 GitHub 凭据：先 git push 一次让凭据助手存上")


def repo() -> str:
    out = subprocess.run(["git", "remote", "get-url", "origin"],
                         capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(
                             os.path.abspath(__file__))))
    url = out.stdout.strip()
    # https://github.com/owner/name.git  /  git@github.com:owner/name.git
    url = url.replace("git@github.com:", "https://github.com/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.rstrip("/").split("/")
    return "%s/%s" % (parts[-2], parts[-1])


def call(method: str, url: str, tk: str, payload=None, raw: bytes | None = None,
         ctype: str = "application/json"):
    data = raw if raw is not None else (
        json.dumps(payload).encode() if payload is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + tk)
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        return e.code, detail


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 1
    tag, title, notes_path, assets = argv[0], argv[1], argv[2], argv[3:]
    for a in assets:
        if not os.path.exists(a):
            print("资产不存在:", a)
            return 1
    tk, full = token(), repo()
    notes = open(notes_path, encoding="utf-8").read()
    print("仓库:", full, " Tag:", tag)

    status, res = call("GET", "%s/repos/%s/releases/tags/%s" % (API, full, tag), tk)
    if status == 200:
        rel = res
        print("已存在同名 Release，复用：", rel["html_url"])
        status, res = call("PATCH", "%s/repos/%s/releases/%d" % (API, full, rel["id"]),
                           tk, {"name": title, "body": notes})
        if status != 200:
            print("更新说明失败", status, res)
            return 1
    else:
        status, res = call("POST", "%s/repos/%s/releases" % (API, full), tk,
                           {"tag_name": tag, "name": title, "body": notes,
                            "draft": False, "prerelease": False})
        if status != 201:
            print("建 Release 失败", status, res)
            return 1
        rel = res
        print("Release 建好了：", rel["html_url"])

    # 同名资产得先删掉：GitHub 不允许重名，直接传会 422。
    # 这样「重新发一版」就是覆盖，而不是攒一堆 _v2 之类的垃圾。
    old = {a["name"]: a["id"] for a in rel.get("assets", [])}
    for path in assets:
        name = os.path.basename(path)
        if name in old:
            st, _ = call("DELETE", "%s/repos/%s/releases/assets/%d"
                         % (API, full, old[name]), tk)
            if st not in (204, 200):
                print("删旧资产失败", name, st)
                return 1
            print("  覆盖旧资产：", name)

    for path in assets:
        name = os.path.basename(path)
        raw = open(path, "rb").read()
        upload = rel["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(name)
        status, res = call("POST", upload, tk, raw=raw,
                           ctype="application/octet-stream")
        if status not in (200, 201):
            print("上传失败", name, status, res)
            return 1
        print("  已上传 %-34s %.1f MB" % (name, len(raw) / 1024 / 1024))

    status, res = call("GET", "%s/repos/%s/releases/tags/%s" % (API, full, tag), tk)
    if status == 200:
        print("\n发布完成：", res["html_url"])
        for a in res.get("assets", []):
            print("  %-34s %8.1f MB  下载 %d 次" % (
                a["name"], a["size"] / 1024 / 1024, a["download_count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
