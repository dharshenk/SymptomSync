"""Integration tests for PendingApprovalService."""

from uuid import UUID

from src.api.models.pending_approval_model import PendingApproval
from src.api.services.pending_approval_service import PendingApprovalService


def make_pending(session_id: UUID, run_state: str = "state-1") -> PendingApproval:
    return PendingApproval(
        chat_session_id=session_id,
        run_state=run_state,
        user_item={"role": "user", "content": "hello"},
        user_message_sequence=3,
    )


async def test_get_returns_none_when_nothing_pending(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    assert await pending_approval_service.get(sample_chat_session) is None


async def test_save_then_get_round_trips(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session))

    pending = await pending_approval_service.get(sample_chat_session)

    assert pending == make_pending(sample_chat_session)


async def test_save_replaces_existing_row(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session, "old"))
    await pending_approval_service.save(make_pending(sample_chat_session, "new"))

    pending = await pending_approval_service.get(sample_chat_session)

    assert pending.run_state == "new"


async def test_delete_removes_row(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session))

    await pending_approval_service.delete(sample_chat_session)

    assert await pending_approval_service.get(sample_chat_session) is None
