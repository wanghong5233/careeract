from uuid import uuid4

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.api.domain.profile import ProfileConflict, ProfileUnavailable


async def profile_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError) and request.url.path != "/api/v1/profile":
        return await request_validation_exception_handler(request, error)
    if isinstance(error, ProfileConflict):
        status, code, message = 409, "profile_conflict", "档案已有更新，请读取最新版本后再保存。"
    elif isinstance(error, ProfileUnavailable):
        status, code, message = 503, "profile_unavailable", "档案服务暂不可用，请稍后读取并核对。"
    elif isinstance(error, RequestValidationError):
        status, code, message = 422, "invalid_profile", "请检查必填项、字段长度和确认状态。"
    else:
        raise error
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", str(uuid4())),
            }
        },
        headers={"Cache-Control": "no-store"},
    )
