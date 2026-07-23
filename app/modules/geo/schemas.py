from pydantic import BaseModel


class StateItem(BaseModel):
    code: str
    name: str


class CityItem(BaseModel):
    name: str
