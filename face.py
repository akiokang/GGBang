import cv2
import os
import numpy as np

# --- 配置参数 ---
# 输入视频文件夹
INPUT_FOLDER = 'vodeo'
# 输出处理后视频的文件夹
OUTPUT_FOLDER = 'processed_videos'
# 输出视频的分辨率 (宽, 高) - 16:9 比例
OUTPUT_RESOLUTION = (1280, 720)
# 脸部区域向下扩展以包含颈部的比例 (例如 0.6 表示向下扩展脸部高度的60%)
NECK_EXTENSION_RATIO = 0.6


# --- 配置结束 ---

def process_videos():
    """
    主函数，用于处理所有视频。
    """
    # 检查输入文件夹是否存在
    if not os.path.exists(INPUT_FOLDER):
        print(f"错误: 找不到名为 '{INPUT_FOLDER}' 的文件夹。")
        return

    # 创建输出文件夹
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"已创建输出文件夹: '{OUTPUT_FOLDER}'")

    # 加载OpenCV的人脸检测器 (Haar Cascade模型)
    # 首先尝试从cv2的默认数据路径加载
    casc_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
    if not os.path.exists(casc_path):
        # 如果失败，则尝试加载同目录下的文件
        casc_path = 'haarcascade_frontalface_default.xml'
        if not os.path.exists(casc_path):
            print("错误: 找不到 'haarcascade_frontalface_default.xml'。")
            print("请从OpenCV官方仓库下载并将其放在脚本同级目录。")
            return

    face_cascade = cv2.CascadeClassifier(casc_path)

    print("人脸检测器加载成功。开始处理视频...")

    # 获取支持的视频文件扩展名
    supported_formats = ('.mp4', '.mov', '.avi', '.mkv')
    video_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(supported_formats)]

    if not video_files:
        print(f"在 '{INPUT_FOLDER}' 文件夹中没有找到支持的视频文件。")
        return

    # 循环处理每个视频文件
    for video_file in video_files:
        input_path = os.path.join(INPUT_FOLDER, video_file)
        output_path = os.path.join(OUTPUT_FOLDER, video_file)

        print(f"\n正在处理: {video_file}")

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            print(f"无法打开视频文件: {video_file}")
            continue

        # 获取视频原始帧率和尺寸
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 设置视频编码器和创建VideoWriter对象
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 使用 'mp4v' 编码器
        out = cv2.VideoWriter(output_path, fourcc, fps, OUTPUT_RESOLUTION)

        last_known_box = None  # 用于在未检测到人脸时沿用上一帧的位置

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 将帧转换为灰度图以进行人脸检测
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 检测人脸
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(50, 50)  # 最小检测尺寸
            )

            target_box = None
            if len(faces) > 0:
                # 如果检测到人脸，选择最大的一张脸
                faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                x, y, w, h = faces[0]

                # --- 计算包含头部和颈部的目标裁剪区域 ---
                # 1. 向下扩展以包含颈部
                new_h = int(h * (1 + NECK_EXTENSION_RATIO))

                # 2. 根据16:9的比例计算新的宽度
                aspect_ratio = OUTPUT_RESOLUTION[0] / OUTPUT_RESOLUTION[1]
                new_w = int(new_h * aspect_ratio)

                # 3. 计算新区域的中心点 (保持脸部水平居中)
                center_x = x + w // 2
                center_y = y + h // 2

                # 4. 计算新区域的左上角坐标
                new_x = center_x - new_w // 2
                new_y = y  # 从头顶开始

                target_box = (new_x, new_y, new_w, new_h)
                last_known_box = target_box
            elif last_known_box is not None:
                # 如果当前帧未检测到人脸，使用上一帧的位置
                target_box = last_known_box

            if target_box:
                nx, ny, nw, nh = [int(v) for v in target_box]

                # --- 裁剪并缩放 ---
                # 创建一个黑色背景
                background = np.zeros((nh, nw, 3), dtype=np.uint8)

                # 计算源区域和目标区域的坐标，处理边界情况
                src_x_start = max(0, nx)
                src_x_end = min(frame_width, nx + nw)
                src_y_start = max(0, ny)
                src_y_end = min(frame_height, ny + nh)

                dst_x_start = max(0, -nx)
                dst_x_end = nw - max(0, (nx + nw) - frame_width)
                dst_y_start = max(0, -ny)
                dst_y_end = nh - max(0, (ny + nh) - frame_height)

                # 将视频帧的有效部分复制到黑色背景上
                if (src_x_end > src_x_start) and (src_y_end > src_y_start):
                    background[dst_y_start:dst_y_end, dst_x_start:dst_x_end] = \
                        frame[src_y_start:src_y_end, src_x_start:src_x_end]

                # 将裁剪出的区域缩放到目标分辨率
                processed_frame = cv2.resize(background, OUTPUT_RESOLUTION, interpolation=cv2.INTER_AREA)
                out.write(processed_frame)
            else:
                # 如果始终未检测到人脸，则写入一个黑屏帧
                black_frame = np.zeros((OUTPUT_RESOLUTION[1], OUTPUT_RESOLUTION[0], 3), dtype=np.uint8)
                out.write(black_frame)

        # 释放资源
        cap.release()
        out.release()
        print(f"处理完成: {video_file} -> 已保存到 {output_path}")

    print("\n所有视频处理完毕！")


if __name__ == '__main__':
    process_videos()