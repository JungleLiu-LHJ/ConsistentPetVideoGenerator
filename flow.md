# 视频生成流程设计 V2

这是一个宠物视频生成 agent，为你的爱宠生成一段长为 30s 的一致性奇幻的视频。

## 总览

* **框架：LangChain / LangGraph（状态机+有向图）**
* **图生文：Qwen-VL（宠物细节描述）**
* **文生文：DeepSeek（分镜脚本）**
* **文/图生图：火山引擎即梦 API（Keyframe 首尾帧）**
* **视频生成：即梦 API（I2V / img→video）**
* **统一一致性策略：角色与风格圣经、end_anchor、相邻段落“尾帧=下一段首帧”**

注意（资产与缓存策略）：

- 对外调用（上传/提交）统一使用 base64 图片；
- 流程内部统一使用 `asset_id + 本地缓存文件路径`（不使用 URL）。`asset_id = sha256(base64)`，缓存在本项目目录：`assets/<asset_id>.<ext>`；
- 节点之间传递图片时仅传 `asset_id`（必要时带 `local_path` 与尺寸信息）；
- 仅在对外接口需要时才携带 base64，避免中间产物过大与重复传输。

---

## T0 输入与设定

**Input**：origin_prompt + 宠物照片（期望成片时长≈30s，n≤4，每段≤8s）

> **备注：主色建议用简单的颜色聚类（本地ColorThief或k-means）提取出 2~4 个 HEX，Qwen可再润色命名（如“暖金#D6A85E”）。**

---

## T1 叙事生成（更强约束+校验）

**T1.1 宠物细节描述（图生文，Qwen-VL）**
输出 `description`（包含：品种、花色 HEX、体态、神态、显著特征、可反复出现的“标记物”如红色小围巾）。

**T1.2 生成风格（StyleBible，自然语言）**

输入：`description`+origin_prompt，输出 `style_bible`（自然语言，不使用 JSON）。

`style_bible`（风格圣经草案，自然语言段落），建议包含下列小节：

* 角色名（可选）、性格标签
* 颜色主副色（HEX）、花纹/毛量/体型/表情关键词
* 画风（如手绘/写实/赛博复古/皮克斯质感等）、镜头语言（dolly/pan/low-angle）
* 背景设定与道具（地形/天气/光照/辅色调）

**T1.3 分镜脚本（深度约束，DeepSeek 文生文）**
输入：`origin_prompt + description + style_bible`
输出：`storyboard`（n 段，n≤4；每段≤8s），每段包括：

* `style`: 画风&镜头基调（**首段视觉定调宜“中性稳态”**，小幅镜头运动，方便后段夸张升级）
* `shot`: 场景/动作描述（**剧情有趣优先**）
* `camera`: 景别、运动（pan/dolly/tilt）、构图要点
* `props_bg`: 必须持续出现的道具/背景元素
* `end_anchor`: **段末姿态锚点**（姿态/朝向/表情/手脚位置、关键道具位置），用于造尾帧
* `duration_sec`: ≤8
* `consistency_flags`: 必须保持的身份/配饰/纹理/色调标记

---

## T2 关键帧生成（一致性核心）

### T2.1生成一张宠物形象图片

得到一个宠物的形象，为了后面保证一致性

Input: `style_bible`+`description`+origin_prompt+原始宠物照片

调用：即梦 图生图

output: 一张风格化以后得宠物图片 `pet_style_Image`

### T2.2 生成一些keyframes

**目标**：得到 n+1 张图像 `image1..image{n+1}`，满足：

* `image1,image2` 作为 s1 的首尾；`image2,image3` 作为 s2 的首尾… 以此类推。
* 循环调用，每次生成一张图。

输入：`description + style_bible + s_i + (optional) pose/face references`+ `pet_style_Image`
调用：即梦 图生图
输出：`KeyframeResult`（见数据契约），包含 `asset_id` 与本地 `local_path`。

---

## T3 段视频生成（I2V，尾帧对齐）

对每段 `s_i`：

* Prompt：`description + s_i.shot + s_i.camera + style_bible（精简）`
* 约束：`first_frame = image_i`，`last_frame = image_{i+1}`（以 `asset_id` 指定）
* 参数：`duration = s_i.duration_sec`，`fps = global_fps（默认 24）`

---

## T4 拼接导出（你原 T2+n）

* 严格统一：`fps/分辨率/比特率`
* 段间过渡：优先每段尾帧=下段首帧的硬切；不完美时用极短交叉溶解

---

# LangGraph 结点拓扑（可直接落地）

**Nodes**

1. `IngestAssets` → 生成 `asset_hash`、基础设定
2. `BuildStyleBible`（LLM）
3. `DescribePet`（Qwen-VL）
4. `DraftStoryboard`（DeepSeek）
5. `ValidateStoryboard`（LLM 规则器：长度/锚点/连贯性）
6. `PlanSegments`（组装 `segments` 与 `consistency_ledger`）
7. `GenKeyframe`（for i in 1..n+1; 即梦 文/图生图；带候选与打分）
8. `PickKeyframe`（自动筛选与回退）
9. `GenVideoSegment`（for each s_i; 即梦 I2V）
10. `QCVideoSegment`（一致性与首尾对齐检查，必要时重试）
11. `AssembleVideo`（拼接导出）
12. `Report`（产出指标与调试日志）

---

# 数据契约（JSON Schema 草案 + 自然语言模板）

**StyleBible（自然语言模板）**

以自然语言分段描述，建议包含：角色与性格；主副色及光照；画风与镜头语言；背景设定与关键道具；负面约束（不希望出现的元素）。

**Segment**

```
{
  "id": 1,
  "duration_sec": 7,
  "style": "whimsical fantasy",
  "shot": "宠物在草原跃起…与会发光的蒲公英互动…",
  "camera": "medium shot, slow dolly-in",
  "props_bg": ["红色小围巾","远处雪山","黄昏侧光"],
  "end_anchor": {
    "pose": "前腿抬起向右，耳朵上扬",
    "facing": "右前方三分之一",
    "expression": "兴奋微笑",
    "prop_state": "围巾向后飘",
    "position_hint_norm": {"x": 0.33, "y": 0.33}
  },
  "consistency_flags": ["围巾必须可见","毛色黄金偏暖","草浪方向一致"]
}
```

---

# JSON Schema（机器可读）

**Asset**

```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Asset",
  "type": "object",
  "required": ["asset_id", "media_type", "local_path"],
  "properties": {
    "asset_id": {"type": "string", "description": "sha256(base64)"},
    "media_type": {"type": "string", "enum": ["image", "video"]},
    "local_path": {"type": "string"},
    "width": {"type": "integer", "minimum": 1},
    "height": {"type": "integer", "minimum": 1},
    "ext": {"type": "string"},
    "sha256": {"type": "string"}
  }
}
```

**Segment (Schema)**

```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Segment",
  "type": "object",
  "required": ["id", "duration_sec", "shot", "camera", "props_bg", "end_anchor"],
  "properties": {
    "id": {"type": "integer", "minimum": 1},
    "duration_sec": {"type": "number", "minimum": 0.5, "maximum": 8},
    "style": {"type": "string"},
    "shot": {"type": "string"},
    "camera": {"type": "string"},
    "props_bg": {"type": "array", "items": {"type": "string"}},
    "end_anchor": {
      "type": "object",
      "required": ["pose", "facing", "expression"],
      "properties": {
        "pose": {"type": "string"},
        "facing": {"type": "string"},
        "expression": {"type": "string"},
        "prop_state": {"type": "string"},
        "position_hint_norm": {
          "type": "object",
          "required": ["x", "y"],
          "properties": {
            "x": {"type": "number", "minimum": 0, "maximum": 1},
            "y": {"type": "number", "minimum": 0, "maximum": 1}
          }
        }
      }
    },
    "consistency_flags": {"type": "array", "items": {"type": "string"}}
  }
}
```

**KeyframeResult**

```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "KeyframeResult",
  "type": "object",
  "required": ["index", "asset_id", "local_path"],
  "properties": {
    "index": {"type": "integer", "minimum": 1},
    "asset_id": {"type": "string"},
    "local_path": {"type": "string"},
    "scores": {
      "type": "object",
      "properties": {
        "aesthetic": {"type": "number", "minimum": 0, "maximum": 1},
        "identity": {"type": "number", "minimum": 0, "maximum": 1},
        "style": {"type": "number", "minimum": 0, "maximum": 1}
      }
    }
  }
}
```

**Report**

```
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Report",
  "type": "object",
  "properties": {
    "asset_hash": {"type": "string"},
    "global_fps": {"type": "integer"},
    "segments": {"type": "array"},
    "cost_estimate": {"type": "number"},
    "timings_ms": {"type": "object"}
  }
}
```

---

# 一致性与“有趣”两手抓的小技巧

1. **角色锚定**：始终带参考图 `asset_id`；若 API 有 **Face/ID / IP-Adapter/Ref Image**，全链路启用。
2. **姿态锚定**：`end_anchor` 尽量结构化（朝向/四肢/表情/道具位置）；尾帧用 pose/depth 条件生成。
3. **色调锁**：统一 `palette_hex + LUT`；跨段轻微胶片颗粒让画面“糊成一锅”。
4. **相邻传递**：尾帧 = 下一段首帧
5. **节奏设计**：首段稳态→中段夸张→末段情绪落点（上扬或反转），每段只“放大一个笑点/奇观”。
