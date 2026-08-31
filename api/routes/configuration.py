from fastapi import APIRouter, Depends
from pydantic import RootModel

from api.security import require_api_auth
from core.config import load_config
from core.constants import TRANSACTION_TYPES

router = APIRouter(
    prefix="/api/config",
    tags=["configuration"],
    dependencies=[Depends(require_api_auth)],
)


class CategoryConfiguration(RootModel[dict[str, dict[str, list[str]]]]):
    pass


@router.get("/categories", response_model=CategoryConfiguration)
def categories() -> dict[str, dict[str, list[str]]]:
    config = load_config()
    return {type_name: config.get(type_name, {}) for type_name in TRANSACTION_TYPES}
