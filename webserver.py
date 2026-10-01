import logging
import random
import time
import uuid
from pathlib import Path

from flask import Flask, g, has_request_context, request

LOG_FILE = Path(__file__).parent / "app.log"


class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = g.get("trace_id", "-") if has_request_context() else "-"
        return True


handlers = [logging.FileHandler(LOG_FILE), logging.StreamHandler()]
for handler in handlers:
    handler.addFilter(TraceIdFilter())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] trace=%(trace_id)s %(filename)s:%(lineno)d %(message)s",
    handlers=handlers,
)
# Mute werkzeug access logs: they are written after the request context is gone,
# so they carry no trace_id and only add noise for the agent.
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logger = logging.getLogger("webserver")
app = Flask("webserver")


@app.before_request
def start_trace():
    g.trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
    logger.info(f"Request started {request.method} {request.full_path.rstrip('?')}")


@app.after_request
def add_trace_header(response):
    response.headers["X-Trace-Id"] = g.trace_id
    return response


@app.route("/chain-divide")
def chain_divide():
    numbers = []
    for position in range(1, 6):
        number = random.randint(0, 4)
        logger.info(f"Generated number #{position}: {number}")
        numbers.append(number)
        time.sleep(random.uniform(0, 0.02))

    result = numbers[0]
    for n in numbers[1:]:
        result = result / n
    logger.info(f"Result: {result}")
    return {"numbers": numbers, "result": result}


if __name__ == "__main__":
    app.run(port=8000)
