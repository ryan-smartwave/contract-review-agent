"""A2A boundary for the Contract Review Agent.

The Agent Gateway (routing between agents, auth, discovery) is Globe's;
this module is only our side of that boundary: an agent card describing
what we do, and a JSON-RPC endpoint that runs a Drive search on request.

Built against a2a-sdk 1.1.2, whose server API is protobuf-based (a break
from the pre-1.0 pydantic `a2a.types` / `A2AStarletteApplication` shape
referenced in older docs). `AgentCard.url` became `AgentCard.supported_interfaces`
(a list of `AgentInterface`), and there is no `A2AStarletteApplication`
builder anymore -- routes are added directly onto a FastAPI app via
`add_a2a_routes_to_fastapi`, so we build a small dedicated FastAPI app here
and mount it in `src/main.py`.
"""

from fastapi import FastAPI

from a2a.helpers.proto_helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import DEFAULT_RPC_URL, TransportProtocol

RPC_URL = DEFAULT_RPC_URL  # "/" -- mounted under /a2a, so served at POST /a2a/


class ContractReviewExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from src.locator.router import get_drive_client
        from src.locator.service import search_contracts

        query = (context.get_user_input() or "").strip()
        if not query:
            await event_queue.enqueue_event(
                new_text_message("Send a keyword to search contracts in Drive.")
            )
            return
        results = search_contracts(query, drive=get_drive_client())
        if not results:
            text = f"No contracts found matching '{query}'."
        else:
            listing = "\n".join(f"- {f.name} (modified {f.modified_time:%Y-%m-%d})" for f in results)
            text = f"Found {len(results)} contract(s) matching '{query}':\n{listing}"
        await event_queue.enqueue_event(new_text_message(text))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


def _build_agent_card() -> AgentCard:
    return AgentCard(
        name="Contract Review Agent",
        description="Finds and reviews contract revisions; proposes clause-anchored redlines.",
        version="0.2.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(url="/a2a/", protocol_binding=TransportProtocol.JSONRPC)
        ],
        skills=[
            AgentSkill(
                id="find_contracts",
                name="Find contracts in Drive",
                description="Keyword search over the authorized Google Drive for contract documents.",
                tags=["contracts", "search"],
            )
        ],
    )


def build_a2a_app() -> FastAPI:
    card = _build_agent_card()
    handler = DefaultRequestHandler(
        agent_executor=ContractReviewExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    sub_app = FastAPI(title="Contract Review Agent A2A boundary")
    add_a2a_routes_to_fastapi(
        sub_app,
        agent_card_routes=create_agent_card_routes(card),
        # enable_v0_3_compat: defensive fallback so callers that omit the
        # A2A-Version header (the SDK then assumes "0.3") aren't rejected
        # with -32009 by the v1.0-only handler -- Globe's gateway is the
        # caller here and we don't control what it sends.
        jsonrpc_routes=create_jsonrpc_routes(
            handler, rpc_url=RPC_URL, enable_v0_3_compat=True
        ),
    )
    return sub_app
