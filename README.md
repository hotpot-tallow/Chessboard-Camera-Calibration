# 棋盘格摄像头标定工具

这个文件夹用于使用棋盘格标定摄像头内参，并导出给 AprilTag 降落识别程序使用的 `fx / fy / cx / cy` 参数。

## 目录

```text
Chessboard-Camera-Calibration/
  capture_chessboard.py      # 采集棋盘格图片
  calibrate_camera.py        # 根据图片计算相机内参和畸变参数
  preview_undistort.py       # 使用标定结果实时预览去畸变效果
  requirements.txt
  README.md
```

## 1. 准备棋盘格

打印一张标准棋盘格，贴在平整硬板上。程序里的 `--cols` 和 `--rows` 填的是棋盘格的“内角点数量”，不是格子数量。

例如常见的 9x6 内角点棋盘格：

- 横向内角点：9
- 纵向内角点：6
- 每个小方格边长：比如 25 mm，则 `--square-size 0.025`

## 2. 安装依赖

电脑上可以直接：

```bash
pip install -r requirements.txt
```

鲁班猫 / Ubuntu 上更推荐：

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy
```

## 3. 采集棋盘格图片

进入本目录：

```bash
cd ~/Chessboard-Camera-Calibration
```

采集图片：

```bash
python capture_chessboard.py --camera 0 --width 1920 --height 1080 --output images
```

窗口打开后：

- 按 `Space` 或 `s` 保存当前画面
- 按 `q` 或 `Esc` 退出

建议采集 20 到 40 张，棋盘格要覆盖画面中心、四角、不同距离和不同倾角。不要只在画面正中间拍。

如果鲁班猫没有桌面窗口，可以用系统相机工具先拍照片，只要把图片放进 `images/` 文件夹即可。

## 4. 执行标定

以 9x6 内角点、25 mm 方格为例：

```bash
python calibrate_camera.py --images images --cols 9 --rows 6 --square-size 0.025 --output camera_calibration.json
```

参数说明：

- `--cols`：横向内角点数量
- `--rows`：纵向内角点数量
- `--square-size`：单个棋盘格边长，单位是米
- `--images`：棋盘格图片目录
- `--output`：输出标定文件

标定完成后会输出：

- `camera_calibration.json`：相机矩阵、畸变参数、重投影误差
- `camera_calibration.npz`：NumPy 格式，方便 Python 直接读取
- `calibration_debug/`：检测角点的调试图片

## 5. 检查去畸变效果

```bash
python preview_undistort.py --camera 0 --width 1920 --height 1080 --calibration camera_calibration.json
```

窗口中会显示原始画面和去畸变画面。按 `q` 或 `Esc` 退出。

## 6. 填入 AprilTag 识别配置

打开标定结果：

```bash
cat camera_calibration.json
```

把里面的参数填到 `Lubancat0N-Apriltag/config/lubancat0n.json`：

```json
"camera": {
  "width": 1920,
  "height": 1080,
  "fx": 标定结果里的 fx,
  "fy": 标定结果里的 fy,
  "cx": 标定结果里的 cx,
  "cy": 标定结果里的 cy
}
```

注意：`width / height` 必须和标定时使用的分辨率一致。如果实际运行 AprilTag 时换了分辨率，需要重新标定，或者按分辨率比例缩放内参。

## 7. 判断标定是否可用

一般来说：

- 重投影误差小于 `0.5 px` 很好
- `0.5 px` 到 `1.0 px` 通常可用
- 大于 `1.0 px` 建议重新拍图

如果误差偏大，优先检查：

- `--cols / --rows` 是否填的是内角点，不是格子数
- `--square-size` 单位是否是米
- 图片是否模糊
- 棋盘格是否弯曲、不平整
- 采集角度是否太单一
