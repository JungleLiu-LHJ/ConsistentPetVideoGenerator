"""Pipeline orchestration for the PetVideoGenerator agent."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List, Sequence

try:  # pragma: no cover - optional dependency
    from langgraph.graph import END, START, Graph

    _LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    Graph = None  # type: ignore[assignment]
    START = "__START__"
    END = "__END__"
    _LANGGRAPH_AVAILABLE = False

try:  # pragma: no cover - optional dependency
    from langchain_core.runnables import RunnableLambda
except ImportError:  # pragma: no cover - optional dependency
    class RunnableLambda:  # type: ignore[override]
        """Minimal fallback that mimics LangChain's RunnableLambda."""

        def __init__(self, func):
            self._func = func

        def __call__(self, *args, **kwargs):
            return self._func(*args, **kwargs)

        def invoke(self, *args, **kwargs):
            return self._func(*args, **kwargs)

from .config import PipelineConfig
from .nodes.base import Node
from .nodes.describe import DescribePet
from .nodes.ingest import IngestAssets
from .nodes.keyframes import GenKeyframe, PickKeyframe
from .nodes.style_bible import BuildStyleBible
from .nodes.storyboard import DraftStoryboard, PlanSegments
from .nodes.video import AssembleVideo, GenVideoSegment, QCVideoSegment, ReportNode
from .services.deepseek import DeepSeekClient
from .services.jimeng import JimengClient
from .services.qwen import QwenClient
from .services.style_bible import StyleBibleGenerator
from .types import RunState
from .utils.run_logger import RunLogger


class PetVideoGenerator:
    """High-level facade exposing the end-to-end generation flow."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig.from_env()
        self.logger = RunLogger(base_dir=self.config.runs_dir)

        # Instantiate mock service clients once; the pipeline reuses them for every run.
        self.qwen = QwenClient(
            api_key=self.config.qwen_api_key,
            api_url=self.config.qwen_api_url,
            use_mock=self.config.enable_mock_generation,
        )
        self.style_bible_generator = StyleBibleGenerator()
        self.deepseek = DeepSeekClient(
            api_key=self.config.deepseek_api_key,
            api_url=self.config.deepseek_api_url,
            use_mock=self.config.enable_mock_generation,
        )
        self.jimeng = JimengClient(
            self.config.assets_dir,
            api_key=self.config.jimeng_api_key,
            api_url=self.config.jimeng_api_url,
            use_mock=self.config.enable_mock_generation,
        )

    def run(
        self,
        *,
        image_paths: Iterable[str],
        origin_prompt: str,
        target_duration_sec: int = 30,
        fps: int = 24,
    ) -> RunState:
        """Execute the pipeline and return the resulting state."""
        run_id = self._new_run_id()
        state = RunState()
        image_paths_list = list(image_paths)
        nodes = self._build_nodes(
            run_id=run_id,
            image_paths=image_paths_list,
            origin_prompt=origin_prompt,
            target_duration_sec=target_duration_sec,
            fps=fps,
        )

        if not nodes:
            raise RuntimeError("Pipeline has no nodes configured.")

        if _LANGGRAPH_AVAILABLE and Graph is not None:
            graph = self._build_graph(nodes)
            app = graph.compile()
            return app.invoke(state)

        # Sequential fallback when LangGraph is unavailable.
        for node in nodes:
            state = self._invoke_node(node, state)
        return state

    def _build_graph(self, nodes: Sequence[Node]):
        """Construct a LangGraph graph wired with runnable nodes."""
        graph = Graph()
        node_names: List[str] = []

        for node in nodes:
            graph.add_node(
                node.name,
                RunnableLambda(lambda state, *, config=None, _node=node: self._invoke_node(_node, state)),
                metadata={"kind": node.name, "may_block": node.name in {"GenKeyframe", "GenVideoSegment"}},
            )
            node_names.append(node.name)

        if not node_names:
            raise RuntimeError("Pipeline has no nodes configured.")

        graph.add_edge(START, node_names[0])
        for previous, current in zip(node_names, node_names[1:]):
            graph.add_edge(previous, current)
        graph.add_edge(node_names[-1], END)

        return graph

    def _build_nodes(
        self,
        *,
        run_id: str,
        image_paths: List[str],
        origin_prompt: str,
        target_duration_sec: int,
        fps: int,
    ) -> Sequence[Node]:
        """Construct node instances wired with the current services."""
        return [
            IngestAssets(
                run_id=run_id,
                logger=self.logger,
                config=self.config,
                source_paths=image_paths,
                origin_prompt=origin_prompt,
                target_duration_sec=target_duration_sec,
                fps=fps,
            ),
            DescribePet(run_id=run_id, logger=self.logger, qwen=self.qwen),
            BuildStyleBible(
                run_id=run_id,
                logger=self.logger,
                generator=self.style_bible_generator,
            ),
            DraftStoryboard(
                run_id=run_id,
                logger=self.logger,
                deepseek=self.deepseek,
            ),
            PlanSegments(run_id=run_id, logger=self.logger),
            GenKeyframe(run_id=run_id, logger=self.logger, jimeng=self.jimeng),
            PickKeyframe(run_id=run_id, logger=self.logger),
            GenVideoSegment(run_id=run_id, logger=self.logger, jimeng=self.jimeng),
            QCVideoSegment(run_id=run_id, logger=self.logger),
            AssembleVideo(run_id=run_id, logger=self.logger, output_dir="outputs"),
            ReportNode(run_id=run_id, logger=self.logger, output_dir="outputs"),
        ]

    def _invoke_node(self, node: Node, state: RunState) -> RunState:
        """Execute a node while emitting structured IO traces."""
        input_snapshot = self._snapshot_state(state)
        self._print_step_io(node.name, "input", input_snapshot)

        started = time.perf_counter()
        updated_state = node.run(state)
        elapsed = time.perf_counter() - started

        output_snapshot = self._snapshot_state(updated_state)
        self._print_step_io(node.name, "output", output_snapshot, elapsed)

        return updated_state

    def _snapshot_state(self, state: RunState | Any) -> Any:
        """Return a compact serialisable view of the state for logging."""
        raw = asdict(state) if is_dataclass(state) else state
        return self._strip_empty(raw)

    def _strip_empty(self, value: Any) -> Any:
        """Recursively remove empty containers for cleaner logging."""
        if isinstance(value, dict):
            cleaned = {k: self._strip_empty(v) for k, v in value.items() if not self._is_empty(v)}
            return cleaned
        if isinstance(value, list):
            processed = [self._strip_empty(item) for item in value if not self._is_empty(item)]
            return processed
        if isinstance(value, tuple):
            processed = tuple(self._strip_empty(item) for item in value if not self._is_empty(item))
            return processed
        return value

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """Return True if the provided value is considered empty for logging."""
        if value is None:
            return True
        if isinstance(value, (str, bytes)) and value == "":
            return True
        if isinstance(value, (list, tuple, set)) and len(value) == 0:
            return True
        if isinstance(value, dict) and len(value) == 0:
            return True
        return False

    def _print_step_io(self, step: str, direction: str, payload: Any, elapsed: float | None = None) -> None:
        """Pretty-print the input/output payload for each step."""
        prefix = ">>" if direction == "input" else "<<"
        timing = f" [{elapsed:.2f}s]" if elapsed is not None and direction == "output" else ""
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default)
        print(f"[{step}] {prefix} {direction}{timing}:\n{body}\n")

    @staticmethod
    def _json_default(obj: Any) -> Any:
        """Fallback serializer for non-JSON compatible objects."""
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, set):
            return list(obj)
        return str(obj)

    @staticmethod
    def _new_run_id() -> str:
        """Return a simple unique run identifier."""
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
