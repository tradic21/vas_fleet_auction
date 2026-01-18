import asyncio
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour

class HelloAgent(Agent):
    class HelloBehav(OneShotBehaviour):
        async def run(self):
            print("Agent radi")
            await self.agent.stop()

    async def setup(self):
        self.add_behaviour(self.HelloBehav())

async def main():
    # koristi lokalni XMPP server koji si pokrenula s `spade run`
    a = HelloAgent("a1@localhost", "a1pass")
    await a.start()
    await asyncio.sleep(1)
    await a.stop()

if __name__ == "__main__":
    asyncio.run(main())
