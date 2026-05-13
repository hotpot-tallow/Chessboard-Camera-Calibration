from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from camera_open import add_camera_args, open_camera


Metrics = Tuple[float, float, float, float]


@dataclass(frozen=True)
class Sample:
    object_points: np.ndarray
    image_points: np.ndarray
    metrics: Metrics


@dataclass(frozen=True)
class CalibrationResult:
    rms: float
    mean_error_px: float
    camera_matrix: np.ndarray
    dist_coeffs: np.ndarray
    rvecs: List[np.ndarray]
    tvecs: List[np.ndarray]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime chessboard camera calibration.")
    add_camera_args(parser)
    parser.add_argument("--cols", type=int, required=True, help="Number of inner corners per row")
    parser.add_argument("--rows", type=int, required=True, help="Number of inner corners per column")
    parser.add_argument("--square-size", type=float, required=True, help="Chessboard square size in meters")
    parser.add_argument("--output", default="camera_calibration.json", help="Output JSON file")
    parser.add_argument("--min-samples", type=int, default=30, help="Samples required before auto calibration")
    parser.add_argument("--sample-delay", type=float, default=0.8, help="Minimum seconds between auto samples")
    parser.add_argument("--sample-distance", type=float, default=0.14, help="Minimum metric distance between samples")
    parser.add_argument("--manual", action="store_true", help="Disable automatic sampling")
    parser.add_argument("--mirror", action="store_true", help="Mirror camera frames")
    return parser.parse_args()


def build_object_points(cols: int, rows: int, square_size: float) -> np.ndarray:
    points = np.zeros((rows * cols, 3), np.float32)
    points[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    points *= square_size
    return points


def detect_chessboard(
    frame: np.ndarray,
    pattern_size: Tuple[int, int],
) -> Optional[np.ndarray]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    if not found:
        return None

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)


def sample_metrics(corners: np.ndarray, image_size: Tuple[int, int], cols: int, rows: int) -> Metrics:
    width, height = image_size
    pts = corners.reshape(-1, 2)
    center = pts.mean(axis=0)

    x = float(center[0] / max(width, 1))
    y = float(center[1] / max(height, 1))

    rect = cv2.minAreaRect(pts.astype(np.float32))
    rect_w, rect_h = rect[1]
    area_ratio = max(rect_w * rect_h, 1.0) / max(width * height, 1)
    size = float(min(1.0, math.sqrt(area_ratio) * 2.0))

    grid = corners.reshape(rows, cols, 2)
    top = max(float(np.linalg.norm(grid[0, -1] - grid[0, 0])), 1.0)
    bottom = max(float(np.linalg.norm(grid[-1, -1] - grid[-1, 0])), 1.0)
    left = max(float(np.linalg.norm(grid[-1, 0] - grid[0, 0])), 1.0)
    right = max(float(np.linalg.norm(grid[-1, -1] - grid[0, -1])), 1.0)
    skew_raw = abs(math.log(top / bottom)) + abs(math.log(left / right))
    skew = float(min(1.0, skew_raw / math.log(3.0)))

    return x, y, size, skew


def metric_distance(a: Metrics, b: Metrics) -> float:
    weights = np.array([1.0, 1.0, 1.4, 1.2], dtype=np.float32)
    return float(np.linalg.norm((np.array(a) - np.array(b)) * weights))


def sample_is_useful(
    metrics: Metrics,
    samples: List[Sample],
    min_distance: float,
) -> bool:
    if not samples:
        return True
    return min(metric_distance(metrics, sample.metrics) for sample in samples) >= min_distance


def coverage(samples: List[Sample]) -> Dict[str, float]:
    if not samples:
        return {"x": 0.0, "y": 0.0, "size": 0.0, "skew": 0.0}

    values = np.array([sample.metrics for sample in samples], dtype=np.float32)
    x_range = float(values[:, 0].max() - values[:, 0].min())
    y_range = float(values[:, 1].max() - values[:, 1].min())
    size_range = float(values[:, 2].max() - values[:, 2].min())
    skew_max = float(values[:, 3].max())

    return {
        "x": min(1.0, x_range / 0.65),
        "y": min(1.0, y_range / 0.65),
        "size": min(1.0, size_range / 0.35),
        "skew": min(1.0, skew_max / 0.45),
    }


def reprojection_error(
    object_points: List[np.ndarray],
    image_points: List[np.ndarray],
    rvecs: List[np.ndarray],
    tvecs: List[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> float:
    total_error = 0.0
    total_points = 0
    for objp, imgp, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        projected, _ = cv2.projectPoints(objp, rvec, tvec, camera_matrix, dist_coeffs)
        error = cv2.norm(imgp, projected, cv2.NORM_L2)
        total_error += error * error
        total_points += len(projected)
    return float(np.sqrt(total_error / total_points))


def calibrate(samples: List[Sample], image_size: Tuple[int, int]) -> CalibrationResult:
    object_points = [sample.object_points for sample in samples]
    image_points = [sample.image_points for sample in samples]
    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points,
        image_points,
        image_size,
        None,
        None,
    )
    mean_error = reprojection_error(object_points, image_points, rvecs, tvecs, camera_matrix, dist_coeffs)
    return CalibrationResult(float(rms), mean_error, camera_matrix, dist_coeffs, rvecs, tvecs)


def write_result(
    output_path: Path,
    result: CalibrationResult,
    samples: List[Sample],
    args: argparse.Namespace,
    image_size: Tuple[int, int],
) -> None:
    fx = float(result.camera_matrix[0, 0])
    fy = float(result.camera_matrix[1, 1])
    cx = float(result.camera_matrix[0, 2])
    cy = float(result.camera_matrix[1, 2])

    payload = {
        "image_width": image_size[0],
        "image_height": image_size[1],
        "pattern": {
            "cols": args.cols,
            "rows": args.rows,
            "square_size_m": args.square_size,
        },
        "camera": {
            "fx": fx,
            "fy": fy,
            "cx": cx,
            "cy": cy,
            "camera_matrix": result.camera_matrix.tolist(),
            "distortion_coefficients": result.dist_coeffs.ravel().tolist(),
        },
        "quality": {
            "rms": result.rms,
            "mean_reprojection_error_px": result.mean_error_px,
            "valid_image_count": len(samples),
            "coverage": coverage(samples),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    np.savez(
        output_path.with_suffix(".npz"),
        camera_matrix=result.camera_matrix,
        dist_coeffs=result.dist_coeffs,
        image_width=image_size[0],
        image_height=image_size[1],
        rms=result.rms,
        mean_reprojection_error_px=result.mean_error_px,
    )


def draw_bar(frame: np.ndarray, label: str, value: float, origin: Tuple[int, int]) -> None:
    x, y = origin
    width = 190
    height = 14
    cv2.putText(frame, label, (x, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.rectangle(frame, (x + 52, y), (x + 52 + width, y + height), (80, 80, 80), 1)
    fill = int(width * max(0.0, min(1.0, value)))
    color = (0, 200, 80) if value >= 0.8 else (0, 180, 240)
    cv2.rectangle(frame, (x + 53, y + 1), (x + 52 + fill, y + height - 1), color, -1)


def draw_overlay(
    frame: np.ndarray,
    samples: List[Sample],
    found: bool,
    result: Optional[CalibrationResult],
    args: argparse.Namespace,
    status: str,
) -> None:
    cov = coverage(samples)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 150), (0, 0, 0), -1)
    cv2.putText(
        frame,
        f"samples {len(samples)}/{args.min_samples}  board {'OK' if found else 'not found'}",
        (16, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0) if found else (0, 180, 255),
        2,
        cv2.LINE_AA,
    )
    draw_bar(frame, "X", cov["x"], (16, 46))
    draw_bar(frame, "Y", cov["y"], (16, 68))
    draw_bar(frame, "Size", cov["size"], (16, 90))
    draw_bar(frame, "Skew", cov["skew"], (16, 112))

    controls = "Space/a add  c calibrate  s save  r reset  u undistort  q quit"
    cv2.putText(frame, controls, (300, 63), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
    cv2.putText(frame, status, (300, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1, cv2.LINE_AA)

    if result is not None:
        fx = result.camera_matrix[0, 0]
        fy = result.camera_matrix[1, 1]
        cx = result.camera_matrix[0, 2]
        cy = result.camera_matrix[1, 2]
        text = f"rms {result.rms:.3f}  err {result.mean_error_px:.3f}px  fx {fx:.1f} fy {fy:.1f} cx {cx:.1f} cy {cy:.1f}"
        cv2.putText(frame, text, (300, 124), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 255, 120), 1, cv2.LINE_AA)


def main() -> None:
    args = parse_args()
    cap = open_camera(args)
    image_size = (args.width, args.height)
    pattern_size = (args.cols, args.rows)
    object_template = build_object_points(args.cols, args.rows, args.square_size)
    output_path = Path(args.output)

    samples: List[Sample] = []
    result: Optional[CalibrationResult] = None
    last_sample_time = 0.0
    status = "move chessboard around the image"
    show_undistorted = False

    print("Realtime chessboard calibration")
    print("Space/a add sample, c calibrate, s save, r reset, u undistort, q quit")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                status = "camera read failed"
                time.sleep(0.1)
                continue

            if args.mirror:
                frame = cv2.flip(frame, 1)

            corners = detect_chessboard(frame, pattern_size)
            found = corners is not None
            display = frame.copy()

            if found and corners is not None:
                cv2.drawChessboardCorners(display, pattern_size, corners, found)
                metrics = sample_metrics(corners, image_size, args.cols, args.rows)
                now = time.monotonic()
                useful = sample_is_useful(metrics, samples, args.sample_distance)

                if not args.manual and useful and now - last_sample_time >= args.sample_delay:
                    samples.append(Sample(object_template.copy(), corners.copy(), metrics))
                    last_sample_time = now
                    status = f"auto added sample {len(samples)}"
                    if len(samples) >= args.min_samples:
                        result = calibrate(samples, image_size)
                        status = "calibrated; press s to save"

                if not useful:
                    status = "try a new position, size, or tilt"

            if show_undistorted and result is not None:
                display = cv2.undistort(display, result.camera_matrix, result.dist_coeffs)

            draw_overlay(display, samples, found, result, args, status)
            cv2.imshow("realtime camera calibration", display)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break
            if key in (ord(" "), ord("a")):
                if corners is None:
                    status = "no chessboard to add"
                else:
                    metrics = sample_metrics(corners, image_size, args.cols, args.rows)
                    samples.append(Sample(object_template.copy(), corners.copy(), metrics))
                    last_sample_time = time.monotonic()
                    result = None
                    status = f"manually added sample {len(samples)}"
            elif key == ord("c"):
                if len(samples) < 8:
                    status = "need at least 8 samples to calibrate"
                else:
                    result = calibrate(samples, image_size)
                    status = "calibrated; press s to save"
            elif key == ord("s"):
                if result is None:
                    status = "calibrate before saving"
                else:
                    write_result(output_path, result, samples, args, image_size)
                    status = f"saved {output_path}"
                    print(status)
            elif key == ord("r"):
                samples.clear()
                result = None
                status = "reset samples"
            elif key == ord("u"):
                show_undistorted = not show_undistorted
                status = f"undistort preview {'on' if show_undistorted else 'off'}"
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
