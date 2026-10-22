from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from api.security import require_api_auth
from core import todos

router = APIRouter(
    prefix="/api/todos", tags=["todos"], dependencies=[Depends(require_api_auth)]
)


class TodoWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)


class TodoState(BaseModel):
    status: Literal["pending", "active", "completed"]


class TodoMove(BaseModel):
    direction: Literal["up", "down"]


class TodoResponse(TodoWrite):
    id: int
    status: Literal["pending", "active", "completed"]
    position: int
    completed_at: str | None


def _call(operation, *args):
    try:
        return operation(*args)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("", response_model=list[TodoResponse])
def list_todos():
    return todos.list_todos()


@router.post("", response_model=TodoResponse, status_code=201)
def create_todo(body: TodoWrite):
    return todos.create_todo(body.title, body.notes)


@router.put("/{todo_id}", response_model=TodoResponse)
def edit_todo(todo_id: int, body: TodoWrite):
    return _call(todos.edit_todo, todo_id, body.title, body.notes)


@router.post("/{todo_id}/state", response_model=TodoResponse)
def set_state(todo_id: int, body: TodoState):
    return _call(todos.set_state, todo_id, body.status)


@router.post("/{todo_id}/move", status_code=204)
def move_todo(todo_id: int, body: TodoMove):
    _call(todos.move_todo, todo_id, body.direction)
    return Response(status_code=204)


@router.delete("/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    _call(todos.delete_todo, todo_id)
    return Response(status_code=204)
