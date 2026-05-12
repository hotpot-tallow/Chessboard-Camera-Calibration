from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture chessboard calibration images from a camera.")
    parser.add_argument("--camera", default="0", help="Camera index or device path, default: 0")
    parser.add_argument("--width", type=int, default=1280, help="Capture width")
    parser.add_argument("--height", type=int, default=720, help="Capture height")
    parser.add_argument("--fps", type=int, default=30, help="Capture FPS")
    parser.add_argument("--output", default="images", help="Directory to save captured images")
    parser.add_argument("--prefix", default="chessboard", help="Saved image filename prefix")
    parser.add_argument("--mirror", action="store_true", help="Mirror preview and saved images")
    return parser.parse_args()


def camera_id(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def open_camera(args: argparse.Namespace) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(camera_id(args.camera))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f"failed to open camera: {args.camera}")
    return cap


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = open_camera(args)
    saved_count = len(list(output_dir.glob(f"{args.prefix}_*.jpg")))

    print("Press Space or s to save an image.")
    print("Press q or Esc to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed")
                time.sleep(0.1)
                continue

            if args.mirror:
                frame = cv2.flip(frame, 1)

            preview = frame.copy()
            cv2.putText(
                preview,
                f"saved: {saved_count}  Space/s: save  q/Esc: quit",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("capture chessboard", preview)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break
            if key in (ord("s"), 32):
                saved_count += 1
                path = output_dir / f"{args.prefix}_{saved_count:03d}.jpg"
                cv2.imwrite(str(path), frame)
                print(f"saved {path}")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
