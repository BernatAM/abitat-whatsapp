from fastapi import APIRouter, HTTPException

from app.domain.schemas import (
    DebugActionResponse,
    DebugConversationResponse,
    DebugConversationsResponse,
    DebugJobsResponse,
    JobsRunRequest,
    JobsRunResponse,
)
from app.services.container import (
    conversation_repository,
    job_repository,
    job_service,
    sage_service,
)


router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/conversations", response_model=DebugConversationsResponse)
def list_conversations() -> DebugConversationsResponse:
    return DebugConversationsResponse(
        conversations=[conversation.to_dict() for conversation in conversation_repository.list_all()]
    )


@router.get("/conversations/{phone}", response_model=DebugConversationResponse)
def get_conversation(phone: str) -> DebugConversationResponse:
    conversation = conversation_repository.get(phone)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return DebugConversationResponse(conversation=conversation.to_dict())


@router.post("/conversations/{phone}/reset", response_model=DebugActionResponse)
def reset_conversation(phone: str) -> DebugActionResponse:
    conversation_repository.reset(phone)
    return DebugActionResponse(detail=f"Conversation reset for {phone}")


@router.get("/jobs", response_model=DebugJobsResponse)
def list_jobs() -> DebugJobsResponse:
    return DebugJobsResponse(jobs=[job.to_dict() for job in job_repository.list_all()])


@router.post("/jobs/run", response_model=JobsRunResponse)
def run_jobs(payload: JobsRunRequest | None = None) -> JobsRunResponse:
    mode = payload.mode if payload else "due"
    executed = job_service.run_jobs(mode=mode)
    return JobsRunResponse(executed_jobs=[job.to_dict() for job in executed])


@router.post("/sage/{phone}/exists", response_model=DebugActionResponse)
def force_sage_exists(phone: str) -> DebugActionResponse:
    sage_service.set_exists(phone)
    return DebugActionResponse(detail=f"SAGE forced to existing customer for {phone}")


@router.post("/sage/{phone}/new", response_model=DebugActionResponse)
def force_sage_new(phone: str) -> DebugActionResponse:
    sage_service.set_new(phone)
    return DebugActionResponse(detail=f"SAGE forced to new customer for {phone}")

