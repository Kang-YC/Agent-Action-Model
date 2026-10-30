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
            norm = math.sqrt(sum(x*x for x in q))
            if abs(norm-1) > 1e-4:
                raise ValueError(f"Expected unit quaternion wxyz: arm={arm}, norm={norm:.9g}, "
                                 "required abs(norm-1)<=0.0001; no_execution=true")
            if type(target["gripper_closed"]) is not bool:
                raise ValueError("gripper_closed must be boolean")
            old = current[arm]
            distance = math.dist(p, old["position"])
            if distance > self.max_translation_m + 1e-9:
                raise ValueError(f"Target exceeds translation bound: arm={arm}, "
                    f"distance_m={distance:.9g}, limit_m={self.max_translation_m}, "
                    f"current_position={old['position']}, target_position={p}; "
                    "metric=3D Euclidean distance, not per-axis; steps does not multiply the limit; no_execution=true")
            previous = vector(old["quaternion_wxyz"], 4)
            dot = abs(sum(a*b for a, b in zip(q, previous)))
            dot /= math.sqrt(sum(x*x for x in q)*sum(x*x for x in previous))
            angle = 2*math.acos(min(1.0, dot))
            if angle > self.max_rotation_rad + 1e-9:
                raise ValueError(f"Target exceeds rotation bound: arm={arm}, "
                                 f"angle_rad={angle:.9g}, limit_rad={self.max_rotation_rad}; no_execution=true")
            targets[arm] = dict(position=p, quaternion_wxyz=q, gripper_closed=target["gripper_closed"])
        return targets

    def translation_rule(self) -> str:
        return (f"For EACH arm independently, dx, dy, dz = target.position - current measured EEF.position "
                f"in meters. sqrt(dx*dx + dy*dy + dz*dz) must be <= {self.max_translation_m} m "
                "(3D Euclidean displacement per call, NOT a separate allowance for each axis). "
                "Check left and right independently; do not add their distances together. "
                "steps repeats control toward the SAME absolute target and does not multiply this limit.")

    def description(self) -> str:
        return (f"Dual ARX X5; {self.eef_link} in {self.frame}; meters and unit wxyz. "
                "Targets are absolute link6 poses, not XYZ deltas or fingertip poses. "
                f"{self.translation_rule()} "
                f"Orientation change must be <= {self.max_rotation_rad} radians (about 20 degrees), "
                "and abs(norm(quaternion_wxyz)-1) <= 0.0001. "
                f"Execute 1..{self.max_steps} steps "
                f"at {1/self.control_dt:g} Hz. True gripper_closed maps to opening=0. "
                "steps repeats control toward the SAME target; it does NOT multiply the displacement allowance. "
                "Check BOTH targets against Observation['current_eef'] on every call; previous desired targets "
                "may not have been reached. Hold an unused arm at its measured pose. "
                "Invalid calls execute zero controls; no target clipping or quaternion normalization is performed. "
                "Per-step bounded IK and joint limits are enforced by the native backend. "
                "Arrival and grasp are not guaranteed; gripper state is a command, not measured contact.")


def vector(value, size: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise ValueError(f"Expected vector of length {size}")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("Expected finite numeric coordinates")
    return [float(x) for x in value]


CONTRACT = RobotContract()
