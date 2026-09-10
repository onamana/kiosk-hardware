#!/usr/bin/env python3
"""JBL Flip 7 물리 버튼(볼륨+/-, 음소거)을 PipeWire 기본 출력 볼륨에 연결한다.

USB로 연결된 JBL Flip 7은 표준 멀티미디어 키보드로 인식되어 KEY_VOLUMEUP/
KEY_VOLUMEDOWN/KEY_MUTE 이벤트를 보낸다. 데스크톱 세션의 gnome-settings-daemon이
없으면(키오스크 환경) 이 키 입력이 아무 데도 연결되지 않으므로, 이 스크립트가
그 역할을 대신해 항상 동작하게 한다. 대상은 이름으로 매번 다시 찾으므로 재부팅·
재연결로 PipeWire 노드 id가 바뀌어도 계속 올바른 스피커를 조절한다.
"""

from __future__ import annotations

import re
import subprocess
import time

from evdev import InputDevice, categorize, ecodes

DEVICE_PATH = "/dev/input/by-id/usb-Harman_JBL_Flip_7_RS0290-KP0431707-event-if00"
SINK_NAME_HINT = "harman_jbl_flip_7"
STEP = 0.05


def _find_sink_id() -> str | None:
    result = subprocess.run(["wpctl", "status", "-n"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        low = line.lower()
        if "alsa_output" not in low or SINK_NAME_HINT not in low:
            continue
        match = re.search(r"(\d+)\.\s*alsa_output", line, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _adjust(delta: float) -> None:
    sink = _find_sink_id()
    if sink is None:
        return
    sign = "+" if delta > 0 else "-"
    subprocess.run(["wpctl", "set-volume", sink, f"{abs(delta)}{sign}"], check=False)


def _toggle_mute() -> None:
    sink = _find_sink_id()
    if sink is None:
        return
    subprocess.run(["wpctl", "set-mute", sink, "toggle"], check=False)


def main() -> None:
    while True:
        try:
            dev = InputDevice(DEVICE_PATH)
            for event in dev.read_loop():
                if event.type != ecodes.EV_KEY or event.value != 1:  # key-down만 처리
                    continue
                key = categorize(event)
                if key.keycode == "KEY_VOLUMEUP":
                    _adjust(STEP)
                elif key.keycode == "KEY_VOLUMEDOWN":
                    _adjust(-STEP)
                elif key.keycode == "KEY_MUTE":
                    _toggle_mute()
        except (OSError, FileNotFoundError):
            # 스피커가 뽑혀 있는 동안은 장치 노드가 없다 — 재연결될 때까지 재시도.
            time.sleep(2)


if __name__ == "__main__":
    main()
