from pydantic import BaseModel


class StateItem(BaseModel):
    code: str
    name: str
