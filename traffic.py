"""Traffic generator: concurrent requests, so log lines of different requests get interleaved."""
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "http://127.0.0.1:8000"


def chain_divide():
    response = requests.get(f"{BASE}/chain-divide")
    return f"{response.status_code} /chain-divide  trace={response.headers.get('X-Trace-Id')}"


def main(count: int = 20):
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(chain_divide) for _ in range(count)]
        for job in jobs:
            print(job.result())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
