from __future__ import annotations

import argparse
from typing import Iterable, Optional, Tuple, Union

import cv2


def add_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera", default="0", help="Camera index, device path, or GStreamer pipeline")
    parser.add_argument("--width", type=int, default=1280, help="Capture width")
    parser.add_argument("--height", type=int, default=720, help="Capture height")
    parser.add_argument("--fps", type=int, default=30, help="Capture FPS")
    parser.add_argument(
        "--backend",
        choices=("auto", "v4l2", "gstreamer", "default"),
        default="auto",
        help="OpenCV camera backend, default: auto",
    )
    parser.add_argument(
        "--fourcc",
        default="",
        help="Optional pixel format such as MJPG, YUYV, or NV12",
    )


def camera_id(value: str) -> Union[int, str]:
    try:
        return int(value)
    except ValueError:
        return value


def _backend_candidates(name: str) -> Iterable[Tuple[str, Optional[int]]]:
    if name == "v4l2":
        return (("v4l2", cv2.CAP_V4L2),)
    if name == "gstreamer":
        return (("gstreamer", cv2.CAP_GSTREAMER),)
    if name == "default":
        return (("default", None),)
    return (
        ("v4l2", cv2.CAP_V4L2),
        ("default", None),
        ("gstreamer", cv2.CAP_GSTREAMER),
    )


def _create_capture(source: Union[int, str], backend: Optional[int]) -> cv2.VideoCapture:
    if backend is None:
        return cv2.VideoCapture(source)
    return cv2.VideoCapture(source, backend)


def _set_capture_properties(cap: cv2.VideoCapture, args: argparse.Namespace) -> None:
    if args.fourcc:
        fourcc = cv2.VideoWriter_fourcc(*args.fourcc[:4])
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def open_camera(args: argparse.Namespace) -> cv2.VideoCapture:
    source = args.camera if args.backend == "gstreamer" else camera_id(args.camera)
    attempted = []

    for backend_name, backend_id in _backend_candidates(args.backend):
        cap = _create_capture(source, backend_id)
        _set_capture_properties(cap, args)
        if cap.isOpened():
            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            print(
                f"opened camera {args.camera} with {backend_name}: "
                f"{actual_width}x{actual_height} {actual_fps:.1f}fps"
            )
            return cap
        attempted.append(backend_name)
        cap.release()

    raise RuntimeError(
        f"failed to open camera: {args.camera}; tried backends: {', '.join(attempted)}"
    )
