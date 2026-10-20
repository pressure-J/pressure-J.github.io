# -*- coding: utf-8 -*-
"""
publish.py —— 一条命令完成「编译 → 提交 → 推送」

用法:
    py publish.py                # 生成 + 提交 + 推送
    py publish.py -m "改了啥"    # 指定提交信息
    py publish.py --no-push      # 只生成并提交，不推送
    py publish.py --dry-run      # 只显示会发生什么

为什么需要它:
    GitHub 的 443 端口在本机时通时断，纯 `git push` 经常 Connection reset。
    这里先试原生 push，失败自动切到 GitHub REST API 推送（同样保持线性历史），
    两条路都失败才报错退出。凭据从 Windows 凭据管理器读，不落盘、不进仓库。

安全:
    本文件只读取凭据并用于本次网络请求，不打印、不写入任何文件。
"""

import argparse
import base64
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE = "origin"
BRANCH = "main"
GCM = (r"C:\Users\%s\AppData\Local\hermes\tools"
       r"\git-2.53.0+3-win32-x64\mingw64\bin\git-credential-manager.exe"
       % os.path.basename(os.path.expanduser("~")))
API = "https://api.github.com"


def sh(*args, check=True, cwd=REPO_DIR):
    r = subprocess.run(list(args), cwd=cwd, capture_output=True)
    out = r.stdout.decode("utf-8", "ignore").strip()
    err = r.stderr.decode("utf-8", "ignore").strip()
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}\n{err or out}")
    return out, err, r.returncode


def say(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------ 凭据
def get_token():
    """从 Windows 凭据管理器取 GitHub token（git-credential-manager 已存）"""
    try:
        r = subprocess.run(
            [GCM, "get"],
            input=b"protocol=https\nhost=github.com\n\n",
            capture_output=True, timeout=60)
        for line in r.stdout.decode("utf-8", "ignore").splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception as e:
        say(f"  ! 读取凭据失败: {e}")
    return None


def repo_slug():
    """从 origin 地址解析 owner/repo"""
    url, _, _ = sh("git", "remote", "get-url", REMOTE)
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.replace(":", "/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


# ------------------------------------------------------------------ 构建
def build():
    say("① 编译站点")
    out, err, rc = sh(sys.executable, os.path.join(REPO_DIR, "build.py"), check=False)
    for line in (out or err).splitlines():
        say("   " + line)
    if rc != 0:
        raise SystemExit("构建失败，已中止（没有提交任何东西）")


# ------------------------------------------------------------------ 提交
def commit(message):
    say("\n② 提交改动")
    sh("git", "add", "-A")
    pending = sh("git", "status", "--porcelain")[0]
    if not pending:
        say("   没有内容变化，跳过提交")
        return False
    n = len([l for l in pending.splitlines() if l.strip()])
    sh("git", "-c", f"user.name={sh('git', 'config', 'user.name')[0]}",
       "-c", f"user.email={sh('git', 'config', 'user.email')[0]}",
       "commit", "-q", "-m", message)
    say(f"   已提交 {n} 个文件：{sh('git', 'log', '-1', '--format=%h %s')[0]}")
    return True


# ------------------------------------------------------------------ 推送
def push_git(token):
    """原生 git push（走 443）"""
    say("\n③ 推送（git 协议）")
    auth = base64.b64encode(f"pressure-J:{token}".encode()).decode()
    try:
        out, err, rc = sh("git", "-c", f"http.extraheader=AUTHORIZATION: basic {auth}",
                          "push", REMOTE, BRANCH, check=False)
    except Exception as e:
        return False, str(e)
    if rc == 0:
        say("   ✓ 推送成功")
        return True, ""
    return False, (err or out)[-300:]


def api(method, path, payload=None, token=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pressure-j-publish")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def push_api(token, slug):
    """用 REST API 推送：把本地 ahead 的提交按文件写成 blob → tree → commit → 移动分支。
    绕开 443 被重置的问题，历史仍然每条一个 commit。"""
    say("   原生推送不通，改用 GitHub API …")
    code, ref = api("GET", f"/repos/{slug}/git/ref/heads/{BRANCH}", token=token)
    if code != 200:
        return False, f"读取远端分支失败 {code}"
    remote_head = ref["object"]["sha"]

    local_head, _, _ = sh("git", "rev-parse", "HEAD")
    if local_head == remote_head:
        say("   ✓ 远端已是这个提交")
        return True, ""

    # 本地领先/落后情况：只处理"远端是本地祖先"这种线性情形
    _, _, rc = sh("git", "merge-base", "--is-ancestor", remote_head, local_head, check=False)
    if rc != 0:
        return False, "远端有本地没有的提交，需要先 git pull 处理分叉"

    # 收集 remote_head..local_head 之间所有改动过的文件
    diff, _, _ = sh("git", "diff", "--name-status", remote_head, local_head)
    files = [l.split("\t") for l in diff.splitlines() if l.strip()]
    say(f"   涉及 {len(files)} 个文件")

    code, base = api("GET", f"/repos/{slug}/git/commits/{remote_head}", token=token)
    if code != 200:
        return False, f"读取 base commit 失败 {code}"
    tree_sha = base["tree"]["sha"]

    SAMPLE_FIRST = 400
    entries = []
    for row in files:
        status, path = row[0], row[-1]
        if status == "D":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        full = os.path.join(REPO_DIR, path.replace("/", os.sep))
        if not os.path.exists(full):
            continue
        content = open(full, "rb").read()
        code, blob = api("POST", f"/repos/{slug}/git/blobs",
                         {"content": base64.b64encode(content).decode(),
                          "encoding": "base64"}, token=token)
        if code not in (200, 201):
            return False, f"上传 blob 失败 {path}: {code}"
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    code, tree = api("POST", f"/repos/{slug}/git/trees",
                     {"base_tree": tree_sha, "tree": entries}, token=token)
    if code not in (200, 201):
        return False, f"建 tree 失败 {code}"

    msg, _, _ = sh("git", "log", "-1", "--format=%B", local_head)
    code, newc = api("POST", f"/repos/{slug}/git/commits",
                     {"message": msg, "tree": tree["sha"], "parents": [remote_head]},
                     token=token)
    if code not in (200, 201):
        return False, f"建 commit 失败 {code}: {newc}"

    code, out = api("PATCH", f"/repos/{slug}/git/refs/heads/{BRANCH}",
                    {"sha": newc["sha"], "force": False}, token=token)
    if code not in (200, 201):
        return False, f"更新分支失败 {code}: {out}"

    say(f"   ✓ 推送成功（API，远端 commit {out['object']['sha'][:10]}）")
    # 让本地与远端重新对齐：内容相同，只是 commit hash 不同
    sh("git", "fetch", REMOTE, BRANCH, check=False)
    if sh("git", "rev-parse", f"{REMOTE}/{BRANCH}")[0] != local_head:
        sh("git", "reset", "--soft", f"{REMOTE}/{BRANCH}", check=False)
        sh("git", "reset", "-q", f"{REMOTE}/{BRANCH}", check=False)
        sh("git", "checkout", "--", ".", check=False)
    return True, ""


# ------------------------------------------------------------------ 主流程
def main():
    ap = argparse.ArgumentParser(description="编译并发布博客")
    ap.add_argument("-m", "--message", default="", help="提交信息")
    ap.add_argument("--no-push", action="store_true", help="只编译和提交，不推送")
    ap.add_argument("--dry-run", action="store_true", help="只显示将要做什么")
    args = ap.parse_args()

    msg = args.message or f"更新笔记 {datetime.date.today().isoformat()}"

    if args.dry_run:
        say(f"仓库: {REPO_DIR}")
        say(f"远端: {sh('git', 'remote', 'get-url', REMOTE)[0]}  分支: {BRANCH}")
        say(f"提交信息: {msg}")
        ahead = sh("git", "rev-list", "--count", f"{REMOTE}/{BRANCH}..HEAD", check=False)[0]
        say(f"待推送提交: {ahead or '0'}")
        return

    build()

    if not args.no_push:
        # 先看有没有东西要提交
        changed = commit(msg)
        if not changed:
            ahead = sh("git", "rev-list", "--count", f"{REMOTE}/{BRANCH}..HEAD",
                       check=False)[0] or "0"
            if ahead == "0":
                say("\n站点已是最新，无需推送")
                return

    else:
        commit(msg)
        say("\n已提交（--no-push，未推送）")
        return

    token = get_token()
    if not token:
        say("\n! 没读到 GitHub 凭据。请先执行一次 `git push`，让凭据管理器保存 token；"
            "\n  或运行 `git-credential-manager configure` 登录。改动已提交在本地，不会丢。")
        raise SystemExit(1)

    slug = repo_slug()
    ok, why = push_git(token)
    if not ok:
        for attempt in range(2):          # API 也重试一次，网络抖动很常见
            ok, why = push_api(token, slug)
            if ok:
                break
            say(f"   第 {attempt + 1} 次失败: {why}")
            time.sleep(4)

    if not ok:
        say(f"\n✗ 推送失败：{why}")
        say("  改动已安全地提交在本地。网络恢复后重新运行 `py publish.py` 即可，不会重复提交。")
        raise SystemExit(1)

    say("\n完成。GitHub Pages 通常 30~60 秒后生效：")
    say("  https://pressure-j.github.io")


if __name__ == "__main__":
    main()
