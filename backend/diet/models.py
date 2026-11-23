"""Food input shared by diet editing and capture preparation."""

from pydantic import BaseModel, Field


class FoodInput(BaseModel):
    food_name: str = Field(min_length=1)
    quantity: str = ""
    ingredients: list[str] = Field(default_factory=list)
