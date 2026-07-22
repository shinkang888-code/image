"""Compute Node 레지스트리 — 여러 ComfyUI 노드 등록·헬스체크·분산 선택.

lasset `packages/lasset-core/src/nodes.ts` 의 provider-agnostic Compute Node
패턴 이식: 아무 Comfy 호환 URL(로컬 8GB, 두 번째 PC, RunPod 등)을 등록해
단일 GPU 한계를 넘어 분산 생성. JSON 파일 저장(무의존, DB 불필요).

이식 요지:
- ComputeNode { id, name, base_url, active, status: online|offline|unknown, last_seen }
- upsert/list/set_active/update_status  (원본 시그니처 대응)
- baseUrl 말미 슬래시 정규화, active 단일 지정
- LIP 확장: pick_active_nodes() 로 여러 active 노드를 라운드로빈 분산
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

NodeStatus = str  # online | offline | unknown


@dataclass
class ComputeNode:
    id: str
    name: str
    base_url: str
    active: bool = True
    status: NodeStatus = "unknown"
    detail: str = ""
    created_at: float = field(default_factory=time.time)
    last_seen_at: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(url: str) -> str:
    return url.rstrip("/")


class NodeRegistry:
    """JSON 파일 기반 노드 레지스트리 (data/nodes.json). 스레드 안전."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._nodes: list[ComputeNode] = self._read()

    def _read(self) -> list[ComputeNode]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [ComputeNode(**n) for n in raw]
        except (json.JSONDecodeError, TypeError):
            return []

    def _write(self) -> None:
        self.path.write_text(
            json.dumps([n.as_dict() for n in self._nodes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list(self) -> list[ComputeNode]:
        with self._lock:
            return list(self._nodes)

    def upsert(self, name: str, base_url: str, node_id: str | None = None,
               active: bool = True) -> ComputeNode:
        with self._lock:
            node = next((n for n in self._nodes if n.id == node_id), None) if node_id else None
            if node is None:
                node = ComputeNode(
                    id=node_id or f"node_{len(self._nodes) + 1}_{int(time.time()) % 100000}",
                    name=name,
                    base_url=_norm(base_url),
                    active=active if self._nodes else True,
                )
                self._nodes.append(node)
            else:
                node.name = name
                node.base_url = _norm(base_url)
                node.active = active
            self._write()
            return node

    def set_active(self, node_id: str, active: bool = True) -> ComputeNode | None:
        with self._lock:
            found = None
            for n in self._nodes:
                if n.id == node_id:
                    n.active = active
                    found = n
            self._write()
            return found

    def update_status(self, node_id: str, status: NodeStatus, detail: str = "") -> None:
        with self._lock:
            for n in self._nodes:
                if n.id == node_id:
                    n.status = status
                    n.detail = detail
                    n.last_seen_at = time.time()
            self._write()

    def active_nodes(self) -> list[ComputeNode]:
        with self._lock:
            act = [n for n in self._nodes if n.active]
            return act or list(self._nodes)

    def remove(self, node_id: str) -> bool:
        with self._lock:
            before = len(self._nodes)
            self._nodes = [n for n in self._nodes if n.id != node_id]
            self._write()
            return len(self._nodes) < before


def ensure_default_node(reg: NodeRegistry, host: str) -> None:
    """노드가 하나도 없으면 config 의 로컬 ComfyUI 를 기본 노드로 등록."""
    if not reg.list():
        reg.upsert(name="local-8gb", base_url=f"http://{host}")
