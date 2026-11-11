import subprocess
import sys
import time

import pytest

from kemocore.runtime import ToolProcesses, tool_processes, run_tool
from kemoserver.workspace import Jobs


def test_managed_tools_preserve_output_errors_and_timeout():
    tools = ToolProcesses()
    result = tools.run([sys.executable, '-c', 'print(input().upper())'], input='hello', capture_output=True, text=True, check=True)
    assert result.stdout == 'HELLO\n'
    with pytest.raises(subprocess.CalledProcessError) as error:
        tools.run([sys.executable, '-c', 'import sys; print("bad"); sys.exit(2)'], capture_output=True, text=True, check=True)
    assert error.value.returncode == 2 and error.value.stdout == 'bad\n'
    with pytest.raises(subprocess.TimeoutExpired):
        tools.run([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=0.1, capture_output=True)
    assert not tools.processes


def test_jobs_inherit_video_session_and_stop_without_orphan_processes(monkeypatch):
    from kemocore import runtime
    monkeypatch.setattr(runtime, 'tool_path', lambda name: sys.executable)
    tools = ToolProcesses()
    jobs = Jobs()
    with tool_processes(tools):
        job = jobs.start('video', lambda progress: run_tool('ffmpeg', ['-c', 'import time; time.sleep(600)'], capture_output=True))
    deadline = time.monotonic() + 3
    while not tools.processes and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert tools.processes
    finally:
        tools.cancel()
    assert jobs.wait(3)
    assert job.status == 'failed'
    assert not tools.processes
    with pytest.raises(InterruptedError):
        tools.run([sys.executable, '-c', 'print("should not launch")'])
    # Cancelling a desktop session does not disable command-line tools in other contexts.
    assert run_tool('ffprobe', ['-c', 'print("outside")'], capture_output=True, text=True).stdout == 'outside\n'
