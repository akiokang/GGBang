import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
import os
import threading
import random
from PIL import Image, ImageTk

# --- 全局变量用于鼠标框选 ---
ref_point = []
cropping = False
selected_hsv_range = None  # 用于存储用户选择的颜色范围

# 支持的视频文件扩展名
SUPPORTED_VIDEO_FORMATS = ('.mp4', '.avi', '.mov', '.mkv', '.flv')


def select_color_with_mouse(event, x, y, flags, param):
    """鼠标回调函数，用于处理框选操作"""
    global ref_point, cropping, selected_hsv_range
    frame = param['frame']
    clone = frame.copy()

    if event == cv2.EVENT_LBUTTONDOWN:
        ref_point = [(x, y)];
        cropping = True
    elif event == cv2.EVENT_LBUTTONUP:
        ref_point.append((x, y));
        cropping = False
        cv2.rectangle(clone, ref_point[0], ref_point[1], (0, 255, 0), 2)
        cv2.imshow("image", clone)
        if len(ref_point) == 2:
            x0, y0 = min(ref_point[0][0], ref_point[1][0]), min(ref_point[0][1], ref_point[1][1])
            x1, y1 = max(ref_point[0][0], ref_point[1][0]), max(ref_point[0][1], ref_point[1][1])
            roi = frame[y0:y1, x0:x1]
            if roi.size == 0: return
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            avg_h = int(np.mean(hsv_roi[:, :, 0]));
            avg_s = int(np.mean(hsv_roi[:, :, 1]));
            avg_v = int(np.mean(hsv_roi[:, :, 2]))
            print(f"框选区域的平均HSV值为: H={avg_h}, S={avg_s}, V={avg_v}")
            h_tolerance = 10;
            s_tolerance = 80;
            v_tolerance = 80
            lower_bound = np.array(
                [max(0, avg_h - h_tolerance), max(40, avg_s - s_tolerance), max(40, avg_v - v_tolerance)])
            upper_bound = np.array([min(179, avg_h + h_tolerance), 255, 255])
            selected_hsv_range = (lower_bound, upper_bound)
            param['app_instance'].update_color_status(True)
            cv2.waitKey(1000);
            cv2.destroyAllWindows()


def get_video_files(folder_path):
    """递归地从文件夹中获取所有支持格式的视频文件路径。"""
    video_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(SUPPORTED_VIDEO_FORMATS):
                video_files.append(os.path.join(root, file))
    return video_files


def process_videos(source_folder, green_screen_folder, output_folder, progress_bar, status_label, hsv_range,
                   freeze_enabled, freeze_duration_str):
    """处理视频的主函数 (文件夹到文件夹, 按背景目录输出)。"""
    if not all([source_folder, green_screen_folder, output_folder]):
        messagebox.showerror("错误", "所有文件夹路径都必须选择！");
        return

    source_videos = get_video_files(source_folder)
    background_videos = get_video_files(green_screen_folder)
    if not source_videos: messagebox.showwarning("警告", "在指定的原视频文件夹中没有找到任何视频文件。"); return
    if not background_videos: messagebox.showwarning("警告", "在指定的绿幕素材文件夹中没有找到任何视频文件。"); return

    if hsv_range:
        lower_green, upper_green = hsv_range;
        print("使用自定义的颜色范围进行处理。")
    else:
        lower_green = np.array([35, 43, 46]);
        upper_green = np.array([77, 255, 255]);
        print("使用默认的颜色范围进行处理。")

    total_operations = len(source_videos) * len(background_videos)
    progress_bar['maximum'] = total_operations
    completed_operations = 0

    try:
        for bg_video_path in background_videos:
            for source_video_path in source_videos:
                current_op_text = f"{os.path.basename(source_video_path)} + {os.path.basename(bg_video_path)}"
                status_label.config(text=f"处理中 ({completed_operations + 1}/{total_operations}): {current_op_text}")

                relative_path = os.path.relpath(os.path.dirname(bg_video_path), green_screen_folder)
                output_subfolder = os.path.join(output_folder, relative_path)
                os.makedirs(output_subfolder, exist_ok=True)

                source_basename = os.path.splitext(os.path.basename(source_video_path))[0]
                bg_basename = os.path.splitext(os.path.basename(bg_video_path))[0]
                output_filename = f"{source_basename}_on_{bg_basename}.mp4"
                output_filepath = os.path.join(output_subfolder, output_filename)

                source_capture = cv2.VideoCapture(source_video_path)
                bg_capture = cv2.VideoCapture(bg_video_path)
                if not source_capture.isOpened() or not bg_capture.isOpened(): continue

                width = int(source_capture.get(cv2.CAP_PROP_FRAME_WIDTH));
                height = int(source_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = source_capture.get(cv2.CAP_PROP_FPS)
                if fps == 0: fps = 30

                fourcc = cv2.VideoWriter_fourcc(*'mp4v');
                out = cv2.VideoWriter(output_filepath, fourcc, fps, (width, height))

                last_combined_frame = None  # 用于存储最后一帧【合成】画面

                while True:
                    source_ret, source_frame = source_capture.read()
                    if not source_ret: break

                    bg_ret, bg_frame = bg_capture.read()
                    if not bg_ret:
                        bg_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        bg_ret, bg_frame = bg_capture.read()
                        if not bg_ret: break

                    bg_frame_resized = cv2.resize(bg_frame, (width, height))

                    hsv = cv2.cvtColor(source_frame, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv, lower_green, upper_green)
                    kernel = np.ones((5, 5), np.uint8);
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                    mask_inv = cv2.bitwise_not(mask)
                    foreground = cv2.bitwise_and(source_frame, source_frame, mask=mask_inv)
                    background = cv2.bitwise_and(bg_frame_resized, bg_frame_resized, mask=mask)

                    combined_frame = cv2.add(foreground, background)
                    # 持续更新最后一帧【合成】画面
                    last_combined_frame = combined_frame

                    out.write(combined_frame)

                # --- 结尾定格逻辑 ---
                # 此处使用的是 last_combined_frame (最后的合成帧), 符合最新要求。
                if freeze_enabled and last_combined_frame is not None:
                    try:
                        duration = float(freeze_duration_str)
                        if duration > 0:
                            num_freeze_frames = int(fps * duration)
                            print(f"添加 {duration}秒 合成画面定格 ({num_freeze_frames} 帧)...")
                            for _ in range(num_freeze_frames):
                                out.write(last_combined_frame)
                    except ValueError:
                        print(f"无效的定格时长: '{freeze_duration_str}'，已跳过。")

                source_capture.release();
                bg_capture.release();
                out.release()

                completed_operations += 1
                progress_bar['value'] = completed_operations
                root.update_idletasks()

        status_label.config(text="处理完成！")
        messagebox.showinfo("成功",
                            f"所有视频处理完成！\n共生成 {completed_operations} 个文件，已保存到: {output_folder}")

    except Exception as e:
        messagebox.showerror("发生错误", f"处理过程中出现错误: {e}")
    finally:
        status_label.config(text="请按步骤选择并开始处理")
        progress_bar['value'] = 0


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("绿幕视频批量处理器 v5.2 (最终版)")
        self.root.geometry("600x580")

        self.source_folder_path = tk.StringVar()
        self.green_screen_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.freeze_enabled = tk.BooleanVar(value=False)
        self.freeze_duration = tk.StringVar(value="3")

        main_frame = tk.Frame(root, padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        path_frame = tk.LabelFrame(main_frame, text="操作步骤", padx=10, pady=10)
        path_frame.pack(fill=tk.X, expand=True, pady=5)
        tk.Button(path_frame, text="1. 选择原视频文件夹", command=self.select_source_folder).grid(row=0, column=0,
                                                                                                  sticky="ew", pady=5)
        tk.Label(path_frame, textvariable=self.source_folder_path, wraplength=350, justify=tk.LEFT).grid(row=0,
                                                                                                         column=1,
                                                                                                         columnspan=2,
                                                                                                         sticky="w",
                                                                                                         padx=10)
        tk.Button(path_frame, text="2. 选择背景素材文件夹", command=self.select_green_screen_folder).grid(row=1,
                                                                                                          column=0,
                                                                                                          sticky="ew",
                                                                                                          pady=5)
        tk.Label(path_frame, textvariable=self.green_screen_folder, wraplength=350, justify=tk.LEFT).grid(row=1,
                                                                                                          column=1,
                                                                                                          columnspan=2,
                                                                                                          sticky="w",
                                                                                                          padx=10)
        tk.Button(path_frame, text="3. 选择输出文件夹", command=self.select_output_folder).grid(row=2, column=0,
                                                                                                sticky="ew", pady=5)
        tk.Label(path_frame, textvariable=self.output_folder, wraplength=350, justify=tk.LEFT).grid(row=2, column=1,
                                                                                                    columnspan=2,
                                                                                                    sticky="w", padx=10)
        path_frame.columnconfigure(1, weight=1)

        settings_frame = tk.LabelFrame(main_frame, text="高级设置 (可选)", padx=10, pady=10)
        settings_frame.pack(fill=tk.X, expand=True, pady=5)

        tk.Button(settings_frame, text="校准颜色", command=self.calibrate_color).grid(row=0, column=0, sticky="ew",
                                                                                      pady=5)
        self.color_status_label = tk.Label(settings_frame, text="颜色范围: 默认值", fg="orange")
        self.color_status_label.grid(row=0, column=1, sticky="w", padx=10)

        tk.Checkbutton(settings_frame, text="开启结尾定格", variable=self.freeze_enabled).grid(row=1, column=0,
                                                                                               sticky="w")
        freeze_entry_frame = tk.Frame(settings_frame)
        freeze_entry_frame.grid(row=1, column=1, sticky="w", padx=10)
        tk.Label(freeze_entry_frame, text="定格时长(秒):").pack(side=tk.LEFT)
        tk.Entry(freeze_entry_frame, textvariable=self.freeze_duration, width=5).pack(side=tk.LEFT)

        control_frame = tk.Frame(main_frame)
        control_frame.pack(fill=tk.X, expand=True, pady=10)
        self.start_button = tk.Button(control_frame, text="开始处理", font=("Helvetica", 12, "bold"), bg="#4CAF50",
                                      fg="white", command=self.start_processing_thread)
        self.start_button.pack(fill=tk.X, ipady=5)

        status_frame = tk.Frame(main_frame)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        self.status_label = tk.Label(status_frame, text="请按步骤选择并开始处理", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar = ttk.Progressbar(status_frame, orient='horizontal', length=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))

    def select_source_folder(self):
        path = filedialog.askdirectory(title="选择包含原视频的根文件夹");
        if path: self.source_folder_path.set(path); self.update_color_status(False)

    def select_green_screen_folder(self):
        path = filedialog.askdirectory(title="选择包含背景视频的文件夹");
        if path: self.green_screen_folder.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory(title="选择一个文件夹用于保存最终结果");
        if path: self.output_folder.set(path)

    def update_color_status(self, calibrated):
        if calibrated:
            self.color_status_label.config(text="颜色范围: 已自定义", fg="green")
        else:
            global selected_hsv_range; selected_hsv_range = None; self.color_status_label.config(
                text="颜色范围: 默认值", fg="orange")

    def calibrate_color(self):
        source_folder = self.source_folder_path.get()
        if not source_folder: messagebox.showerror("错误", "请先在“步骤1”中选择“原视频文件夹”！"); return
        source_videos = get_video_files(source_folder)
        if not source_videos: messagebox.showerror("错误", "在“原视频文件夹”中找不到任何视频文件用于校准。"); return
        video_for_calibration = source_videos[0]
        messagebox.showinfo("校准提示",
                            f"将使用以下视频的第一帧进行颜色校准：\n{os.path.basename(video_for_calibration)}")
        cap = cv2.VideoCapture(video_for_calibration)
        if not cap.isOpened(): messagebox.showerror("错误", "无法打开用于校准的视频文件。"); return
        ret, frame = cap.read();
        cap.release()
        if not ret: messagebox.showerror("错误", "无法读取视频的第一帧。"); return
        cv2.namedWindow("image");
        cv2.putText(frame, "Drag a box on the green area, then release. Press 'q' to quit.", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        param = {'frame': frame, 'app_instance': self};
        cv2.setMouseCallback("image", select_color_with_mouse, param)
        while True:
            cv2.imshow("image", frame)
            if cv2.waitKey(1) & 0xFF == ord("q") or cv2.getWindowProperty("image", cv2.WND_PROP_VISIBLE) < 1: break
        cv2.destroyAllWindows()

    def start_processing_thread(self):
        self.start_button.config(state=tk.DISABLED)
        processing_thread = threading.Thread(
            target=process_videos,
            args=(self.source_folder_path.get(), self.green_screen_folder.get(), self.output_folder.get(),
                  self.progress_bar, self.status_label, selected_hsv_range, self.freeze_enabled.get(),
                  self.freeze_duration.get())
        )
        processing_thread.daemon = True
        processing_thread.start()
        self.check_thread(processing_thread)

    def check_thread(self, thread):
        if thread.is_alive():
            self.root.after(100, lambda: self.check_thread(thread))
        else:
            self.start_button.config(state=tk.NORMAL)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()