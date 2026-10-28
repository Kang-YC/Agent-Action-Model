"""Snapshot static hardware/calibration and render it inline for the B model."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import yaml


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_context(robodojo: Path, reference: Path, output: Path) -> dict:
    # Use the same static-only derivation as A, without importing its agent,
    # loading scenes, connecting RPC, or reading prior episode observations.
    helper = reference / "hybrid_rollout/luban_direct/geometry.py"
    helper_hash = sha256(helper)
    spec = importlib.util.spec_from_file_location("b_static_geometry_source", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calibration = module.build_calibration(robodojo)
    if sha256(helper) != helper_hash:
        raise RuntimeError("Static geometry source changed while building context")
    relative_paths = [*calibration["source_sha256"], "env_cfg/robot/dual_x5.yml"]
    sources = {}
    snapshot = output / "embodiment_source"
    for relative in relative_paths:
        path = robodojo / relative
        actual = sha256(path)
        if relative in calibration["source_sha256"] and actual != calibration["source_sha256"][relative]:
            raise RuntimeError(f"Calibration input changed: {relative}")
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha256(target) != actual:
            raise RuntimeError(f"Calibration snapshot mismatch: {relative}")
        sources[relative] = actual
    shutil.copyfile(helper, snapshot / "geometry.py")
    if sha256(snapshot / "geometry.py") != helper_hash:
        raise RuntimeError("Geometry source snapshot mismatch")
    urdf = ET.parse(snapshot / "Assets/Robots/x5/X5A.urdf").getroot()
    joints = []
    for joint in urdf.findall("joint"):
        joints.append(dict(name=joint.attrib["name"], type=joint.attrib["type"],
            **{name: joint.find(name).attrib for name in ("parent", "child", "origin", "axis", "limit", "mimic")
               if joint.find(name) is not None}))
    mounts = yaml.safe_load((snapshot / "env_cfg/robot/dual_x5.yml").read_text())["robots"]
    if len(mounts) != 2:
        raise ValueError("Expected exactly two X5 arm mounts")
    robot_configuration = yaml.safe_load((snapshot / "Assets/Robots/x5/robot_config.yml").read_text())
    context = dict(schema="agent_action.b_embodiment.v1", source_sha256=sources,
        geometry_helper_sha256=helper_hash, robot_type="dual ARX X5",
        urdf_conventions=dict(origin_xyz="Meters in parent link frame",
            origin_rpy="Radians; R_parent_joint = Rz(yaw) @ Ry(pitch) @ Rx(roll)",
            joint_axis="Joint-local axis", revolute_limits="Radians", prismatic_limits="Meters"),
        mount_conventions="default_root_pos: environment-origin meters; default_root_rot: configured wxyz; runtime may normalize quaternion",
        calibration=calibration, urdf_joint_chain=joints,
        robot_configuration=robot_configuration,
        configured_arm_mounts=dict(zip(("left", "right"), mounts)),
        coordinate_rules=[
            "Both arms' position targets and current_eef use the same environment-origin axes, meters; orientations are unit wxyz.",
            "Commanded pose is link6, not the fingertip/contact point. The geometry-derived finger extension is link6 local +X.",
            "The +0.145m local-X contact reference is approximate static geometry, not an object grasp point. Rotate it by the actual link6 orientation; do not treat it as a fixed world-Z offset.",
            "Mount transforms and camera poses below are configured static values, not a live pose measurement. Wrist camera extrinsics are relative to their camera link, not fixed world extrinsics.",
            "Camera K below is configuration-derived, NOT measured runtime K. Isaac may adjust apertures for square pixels. Do not treat nominal K as exact metric-depth calibration; do not infer depth from a pixel alone.",
            "USD/OpenGL camera axes differ from environment axes: camera +X right, +Y up, -Z viewing. Apply the appropriate transforms; do not command pixel/camera coordinates as environment coordinates."],
        observation_rules=[
            "current_state has 14 native proprioceptive scalars: left joint1..6 (radians), left opening, right joint1..6 (radians), right opening. Opening convention is 0 closed, 1 open.",
            "current_eef contains measured link6 position/orientation; gripper_closed after actions is the last acknowledged command. Neither opening scalar nor command proves contact or grasp.",
            "ACK means controls were acknowledged, not arrival or task success. Compare measured pose and RGB against the intended effect.",
            "No hidden object positions, task layouts, reward labels, policy trajectories, or grasp scripts are supplied."],
        limitations=["Nominal camera parameters have not been checked against runtime Camera.get_intrinsics_matrix.",
                     "Task-specific completion conditions must be supplied separately when the native interface exposes them."])
    (output / "embodiment_context.json").write_text(json.dumps(context, indent=2))
    return context


def render_context(context: dict) -> str:
    return ("\nStatic robot and camera context (known before this episode; no object truth):\n"
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
            + "\nUse this context together with current measured proprioception and RGB.\n")
