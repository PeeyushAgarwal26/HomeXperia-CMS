import uuid

from pydantic import BaseModel


class ChildCategoryItem(BaseModel):
    id: uuid.UUID
    name: str


class ParentCategoryNode(BaseModel):
    id: uuid.UUID
    name: str
    children: list[ChildCategoryItem]
