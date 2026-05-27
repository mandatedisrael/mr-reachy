"""Body language for Mr Reachy.

Maps emotion tags (from the chat model) to short head + antenna gestures, plus
ambient "listening" / "talking" motions. All angles stay well inside the SDK
safety envelope (head pitch/roll +/-40 deg, head yaw +/-180 deg); the SDK clamps
anyway, but we keep gestures gentle and natural.

Translations (x/y/z) are in millimetres, rotations in degrees.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field

from reachy_mini.utils import create_head_pose

# Antenna deflection (radians). The antennas double as expressive "ears".
A_UP = 0.7
A_DOWN = -0.6


@dataclass
class Frame:
    """One keyframe of a gesture."""

    head: dict = field(default_factory=dict)  # kwargs for create_head_pose (mm + degrees)
    antennas: tuple[float, float] = (0.0, 0.0)
    duration: float = 0.4


def _f(duration: float = 0.4, antennas: tuple[float, float] = (0.0, 0.0), **head) -> Frame:
    return Frame(head=head, antennas=antennas, duration=duration)


# Each gesture is a list of frames played in sequence and returning to rest.
GESTURES: dict[str, list[Frame]] = {
    "neutral": [_f(0.5)],
    "happy": [
        _f(0.25, (A_UP, A_DOWN), pitch=-8, z=10),
        _f(0.25, (A_DOWN, A_UP), pitch=-8, z=10),
        _f(0.3, (A_UP, A_DOWN)),
        _f(0.3),
    ],
    "excited": [
        _f(0.18, (A_UP, A_UP), pitch=-12, z=14),
        _f(0.18, (A_DOWN, A_DOWN), pitch=-4, z=4),
        _f(0.18, (A_UP, A_UP), pitch=-12, z=14),
        _f(0.3, (0.3, 0.3)),
    ],
    "curious": [
        _f(0.5, (A_UP, 0.1), roll=18, yaw=14),
        _f(0.5, (A_UP, 0.1), roll=18, yaw=14, pitch=-6),
    ],
    "thinking": [
        _f(0.7, (0.2, A_UP), yaw=-18, pitch=-12),
        _f(0.6, (0.2, A_UP), yaw=-10, pitch=-12),
    ],
    "confused": [
        _f(0.4, (A_UP, A_DOWN), roll=-20),
        _f(0.4, (A_DOWN, A_UP), roll=18),
        _f(0.4, (0.3, -0.3), roll=-10),
    ],
    "sad": [
        _f(0.8, (A_DOWN, A_DOWN), pitch=18, z=-10),
        _f(0.6, (A_DOWN, A_DOWN), pitch=14, z=-8),
    ],
    "surprised": [
        _f(0.15, (0.9, 0.9), pitch=-18, z=14),
        _f(0.5, (0.7, 0.7), pitch=-10, z=8),
    ],
    "nod_yes": [
        _f(0.25, pitch=18),
        _f(0.25, pitch=-10),
        _f(0.25, pitch=14),
        _f(0.25),
    ],
    "shake_no": [
        _f(0.25, (0.2, 0.2), yaw=22),
        _f(0.25, (0.2, 0.2), yaw=-22),
        _f(0.25, (0.2, 0.2), yaw=16),
        _f(0.25),
    ],
}

# Resting / awake neutral pose.
REST = create_head_pose(mm=True, degrees=True)


def _pose(frame: Frame):
    return create_head_pose(mm=True, degrees=True, **frame.head)


def play(reachy, emotion: str, stop_event: threading.Event | None = None) -> None:
    """Play a named gesture sequence. Blocks until finished (or stop_event set)."""
    frames = GESTURES.get(emotion, GESTURES["neutral"])
    for frame in frames:
        if stop_event is not None and stop_event.is_set():
            break
        reachy.goto_target(
            head=_pose(frame), antennas=list(frame.antennas), duration=frame.duration
        )


def go_rest(reachy, duration: float = 0.4) -> None:
    reachy.goto_target(head=REST, antennas=[0.0, 0.0], duration=duration)
