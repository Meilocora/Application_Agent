from application_agent.arbeitsagentur import search_jobs


def main() -> None:
    jobs = search_jobs("Python Entwickler", "München", size=5)
    for job in jobs:
        print(f"{job.title} | {job.company} | {job.location}")
        print(f"   {job.url}")
        
    print(jobs[0].model_dump_json(indent=2))
