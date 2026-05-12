from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate a camera with chessboard images.")
    parser.add_argument("--images", default="images", help="Directory containing chessboard images")
    parser.add_argument("--cols", type=int, required=True, help="Number of inner chessboard corners per row")
    parser.add_argument("--rows", type=int, required=True, help="Number of inner chessboard corners per column")
    parser.add_argument("--square-size", type=float, required=True, help="Chessboard square size in meters")
    parser.add_argument("--output", default="camera_calibration.json", help="Output JSON file")
    parser.add_argument("--debug-dir", default="calibration_debug", help="Directory for corner debug images")
    parser.add_argument("--no-debug-images", action="store_true", help="Do not write debug images")
    return parser.parse_args()


def iter_images(image_dir: Path) -> Iterable[Path]:
    for path in sorted(image_dir.iterdir()):
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def build_object_points(cols: int, rows: int, square_size: float) -> np.ndarray:
    points = np.zeros((rows * cols, 3), np.float32)
    points[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    points *= square_size
    return points


def reprojection_errors(
    object_points: list[np.ndarray],
    image_points: list[np.ndarray],
    rvecs: list[np.ndarray],
    tvecs: list[np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
) -> tuple[float, list[float]]:
    per_image_errors = []
    total_error = 0.0
    total_points = 0

    for objp, imgp, rvec, tvec in zip(object_points, image_points, rvecs, tvecs):
        projected, _ = cv2.projectPoints(objp, rvec, tvec, camera_matrix, dist_coeffs)
        error = cv2.norm(imgp, projected, cv2.NORM_L2)
        point_count = len(projected)
        per_image_errors.append(float(error / np.sqrt(point_count)))
        total_error += error * error
        total_points += point_count

    return float(np.sqrt(total_error / total_points)), per_image_errors


def main() -> None:
    args = parse_args()
    image_dir = Path(args.images)
    output_path = Path(args.output)
    debug_dir = Path(args.debug_dir)

    if not image_dir.is_dir():
        raise FileNotFoundError(f"image directory not found: {image_dir}")

    image_paths = list(iter_images(image_dir))
    if not image_paths:
        raise RuntimeError(f"no calibration images found in {image_dir}")

    if not args.no_debug_images:
        debug_dir.mkdir(parents=True, exist_ok=True)

    pattern_size = (args.cols, args.rows)
    object_template = build_object_points(args.cols, args.rows, args.square_size)
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    used_images: list[str] = []
    rejected_images: list[str] = []
    image_size: tuple[int, int] | None = None

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )

    for image_path in image_paths:
        image = cv2.imread(str(image_path))
        if image is None:
            rejected_images.append(str(image_path))
            print(f"skip unreadable image: {image_path}")
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        current_size = (gray.shape[1], gray.shape[0])
        if image_size is None:
            image_size = current_size
        elif image_size != current_size:
            rejected_images.append(str(image_path))
            print(f"skip different image size: {image_path} {current_size} != {image_size}")
            continue

        found, corners = cv2.findChessboardCorners(
            gray,
            pattern_size,
            cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE,
        )

        if not found:
            rejected_images.append(str(image_path))
            print(f"corners not found: {image_path}")
            continue

        refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        object_points.append(object_template.copy())
        image_points.append(refined)
        used_images.append(str(image_path))
        print(f"corners found: {image_path}")

        if not args.no_debug_images:
            debug = image.copy()
            cv2.drawChessboardCorners(debug, pattern_size, refined, found)
            cv2.imwrite(str(debug_dir / image_path.name), debug)

    if image_size is None:
        raise RuntimeError("no readable calibration images")
    if len(object_points) < 8:
        raise RuntimeError(f"need at least 8 valid chessboard images, got {len(object_points)}")

    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points,
        image_points,
        image_size,
        None,
        None,
    )

    mean_error, per_image_errors = reprojection_errors(
        object_points,
        image_points,
        rvecs,
        tvecs,
        camera_matrix,
        dist_coeffs,
    )

    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])

    result = {
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
            "camera_matrix": camera_matrix.tolist(),
            "distortion_coefficients": dist_coeffs.ravel().tolist(),
        },
        "quality": {
            "rms": float(rms),
            "mean_reprojection_error_px": mean_error,
            "per_image_reprojection_error_px": per_image_errors,
            "valid_image_count": len(used_images),
            "rejected_image_count": len(rejected_images),
        },
        "used_images": used_images,
        "rejected_images": rejected_images,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    npz_path = output_path.with_suffix(".npz")
    np.savez(
        npz_path,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        image_width=image_size[0],
        image_height=image_size[1],
        rms=rms,
        mean_reprojection_error_px=mean_error,
    )

    print()
    print(f"valid images: {len(used_images)}")
    print(f"rejected images: {len(rejected_images)}")
    print(f"image size: {image_size[0]}x{image_size[1]}")
    print(f"rms: {rms:.4f}")
    print(f"mean reprojection error: {mean_error:.4f} px")
    print(f"fx={fx:.6f} fy={fy:.6f} cx={cx:.6f} cy={cy:.6f}")
    print(f"wrote {output_path}")
    print(f"wrote {npz_path}")


if __name__ == "__main__":
    main()
