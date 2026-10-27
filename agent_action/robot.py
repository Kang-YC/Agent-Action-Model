"""Shared dual-X5 contract and validation, independent of the simulator."""

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class RobotContract:
    robot_adapter: str = "dual_arx_x5"
    frame: str = "environment_origin"
    eef_link: str = "link6"
    control_dt: float = 0.04
    max_translation_m: float = 0.05
    max_rotation_rad: float = 0.35
    max_steps: int = 5
    cameras: tuple[str, ...] = ("cam_high", "cam_left_wrist", "cam_right_wrist")

    def check_metadata(self, metadata: dict) -> None:
        expected = asdict(self)
        for key in ("robot_adapter", "frame", "eef_link"):
            if metadata.get(key) != expected[key]:
                raise ValueError(f"Incompatible {key}: {metadata.get(key)!r}")
        if not math.isclose(metadata["control_dt"], self.control_dt, abs_tol=1e-8):
            raise ValueError("Expected 25 Hz native controls")
        if tuple(metadata["cameras"]) != self.cameras or metadata["action_dim"] != 14:
            raise ValueError("Expected three cameras and 14D dual-arm controls")
        if metadata["gripper_semantics"] != "continuous_0_closed_1_open":
            raise ValueError("Incompatible gripper semantics")

    def validate(self, left: dict, right: dict, steps: int, current: dict) -> dict:
        if type(steps) is not int or not 1 <= steps <= self.max_steps:
            raise ValueError(f"steps must be an integer in 1..{self.max_steps}")
        targets = {}
        for arm, target in (("left", left), ("right", right)):
            if not isinstance(target, dict) or set(target) != {"position", "quaternion_wxyz", "gripper_closed"}:
                raise ValueError(f"{arm} requires position, quaternion_wxyz, gripper_closed only")
            p = vector(target["position"], 3)
            q = vector(target["quaternion_wxyz"], 4)
            if abs(math.sqrt(sum(x*x for x in q))-1) > 1e-4:
                raise ValueError("Expected unit quaternion wxyz")
            if type(target["gripper_closed"]) is not bool:
                raise ValueError("gripper_closed must be boolean")
            old = current[arm]
            if math.dist(p, old["position"]) > self.max_translation_m + 1e-9:
                raise ValueError("Target exceeds translation bound")
            previous = vector(old["quaternion_wxyz"], 4)
            dot = abs(sum(a*b for a, b in zip(q, previous)))
            dot /= math.sqrt(sum(x*x for x in q)*sum(x*x for x in previous))
            if 2*math.acos(min(1.0, dot)) > self.max_rotation_rad + 1e-9:
                raise ValueError("Target exceeds rotation bound")
            targets[arm] = dict(position=p, quaternion_wxyz=q, gripper_closed=target["gripper_closed"])
        return targets

    def description(self) -> str:
        return (f"Dual ARX X5; {self.eef_link} in {self.frame}; meters and unit wxyz. "
                f"Explicit left/right targets within {self.max_translation_m} m and "
                f"{self.max_rotation_rad} rad of measured pose; 1..{self.max_steps} steps "
                f"at {1/self.control_dt:g} Hz. True gripper_closed maps to opening=0. "
                "Per-step bounded IK and joint limits are enforced by the native backend. "
                "Arrival and grasp are not guaranteed; gripper state is a command, not measured contact.")


def vector(value, size: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"Expected vector of length {size}")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("Expected finite numeric coordinates")
    return [float(x) for x in value]


CONTRACT = RobotContract()
