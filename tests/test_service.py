import copy
import os

import pytest

from agent_action.service import config_hash, matches_process, process_identity, verify_adoption


def test_process_identity_guards_against_pid_reuse_and_unrelated_commands():
    state = process_identity(os.getpid())
    assert matches_process(state)
    changed = copy.deepcopy(state)
    changed["start_ticks"] = str(int(changed["start_ticks"]) + 1)
    assert not matches_process(changed)
    changed = copy.deepcopy(state)
    changed["argv"] = ["unrelated-process"]
    assert not matches_process(changed)
    with pytest.raises(ValueError, match="not a vLLM"):
        verify_adoption(os.getpid(), {})
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})
