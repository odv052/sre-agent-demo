# Turning Backend Logs into Actionable Insights

A demo of an AI agent that reads backend logs and source code, figures out why requests fail,
and writes an incident report. Everything runs locally: the agent uses a small open model via
[Ollama](https://ollama.com), so no logs or code leave the machine.

The agent follows a four-step pipeline:

| Step | What happens | LLM? |
|---|---|---|
| **Detect** | Parse `app.log`, find errors, extract the exception and our own stack frames, group repeated errors into one incident | no, plain code |
| **Route** | Classify the incident (category, severity); resolve the owning team from a CODEOWNERS-like map | partly |
| **Investigate** | A tool-using agent reads the code and pulls the logs of affected requests by `trace_id` | yes |
| **Report** | Write a Markdown report: facts (counts, timestamps, owner) come from code, hypothesis and fix from the LLM | yes |

## The bug

`webserver.py` has one endpoint, `/chain-divide`. It generates five random numbers from 0 to 4,
logs each of them, then divides them one by another. Sometimes a divisor is 0.

The stack trace only shows `result = result / divisor`. Which number was zero is only in the logs,
and since requests run concurrently, log lines of different requests are interleaved.
The agent has to use the `trace_id` that every log line carries to reconstruct a single request:

```
INFO [webserver] trace=9b107240b02d401b webserver.py:49 Generated number #1: 2
INFO [webserver] trace=4c5d350d9fde48cd webserver.py:49 Generated number #1: 0
INFO [webserver] trace=0141bc38989a4340 webserver.py:49 Generated number #2: 3
```

## Setup

Requirements: Python 3 (tested with 3.14) and [Ollama](https://ollama.com).

```bash
ollama pull qwen3.5:4b

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running the demo

```bash
# terminal 1: start the web server (writes app.log)
.venv/bin/python webserver.py

# terminal 2: send concurrent traffic (default 20 requests)
.venv/bin/python traffic.py 30

# run the agent over app.log
.venv/bin/python -m sre_agent.agent
```

The agent prints each pipeline step and every tool call live, then saves the report to
`reports/<timestamp>-<exception>.md`.

To start from a clean slate, delete `app.log` before starting the server.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_MODEL` | `qwen3.5:4b` | Any Ollama model with tool calling |
| `AGENT_THINK` | off | Set to `1` to enable the model's thinking mode (slower) |

```bash
AGENT_MODEL=qwen3.5:35b .venv/bin/python -m sre_agent.agent
```

`qwen3.5:4b` is fast but sometimes gets details wrong, e.g. at which step the division failed.
`qwen3.5:35b` (a Mixture-of-Experts model, ~3B active parameters, 24 GB download) is noticeably
more accurate and still reasonably fast on a machine with enough memory.

## Agent tools

The investigator can only read files inside the project (`.venv`, `.git`, `reports` are off limits):

| Tool | Purpose |
|---|---|
| `get_trace(trace_id)` | All log lines of one request, in order |
| `search_logs(pattern)` | Regex search over `app.log` |
| `read_file(path, start, end)` | Read source code with line numbers |
| `search_code(pattern)` | Regex search over the source code |
| `list_files()` | List project source files |

If the agent finishes without calling `get_trace`, it is asked to look at the request logs and answer
again. If it hits the step limit, it summarizes what it has found so far instead of returning nothing.

## Project layout

```
webserver.py          Flask app with the buggy /chain-divide endpoint and trace_id logging
traffic.py            Concurrent traffic generator
sre_agent/
  agent.py            Detect -> Route -> Investigate -> Report pipeline
  utils.py            Log parsing and agent tools
  models.py           Data classes and structured-output schemas
  report.md.j2        Jinja2 template of the incident report
reports/              Generated incident reports
app.log               Server log the agent analyzes (created by webserver.py)
```
