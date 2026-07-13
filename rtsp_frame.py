import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import TypedDict

import cv2
import pymysql

from app.config.settings import settings


# =========================
# 설정값
# =========================

INPUT_FPS_ASSUMED = 60
OUTPUT_FRAME_COUNT = 2
JPEG_QUALITY = 90
RECONNECT_DELAY_SEC = 3


class CameraConfig(TypedDict):
    camera_id: str
    rtsp_url: str
    output_dir: Path


def load_cameras_from_db() -> list[CameraConfig]:
    db_config = {
        "host": settings.mariadb_host,
        "user": settings.mariadb_user,
        "password": settings.mariadb_password,
        "database": settings.mariadb_db_name,
        "port": settings.mariadb_port,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }

    with pymysql.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT cctv_id, rtsp_url, frame_dir
                FROM cctv_info
                WHERE rtsp_url IS NOT NULL
                  AND rtsp_url <> ''
                  AND frame_dir IS NOT NULL
                  AND frame_dir <> ''
                ORDER BY cctv_id
                """
            )
            rows = cursor.fetchall()

    cameras = []
    for row in rows:
        cameras.append(
            {
                "camera_id": f"CAM-{row['cctv_id']}",
                "rtsp_url": row["rtsp_url"],
                "output_dir": Path(row["frame_dir"]).expanduser(),
            }
        )

    return cameras


# =========================
# RTSP 연결
# =========================

def open_rtsp_capture(rtsp_url: str) -> cv2.VideoCapture:
    """
    RTSP 카메라에 연결한다.
    """
    # TCP 방식 RTSP 사용. UDP보다 안정적인 경우가 많음.
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    # 일부 환경에서만 적용됨. 안 먹어도 문제는 없음.
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, INPUT_FPS_ASSUMED)

    return cap


# =========================
# 1초 동안 프레임 수집
# =========================

def collect_frames_for_one_second(cap: cv2.VideoCapture) -> list:
    """
    RTSP에서 약 1초 동안 프레임을 읽어서 리스트로 반환한다.
    """
    frames = []
    start_time = time.monotonic()

    while time.monotonic() - start_time < 1.0:
        ret, frame = cap.read()

        if not ret or frame is None:
            break

        frames.append(frame)

    return frames


# =========================
# 수집한 프레임 중 30장 선택
# =========================

def select_30_frames(frames: list) -> list:
    """
    1초 동안 들어온 프레임 중 30장을 고른다.

    예:
    - 60장이 들어오면 거의 2장 중 1장 선택
    - 45장이 들어오면 전체 구간에서 균등하게 30장 선택
    - 30장 이하면 그대로 사용
    """
    if len(frames) <= OUTPUT_FRAME_COUNT:
        return frames

    step = len(frames) / OUTPUT_FRAME_COUNT

    selected = []
    for i in range(OUTPUT_FRAME_COUNT):
        index = int(i * step)
        selected.append(frames[index])

    return selected


# =========================
# 디렉터리 교체 저장
# =========================

def replace_output_dir_with_frames(frames: list, output_dir: Path):
    """
    기존 output_dir 내부 프레임을 삭제하고,
    새 프레임 30장을 저장한다.

    중간에 저장 실패했을 때 기존 폴더를 최대한 덜 망가뜨리기 위해
    임시 폴더에 먼저 저장한 뒤 교체한다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="frames_tmp_"))

    try:
        # 1. 임시 디렉터리에 먼저 새 프레임 저장
        for i, frame in enumerate(frames):
            filename = temp_dir / f"frame_{i:03d}.jpg"

            success = cv2.imwrite(
                str(filename),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )

            if not success:
                raise RuntimeError(f"프레임 저장 실패: {filename}")

        # 2. 기존 디렉터리 안의 파일 삭제
        for old_file in output_dir.iterdir():
            if old_file.is_file():
                old_file.unlink()
            elif old_file.is_dir():
                shutil.rmtree(old_file)

        # 3. 새 파일을 output_dir로 이동
        for new_file in temp_dir.iterdir():
            shutil.move(str(new_file), str(output_dir / new_file.name))

    finally:
        # 임시 디렉터리 정리
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


# =========================
# 카메라별 메인 루프
# =========================

def capture_camera_loop(camera_id: str, rtsp_url: str, output_dir: Path) -> None:
    print(f"[{camera_id}] RTSP 프레임 수집 시작")
    print(f"[{camera_id}] 저장 디렉터리: {output_dir.resolve()}")

    cap = open_rtsp_capture(rtsp_url)

    while True:
        if not cap.isOpened():
            print(f"[{camera_id}] RTSP 연결 실패. 재연결 시도 중...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(rtsp_url)
            continue

        frames = collect_frames_for_one_second(cap)

        if len(frames) == 0:
            print(f"[{camera_id}] 프레임 수신 실패. 재연결 시도 중...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(rtsp_url)
            continue

        selected_frames = select_30_frames(frames)

        replace_output_dir_with_frames(selected_frames, output_dir)

        print(
            f"[{camera_id}] 수신 프레임: {len(frames)}장 -> "
            f"저장 프레임: {len(selected_frames)}장"
        )


# =========================
# 메인 루프
# =========================

def main():
    print("RTSP 멀티카메라 프레임 수집 시작")

    cameras = load_cameras_from_db()
    if not cameras:
        raise RuntimeError("cctv_info 테이블에서 사용할 카메라 설정을 찾지 못했습니다.")

    threads = []
    for camera in cameras:
        thread = threading.Thread(
            target=capture_camera_loop,
            args=(camera["camera_id"], camera["rtsp_url"], camera["output_dir"]),
            daemon=False,
            name=f"rtsp-frame-{camera['camera_id']}",
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
