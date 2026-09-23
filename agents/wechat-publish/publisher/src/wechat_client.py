"""微信公众号 API 客户端：access_token 缓存 + 三个核心接口。

接口分工（不可混淆）：
- media/uploadimg          上传正文内图片      → mmbiz.qpic.cn URL
- material/add_material    上传封面（永久素材） → thumb_media_id
- draft/add                写入草稿箱          → media_id
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.weixin.qq.com"
# token 提前刷新余量（秒），避免临界点失效
TOKEN_REFRESH_MARGIN = 300


class WeChatAPIError(Exception):
    """微信 API 调用失败（含 errcode/errmsg）。"""

    def __init__(self, errcode: int, errmsg: str, api: str = ""):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"[{api}] errcode={errcode} errmsg={errmsg}")


class WeChatClient:
    """微信公众号 API 客户端。

    access_token 缓存到本地文件（跨进程复用），避免每次调用都重新获取
    而触发频次限制（官方每日获取次数有配额）。
    """

    def __init__(self, appid: str, appsecret: str, cache_dir: Path | None = None):
        self.appid = appid
        self.appsecret = appsecret
        self._cache_file = (cache_dir or Path.home() / ".aipyapp" / "wechat-publisher") / f"token_{appid}.json"
        self._token: str | None = None
        self._token_expire_at: float = 0
        # 磁盘缓存每进程只读一次：避免 token 失效后内存置空、又被磁盘旧值读回
        self._cache_loaded: bool = False
        self._session = requests.Session()

    # ---------- access_token ----------

    def _load_cached_token(self) -> None:
        # 磁盘缓存每进程只读一次：token 失效后内存置空时，不再从磁盘读回旧值
        if self._cache_loaded:
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            self._token = data["token"]
            self._token_expire_at = data["expire_at"]
        except Exception:
            self._token = None
            self._token_expire_at = 0
        finally:
            self._cache_loaded = True

    def _save_cached_token(self, expires_in: int) -> None:
        self._token_expire_at = time.time() + expires_in
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps({"token": self._token, "expire_at": self._token_expire_at}),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("token 缓存写入失败（不影响运行）: %s", e)
            return
        # 缓存文件含 access_token，收紧权限为仅属主可读写
        with contextlib.suppress(OSError):
            os.chmod(self._cache_file, 0o600)

    def get_access_token(self) -> str:
        """获取有效 access_token；优先用缓存，过期前 TOKEN_REFRESH_MARGIN 秒强制刷新。"""
        if self._token is None:
            self._load_cached_token()
        if self._token and time.time() < self._token_expire_at - TOKEN_REFRESH_MARGIN:
            return self._token

        resp = self._session.get(
            f"{API_BASE}/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.appid,
                "secret": self.appsecret,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" not in data:
            # 40001=secret错误 40164=IP不在白名单 45009=频率超限
            raise WeChatAPIError(data.get("errcode", -1), data.get("errmsg", "unknown"), "cgi-bin/token")
        self._token = data["access_token"]
        self._save_cached_token(data.get("expires_in", 7200))
        return self._token

    def _post(self, api_path: str, **kwargs) -> dict:
        """带 access_token 的 POST 请求；token 失效自动重取一次。

        注意：微信 API 要求请求体为 UTF-8 JSON（中文原样传输）。
        requests 的 json= 参数默认 ensure_ascii=True，会把中文转成 \\uXXXX，
        导致草稿箱显示 unicode 乱码——因此手动 dumps(ensure_ascii=False) 后以 data= 发送。
        """
        if "json" in kwargs:
            payload = json.dumps(kwargs.pop("json"), ensure_ascii=False).encode("utf-8")
            headers = kwargs.pop("headers", {})
            headers["Content-Type"] = "application/json; charset=utf-8"
            kwargs["data"] = payload
            kwargs["headers"] = headers
        for attempt in (1, 2):
            token = self.get_access_token()
            kwargs.setdefault("params", {})
            kwargs["params"]["access_token"] = token
            resp = self._session.post(f"{API_BASE}{api_path}", timeout=60, **kwargs)
            data = resp.json()
            errcode = data.get("errcode", 0)
            # 40001/42001 = token 无效或过期 → 重取一次
            if errcode in (40001, 42001) and attempt == 1:
                self._token = None
                self._token_expire_at = 0
                # 同时删除磁盘缓存：否则 get_access_token() 会重新读回同一个失效 token
                # （常见于后台重置 AppSecret 后，旧 token 已永久失效）
                try:
                    self._cache_file.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning("token 缓存删除失败（不影响运行）: %s", e)
                continue
            if errcode != 0:
                raise WeChatAPIError(errcode, data.get("errmsg", "unknown"), api_path)
            return data
        raise WeChatAPIError(-1, "unreachable", api_path)

    # ---------- 三个核心接口 ----------

    def upload_content_image(self, image_path: Path) -> str:
        """上传正文内图片（uploadimg），返回 mmbiz.qpic.cn URL。

        限制：10MB 以内，jpg/png。
        """
        with image_path.open("rb") as f:
            data = self._post(
                "/cgi-bin/media/uploadimg",
                files={"media": (image_path.name, f, "application/octet-stream")},
            )
        return data["url"]

    def upload_cover(self, image_path: Path) -> str:
        """上传封面为永久素材（add_material type=image），返回 thumb_media_id。"""
        with image_path.open("rb") as f:
            data = self._post(
                "/cgi-bin/material/add_material",
                params={"type": "image"},
                files={"media": (image_path.name, f, "application/octet-stream")},
            )
        return data["media_id"]

    def add_draft(self, articles: list[dict]) -> str:
        """新增草稿（draft/add），返回草稿 media_id。

        articles 中每篇须含：title、content（HTML）、thumb_media_id；
        可选：author（≤16字）、digest（≤120字）。
        """
        data = self._post("/cgi-bin/draft/add", json={"articles": articles})
        return data["media_id"]
