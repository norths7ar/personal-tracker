"""Foreground runner launched with detached, file-backed stdio by the manager."""

import argparse
import asyncio
import json
import logging
import os
import secrets
from pathlib import Path

import uvicorn

from scripts.service_manager import process_identity


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    options = parser.parse_args()
    data = Path(os.environ["TRACKER_DATA_DIR"]).resolve()
    token = os.environ.pop("TRACKER_CONTROL_TOKEN")
    instance = secrets.token_hex(16)
    # Import only after the instance environment is established. No production
    # database/configuration is opened by the manager or status queries.
    from api.main import app

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=options.port, log_level="info")
    )
    app.state.service_runtime = {
        "token": token,
        "instance": instance,
        "server": server,
    }
    identity = process_identity(os.getpid())
    state = {
        "pid": os.getpid(),
        **identity,
        "port": options.port,
        "data_directory": str(data),
        "token": token,
        "instance": instance,
    }
    runtime = data / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    pending = runtime / "personal-tracker.pending"
    pending.write_text(json.dumps(state), encoding="utf-8")
    state_path = runtime / "personal-tracker.json"
    pending.replace(state_path)

    async def serve() -> None:
        task = asyncio.create_task(server.serve())
        try:
            async with asyncio.timeout(40):
                while not server.started and not task.done():
                    await asyncio.sleep(0.1)
        except TimeoutError:
            logging.error("Service startup exceeded 40 seconds; cancelling startup.")
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return
        await task

    try:
        asyncio.run(serve())
    finally:
        # Only remove this runner's state, never another instance's record.
        if state_path.is_file():
            recorded = json.loads(state_path.read_text(encoding="utf-8"))
            if recorded.get("instance") == instance:
                state_path.unlink()


if __name__ == "__main__":
    main()
