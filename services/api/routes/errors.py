from uuid import uuid4

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.api.domain.memory import (
    MemoryConflict,
    MemoryInvalid,
    MemoryNotFound,
    MemoryUnavailable,
)
from services.api.domain.privacy import RestrictedContent
from services.api.domain.profile import ProfileConflict, ProfileUnavailable
from services.api.domain.project import (
    ProjectConflict,
    ProjectInvalid,
    ProjectNotFound,
    ProjectUnavailable,
)
from services.api.domain.work_session import (
    WorkSessionHistoryUnavailable,
    WorkSessionInvalid,
    WorkSessionNotFound,
    WorkSessionUnavailable,
)


async def profile_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError) and request.url.path != "/api/v1/profile":
        if request.url.path.startswith("/api/v1/projects"):
            return await project_error(request, error)
        if request.url.path.startswith("/api/v1/agent"):
            return await work_session_error(request, error)
        if request.url.path.startswith("/api/v1/memories"):
            return await memory_error(request, error)
        if request.url.path.startswith(("/agui", "/api/v1/")):
            return JSONResponse(
                {
                    "error": {
                        "code": "invalid_request",
                        "message": "请检查请求格式和字段。",
                        "request_id": str(uuid4()),
                    }
                },
                status_code=422,
                headers={"Cache-Control": "no-store"},
            )
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


async def privacy_error(request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RestrictedContent):
        raise error
    return JSONResponse(
        {
            "error": {
                "code": "restricted_content",
                "message": str(error),
                "request_id": getattr(request.state, "request_id", str(uuid4())),
            }
        },
        status_code=422,
        headers={"Cache-Control": "no-store"},
    )


async def project_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError):
        status, code, message = 422, "invalid_project", "请检查项目标题、描述和阶段状态。"
    elif isinstance(error, ProjectInvalid):
        status, code, message = 422, "invalid_project", "项目请求无效，请检查参数后重试。"
    elif isinstance(error, ProjectNotFound):
        status, code, message = 404, "project_not_found", "找不到该职业项目。"
    elif isinstance(error, ProjectConflict):
        status, code, message = 409, "project_conflict", "项目已有更新，请读取最新版本后再保存。"
    elif isinstance(error, ProjectUnavailable):
        status, code, message = 503, "project_unavailable", "项目服务暂不可用，请稍后重试。"
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


async def work_session_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError):
        status, code, message = 422, "invalid_agent_session", "请检查伙伴会话标识和项目关联。"
    elif isinstance(error, WorkSessionInvalid):
        status, code, message = 422, "invalid_agent_session", "伙伴会话标识无效。"
    elif isinstance(error, WorkSessionNotFound):
        status, code, message = 404, "agent_session_not_found", "找不到该伙伴工作。"
    elif isinstance(error, WorkSessionHistoryUnavailable):
        status, code, message = (
            503,
            "agent_history_unavailable",
            "伙伴历史暂时无法读取，请稍后重试。",
        )
    elif isinstance(error, WorkSessionUnavailable):
        status, code, message = (
            503,
            "agent_session_unavailable",
            "伙伴工作暂时无法保存，请稍后重试。",
        )
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


async def memory_error(request: Request, error: Exception) -> JSONResponse:
    if isinstance(error, RequestValidationError):
        status, code, message = 422, "invalid_memory", "请检查规则或笔记的标题、内容和版本。"
    elif isinstance(error, MemoryInvalid):
        status, code, message = 422, "invalid_memory", "规则或笔记内容无效，请检查后重试。"
    elif isinstance(error, MemoryNotFound):
        status, code, message = 404, "memory_not_found", "找不到该规则或笔记。"
    elif isinstance(error, MemoryConflict):
        status, code, message = 409, "memory_conflict", "内容已有更新，请读取最新版本后再操作。"
    elif isinstance(error, MemoryUnavailable):
        status, code, message = 503, "memory_unavailable", "规则与笔记服务暂不可用，请稍后重试。"
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
