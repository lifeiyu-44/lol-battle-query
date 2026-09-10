# -*- coding: utf-8 -*-
"""发布 Release：创建 tag/release 并上传打包好的 exe（幂等，可重复执行）。

用法：python scripts/publish_release.py <tag> <asset_path> [title] [body_file]
凭据取自 git credential manager；直连与系统代理自动回退（本机代理时有时无）。
"""
import json
import sys
import time
from pathlib import Path

import requests

REPO = "lifeiyu-44/lol-battle-query"
API = "https://api.github.com/repos/" + REPO
UPLOAD = "https://uploads.github.com/repos/" + REPO
PROXY = "http://127.0.0.1:12334"  # 本机 VPN/代理端口，直连失败时自动切换


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


def api_request(token, method, url, max_rounds=2, **kwargs):
    """直连与代理各试一轮；返回最终 response。"""
    last = None
    extra_headers = {**headers(token), **kwargs.pop("headers", {})}
    for use_proxy in (False, True) if max_rounds else ():
        session = requests.Session()
        session.trust_env = False
        if use_proxy:
            session.proxies = {"http": PROXY, "https": PROXY}
        try:
            last = session.request(method, url, headers=extra_headers,
                                   timeout=(10, 600) if method == "POST" else 30, **kwargs)
            return last
        except requests.RequestException as e:
            last = e
            print("  ({}) 直连失败，改走代理再试".format("proxy" if use_proxy else "direct")
                  if not use_proxy else "  (proxy) 也失败")
            time.sleep(2)
    if isinstance(last, Exception):
        raise last
    return last


def main():
    tag, asset_path = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else tag
    body = Path(sys.argv[4]).read_text(encoding="utf-8") if len(sys.argv) > 4 else ""
    token = fill_token()
    if not token:
        print("NO_TOKEN")
        sys.exit(1)

    release_id = None
    for attempt in range(6):
        resp = api_request(token, "POST", API + "/releases", json={
            "tag_name": tag, "target_commitish": "main", "name": title, "body": body,
            "draft": False, "prerelease": False})
        if resp.status_code == 201:
            release_id = resp.json()["id"]
            print("release created:", resp.json().get("html_url"))
            break
        if resp.status_code == 422:  # 已存在 → 找现有 release
            resp2 = api_request(token, "GET", API + "/releases/tags/" + tag)
            if resp2.status_code == 200:
                release_id = resp2.json()["id"]
                print("release exists:", resp2.json().get("html_url"))
                break
        print("create failed:", resp.status_code, str(resp.text)[:200])
        time.sleep(20)
    if not release_id:
        print("RELEASE_FAILED")
        sys.exit(1)

    asset_name = "lol-battle-query-{}.exe".format(tag)  # 附件名统一 ASCII，中文名留给 exe 本体
    existing = api_request(token, "GET", API + "/releases/{}/assets".format(release_id)).json()
    if any(a["name"] == asset_name for a in existing):
        print("asset already uploaded:", asset_name)
        return
    for attempt in range(6):
        resp = api_request(token, "POST",
                           UPLOAD + "/releases/{}/assets".format(release_id),
                           params={"name": asset_name},
                           headers={**headers(token), "Content-Type": "application/octet-stream"},
                           data=Path(asset_path).read_bytes())
        if resp.status_code == 201:
            print("asset uploaded:", asset_name, resp.json()["browser_download_url"])
            return
        print("upload failed:", resp.status_code, str(resp.content)[:200])
        time.sleep(20)
    print("ASSET_FAILED")
    sys.exit(1)


if __name__ == "__main__":
    main()
