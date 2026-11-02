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


async def test_claim_returns_row_once_and_keeps_it_processing(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session))

    first = await pending_approval_service.claim(sample_chat_session)
    second = await pending_approval_service.claim(sample_chat_session)

    assert first == make_pending(sample_chat_session)
    assert second is None
    pending = await pending_approval_service.get(sample_chat_session)
    assert pending.status == "processing"


async def test_save_after_claim_makes_it_claimable_again(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session))
    claimed = await pending_approval_service.claim(sample_chat_session)

    await pending_approval_service.save(claimed)

    assert (await pending_approval_service.get(sample_chat_session)).status == "pending"
    assert await pending_approval_service.claim(sample_chat_session) is not None


async def test_stale_claim_is_treated_as_pending(
    pending_approval_service: PendingApprovalService, sample_chat_session: UUID
):
    await pending_approval_service.save(make_pending(sample_chat_session))
    await pending_approval_service.claim(sample_chat_session)
    pending_approval_service._postgres_client.execute_command(
        "UPDATE pending_approvals SET claimed_at = CURRENT_TIMESTAMP - interval '1 hour'"
    )

    assert (await pending_approval_service.get(sample_chat_session)).status == "pending"
    assert await pending_approval_service.claim(sample_chat_session) is not None
