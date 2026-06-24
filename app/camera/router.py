import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(prefix="/camera", tags=["camera"])

MEDIAMTX_WEBRTC_URL = os.getenv("MEDIAMTX_WEBRTC_URL", "http://127.0.0.1:8889/stream1")
MEDIAMTX_HLS_URL = os.getenv("MEDIAMTX_HLS_URL", "http://127.0.0.1:8888/stream1")


@router.get("", response_class=HTMLResponse)
def camera_page() -> str:
    return f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VIGI C440-W Stream</title>
  <style>
    :root {{ color-scheme: dark; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #111; color: #f4f4f4; }}
    header {{ padding: 16px 20px; border-bottom: 1px solid #333; }}
    h1 {{ margin: 0; font-size: 20px; }}
    main {{ padding: 16px; max-width: 1180px; margin: 0 auto; }}
    h2 {{ margin: 0 0 8px; font-size: 15px; color: #cfcfcf; }}
    iframe {{ width: 100%; height: min(72vh, 720px); background: #000; border: 1px solid #333; display: block; }}
    .meta {{ color: #aaa; font-size: 13px; margin-top: 8px; line-height: 1.45; }}
    a {{ color: #8fc7ff; }}
  </style>
</head>
<body>
  <header><h1>VIGI C440-W Camera</h1></header>
  <main>
    <section>
      <h2>Stream1 WebRTC</h2>
      <iframe src="{MEDIAMTX_WEBRTC_URL}" allow="autoplay; fullscreen"></iframe>
      <div class="meta">MediaMTX proxies stream1 as H.264. WebRTC: <a href="{MEDIAMTX_WEBRTC_URL}" target="_blank">{MEDIAMTX_WEBRTC_URL}</a> / HLS: <a href="{MEDIAMTX_HLS_URL}" target="_blank">{MEDIAMTX_HLS_URL}</a></div>
    </section>
  </main>
</body>
</html>
"""


@router.get("/status")
def camera_status():
    return {
        "mode": "mediamtx",
        "webrtc_url": MEDIAMTX_WEBRTC_URL,
        "hls_url": MEDIAMTX_HLS_URL,
    }
