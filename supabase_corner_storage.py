#!/usr/bin/env python3
"""把 World Labs 结果写入 Supabase corner_projects 表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import requests


class SupabaseStorageError(RuntimeError):
    """Supabase 写入异常。"""


class SupabaseCornerStorage:
    """使用 Supabase REST API 往 corner_projects 表插入一条记录。"""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        table_name: str = "corner_projects",
        timeout: int = 60,
    ) -> None:
        if not supabase_url:
            raise ValueError("supabase_url is required")
        if not service_role_key:
            raise ValueError("service_role_key is required")

        self.supabase_url = supabase_url.rstrip("/")
        self.table_name = table_name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "apikey": service_role_key,
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            }
        )

    def insert_world_url(
        self,
        *,
        world_url: str,
        original_image_url: str,
        render_status: str = "success",
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """把 world_url 写入 word_model_url，同时补上表里的必填字段。"""
        payload = {
            "render_status": render_status,
            "original_image_url": original_image_url,
            "word_model_url": world_url,
        }
        if error_message:
            payload["error_message"] = error_message

        response = self.session.post(
            f"{self.supabase_url}/rest/v1/{self.table_name}",
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            raise SupabaseStorageError(
                f"Insert failed: HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        if isinstance(data, list):
            return data[0] if data else {}
        return data


def build_original_image_url(image_url: str = "", image_file: str = "") -> str:
    """为 original_image_url 生成一个稳定值。"""
    if image_url:
        return image_url
    if image_file:
        return Path(image_file).resolve().as_uri()
    raise ValueError("Either image_url or image_file is required")
