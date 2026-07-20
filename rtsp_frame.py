import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, TypedDict

import cv2
import pymysql

from app.config.settings import settings


# =========================
# 설정값
# =========================

INPUT_FPS_ASSUMED = 60
CAPTURE_INTERVAL_SEC = 1.0
OUTPUT_MAX_EDGE = 1280
JPEG_QUALITY = 90
RECONNECT_DELAY_SEC = 3
OUTPUT_FRAME_NAME = "frame_000.jpg"


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
    output_dirs: set[Path] = set()
    for row in rows:
        output_dir = Path(row["frame_dir"]).expanduser().resolve()
        if output_dir in output_dirs:
            raise RuntimeError(
                f"여러 카메라가 같은 frame_dir을 사용합니다: {output_dir}"
            )
        output_dirs.add(output_dir)
        cameras.append(
            {
                "camera_id": f"CAM-{row['cctv_id']}",
                "rtsp_url": row["rtsp_url"],
                "output_dir": output_dir,
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
# 최신 프레임 한 장 수집
# =========================

def collect_latest_frame(
    cap: cv2.VideoCapture,
    duration_sec: float = CAPTURE_INTERVAL_SEC,
) -> Any | None:
    """
    RTSP를 계속 비우면서 지정 시간 동안의 최신 프레임 한 장만 반환한다.

    프레임을 모두 리스트에 쌓지 않으므로 카메라 해상도/FPS와 무관하게
    중간 프레임은 grab()으로 비우고 마지막 프레임만 retrieve()해 ndarray로
    만든다. 따라서 RTSP/FFmpeg 버퍼 지연을 막으면서 Python에는 원본 한 장만
    전달하고, 매 프레임의 BGR 변환/메모리 복사도 피한다.
    """
    grabbed = False
    deadline = time.monotonic() + max(0.0, duration_sec)

    while time.monotonic() < deadline:
        if not cap.grab():
            break
        grabbed = True

    if not grabbed:
        return None
    ret, frame = cap.retrieve()
    if not ret or frame is None:
        return None
    return frame


# =========================
# VLM 입력 크기로 축소
# =========================

def resize_for_vlm(frame: Any, max_edge: int = OUTPUT_MAX_EDGE) -> Any:
    """종횡비를 유지하면서 장축이 max_edge를 넘을 때만 축소한다."""
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= max_edge:
        return frame

    scale = max_edge / longest
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    return cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=cv2.INTER_AREA,
    )


# =========================
# 원자적 최신 프레임 게시
# =========================

def _remove_orphaned_files(output_dir: Path) -> None:
    """이전 비정상 종료의 임시파일과 구버전 추가 프레임을 정리한다."""
    for path in output_dir.glob(f".{OUTPUT_FRAME_NAME}.*.tmp"):
        path.unlink(missing_ok=True)
    for path in output_dir.glob("frame_*.jpg"):
        if path.name != OUTPUT_FRAME_NAME:
            path.unlink(missing_ok=True)


def publish_frame_atomic(frame: Any, output_dir: Path) -> Path:
    """
    완성된 JPEG 한 장을 frame_000.jpg로 원자적으로 게시한다.

    임시파일을 최종 파일과 같은 디렉터리에 만들기 때문에 os.replace가
    같은 tmpfs 안의 원자적 rename으로 동작한다. 교체 전 독자는 기존 JPEG를,
    교체 후 독자는 새 JPEG 전체를 보며 빈 파일/부분 파일은 노출되지 않는다.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )
    if not success:
        raise RuntimeError("프레임 JPEG 인코딩 실패")

    final_path = output_dir / OUTPUT_FRAME_NAME
    fd: int | None = None
    temp_path: Path | None = None

    try:
        fd, temp_name = tempfile.mkstemp(
            dir=output_dir,
            prefix=f".{OUTPUT_FRAME_NAME}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as file_obj:
            fd = None
            file_obj.write(encoded.tobytes())
        os.replace(temp_path, final_path)
        temp_path = None
    finally:
        if fd is not None:
            os.close(fd)
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return final_path


# =========================
# 카메라별 메인 루프
# =========================

def capture_camera_loop(camera_id: str, rtsp_url: str, output_dir: Path) -> None:
    print(f"[{camera_id}] RTSP 프레임 수집 시작")
    print(f"[{camera_id}] 저장 디렉터리: {output_dir.resolve()}")

    prepared = False
    cap: cv2.VideoCapture | None = None

    while True:
        try:
            if not prepared:
                output_dir.mkdir(parents=True, exist_ok=True)
                _remove_orphaned_files(output_dir)
                prepared = True

            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                cap = open_rtsp_capture(rtsp_url)
                if not cap.isOpened():
                    raise RuntimeError("RTSP 연결 실패")

            latest = collect_latest_frame(cap)
            if latest is None:
                raise RuntimeError("프레임 수신 실패")

            resized = resize_for_vlm(latest)
            published = publish_frame_atomic(resized, output_dir)
            height, width = resized.shape[:2]
            print(
                f"[{camera_id}] 최신 프레임 게시: {published.name} "
                f"({width}x{height})"
            )
        except Exception as exc:  # 한 번의 장애로 카메라 스레드가 죽지 않게 재시도
            print(f"[{camera_id}] {exc}. {RECONNECT_DELAY_SEC}초 후 재시도합니다.")
            if cap is not None:
                cap.release()
                cap = None
            time.sleep(RECONNECT_DELAY_SEC)


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
