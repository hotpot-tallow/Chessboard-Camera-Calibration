# Chessboard Camera Calibration

这个工具用于像 ROS `camera_calibration` 一样实时标定摄像头：打开摄像头后自动识别棋盘格，提示采样覆盖度，采集到足够多不同位置、大小和倾斜角度的样本后，直接计算并保存相机内参。

标定结果里的 `fx / fy / cx / cy` 可以填入 `Lubancat0N-Apriltag/config/lubancat0n.json`，用于 AprilTag 精准降落识别。

## 文件

```text
realtime_calibration.py   # 主程序，实时采样、实时标定、保存结果
calibrate_camera.py       # 实时标定入口，等同于 realtime_calibration.py
preview_undistort.py      # 用标定结果预览去畸变效果
capture_chessboard.py     # 备用：手动采集棋盘格图片
offline_calibrate_from_images.py  # 备用：离线图片标定
requirements.txt
```

## 1. 准备棋盘格

程序参数里的 `--cols` 和 `--rows` 填的是棋盘格内角点数量，不是方格数量。

例如一张 10x7 个方格的棋盘格，内角点通常是：

```text
--cols 9 --rows 6
```

如果每个小方格边长是 25 mm，则：

```text
--square-size 0.025
```

单位必须是米。

## 2. 安装依赖

电脑上可以使用：

```bash
pip install -r requirements.txt
```

鲁班猫 / Ubuntu 上更推荐用系统包，避免在板子上编译 OpenCV：

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy
```

## 3. 实时标定

进入目录：

```bash
cd ~/Chessboard-Camera-Calibration
```

运行实时标定，下面以 1920x1080、9x6 内角点、25 mm 方格为例：

```bash
python3 realtime_calibration.py --camera 0 --width 1920 --height 1080 --cols 9 --rows 6 --square-size 0.025
```

也可以使用兼容入口：

```bash
python3 calibrate_camera.py --camera 0 --width 1920 --height 1080 --cols 9 --rows 6 --square-size 0.025
```

MIPI 摄像头建议显式使用 V4L2 后端。如果 AprilTag 实际运行分辨率是 1280x720，就这样标定：

```bash
python3 realtime_calibration.py --backend v4l2 --camera 0 --width 1280 --height 720 --cols 9 --rows 6 --square-size 0.025
```

如果 `v4l2-ctl --list-formats-ext` 里显示摄像头使用 `YUYV`，可以指定：

```bash
python3 realtime_calibration.py --backend v4l2 --camera 0 --width 1280 --height 720 --fourcc YUYV --cols 9 --rows 6 --square-size 0.025
```

如果显示 `MJPG`，可以指定：

```bash
python3 realtime_calibration.py --backend v4l2 --camera 0 --width 1280 --height 720 --fourcc MJPG --cols 9 --rows 6 --square-size 0.025
```

窗口打开后，把棋盘格移动到画面的中心、四角、不同距离和不同倾斜角度。程序会自动采样，并显示四个覆盖度：

- `X`：棋盘格在画面横向位置的覆盖
- `Y`：棋盘格在画面纵向位置的覆盖
- `Size`：远近大小变化覆盖
- `Skew`：倾斜透视覆盖

采样足够后程序会自动标定，并在窗口上显示：

```text
rms / err / fx / fy / cx / cy
```

按键：

```text
Space 或 a  手动加入当前样本
c           手动执行标定
s           保存 camera_calibration.json 和 camera_calibration.npz
r           清空样本重新开始
u           切换去畸变预览
q 或 Esc    退出
```

## 4. 常用参数

最少采样数量默认是 30，可以修改：

```bash
python3 realtime_calibration.py --camera 0 --width 1920 --height 1080 --cols 9 --rows 6 --square-size 0.025 --min-samples 40
```

如果不想自动采样，只想自己按键采样：

```bash
python3 realtime_calibration.py --camera 0 --width 1920 --height 1080 --cols 9 --rows 6 --square-size 0.025 --manual
```

指定输出文件：

```bash
python3 realtime_calibration.py --camera 0 --width 1920 --height 1080 --cols 9 --rows 6 --square-size 0.025 --output lubancat_camera_1080p.json
```

## 5. 检查去畸变效果

保存后可以单独预览去畸变效果：

```bash
python3 preview_undistort.py --camera 0 --width 1920 --height 1080 --calibration camera_calibration.json
```

## 6. 填入 AprilTag 项目

打开 `camera_calibration.json`，找到：

```json
"camera": {
  "fx": 1234.0,
  "fy": 1234.0,
  "cx": 960.0,
  "cy": 540.0
}
```

把这些值填入：

```text
Lubancat0N-Apriltag/config/lubancat0n.json
```

对应位置：

```json
"camera": {
  "width": 1920,
  "height": 1080,
  "fx": 1234.0,
  "fy": 1234.0,
  "cx": 960.0,
  "cy": 540.0
}
```

注意：标定分辨率必须和 AprilTag 运行分辨率一致。如果标定用 1920x1080，识别也要用 1920x1080。

## 7. 标定质量判断

一般经验：

- 平均重投影误差小于 `0.5 px` 很好
- `0.5 px` 到 `1.0 px` 通常可用
- 大于 `1.0 px` 建议重新标定

误差偏大时，优先检查：

- `--cols / --rows` 是否填的是内角点数量
- 棋盘格是否平整、没有翘曲
- 图片是否清晰、没有运动模糊
- 样本是否覆盖中心、四角、远近和倾斜角度
- 标定分辨率是否和实际运行分辨率一致

## 8. 无桌面环境备用流程

如果板子没有显示器，实时窗口打不开，可以先用其他工具拍棋盘格图片放到 `images/`，再离线标定：

```bash
python3 offline_calibrate_from_images.py --images images --cols 9 --rows 6 --square-size 0.025 --output camera_calibration.json
```

## 9. 摄像头打不开时

先确认系统能取流：

```bash
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=10
```

如果输出一串 `<`，说明 V4L2 取流成功。此时程序打不开通常是 OpenCV 后端或像素格式问题，优先试：

```bash
python3 realtime_calibration.py --backend v4l2 --camera 0 --width 1280 --height 720 --cols 9 --rows 6 --square-size 0.025
```

查看设备和支持格式：

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

如果真实设备不是 `/dev/video0`，例如是 `/dev/video2`，命令改成：

```bash
python3 realtime_calibration.py --backend v4l2 --camera 2 --width 1280 --height 720 --cols 9 --rows 6 --square-size 0.025
```
