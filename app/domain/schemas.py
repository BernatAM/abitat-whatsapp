from __future__ import annotations

from pydantic import BaseModel, Field


class DemoMessageRequest(BaseModel):
    phone: str = Field(..., examples=["+34600000000"])
    text: str = Field(..., examples=["Sí"])


class DemoMessageResponse(BaseModel):
    phone: str
    state: str
    replies: list[str]


class WhatsAppWebhookMessage(BaseModel):
    from_phone: str = Field(..., alias="from")
    text: str

    model_config = {"populate_by_name": True}


class WhatsAppWebhookRequest(BaseModel):
    message: WhatsAppWebhookMessage


class WebhookResponse(BaseModel):
    phone: str
    state: str
    messages_sent: list[str]


class MetaWebhookVerificationResponse(BaseModel):
    detail: str


class JobsRunRequest(BaseModel):
    mode: str = Field(default="due", description="due o all")


class JobsRunResponse(BaseModel):
    executed_jobs: list[dict]


class DebugConversationResponse(BaseModel):
    conversation: dict


class DebugConversationsResponse(BaseModel):
    conversations: list[dict]


class DebugJobsResponse(BaseModel):
    jobs: list[dict]


class DebugActionResponse(BaseModel):
    ok: bool = True
    detail: str
