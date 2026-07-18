from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str


class ProductResponse(ProductCreate):
    id: int
