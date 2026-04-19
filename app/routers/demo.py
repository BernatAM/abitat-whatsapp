from fastapi import APIRouter

from app.domain.schemas import DemoMessageRequest, DemoMessageResponse
from app.services.container import conversation_service


router = APIRouter(tags=["demo"])


@router.post("/demo/message", response_model=DemoMessageResponse)
def demo_message(payload: DemoMessageRequest) -> DemoMessageResponse:
    conversation, replies = conversation_service.process_incoming_message(
        phone=payload.phone,
        text=payload.text,
    )
    return DemoMessageResponse(
        phone=conversation.phone,
        state=conversation.current_state,
        replies=replies,
    )

