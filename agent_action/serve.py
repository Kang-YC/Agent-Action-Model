"""Validate a local checkpoint, record its identity, and start pinned vLLM."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys


def checkpoint_manifest(config: dict) -> dict:
    root = Path(config["checkpoint"]).resolve(strict=True)
    index = json.loads((root / "model.safetensors.index.json").read_text())
    shards = []
    for name in sorted(set(index["weight_map"].values())):
        path = root / name
        stat = path.stat()
        if stat.st_size <= 0:
            raise ValueError(f"Empty weight shard: {name}")
        shards.append(dict(name=name, size=stat.st_size, mtime_ns=stat.st_mtime_ns))
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
        "config.json", "generation_config.json", "model.safetensors.index.json",
        "chat_template.jinja", "processor_config.json", "tokenizer_config.json", "tokenizer.json")}
    model_config = json.loads((root / "config.json").read_text())
    return dict(checkpoint=str(root), served_model_name=config["served_model_name"],
                architectures=model_config["architectures"], model_type=model_config["model_type"],
                files_sha256=files, weight_shards=shards, weight_bytes=sum(s["size"] for s in shards),
                weight_identity_scope="path_size_mtime_and_index; weight_contents_not_hashed")


def server_arguments(config: dict) -> list[str]:
    return ["serve", config["checkpoint"], "--served-model-name", config["served_model_name"],
            "--host", config["host"], "--port", str(config["port"]), "--dtype", config["dtype"],
            "--max-model-len", str(config["max_model_len"]), "--max-num-seqs", str(config["max_num_seqs"]),
            "--gpu-memory-utilization", str(config["gpu_memory_utilization"]),
            "--max-num-batched-tokens", str(config["max_num_batched_tokens"]),
            "--limit-mm-per-prompt", json.dumps({"image": config["max_images"], "video": 0}),
            "--mm-processor-kwargs", json.dumps({"max_pixels": config["max_image_pixels"]}),
            "--default-chat-template-kwargs", json.dumps({"enable_thinking": config["enable_thinking"]}),
            "--generation-config", "vllm", "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder",
            "--reasoning-parser", "qwen3", "--enforce-eager", "--no-enable-prefix-caching"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    manifest = checkpoint_manifest(config)
    manifest["inference_config"] = config
    manifest["server_arguments"] = server_arguments(config)
    if not args.inspect_only:
        version = importlib.metadata.version("vllm")
        if version != config["vllm_version"]:
            raise ValueError(f"vLLM version {version} differs from pinned {config['vllm_version']}")
        manifest["runtime_versions"] = {name: importlib.metadata.version(name) for name in (
            "vllm", "torch", "transformers", "tokenizers")}
        manifest["process_id"] = os.getpid()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(manifest, stream, indent=2)
    if args.inspect_only:
        print(f"Verified {len(manifest['weight_shards'])} shards; manifest: {args.output}")
        return
    os.execv(sys.executable, [sys.executable, "-m", "vllm.entrypoints.cli.main", *server_arguments(config)])


if __name__ == "__main__":
    main()
