import asyncio

from agents import Runner, ToolCallItem

from application_agent.job_agents import job_scout


async def run() -> None:
    wish = "I'm looking for a junior Python developer position in Munich, ideally with an AI focus."
    result = await Runner.run(job_scout, wish)

    # Show which searches the agent decided to run on its own.
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            print(f"Tool call: {item.raw_item.name}({item.raw_item.arguments})")

    print()
    print(result.final_output)


def main() -> None:
    asyncio.run(run())
