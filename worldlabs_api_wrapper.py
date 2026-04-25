#!/usr/bin/env python3
"""World Labs API 封装。

功能：
- 用图片 URL 生成世界模型
- 用本地图片生成世界模型（prepare upload + PUT 上传）
- 轮询 operation 直到生成完成
- 返回世界链接（world_marble_url）

示例：
  # 在后端代码里直接函数调用：
  from worldlabs_api_wrapper import generate_world_from_one_image
  result = generate_world_from_one_image(
      api_key="YOUR_WLT_API_KEY",
      image_file="./input_picture/test.jpg",
      display_name="Demo",
  )
  print(result["world_marble_url"])

  # 也支持命令行：
  python3 worldlabs_api_wrapper.py --api-key YOUR_WLT_API_KEY --image-url https://example.com/a.jpg
  python3 worldlabs_api_wrapper.py --image-file ./input_picture/test.jpg --text-prompt "cozy interior"
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.exceptions import RequestException


DEFAULT_BASE_URL = "https://api.worldlabs.ai/marble/v1"
DEFAULT_MODEL = "marble-1.0-draft"


class WorldLabsError(RuntimeError):
    """World Labs API 请求异常。"""


@dataclass
class OperationResult:
    """轮询结束后的标准化结果。"""
    operation_id: str
    done: bool
    world_id: Optional[str]
    world_url: Optional[str]
    raw: Dict[str, Any]


class WorldLabsClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
        use_env_proxy: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        # 默认忽略系统 HTTP(S)_PROXY，避免本地代理把 API 请求截断。
        self.session.trust_env = use_env_proxy
        self.session.headers.update({"WLT-Api-Key": self.api_key})

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _raise_for_status(self, response: requests.Response) -> None:
        if response.ok:
            return
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise WorldLabsError(f"HTTP {response.status_code}: {body}")

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self.session.post(
                self._url(path),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except RequestException as exc:
            raise WorldLabsError(f"Request failed for {path}: {exc}") from exc
        self._raise_for_status(resp)
        return resp.json()

    def _post_json_try_paths(self, paths: list[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for path in paths:
            try:
                return self._post_json(path, payload)
            except Exception as exc:
                last_error = exc
        raise WorldLabsError(f"All candidate endpoints failed: {paths}. Last error: {last_error}")

    def _log(self, message: str, verbose: bool) -> None:
        """按需输出调试日志。"""
        if verbose:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[WorldLabs {now}] {message}", flush=True)

    def generate_world(
        self,
        *,
        display_name: str,
        model: str,
        image_uri: Optional[str] = None,
        media_asset_id: Optional[str] = None,
        text_prompt: Optional[str] = None,
    ) -> str:
        """创建世界生成任务，返回 operation_id。"""
        if bool(image_uri) == bool(media_asset_id):
            raise ValueError("Provide exactly one of image_uri or media_asset_id")

        image_prompt: Dict[str, Any]
        if image_uri:
            image_prompt = {"source": "uri", "uri": image_uri}
        else:
            image_prompt = {"source": "media_asset", "media_asset_id": media_asset_id}

        world_prompt: Dict[str, Any] = {
            "type": "image",
            "image_prompt": image_prompt,
        }
        if text_prompt:
            world_prompt["text_prompt"] = text_prompt

        payload = {
            "display_name": display_name,
            "model": model,
            "permission": {
                "public": True,
                "allow_id_access": True,
                "allowed_readers": [],
                "allowed_writers": [],
            },
            "world_prompt": world_prompt,
        }

        data = self._post_json("worlds:generate", payload)
        operation_id = data.get("operation_id")
        if not operation_id:
            raise WorldLabsError(f"Missing operation_id in response: {data}")
        return operation_id

    def prepare_upload(self, filename: str, content_type: str, content_length: int) -> Dict[str, Any]:
        """创建上传会话信息。

        返回里通常包含：
        - media_asset：素材对象，里面通常有 media_asset_id
        - upload_info：上传信息，里面通常有 upload_url 和 required_headers
        """
        extension = Path(filename).suffix.lstrip(".").lower() or None
        kind = "image" if content_type.startswith("image/") else "video"
        payload = {
            "file_name": filename,
            "kind": kind,
            "extension": extension,
        }
        return self._post_json("media-assets:prepare_upload", payload)

    def upload_file(
        self,
        upload_url: str,
        file_path: Path,
        content_type: str,
        required_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """把本地文件字节流上传到预签名 upload_url。"""
        headers = {"Content-Type": content_type}
        if required_headers:
            headers.update(required_headers)
        with file_path.open("rb") as f:
            try:
                resp = requests.put(
                    upload_url,
                    data=f,
                    headers=headers,
                    timeout=self.timeout,
                    proxies={},
                )
            except RequestException as exc:
                raise WorldLabsError(f"Upload request failed: {exc}") from exc
        if not resp.ok:
            raise WorldLabsError(f"Upload failed: HTTP {resp.status_code} {resp.text}")

    def get_operation(self, operation_id: str) -> Dict[str, Any]:
        """获取 operation 原始 JSON（包含 done/error/response 等字段）。"""
        try:
            resp = self.session.get(self._url(f"operations/{operation_id}"), timeout=self.timeout)
        except RequestException as exc:
            raise WorldLabsError(f"Get operation failed: {exc}") from exc
        self._raise_for_status(resp)
        return resp.json()

    def get_world(self, world_id: str) -> Dict[str, Any]:
        """获取 world 原始 JSON（可能包含 world_marble_url 等字段）。"""
        try:
            resp = self.session.get(self._url(f"worlds/{world_id}"), timeout=self.timeout)
        except RequestException as exc:
            raise WorldLabsError(f"Get world failed: {exc}") from exc
        self._raise_for_status(resp)
        return resp.json()

    def wait_for_operation(
        self,
        operation_id: str,
        *,
        timeout_seconds: int = 600,
        poll_interval_seconds: int = 5,
        verbose: bool = False,
    ) -> OperationResult:
        """轮询 operation 直到完成，返回标准化 OperationResult。"""
        deadline = time.time() + timeout_seconds
        attempt = 0
        self._log(f"开始轮询 operation_id={operation_id}", verbose)

        while time.time() < deadline:
            attempt += 1
            try:
                data = self.get_operation(operation_id)
            except WorldLabsError as exc:
                self._log(f"第 {attempt} 次轮询请求失败: {exc}", verbose)
                time.sleep(poll_interval_seconds)
                continue
            status = data.get("status") or data.get("state") or data.get("phase") or "unknown"
            self._log(
                f"第 {attempt} 次轮询: done={data.get('done')} status={status}",
                verbose,
            )

            if data.get("done"):
                if data.get("error"):
                    raise WorldLabsError(f"Operation failed: {data['error']}")

                response = data.get("response") or {}
                world_id = response.get("world_id")
                world_url = response.get("world_marble_url")

                # 有些返回里不会立刻带最终 URL，这里可回查 world 补齐链接。
                if world_id and not world_url:
                    world_data = self.get_world(world_id)
                    world_url = world_data.get("world_marble_url")

                self._log(
                    f"生成完成: world_id={world_id} world_marble_url={world_url}",
                    verbose,
                )

                return OperationResult(
                    operation_id=operation_id,
                    done=True,
                    world_id=world_id,
                    world_url=world_url,
                    raw=data,
                )

            time.sleep(poll_interval_seconds)

        raise TimeoutError(
            f"Operation {operation_id} timed out after {timeout_seconds} seconds"
        )

    def generate_from_image_url(
        self,
        image_url: str,
        *,
        display_name: str = "Generated World",
        model: str = DEFAULT_MODEL,
        text_prompt: Optional[str] = None,
        timeout_seconds: int = 600,
        poll_interval_seconds: int = 5,
        verbose: bool = False,
    ) -> OperationResult:
        """从图片 URL 发起生成并返回最终 OperationResult。"""
        operation_id = self.generate_world(
            display_name=display_name,
            model=model,
            image_uri=image_url,
            text_prompt=text_prompt,
        )
        self._log(f"已创建生成任务 operation_id={operation_id}", verbose)
        return self.wait_for_operation(
            operation_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            verbose=verbose,
        )

    def generate_from_image_file(
        self,
        file_path: str | Path,
        *,
        display_name: str = "Generated World",
        model: str = DEFAULT_MODEL,
        text_prompt: Optional[str] = None,
        timeout_seconds: int = 600,
        poll_interval_seconds: int = 5,
        verbose: bool = False,
    ) -> OperationResult:
        """从本地图片发起生成并返回最终 OperationResult。"""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content_length = path.stat().st_size

        prep = self.prepare_upload(path.name, content_type, content_length)
        media_asset = prep.get("media_asset") or {}
        upload_info = prep.get("upload_info") or {}
        upload_url = upload_info.get("upload_url")
        required_headers = upload_info.get("required_headers") or {}
        media_asset_id = media_asset.get("media_asset_id") or media_asset.get("id")
        if not upload_url or not media_asset_id:
            raise WorldLabsError(f"Invalid prepare_upload response: {prep}")

        self._log(
            f"已准备上传素材 media_asset_id={media_asset_id} file={path.name}",
            verbose,
        )
        self.upload_file(upload_url, path, content_type, required_headers=required_headers)
        self._log("本地图片上传完成", verbose)

        operation_id = self.generate_world(
            display_name=display_name,
            model=model,
            media_asset_id=media_asset_id,
            text_prompt=text_prompt,
        )
        self._log(f"已创建生成任务 operation_id={operation_id}", verbose)
        return self.wait_for_operation(
            operation_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            verbose=verbose,
        )


def generate_world_from_one_image(
    *,
    api_key: str,
    image_url: Optional[str] = None,
    image_file: Optional[str] = None,
    display_name: str = "Generated World",
    model: str = DEFAULT_MODEL,
    text_prompt: Optional[str] = None,
    timeout_seconds: int = 600,
    poll_interval_seconds: int = 5,
    base_url: str = DEFAULT_BASE_URL,
    verbose: bool = False,
    use_env_proxy: bool = False,
) -> Dict[str, Any]:
    """后端最常用入口：单图生成世界模型。

    返回固定结构 dict：
    - operation_id (str)：生成任务 ID
    - world_id (str | None)：世界 ID（如果可用）
    - world_marble_url (str | None)：世界链接（前端可用于 iframe/跳转）
    - done (bool)：任务是否完成
    """
    if bool(image_url) == bool(image_file):
        raise ValueError("Provide exactly one of image_url or image_file")

    client = WorldLabsClient(
        api_key=api_key,
        base_url=base_url,
        use_env_proxy=use_env_proxy,
    )
    if image_url:
        result = client.generate_from_image_url(
            image_url,
            display_name=display_name,
            model=model,
            text_prompt=text_prompt,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            verbose=verbose,
        )
    else:
        result = client.generate_from_image_file(
            image_file,
            display_name=display_name,
            model=model,
            text_prompt=text_prompt,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            verbose=verbose,
        )

    # 这是建议直接返回给前端/上层接口的结果结构。
    return {
        "operation_id": result.operation_id,
        "world_id": result.world_id,
        "world_marble_url": result.world_url,
        "done": result.done,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a World Labs world from one image")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image-url", help="Publicly accessible image URL")
    source.add_argument("--image-file", help="Local image file path")

    parser.add_argument("--api-key", default=None, help="World Labs API key (or use WLT_API_KEY)")
    parser.add_argument("--display-name", default="Generated World", help="World display name")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name, default marble-1.0-draft")
    parser.add_argument("--text-prompt", default=None, help="Optional extra text prompt")
    parser.add_argument("--timeout", type=int, default=600, help="Max wait time in seconds")
    parser.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="World Labs API base URL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = args.api_key or os.getenv("WLT_API_KEY")
    if not api_key:
        print("Error: missing API key. Use --api-key or set WLT_API_KEY", file=sys.stderr)
        return 1

    try:
        output = generate_world_from_one_image(
            api_key=api_key,
            image_url=args.image_url,
            image_file=args.image_file,
            display_name=args.display_name,
            model=args.model,
            text_prompt=args.text_prompt,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
            base_url=args.base_url,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
