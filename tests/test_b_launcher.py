import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("backend_dies", [True, False])
def test_launcher_stops_controller_after_backend_exit(tmp_path, backend_dies):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile("scripts/run_b_line.sh", scripts / "run_b_line.sh")
    (scripts / "start_native.sh").write_text(
        '#!/bin/bash\necho \'{"event": "ready"}\'\nexec sleep '
        + ('3\n' if backend_dies else '30\n'))
    controller = tmp_path / "fake-python"
    controller.write_text('#!/bin/bash\n'
        'trap \'echo terminated > "$STOP_MARKER"; exit 7\' TERM\n'
        + ('while true; do sleep 0.1; done\n' if backend_dies else 'exit 0\n'))
    controller.chmod(0o755)
    marker = tmp_path / "stopped"
    output = tmp_path / "run"
    result = subprocess.run(["bash", str(scripts / "run_b_line.sh"), str(output)],
        env=dict(os.environ, B_LINE_PYTHON=str(controller), STOP_MARKER=str(marker)),
        capture_output=True, text=True, timeout=15)
    if backend_dies:
        assert result.returncode != 0
        assert marker.read_text().strip() == "terminated"
        assert "native_backend_exited" in (output / "launcher_error.json").read_text()
    else:
        assert result.returncode == 0
        assert not (output / "launcher_error.json").exists()
