# PetVideoGenerator Agent 说明（根据 flow.md 整理）

目标：基于一到多张宠物图片与文字意图，生成约 30s 的一致性奇幻视频。本文档仅描述步骤、输入输出与每一步的 Prompt 模板；

结构：采用“可单步运行”的节点化流程。每个节点输入/输出均为 JSON，可单独执行与调试；运行时会记录每一步的 prompt 与返回到 `runs/<run_id>/` 目录中。

注意：流程内部统一通过 `asset_id`（sha256(base64)）标识图片或视频，并缓存于 `assets/`，节点间仅传递 `asset_id`（必要时附带 `local_path` 与尺寸信息）。

要求：代码简洁清晰，每个函数有相应的注释，注释要全面清晰，方便人看懂

本项目的流程在文件flow.md中

## 节点一览（LangGraph 拓扑映射）

1. IngestAssets → 生成 `asset_hash` 与基础设定
2. DescribePet（Qwen-VL）
3. BuildStyleBible（LLM）
4. DraftStoryboard（DeepSeek）
5. ValidateStoryboard（LLM 规则器）
6. PlanSegments（组装 `segments` 与 `consistency_ledger`）
7. GenKeyframe（即梦 文/图生图，逐张）
8. PickKeyframe（筛选与回退）
9. GenVideoSegment（即梦 I2V）
10. QCVideoSegment（一致性与首尾对齐检查）
11. AssembleVideo（拼接导出）
12. Report（产出指标与调试日志）

——

## 通用数据约定

- Asset: `{ asset_id, media_type: "image|video", local_path, width?, height?, ext? }`
- Segment: 参考 flow.md 的 JSON Schema（包含 `id, duration_sec, style, shot, camera, props_bg, end_anchor, consistency_flags`）
- KeyframeResult: `{ index, asset_id, local_path, scores? }`
- Report: `{ asset_hash, global_fps, segments, cost_estimate?, timings_ms? }`

——

## 运行与调试

- 可以单步运行
- 日志与留痕：所有步骤的 prompt 与返回，会写入 `runs/<run_id>/<step_name>-prompt.txt` 与 `runs/<run_id>/<step_name>-response.json`。
- 单元测试：`python -m unittest` 可针对每个步骤的最小输入进行快速回归（使用本地伪实现，不依赖外部 API）。

——

## 步骤与 Prompt 模板

以下为每个步骤的用途、输入输出说明与建议 Prompt 模板。模板中的变量以 `{{var}}` 表示。

### 1) IngestAssets

- 用途：导入用户素材，计算 `asset_id`，建立本地缓存映射。
- 输入：`{ images: ["path1",...], origin_prompt: "...", target_duration_sec?: 30, fps?: 24 }`
- 输出：`{ asset_hash, assets: [Asset], origin_prompt, target_duration_sec, fps }`
- Prompt：无（纯本地处理）。

### 2) DescribePet（Qwen-VL）

- 用途：对宠物进行细节描述（品种、花色 HEX、体态、神态、显著特征、可复用标记物）。
- 输入：`{ assets: [Asset], origin_prompt }`
- 输出：`{ description: "..." }`
- Prompt 模板（图生文）：

```
你将查看一只宠物的参考图像，并输出简洁但信息密度高的客观描述：
- 品种与体型；
- 主要/次要毛色与建议 HEX 调色（2~4 个）；
- 花纹与显著特征；
- 常驻配饰/标记物（如红色小围巾）；
- 常见表情与姿态关键词。
请使用详细要点式中文，不要输出 JSON
```

### 3) BuildStyleBible（LLM）

- 用途：根据宠物描述，生成自然语言风格圣经（角色、色彩、画风、镜头语言、背景与道具、负面约束）。
- 输入：`{ description }`
- 输出：`{ style_bible: "..." }`
- Prompt 模板：

```
基于以下宠物描述，为后续视觉生成撰写“风格圣经（style bible)”（自然语言分段，不要使用 JSON），需要传神眼眸、平滑赛璐珞上色、干净线稿。突出情绪张力与角色存在感，传递典型动画场景的动势氛围：
【宠物描述】
{{description}}

要求：
- 角色与性格标签；
- 主/副色（HEX）与光照倾向；
- 画风与镜头语言关键词；
- 背景设定与关键道具；
- 负面约束（避免出现的元素）。
```

### 4) DraftStoryboard（DeepSeek）

- 用途：结合意图、宠物描述与风格圣经，生成 1~4 段、每段≤8s 的分镜。
- 输入：`{ origin_prompt, description, style_bible, target_duration_sec }`
- 输出：`{ storyboard: [Segment-like (自然语言字段同 flow.md 定义)] }`
- Prompt 模板：

```
请基于“用户意图+宠物描述+风格圣经”生成分镜脚本，要求 1~4 段、每段≤8s。
首段视觉定调宜中性稳态（小幅镜头运动），以利后续夸张升级。
每段需包含：style, shot, camera, props_bg, end_anchor(结构化姿态/朝向/表情/道具位置), duration_sec, consistency_flags。
用户意图：{{origin_prompt}}
宠物描述：{{description}}
风格圣经：{{style_bible}}
总时长目标：{{target_duration_sec}} 秒
以紧凑中文输出，字段名中文或英文均可，但语义需清晰。用json格式输出，输出是json的数组，每一个element是一段
```

### 6) PlanSegments

- 用途：将通过校验的分镜转为标准 `segments[]` 与 `consistency_ledger`。
- 输入：`{ storyboard }`
- 输出：`{ segments: [Segment], consistency_ledger: { keys: [...] } }`
- Prompt：无（纯本地映射与整理）。

### 7) GenKeyframe（即梦 文/图生图）

- 用途：按段生成 n+1 张关键帧，使相邻段落尾帧=下一段首帧。
- 输入：`{ description, style_bible, segment_i, prev_image_asset_id? }`
- 输出：`{ keyframe: KeyframeResult }`
- Prompt 模板（文/图生图）：

```
根据下列条件生成关键帧：
- 画面风格与镜头基调：{{segment_style}}
- 场景/动作要点：{{segment_shot}}
- 镜头语言：{{segment_camera}}
- 必要道具/背景：{{segment_props_bg}}
- 姿态锚点（段末）：{{end_anchor}}
- 宠物描述（身份一致性）：{{description}}
- 风格圣经（精简版可）：{{style_bible_brief}}
若提供前一帧参考，请在构图与姿态上对齐其语义（prev_image）。
输出高一致性、可作为下一段起始的关键帧。
```

### 9) GenVideoSegment（即梦 I2V）

- 用途：基于首尾帧（asset_id 指定）生成每段视频片段。
- 输入：`{ segment, first_frame_asset_id, last_frame_asset_id, fps }`
- 输出：`{ video: Asset }`
- Prompt 模板：

```
生成视频片段，遵守：
- first_frame = {{first_frame_asset_id}}
- last_frame  = {{last_frame_asset_id}}
- duration = {{duration_sec}} s, fps = {{fps}}
段落内容：
- 场景/动作：{{segment_shot}}
- 镜头语言：{{segment_camera}}
- 风格基调：{{segment_style}}
- 一致性标记：{{consistency_flags}}
```


### 11) AssembleVideo

- 用途：统一 fps/分辨率/比特率，将各段按“尾帧=下一段首帧”顺序拼接。可以用ffmep进行拼接
- 输入：`{ videos: [Asset], fps, resolution?, bitrate? }`
- 输出：`{ final_video: Asset }`
- Prompt：无（本地处理）。

### 12) Report

- 用途：汇总运行指标与调试日志，输出报告。
- 输入：`{ ... }`
- 输出：`{ report: Report }`
- Prompt：无。

——

## 依赖与外部服务（对接预留）

- Qwen-VL：用于图生文（DescribePet）
- DeepSeek：用于文生文（DraftStoryboard）
- 即梦 API：文/图生图（GenKeyframe）、I2V（GenVideoSegment）

注：本仓库的默认实现以本地伪实现代替上述服务，便于单元测试与离线调试。对接真实服务时，仅需替换相应 Step 的调用逻辑，保留 I/O 契约与日志接口即可。
