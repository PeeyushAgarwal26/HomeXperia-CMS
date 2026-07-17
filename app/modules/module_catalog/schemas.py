from __future__ import annotations

from pydantic import BaseModel


class ModuleTreeNode(BaseModel):
    key: str
    name: str
    is_buildable: bool
    children: list[ModuleTreeNode] = []


ModuleTreeNode.model_rebuild()
