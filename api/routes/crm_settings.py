"""后台可配置项接口（/api/crm-settings）

对应 data/crm_settings.json，供 /crm 的"会话成员 / 设置"面板读写。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agentlab.crm_settings import get_settings, update_settings

router = APIRouter()


class SettingsPatch(BaseModel):
    target_contacts: list[str] | None = None
    poll_interval: float | None = None
    quality_enabled: bool | None = None
    wechat_system_prompt: str | None = None
    rag_system_prompt: str | None = None
    quality_system_prompt: str | None = None


@router.get("", response_model=dict)
def read_settings() -> dict:
    return get_settings()


@router.put("", response_model=dict)
def write_settings(patch: SettingsPatch) -> dict:
    return update_settings(patch.model_dump(exclude_none=True))