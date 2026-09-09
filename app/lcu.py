# -*- coding: utf-8 -*-
"""LCU (League Client Update) 本地接口连接模块。

国服客户端与外服一样基于 LCU 架构：登录客户端后，LeagueClientUx 进程会在
本机开一个 HTTPS 服务，认证信息（端口 + token）写在该进程的命令行参数里。
"""
import base64
import re

import psutil
import requests
import urllib3

# 国服 LCU 使用自签证书，必须跳过校验
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UX_PROCESS_NAME = "leagueclientux.exe"


class LcuError(Exception):
    """连接/请求失败，message 可直接展示给用户。"""


class LcuClient:
    def __init__(self):
        self.port = None
        self.token = None
        self._session = requests.Session()

    # ---------- 连接 ----------

    @staticmethod
    def _find_ux_process():
        """从 LeagueClientUx 进程命令行解析端口与 token。"""
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name != UX_PROCESS_NAME:
                    continue
                cmdline = " ".join(proc.info.get("cmdline") or [])
                m_port = re.search(r"--app-port=(\d+)", cmdline)
                m_tok = re.search(r"--remoting-auth-token=([\w-]+)", cmdline)
                if m_port and m_tok:
                    return m_port.group(1), m_tok.group(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return None

    def connect(self):
        """尝试连接本机 LCU。成功返回当前召唤师信息，失败抛 LcuError。"""
        found = self._find_ux_process()
        if not found:
            raise LcuError(
                "未检测到英雄联盟客户端。请先通过 WeGame 启动并登录《英雄联盟》，"
                "登录到客户端大厅后，再回到本工具点击重试。"
            )
        self.port, self.token = found
        auth = base64.b64encode(("riot:" + self.token).encode()).decode()
        self._session.headers.update({"Authorization": "Basic " + auth})
        # 连通性验证：取当前登录召唤师
        code, data = self.request("GET", "/lol-summoner/v1/current-summoner")
        if code != 200 or not isinstance(data, dict) or not data.get("summonerId"):
            raise LcuError("已找到客户端，但尚未登录游戏账号，请先登录到客户端大厅。")
        return data

    @property
    def connected(self):
        return self.port is not None

    # ---------- 请求 ----------

    def request(self, method, path, params=None, body=None, timeout=15):
        url = "https://127.0.0.1:{port}{path}".format(port=self.port, path=path)
        try:
            resp = self._session.request(
                method, url, params=params, json=body, timeout=timeout, verify=False
            )
        except requests.exceptions.ConnectionError:
            self.port = None
            raise LcuError("与客户端的连接已断开（客户端可能被关闭），请重新连接。")
        except requests.exceptions.Timeout:
            raise LcuError("客户端接口响应超时，请稍后重试。")
        if resp.status_code == 404:
            return 404, None
        if resp.status_code in (401, 403):
            self.port = None
            raise LcuError("客户端认证失效，请点击重试重新连接。")
        if resp.status_code >= 400:
            return resp.status_code, None
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, None
