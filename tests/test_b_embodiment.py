import json
from pathlib import Path

from agent_action.b_embodiment import build_context, render_context
from agent_action.b_history import select_history


def test_static_calibration_is_inline_snapshotted_and_survives_history_window(tmp_path):
    robot, reference, output = [tmp_path / name for name in ("robot", "reference", "output")]
    output.mkdir()
    urdf = robot / "Assets/Robots/x5/X5A.urdf"
    urdf.parent.mkdir(parents=True)
    urdf.write_text('<robot name="x5"><joint name="joint1" type="revolute">'
                    '<parent link="base_link"/><child link="link1"/>'
                    '<limit lower="-1" upper="1"/></joint></robot>')
    (urdf.parent / "robot_config.yml").write_text('ee_link: link6\ngripper_bias: 0.145\n')
    mounts = robot / "env_cfg/robot/dual_x5.yml"
    mounts.parent.mkdir(parents=True)
    mounts.write_text('robots:\n  - default_root_pos: [-0.3, -0.45, 0.765]\n  - default_root_pos: [0.3, -0.45, 0.765]\n')
    helper = reference / "hybrid_rollout/luban_direct/geometry.py"
    helper.parent.mkdir(parents=True)
    helper.write_text('import hashlib\n'
                      'def build_calibration(root):\n'
                      ' p="Assets/Robots/x5/X5A.urdf"\n'
                      ' paths=[p,"Assets/Robots/x5/robot_config.yml"]\n'
                      ' return dict(source_sha256={q:hashlib.sha256((root/q).read_bytes()).hexdigest() for q in paths}, '
                      'cameras={"cam_high":{"K":[[1,0,0],[0,1,0],[0,0,1]]}})\n')
    context = build_context(robot, reference, output)
    prompt = render_context(context)
    assert "cam_high" in prompt and "default_root_pos" in prompt
    assert "joint1" in prompt and "link6 local +X" in prompt
    assert "NOT measured runtime K" in prompt
    assert "14 native proprioceptive scalars" in prompt
    assert (output / "embodiment_source/Assets/Robots/x5/X5A.urdf").read_bytes() == urdf.read_bytes()
    assert json.loads((output / "embodiment_context.json").read_text()) == context
    messages = [dict(role="system", content=prompt), dict(role="user", content="task")]
    for i in range(12):
        messages.extend([dict(role="assistant", tool_calls=[dict(id=str(i))]),
                         dict(role="tool", tool_call_id=str(i), content="state")])
    selected, audit = select_history(messages, 8)
    assert audit["omitted_messages"]
    assert prompt in selected[0]["content"]
