# -*- coding: utf-8 -*-
"""发布 Release：创建 tag/release 并上传打包好的 exe（幂等，可重复执行）。

用法：python scripts/publish_release.py <tag> <asset_path> [title] [body_file]
凭据取自 git credential manager；网络请求直连（不走系统代理）。
"""
import json
import sys
import time
from pathlib import Path

import requests

REPO = "lifeiyu-44/lol-battle-query"
API = "https://api.github.com/repos/" + REPO
UPLOAD = "https://uploads.github.com/repos/" + REPO


def fill_token():
    import subprocess
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return None


def headers(token):
    return {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}


def main():
    tag, asset_path = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else tag
    body = Path(sys.argv[4]).read_text(encoding="utf-8") if len(sys.argv) > 4 else ""
    token = fill_token()
    if not token:
        print("NO_TOKEN")
        sys.exit(1)
    session = requests.Session()
    session.trust_env = False  # 本机代理常不可用，直连

    release_id = None
    for attempt in range(6):
        resp = session.post(API + "/releases", headers=headers(token), json={
            "tag_name": tag, "target_commitish": "main", "name": title, "body": body,
            "draft": False, "prerelease": False}, timeout=30)
        if resp.status_code == 201:
            release_id = resp.json()["id"]
            print("release created:", resp.json().get("html_url"))
            break
        if resp.status_code == 422:  # 已存在 → 找现有 release
            resp2 = session.get(API + "/releases/tags/" + tag, headers=headers(token), timeout=30)
            if resp2.status_code == 200:
                release_id = resp2.json()["id"]
                print("release exists:", resp2.json().get("html_url"))
                break
        print("create failed:", resp.status_code, str(resp.json())[:200])
        time.sleep(20)
    if not release_id:
        print("RELEASE_FAILED")
        sys.exit(1)

    asset_name = Path(asset_path).name.encode("ascii", "ignore").decode() or "app.exe"
    existing = session.get(API + "/releases/" + str(release_id) + "/assets",
                           headers=headers(token), timeout=30).json()
    if any(a["name"] == asset_name for a in existing):
        print("asset already uploaded:", asset_name)
        return
    for attempt in range(6):
        data = Path(asset_path).read_bytes()
        resp = session.post(
            UPLOAD + "/releases/{}/assets".format(release_id),
            params={"name": asset_name}, headers={**headers(token), "Content-Type": "application/octet-stream"},
            data=data, timeout=600)
        if resp.status_code == 201:
            print("asset uploaded:", asset_name, resp.json()["browser_download_url"])
            return
        print("upload failed:", resp.status_code, str(resp.content)[:200])
        time.sleep(20)
    print("ASSET_FAILED")
    sys.exit(1)


if __name__ == "__main__":
    main()
