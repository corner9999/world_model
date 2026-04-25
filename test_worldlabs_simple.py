#!/usr/bin/env python3
"""非常简单的本地测试脚本：单图生成世界并打印结果。"""

from worldlabs_api_wrapper import generate_world_from_one_image


# ====== 这里改成你的参数 ======
API_KEY = "2UPzwfxx0Hdh3bV0TSb3XIK9G9XxLfAp"
IMAGE_FILE = "/Users/jan/Desktop/Picture2Picture/input_picture/room.png"  # 例如: "/Users/jan/Desktop/Picture2Picture/input_picture/test.jpg"
IMAGE_URL = ""   # 例如: "https://example.com/test.jpg"
DISPLAY_NAME = "Simple Test World"
TEXT_PROMPT = None
VERBOSE = True
USE_ENV_PROXY = False
# ===========================


def main() -> None:
    result = generate_world_from_one_image(
        api_key=API_KEY,
        image_file=IMAGE_FILE or None,
        image_url=IMAGE_URL or None,
        display_name=DISPLAY_NAME,
        text_prompt=TEXT_PROMPT,
        verbose=VERBOSE,
        use_env_proxy=USE_ENV_PROXY,
    )

    print("生成完成，返回结果：")
    print(result)
    print("world_marble_url =", result.get("world_marble_url"))


if __name__ == "__main__":
    main()
