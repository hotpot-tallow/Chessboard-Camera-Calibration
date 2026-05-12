from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Tuple, Union

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview live camera undistortion with calibration JSON.")
    parser.add_argument("--camera", default="0", help="Camera index or device path, default: 0")
    parser.add_argument("--width", type=int, default=1280, help="Capture width")
    parser.add_argument("--height", type=int, default=720, help="Capture height")
    parser.add_argument("--fps", type=int, default=30, help="Capture FPS")
    parser.add_argument("--calibration", default="camera_calibration.json", help="Calibration JSON path")
    parser.add_argument("--alpha", type=float, default=0.0, help="Free scaling parameter, 0 crops black borders, 1 keeps all pixels")
    return parser.parse_args()


def camera_id(value: str) -> Union[int, str]:
    try:
        return int(value)
    except ValueError:
        return value


def load_calibration(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    data = json.loads(path.read_text(encoding="utf-8"))
    camera = data["camera"]
    camera_matrix = np.array(camera["camera_matrix"], dtype=np.float64)
    dist_coeffs = np.array(camera["distortion_coefficients"], dtype=np.float64)
    return camera_matrix, dist_coeffs


def main() -> None:
    args = parse_args()
    camera_matrix, dist_coeffs = load_calibration(Path(args.calibration))

    cap = cv2.VideoCapture(camera_id(args.camera))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f"failed to open camera: {args.camera}")

    new_matrix, roi = cv2.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (args.width, args.height),
        args.alpha,
        (args.width, args.height),
    )

    print("Press q or Esc to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed")
                time.sleep(0.1)
                continue

            undistorted = cv2.undistort(frame, camera_matrix, dist_coeffs, None, new_matrix)
            x, y, w, h = roi
            if w > 0 and h > 0:
                cv2.rectangle(undistorted, (x, y), (x + w, y + h), (0, 255, 0), 2)

            combined = np.hstack((frame, undistorted))
            cv2.putText(
                combined,
                "left: raw    right: undistorted    q/Esc: quit",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("undistort preview", combined)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
