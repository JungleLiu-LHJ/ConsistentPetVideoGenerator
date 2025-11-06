 # 宠物长视频生成器（Pet Video Generator / PVGen）

 用 LangGraph 编排的 AI 视频流水线：从宠物参考照片 + 文本故事，生成 30 秒以上、跨镜头一致性强的长视频。

 PVGen 是一个基于 LangGraph 的节点式智能体（node-based agent）。它接收一张或多张宠物参考图与故事提示词，输出时长 30 秒以上的奇幻风格视频；通过“风格手册（style bible）+ 分镜（storyboard）+ 镜头图（shot graph）”等环节，尽量保证角色形象、画面风格与场景在多个镜头之间保持一致。项目内置可重复的本地 Mock 客户端，支持在无外网环境下端到端运行；同时预留了对 Qwen‑VL、DeepSeek（OpenAI 兼容）与火山引擎即梦等真实服务的对接。

 如果需要英文说明，请查看 `README.md`。

 ## 亮点与优势

 - 长时一致性：通过“风格手册 + 分镜 + 关键帧/镜头引导”控制角色与风格在不同镜头和更长时长下保持一致。
 - LangGraph 编排：以显式 DAG 执行节点，支持重试、分支与并行，便于观察与调试，更易稳定产出更长视频。
 - Mock 优先，随时切换真机：默认使用可复现的本地 Mock，无需网络即可全流程验证；一键关停 Mock 切换至真实 API。
 - 可追溯与可复现：所有步骤的提示词、响应与产物写入 `runs/`，媒体缓存集中在 `assets/`，便于复盘与复现。
 - 易于扩展的服务封装：支持 Qwen‑VL（感知/理解）、DeepSeek/OpenAI 兼容（推理/提示生成）、即梦（视频合成）；也可按统一接口接入自研或其他厂商。
 - 简洁 CLI 与单元测试：命令行一条指令生成视频；测试用例覆盖 Mock 模式下的关键逻辑。

 ## 环境准备

 - Python 3.10 或更高（3.9 不支持本项目使用的 `dataclasses` slots）
 - macOS 或 Linux 的 `bash` 终端
 - 如需调用真实服务，安装可选依赖：`langgraph`、`langchain-core`、`dashscope`（Qwen‑VL）、`openai`（DeepSeek 兼容）、`volcengine-python-sdk`、`requests`

 快速开始：

 ```bash
 python3 -m venv .venv
 source .venv/bin/activate
 pip install langgraph langchain-core dashscope openai volcengine-python-sdk requests
 ```

 ## 运行方式

 命令行入口：

 ```bash
 python run.py "让宠物在魔法森林完成奇幻冒险" /path/to/pet1.png [/path/to/pet2.png ...] --duration 30 --fps 24
 ```

 ### 执行模式

 - Mock 模式（默认）：当 `PVGEN_ENABLE_MOCKS=true`（默认）时，流水线使用本地 Mock 客户端生成 `.txt` 等占位产物，不发起任何外部网络请求。
 - 在线模式：设置 `PVGEN_ENABLE_MOCKS=false` 并提供各上游服务的密钥：

   ```bash
   export PVGEN_ENABLE_MOCKS=false
   export QWEN_API_KEY=...
   export DEEPSEEK_API_KEY=...
   export JIMENG_API_KEY=...        # 可使用 AK:SK 或分别设置 JIMENG_API_SECRET
   python run.py "prompt" /path/image.png
   ```

 运行期间，各节点会将精简 JSON 快照打印到标准输出，并将提示词/响应记录写入 `runs/<run_id>/`。生成的媒体缓存到 `assets/`，最终清单/报告在 `outputs/` 下。

 在启用 LangGraph 时，节点按图执行，具备更好的稳定性与可观测性，更利于生成更长且一致性更好的视频；若环境未安装 LangGraph，流水线会回退到顺序执行。

 ## 测试

 ```bash
 python -m unittest discover -s tests
 ```

 若出现 `TypeError: dataclass() got an unexpected keyword argument 'slots'`，请升级到 Python 3.10 及以上版本。

 ## 项目结构

 - `run.py` – CLI 入口
 - `pvgen/pipeline.py` – 编排器：优先构建 LangGraph 图，缺失时回退顺序执行
 - `pvgen/nodes/` – 各步骤（素材导入、宠物描述、风格手册、分镜、关键帧、视频生成、质检、拼接、报告）
 - `pvgen/services/` – Qwen、DeepSeek、即梦等服务客户端（带 Mock）
 - `pvgen/utils/` – 通用工具（提示词、日志、文件 IO）
 - `tests/` – 基于 Mock 的回归测试
 - `flow.md`、`agent.md` – 设计与流程文档

 ## 在线 API 清单

 1. 收集密钥：Qwen‑VL（`QWEN_API_KEY`）、DeepSeek（`DEEPSEEK_API_KEY`）、即梦（`JIMENG_API_KEY` 与可选 `JIMENG_API_SECRET`）。
 2. 安装“环境准备”中的可选依赖。
 3. 如需自定义缓存目录，设置 `PVGEN_ASSETS_DIR` / `PVGEN_RUNS_DIR`。
 4. 设置 `PVGEN_ENABLE_MOCKS=false` 并执行 `python run.py`。
 5. 查看 `outputs/<run_id>-final.txt` 获取最终清单，并在 `assets/` 查看生成媒体。

 以上步骤支持先在本地以 Mock 模式开发验证，准备好密钥与网络后再切换到真实服务。

