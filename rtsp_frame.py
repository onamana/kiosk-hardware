import os
import cv2
import time
import shutil
import tempfile
from pathlib import Path


# =========================
# 설정값
# =========================

RTSP_URL = "rtsp://admin:ekthf123@172.16.0.243:554/stream1"

OUTPUT_DIR = Path("./frames")

INPUT_FPS_ASSUMED = 60
OUTPUT_FRAME_COUNT = 30

JPEG_QUALITY = 90

RECONNECT_DELAY_SEC = 3


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
# 메인 루프
# =========================

def main():
    print("RTSP 프레임 수집 시작")
    print(f"저장 디렉터리: {OUTPUT_DIR.resolve()}")

    cap = open_rtsp_capture(RTSP_URL)

    while True:
        if not cap.isOpened():
            print("RTSP 연결 실패. 재연결 시도 중...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(RTSP_URL)
            continue

        frames = collect_frames_for_one_second(cap)

        if len(frames) == 0:
            print("프레임 수신 실패. 재연결 시도 중...")
            cap.release()
            time.sleep(RECONNECT_DELAY_SEC)
            cap = open_rtsp_capture(RTSP_URL)
            continue

        selected_frames = select_30_frames(frames)

        replace_output_dir_with_frames(selected_frames, OUTPUT_DIR)

        print(
            f"수신 프레임: {len(frames)}장 → 저장 프레임: {len(selected_frames)}장"
        )


if __name__ == "__main__":
    main()