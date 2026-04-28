import asyncio

from bot.utils.task_helpers import wait_until_ready_or_stop


class ReadyBot:
    async def wait_until_ready(self):
        return None


class UninitialisedBot:
    async def wait_until_ready(self):
        raise RuntimeError("Client has not been properly initialised")


class LoopHandle:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_wait_until_ready_or_stop_returns_true_for_ready_bot():
    loop = LoopHandle()

    assert asyncio.run(wait_until_ready_or_stop(ReadyBot(), loop, "ready.loop")) is True
    assert loop.stopped is False


def test_wait_until_ready_or_stop_stops_loop_for_uninitialised_bot():
    loop = LoopHandle()

    assert asyncio.run(wait_until_ready_or_stop(UninitialisedBot(), loop, "offline.loop")) is False
    assert loop.stopped is True
