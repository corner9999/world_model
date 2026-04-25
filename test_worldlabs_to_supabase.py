#!/usr/bin/env python3
"""简单测试：生成 World Labs world_url，并存到 Supabase corner_projects。"""

from __future__ import annotations

from supabase_corner_storage import (
    SupabaseCornerStorage,
    build_original_image_url,
)
from worldlabs_api_wrapper import generate_world_from_one_image


# ====== World Labs 配置 ======
WORLDLABS_API_KEY = "MgHj6nmvMCICkgVnj35gv3jYU3tBAttU"
IMAGE_FILE = "/Users/jan/Desktop/Picture2Picture/input_picture/room.png"
IMAGE_URL = ""
DISPLAY_NAME = "Simple Test World"
TEXT_PROMPT = None
WORLDLABS_VERBOSE = True
WORLDLABS_USE_ENV_PROXY = False

# ====== Supabase 配置 ======
SUPABASE_URL = "https://zxgmqrpxwpfzrtlqfvws.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp4Z21xcnB4d3BmenJ0bHFmdndzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NjQwMzk4OCwiZXhwIjoyMDkxOTc5OTg4fQ.QhvDkQNd0X9wPlgvgDksbQ2JdjoMfFkSu5QeOi47w9I"
TABLE_NAME = "corner_projects"
# ============================


def main() -> None:
    storage = SupabaseCornerStorage(
        supabase_url=SUPABASE_URL,
        service_role_key=SUPABASE_SERVICE_ROLE_KEY,
        table_name=TABLE_NAME,
    )
    original_image_url = build_original_image_url(
        image_url=IMAGE_URL,
        image_file=IMAGE_FILE,
    )

    try:
        world_result = generate_world_from_one_image(
            api_key=WORLDLABS_API_KEY,
            image_file=IMAGE_FILE or None,
            image_url=IMAGE_URL or None,
            display_name=DISPLAY_NAME,
            text_prompt=TEXT_PROMPT,
            verbose=WORLDLABS_VERBOSE,
            use_env_proxy=WORLDLABS_USE_ENV_PROXY,
        )
        world_url = world_result.get("world_marble_url") or ""
        if not world_url:
            raise RuntimeError(f"World Labs returned empty world_marble_url: {world_result}")

        row = storage.insert_world_url(
            world_url=world_url,
            original_image_url=original_image_url,
            render_status="success",
        )
        print("已成功写入 Supabase：")
        print(row)

    except Exception as exc:
        print("World Labs 主流程失败：", exc)
        try:
            row = storage.insert_world_url(
                world_url="",
                original_image_url=original_image_url,
                render_status="failed",
                error_message=str(exc),
            )
            print("失败信息已记录到 Supabase：")
            print(row)
        except Exception as db_exc:
            print("写入 Supabase 失败记录时又报错：", db_exc)
        raise


if __name__ == "__main__":
    main()
