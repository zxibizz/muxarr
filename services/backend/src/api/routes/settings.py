"""Reading and editing the settings the UI owns.

Fields pinned by an environment variable are reported in ``locked`` and refused
on write: whoever set them in compose expects compose to stay authoritative.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies.auth import authorise, get_container
from src.application.use_cases.settings.probe_ai import AiProbe
from src.core.container import AppContainer
from src.schemas.settings import AiTestRequest, AiTestResult, SettingsPatch, SettingsView
from src.settings.mutable import to_raw

router = APIRouter(prefix="/v1", tags=["settings"], dependencies=[Depends(authorise)])


@router.get("/settings", response_model=SettingsView)
async def read_settings(
    container: Annotated[AppContainer, Depends(get_container)],
) -> SettingsView:
    await container.sync_settings()
    return _view(container)


@router.patch("/settings", response_model=SettingsView)
async def update_settings(
    patch: SettingsPatch,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SettingsView:
    changes = {name: to_raw(value) for name, value in patch.model_dump(exclude_unset=True).items()}
    await container.update_settings.execute(changes)
    await container.sync_settings()
    return _view(container)


@router.post("/settings/ai/test", response_model=AiTestResult)
async def probe_ai_provider(
    request: AiTestRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AiTestResult:
    await container.sync_settings()
    probe = AiProbe(
        base_url=request.base_url,
        model=request.model,
        # A blank field means the user did not retype the saved key.
        api_key=request.api_key or container.settings.ai_api_key,
        timeout=request.timeout_seconds,
    )
    # The completer is blocking httpx; the loop still has long-polls to serve.
    result = await asyncio.to_thread(container.probe_ai_provider.execute, probe)
    return AiTestResult(ok=result.ok, message=result.message, latency_ms=result.latency_ms)


def _view(container: AppContainer) -> SettingsView:
    settings = container.settings
    return SettingsView(
        dedupe=settings.dedupe,
        skip_image_subtitles=settings.skip_image_subtitles,
        skip_undetermined_language=settings.skip_undetermined_language,
        max_external_tracks=settings.max_external_tracks,
        sub_charset=settings.sub_charset,
        keep_audio_languages=list(settings.keep_audio_languages),
        keep_subtitle_languages=list(settings.keep_subtitle_languages),
        mux_timeout_seconds=settings.mux_timeout_seconds,
        free_space_factor=settings.free_space_factor,
        preserve_ownership=settings.preserve_ownership,
        max_concurrent_muxes=settings.max_concurrent_muxes,
        job_ttl_seconds=settings.job_ttl_seconds,
        history_max_records=settings.history_max_records,
        operation_log_max_entries=settings.operation_log_max_entries,
        ai_mode=settings.ai_mode,
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
        ai_timeout_seconds=settings.ai_timeout_seconds,
        ai_max_entries=settings.ai_max_entries,
        ai_name_tracks=settings.ai_name_tracks,
        ai_api_key_set=bool(settings.ai_api_key),
        log_level=settings.log_level,
        locked=sorted(container.locked),
    )
