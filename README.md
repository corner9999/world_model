# Picture2Picture

这个目录里已经有一套最小可用的 World Labs 生成链路，支持：

- 输入一张图片生成 World Labs 世界模型
- 拿到 `world_marble_url`
- 把结果写入 Supabase 的 `corner_projects` 表

## 现有文件

- [worldlabs_api_wrapper.py](/Users/jan/Desktop/Picture2Picture/worldlabs_api_wrapper.py)
  World Labs API 封装。核心函数是 `generate_world_from_one_image(...)`

- [supabase_corner_storage.py](/Users/jan/Desktop/Picture2Picture/supabase_corner_storage.py)
  Supabase 写库封装。核心函数是 `SupabaseCornerStorage.insert_world_url(...)`

- [test_worldlabs_simple.py](/Users/jan/Desktop/Picture2Picture/test_worldlabs_simple.py)
  只测试 World Labs 生成，不写数据库

- [test_worldlabs_to_supabase.py](/Users/jan/Desktop/Picture2Picture/test_worldlabs_to_supabase.py)
  一键测试：生成世界模型 + 写入 Supabase

## 先跑哪个脚本

如果只想测试 World Labs 是否能生成 world URL：

```bash
python3 /Users/jan/Desktop/Picture2Picture/test_worldlabs_simple.py
```

如果想测试完整链路，生成后直接写入 Supabase：

```bash
python3 /Users/jan/Desktop/Picture2Picture/test_worldlabs_to_supabase.py
```

## 当前数据库写入方式

Supabase 表名：

```text
corner_projects
```

当前脚本把世界模型链接写进：

```text
word_model_url
```

同时还会补最少的必填字段：

- `render_status`
- `original_image_url`
- `word_model_url`

如果生成失败，也会插入一条失败记录，并把错误写进：

```text
error_message
```

## 后端核心函数

### 1. 生成世界模型

文件：
[worldlabs_api_wrapper.py](/Users/jan/Desktop/Picture2Picture/worldlabs_api_wrapper.py)

核心函数：

```python
generate_world_from_one_image(...)
```

最常用写法：

```python
from worldlabs_api_wrapper import generate_world_from_one_image

result = generate_world_from_one_image(
    api_key="YOUR_WLT_API_KEY",
    image_file="/absolute/path/to/image.png",
    display_name="Simple Test World",
    text_prompt=None,
    verbose=True,
    use_env_proxy=False,
)
```

当前默认模型是：

```text
marble-1.0-draft
```

返回值结构：

```python
{
    "operation_id": "...",
    "world_id": "...",
    "world_marble_url": "https://marble.worldlabs.ai/world/...",
    "done": True,
}
```

前端最关心的是：

```python
result["world_marble_url"]
```

### 2. 存数据库

文件：
[supabase_corner_storage.py](/Users/jan/Desktop/Picture2Picture/supabase_corner_storage.py)

核心类和方法：

```python
storage = SupabaseCornerStorage(
    supabase_url="https://xxx.supabase.co",
    service_role_key="YOUR_SERVICE_ROLE_KEY",
    table_name="corner_projects",
)

row = storage.insert_world_url(
    world_url="https://marble.worldlabs.ai/world/...",
    original_image_url="file:///.../room.png",
    render_status="success",
)
```

## 前端应该怎么调用

前端不要直接调用 World Labs，也不要直接拿 `service_role key` 连 Supabase。

推荐做法是：

1. 前端把图片传给你自己的后端接口
2. 后端调用 `generate_world_from_one_image(...)`
3. 后端调用 `insert_world_url(...)`
4. 后端把结果返回给前端

也就是说，前端真正应该调的是你自己的后端 API，不是这两个 Python 文件本身。

## 推荐后端接口

建议后端对前端暴露一个接口，例如：

```text
POST /api/worlds/create
```

请求体示例：

```json
{
  "image_url": "https://example.com/test.png"
}
```

或者后端支持文件上传：

```text
multipart/form-data
file=<image>
```

后端内部逻辑建议这样写：

```python
from supabase_corner_storage import SupabaseCornerStorage, build_original_image_url
from worldlabs_api_wrapper import generate_world_from_one_image


def create_world_and_save(image_file: str = "", image_url: str = "") -> dict:
    world_result = generate_world_from_one_image(
        api_key="YOUR_WLT_API_KEY",
        image_file=image_file or None,
        image_url=image_url or None,
        display_name="Frontend Request",
        verbose=True,
        use_env_proxy=False,
    )

    storage = SupabaseCornerStorage(
        supabase_url="https://your-project.supabase.co",
        service_role_key="YOUR_SERVICE_ROLE_KEY",
        table_name="corner_projects",
    )

    row = storage.insert_world_url(
        world_url=world_result["world_marble_url"],
        original_image_url=build_original_image_url(
            image_url=image_url,
            image_file=image_file,
        ),
        render_status="success",
    )

    return {
        "success": True,
        "operation_id": world_result["operation_id"],
        "world_id": world_result["world_id"],
        "world_marble_url": world_result["world_marble_url"],
        "db_row": row,
    }
```

## 建议返回给前端的数据

建议你的后端接口最终返回：

```json
{
  "success": true,
  "operation_id": "xxx",
  "world_id": "xxx",
  "world_marble_url": "https://marble.worldlabs.ai/world/xxx"
}
```

前端拿到后：

- 如果 World Labs 页面允许嵌入，可以用 `iframe` 展示
- 如果不能嵌入，就用新标签页打开 `world_marble_url`

前端最简单示例：

```js
const res = await fetch("/api/worlds/create", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    image_url: "https://example.com/test.png",
  }),
});

const data = await res.json();
const worldUrl = data.world_marble_url;
```

然后展示：

```html
<iframe
  src={worldUrl}
  style={{ width: "100%", height: "80vh", border: 0 }}
/>
```

如果打不开，通常是 world 权限或站点嵌入限制问题，这时改成：

```js
window.open(worldUrl, "_blank");
```

## 注意事项

- `WORLDLABS_API_KEY` 只能放后端
- `SUPABASE_SERVICE_ROLE_KEY` 只能放后端
- 前端不要直接调用 Supabase `service_role key`
- 当前脚本默认生成的是公开 world，便于链接访问
- 如果你的本机有代理问题，保持 `use_env_proxy=False`

## 当前最适合联调的入口

如果只是本地验证完整链路，直接跑：

```bash
python3 /Users/jan/Desktop/Picture2Picture/test_worldlabs_to_supabase.py
```

如果是给前端正式联调，建议下一步新增一个真正的后端接口文件，例如：

```text
/Users/jan/Desktop/Picture2Picture/backend/app.py
```

然后在里面封装 `POST /api/worlds/create`。
