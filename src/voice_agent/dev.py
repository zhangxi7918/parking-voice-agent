from __future__ import annotations

import asyncio
import signal
import sys


async def _run_processes(commands: list[list[str]]) -> int:
    processes = [await asyncio.create_subprocess_exec(*command) for command in commands]
    stop_event = asyncio.Event()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    wait_tasks = [asyncio.create_task(process.wait()) for process in processes]
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        [*wait_tasks, stop_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()

    first_exit_code = 0
    for task in done:
        if task is stop_task:
            continue
        exit_code = task.result()
        if exit_code != 0:
            first_exit_code = exit_code

    await _terminate_processes(processes)
    return first_exit_code


async def _terminate_processes(processes: list[asyncio.subprocess.Process]) -> None:
    running_processes = [process for process in processes if process.returncode is None]
    for process in running_processes:
        process.terminate()

    if not running_processes:
        return

    try:
        await asyncio.wait_for(
            asyncio.gather(*(process.wait() for process in running_processes)),
            timeout=8,
        )
    except asyncio.TimeoutError:
        for process in running_processes:
            if process.returncode is None:
                process.kill()
        await asyncio.gather(*(process.wait() for process in running_processes))


def main() -> None:
    python = sys.executable
    commands = [
        [
            python,
            "-m",
            "uvicorn",
            "voice_agent.server:create_app",
            "--factory",
            "--reload",
        ],
        [
            python,
            "-m",
            "voice_agent.livekit_worker",
            "dev",
        ],
    ]
    raise SystemExit(asyncio.run(_run_processes(commands)))


if __name__ == "__main__":
    main()
