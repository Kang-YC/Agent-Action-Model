"""Fixed-command development check; never a scored model evaluation."""

import argparse
from copy import deepcopy
import math
from pathlib import Path

from agent_action.native import NativeRobot, save_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="classify_objects")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--port", type=int, default=19123)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient

    rpc = RPCClient("127.0.0.1", args.port, timeout=600)
    robot = None
    report = dict(kind="fixed_command_development_smoke", checks=[])
    try:
        robot = NativeRobot(rpc, args.output, args.task, args.seed)
        for name in ("hold", "translate", "rotate", "gripper", "invalid_translation", "duplicate_call"):
            robot.begin_cell()
            targets = deepcopy(robot.current)
            initial = deepcopy(robot.current)
            before = robot.tick
            if name == "translate":
                targets["left"]["position"][2] += .01
            elif name == "rotate":
                w, x, y, z = targets["left"]["quaternion_wxyz"]
                c, s = math.cos(.025), math.sin(.025)
                targets["left"]["quaternion_wxyz"] = [c*w-s*z, c*x-s*y, c*y+s*x, c*z+s*w]
            elif name == "gripper":
                for arm in targets:
                    targets[arm]["gripper_closed"] = not targets[arm]["gripper_closed"]
            elif name == "invalid_translation":
                targets["left"]["position"][2] += .051
            elif name == "duplicate_call":
                robot.move_to(**targets, steps=1)
            try:
                packet = robot.move_to(**targets, steps=1)
            except (ValueError, RuntimeError) as error:
                if name not in ("invalid_translation", "duplicate_call") or robot.uncertain:
                    raise
                expected = before + (name == "duplicate_call")
                if robot.tick != expected:
                    raise AssertionError("Rejected action changed native step")
                report["checks"].append(dict(name=name, passed=True, rejection=str(error), step_id=robot.tick))
            else:
                if name in ("invalid_translation", "duplicate_call"):
                    raise AssertionError("Invalid action was accepted")
                if robot.tick != before + 1 or len(packet["images"]) != 3:
                    raise AssertionError("Action/observation mismatch")
                if name == "hold" and any(math.dist(initial[arm]["position"], packet["current_eef"][arm]["position"]) > .005
                                          for arm in initial):
                    raise AssertionError("Hold drift exceeds 5 mm")
                if name == "translate" and packet["current_eef"]["left"]["position"][2] <= initial["left"]["position"][2] + 1e-5:
                    raise AssertionError("No measured upward translation")
                if name == "rotate":
                    old = initial["left"]["quaternion_wxyz"]
                    new = packet["current_eef"]["left"]["quaternion_wxyz"]
                    dot = abs(sum(a*b for a, b in zip(old, new)))
                    dot /= math.sqrt(sum(x*x for x in old)*sum(x*x for x in new))
                    if 2*math.acos(min(1., dot)) < 1e-5:
                        raise AssertionError("No measured rotation")
                if name == "gripper":
                    if any(packet["current_eef"][arm]["gripper_closed"] != targets[arm]["gripper_closed"] for arm in targets):
                        raise AssertionError("Last acknowledged gripper command mismatch")
                report["checks"].append(dict(name=name, passed=True, step_id=robot.tick,
                                              measured_eef=packet["current_eef"], target=targets,
                                              native_gripper_opening_feedback=packet["native_gripper_opening_feedback"]))
        report["passed"] = True
    finally:
        if robot is not None:
            save_json(robot.output / "smoke_report.json", report)
            robot.close("fixed_command_smoke")
        else:
            rpc.close()
    print(f"Passed {len(report['checks'])} fixed-command checks: {args.output}")


if __name__ == "__main__":
    main()
