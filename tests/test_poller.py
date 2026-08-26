import asyncio

import pytest

from src import main


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_poll_inbox_forever_calls_process_each_interval(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "process_inbox", lambda client: calls.append(client))
    task = asyncio.create_task(main.poll_inbox_forever(client="fake", interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    assert len(calls) >= 2
    assert calls[0] == "fake"
