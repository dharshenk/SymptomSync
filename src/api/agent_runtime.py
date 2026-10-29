from dataclasses import dataclass
from datetime import date
import os

from agents import Agent, RunContextWrapper, RunState, Runner, ToolApprovalItem
from dotenv import load_dotenv
from jinja2 import Template

from src.api.agent_tools import ToolContext
from src.api.models.chat_model import Decision
from src.api.telemetry import traced

load_dotenv()

SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH")

CHANGES_REJECTION_MESSAGE = (
    "The patient chose 'Changes needed', so the appointment was NOT booked. "
    "Ask the patient which details they want to change, save them with "
    "update_patient_details, then call book_appointment again."
)


@dataclass
class Finished:
    """The run produced a reply; `items` are the agent items to store for replay."""

    text: str
    items: list[dict]


@dataclass
class NeedsApproval:
    """The run paused for a Decision; `state` is the string to resume it from."""

    state: str


RunOutcome = Finished | NeedsApproval


def format_messages_for_runner(
    user_question: str,
    system_prompt: str,
    previous_items: list[dict] | None = None,
) -> list[dict]:
    """
    Build the input item list for OpenAI's Runner.
    Always appends the current user question, and prepends previous agent items
    (messages, tool calls and tool outputs) if given.
    """

    messages: list[dict] = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if previous_items:
        messages.extend(previous_items)

    messages.append({"role": "user", "content": user_question})

    return messages


def get_system_prompt():
    with open(SYSTEM_PROMPT_PATH) as fp:
        raw_prompt_text = fp.read()

    template = Template(raw_prompt_text)
    today_str = date.today().strftime("%A, %B %d, %Y")
    system_prompt = template.render(current_date=today_str)

    return system_prompt


def outcome_from_result(result) -> RunOutcome:
    if result.interruptions:
        return NeedsApproval(
            state=result.to_state().to_string(context_serializer=lambda _: {})
        )
    return Finished(
        text=result.final_output,
        items=[
            item.to_input_item()
            for item in result.new_items
            if not isinstance(item, ToolApprovalItem)
        ],
    )


class AgentRuntime:
    """Runs the agent for the chat flow; no SDK type crosses this boundary.

    Holds no Pending Approval state: a paused run is handed back as a string
    and resumed from one.
    """

    def __init__(self, agent: Agent):
        self._agent = agent

    @traced("agent.run")
    async def run(
        self, history: list[dict], user_text: str, context: ToolContext
    ) -> RunOutcome:
        """Start a run on the stored agent items plus the patient's new text."""
        agent_input = format_messages_for_runner(
            user_question=user_text,
            previous_items=history,
            system_prompt=get_system_prompt(),
        )
        result = await Runner.run(
            starting_agent=self._agent, input=agent_input, context=context
        )
        return outcome_from_result(result)

    @traced("agent.run")
    async def resume(
        self, state: str, context: ToolContext, decision: Decision
    ) -> RunOutcome:
        """Resume a paused run with the patient's Decision."""
        # The context isn't stored with the state (services, UUIDs), so it is
        # supplied here, on the restored state. It must not be passed to
        # Runner.run: that replaces the state's context and drops the approvals.
        run_state = await RunState.from_string(
            self._agent, state, context_override=RunContextWrapper(context)
        )
        for interruption in run_state.get_interruptions():
            if decision == Decision.GO_AHEAD:
                run_state.approve(interruption)
            else:
                run_state.reject(
                    interruption, rejection_message=CHANGES_REJECTION_MESSAGE
                )
        result = await Runner.run(starting_agent=self._agent, input=run_state)
        return outcome_from_result(result)
