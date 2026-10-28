"""Explicit B-line text window; keep complete tool exchanges and latest RGB state."""

import hashlib
import json


def select_history(messages: list[dict], turns: int) -> tuple[list[dict], dict]:
    if turns < 0:
        raise ValueError("History turns must be non-negative")
    starts = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    keep = set(range(len(messages)))
    if turns and len(starts) > turns:
        keep = set(range(starts[0])) | set(range(starts[-turns], len(messages)))
        # Errors may span many turns. Preserve the last actual observation, even
        # when it precedes the text window, with its producing tool-call group.
        latest_image = max((i for i, m in enumerate(messages)
                            if isinstance(m.get("content"), list)
                            and any(b.get("type") == "image_path" for b in m["content"])),
                           default=-1)
        if latest_image >= starts[0]:
            group = max(i for i in starts if i <= latest_image)
            end = next((i for i in starts if i > group), len(messages))
            keep.update(range(group, end))
    omitted = [i for i in range(len(messages)) if i not in keep]
    audit = dict(policy="all_text" if not turns else "recent_complete_turns",
                 turns=turns, retained_message_indices=sorted(keep),
                 omitted_messages=[dict(index=i, sha256=hashlib.sha256(
                     json.dumps(messages[i], sort_keys=True).encode()).hexdigest()) for i in omitted])
    selected = [dict(m) for i, m in enumerate(messages) if i in keep]
    if omitted:
        notice = (f"\nExplicit history window: {len(omitted)} earlier messages are omitted from this request. "
                  f"The initial instruction, latest observation and last {turns} complete exchanges are retained. "
                  "Python variables persist unchanged. Use stored variables for earlier visually observed facts; "
                  "do not assume omitted text or old images remain visible.")
        # The runner always supplies a system instruction. Keep its role and
        # tool protocol intact; do not insert an unmatched user/tool message.
        system = next((m for m in selected if m.get("role") == "system"), None)
        if system is None:
            raise ValueError("Windowed history requires a system instruction")
        content = system.get("content", "")
        system["content"] = content + notice if isinstance(content, str) else [*content, dict(type="text", text=notice)]
    return selected, audit
