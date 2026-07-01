import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import cv2


RTSP_URL1 = "rtsp://admin:ekthf123@172.16.0.243:554/stream1"
RTSP_URL2 = "rtsp://admin:ekthf123@172.16.0.20:554/stream1"

CAMERAS = {
    "CAM-1": {
        "rtsp_url": RTSP_URL1,
        "output_dir": Path("./frame1"),
    },
    "CAM-3": {
        "rtsp_url": RTSP_URL2,
        "output_dir": Path("./frame2"),
    },
}

INPUT_FPS_ASSUMED = 60
OUTPUT_FRAME_COUNT = 30
JPEG_QUALITY = 90
RECONNECT_DELAY_SEC = 3


def open_rtsp_capture(rtsp_url: str) -> cv2.VideoCapture:
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, INPUT_FPS_ASSUMED)
    return cap


def collect_frames_for_one_second(cap: cv2.VideoCapture) -> list:
    frames = []
    start_time = time.monotonic()

    while time.monotonic() - start_time < 1.0:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        frames.append(frame)

    return frames


def select_30_frames(frames: list) -> list:
    if len(frames) <= OUTPUT_FRAME_COUNT:
        return frames

    step = len(frames) / OUTPUT_FRAME_COUNT
    return [frames[int(i * step)] for i in range(OUTPUT_FRAME_COUNT)]


def replace_output_dir_with_frames(frames: list, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="frames_tmp_"))

    try:
        for i, frame in enumerate(frames):
            filename = temp_dir / f"frame_{i:03d}.jpg"
            success = cv2.imwrite(
                str(filename),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )
            if not success:
                raise RuntimeError(f"failed to save frame: {filename}")

        for old_file in output_dir.iterdir():
            if old_file.is_file():
                old_file.unlink()
            elif old_file.is_dir():
                shutil.rmtree(old_file)

        for new_file in temp_dir.iterdir():
            shutil.move(str(new_file), str(output_dir / new_file.name))
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def capture_camera_loop(camera_id: str, rtsp_url: str, output_dir: Path) -> None:
    print(f"[{camera_id}] RTSP frame capture start")
    print(f"[{camera_id}] output directory: {output_dir.resolve()}")

    cap = open_rtsp_capture(rtsp_url)

    while True:
        if not cap.isOpened():
            print(f"[{camera_id}] RTSP connection failed. Reconnecting...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(rtsp_url)
            continue

        frames = collect_frames_for_one_second(cap)
        if len(frames) == 0:
            print(f"[{camera_id}] no frames received. Reconnecting...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(rtsp_url)
            continue

        selected_frames = select_30_frames(frames)
        replace_output_dir_with_frames(selected_frames, output_dir)
        print(
            f"[{camera_id}] received frames: {len(frames)} -> "
            f"saved frames: {len(selected_frames)}"
        )


def main() -> None:
    print("RTSP multi-camera frame capture start")
    threads = []

    for camera_id, camera in CAMERAS.items():
        thread = threading.Thread(
            target=capture_camera_loop,
            args=(camera_id, camera["rtsp_url"], camera["output_dir"]),
            daemon=False,
            name=f"rtsp-frame-{camera_id}",
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
