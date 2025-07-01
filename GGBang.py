# GGBang_Final.py (v18.0 - Truly Complete, All Functions Restored)
import customtkinter as ctk
from tkinter import filedialog, colorchooser, messagebox as tk_messagebox
import threading
import subprocess
import time
import os
import gc
from pathlib import Path
import json
import random
import re
import shutil
import sys
import subprocess
import platform
import moviepy.config as cf
# --- 智能配置 ImageMagick 路径 ---
# 判断程序是否被 PyInstaller 打包
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # 如果是打包状态，则ImageMagick的路径在程序内部
    # sys._MEIPASS 指向PyInstaller解压后的临时文件夹
    imagemagick_path = os.path.join(sys._MEIPASS, 'imagemagick', 'magick.exe')
else:
    # 如果是开发环境（直接运行.py），则指向项目内的相对路径
    current_dir = os.path.dirname(__file__)
    imagemagick_path = os.path.join(current_dir, 'imagemagick', 'magick.exe')

# 检查路径是否存在，然后应用配置
if os.path.exists(imagemagick_path):
    cf.change_settings({"IMAGEMAGICK_BINARY": imagemagick_path})
    print(f"MoviePy 已绑定ImageMagick路径: {imagemagick_path}")
else:
    # 这一行在打包后不应出现，仅用于开发时调试
    print("警告: 在预期的打包路径中未找到ImageMagick程序。")

# --- AI抠像功能需要的新库 ---
try:
    pass
except ImportError:
    tk_messagebox.showerror("依赖缺失", "AI抠像功能所需的核心库 (cv2, rembg, onnxruntime) 未安装。\n请运行: pip install opencv-python rembg onnxruntime\n如需GPU加速，请额外安装: pip install onnxruntime-gpu")

# ==============================================================================
# 全局辅助函数
# ==============================================================================
def get_resource_path(relative_path):
    """ 获取【只读资源】的绝对路径 (用于打包后的字体、图片等) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def get_persistent_settings_path(filename):
    """ 获取【可写配置文件】的永久保存路径 (保存在用户主目录) """
    app_config_dir = os.path.join(os.path.expanduser('~'), '.ggbang_config')
    if not os.path.exists(app_config_dir):
        os.makedirs(app_config_dir)
    return os.path.join(app_config_dir, filename)

def video_parse_rgba(rgba_string):
    from PIL import ImageColor
    if isinstance(rgba_string, str) and rgba_string.startswith('rgba'):
        try:
            parts = re.findall(r"[-+]?\d*\.\d+|\d+", rgba_string)
            parts = [float(p) for p in parts]
            if len(parts) == 4: return tuple(int(p) for p in parts[:3]), parts[3]
        except (ValueError, TypeError): pass
    try: return ImageColor.getrgb(rgba_string), 1.0
    except ValueError: return (0,0,0), 0.5

def video_create_text_overlay(text, shared_style, specific_config, video_size):
    from moviepy.editor import TextClip, ColorClip, CompositeVideoClip
    from PIL import Image, ImageDraw
    import numpy as np
    video_width, _ = video_size
    colors = specific_config['colors']
    font_file = shared_style['font_file']
    font_size = shared_style['size']
    max_width_ratio = shared_style.get("max_width_ratio", 0.9)
    padding_horizontal = shared_style.get("padding_horizontal", 30)
    padding_vertical = shared_style.get("padding_vertical", 25)
    stroke_width = shared_style.get('stroke_width', 0)
    corner_radius = shared_style.get('corner_radius', 0)
    no_background = shared_style.get('no_background', False)
    text_color = colors['text']
    stroke_color = colors.get('stroke')
    bg_color_str = colors.get('background', 'rgba(0,0,0,0)')
    max_pixel_width = int(video_width * max_width_ratio)
    text_for_moviepy = text.replace('/', '\n')
    probe_clip = None
    try:
        probe_clip = TextClip(txt=text_for_moviepy, font=font_file, fontsize=font_size, method='label')
        single_line_width = probe_clip.size[0]
    finally:
        if probe_clip: probe_clip.close()
    creation_args = {'font': font_file, 'fontsize': font_size, 'color': text_color, 'stroke_color': stroke_color, 'stroke_width': stroke_width}
    if single_line_width > max_pixel_width:
        creation_args.update({'method': 'caption', 'size': (max_pixel_width, None), 'align': 'center'})
    else:
        creation_args.update({'method': 'label'})
    text_clip = None
    try:
        text_clip = TextClip(txt=text_for_moviepy, **creation_args)
        if no_background:
            # 如果禁用背景，直接返回纯文本剪辑
            return text_clip
        actual_text_width, actual_text_height = text_clip.size
        bg_width = actual_text_width + (2 * padding_horizontal)
        bg_height = actual_text_height + (2 * padding_vertical)
        bg_size = (int(bg_width), int(bg_height))
        bg_rgb, bg_alpha = video_parse_rgba(bg_color_str)
        bg_clip_opaque = ColorClip(size=bg_size, color=bg_rgb)
        if corner_radius > 0:
            mask_image = Image.new('L', bg_size, 0)
            draw = ImageDraw.Draw(mask_image)
            draw.rounded_rectangle(((0, 0), bg_size), int(corner_radius), fill=255)
        else:
            mask_image = Image.new('L', bg_size, 255)
        mask_array = np.array(mask_image) / 255.0
        final_alpha_channel = mask_array * bg_alpha
        bg_clip = bg_clip_opaque.set_opacity(final_alpha_channel)
        return CompositeVideoClip([bg_clip, text_clip.set_position('center')], size=bg_size)
    finally:
        # 这里 text_clip 不能关闭，因为如果返回的是它本身，后续会用到
        if no_background and text_clip:
             pass # 不关闭
        if text_clip: text_clip.close()

def image_preprocess(img, config, logger, img_path_for_logging=""):
    from PIL import Image, ImageOps
    original_width, original_height = img.size
    processed_img = img
    zoom_percentages = config.get("zoom_crop_percentages", [])
    if zoom_percentages:
        chosen_percentage = random.choice(zoom_percentages)
        if chosen_percentage != 0:
            logger(f"  ℹ️ 应用缩放/裁剪: {chosen_percentage}% 于 {img_path_for_logging}")
            if chosen_percentage > 0:
                scale = 1 + chosen_percentage / 100.0
                scaled_w, scaled_h = int(round(original_width * scale)), int(round(original_height * scale))
                scaled_img = processed_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                crop_x, crop_y = (scaled_w - original_width) / 2.0, (scaled_h - original_height) / 2.0
                processed_img = scaled_img.crop((int(crop_x), int(crop_y), int(crop_x + original_width), int(crop_y + original_height)))
            elif chosen_percentage < 0:
                scale = 1 - abs(chosen_percentage) / 100.0
                shrunk_w, shrunk_h = int(round(original_width * scale)), int(round(original_height * scale))
                shrunk_img = processed_img.resize((shrunk_w, shrunk_h), Image.Resampling.LANCZOS)
                new_bg = Image.new('RGB', (original_width, original_height), (0, 0, 0))
                new_bg.paste(shrunk_img, ((original_width - shrunk_w) // 2, (original_height - shrunk_h) // 2))
                processed_img = new_bg
    if config.get("allow_random_horizontal_flip", False) and random.choice([True, False]):
        logger(f"  ℹ️ 应用水平翻转于 {img_path_for_logging}")
        processed_img = processed_img.transpose(Image.FLIP_LEFT_RIGHT)
    if processed_img.size != (original_width, original_height):
        logger(f"  ⚠️ 警告: 预处理后尺寸不符，强制调整: {img_path_for_logging}")
        processed_img = ImageOps.fit(processed_img, (original_width, original_height), Image.Resampling.LANCZOS)
    return processed_img

def image_wrap_text(draw, text, font, max_width):
    if not text.strip(): return [], 0, []
    lines, words, current_line = [], text.split(), ""
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        if draw.textbbox((0,0), test_line, font=font)[2] <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
    if current_line: lines.append(current_line)
    if not lines: return [], 0, []
    widths = [draw.textbbox((0,0), l, font=font)[2] for l in lines]
    heights = [draw.textbbox((0,0), l, font=font)[3] - draw.textbbox((0,0), l, font=font)[1] for l in lines]
    return lines, max(widths), heights

def image_apply_text(img_path, text, config, pos_tuple, output_path, logger, stop_event):
    from PIL import Image, ImageDraw, ImageFont 
    if stop_event.is_set(): return 'STOPPED'
    try: base_img = Image.open(img_path).convert("RGB")
    except Exception as e: logger(f"❌ 打开图片失败: {img_path} - {e}"); return False
    img = image_preprocess(base_img, config, logger, img_path)
    draw = ImageDraw.Draw(img)
    W, H = img.size
    try: font = ImageFont.truetype(config["font_path"], config.get("font_size", 32))
    except Exception as e: logger(f"❌ 加载字体失败: {config['font_path']} - {e}"); img.save(output_path); return True
    font_color, bg_color = tuple(config.get("font_color", [0, 0, 0])), tuple(config.get("font_background_color", [255, 255, 255]))
    max_w_ratio, line_spacing = config.get("max_text_width_ratio", 0.8), random.choice(config.get("line_spacing_options", [10]))
    padding, align, radius = config.get("text_padding", 10), config.get("text_align_in_block", "center"), config.get("corner_radius", 0)
    no_background = config.get('no_background', False)
    lines, block_w, _ = image_wrap_text(draw, text, font, W * max_w_ratio)
    if not lines: img.save(output_path); return True
    total_text_height, line_heights = 0, []
    for line in lines:
        line_bbox = draw.textbbox((0, 0), line, font=font)
        height = line_bbox[3] - line_bbox[1]
        line_heights.append(height)
    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    block_x, block_y = W * pos_tuple[0] - block_w / 2, H * pos_tuple[1] - total_text_height / 2
    current_y = block_y
    for i, line in enumerate(lines):
        line_bbox = draw.textbbox((0, 0), line, font=font)
        line_w, line_top_offset = line_bbox[2] - line_bbox[0], line_bbox[1] 
        line_x = block_x
        if align == 'center': line_x += (block_w - line_w) / 2
        elif align == 'right': line_x += block_w - line_w
        actual_text_x, actual_text_y = line_x, current_y + line_top_offset
        # --- 主要修改点 ---
        if not no_background:
            bg_coords = (actual_text_x - padding, actual_text_y - padding, actual_text_x + line_w + padding, actual_text_y + line_heights[i] + padding)
            if radius > 0 and hasattr(draw, "rounded_rectangle"): draw.rounded_rectangle(bg_coords, radius=radius, fill=bg_color)
            else: draw.rectangle(bg_coords, fill=bg_color)
        draw.text((line_x, current_y), line, font=font, fill=font_color)
        current_y += line_heights[i] + line_spacing
    try: img.save(output_path); logger(f"  ✅ 已写入：{output_path}"); return True
    except Exception as e: logger(f"❌ 保存图片失败: {output_path} - {e}"); return False

# ==============================================================================
#  主GUI应用程序类
# ==============================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GGBang v18.0 (最终完整版)")
        self.geometry("950x850")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        ctk.set_default_color_theme("blue")
        self.SETTINGS_FILE = get_persistent_settings_path("gui_settings.json")
        self.video_stop_event, self.image_stop_event, self.ai_matting_stop_event, self.ab_image_stop_event,self.cut_stop_event = threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event()
        self.video_stop_event, self.image_stop_event, self.ai_matting_stop_event, self.ab_image_stop_event, self.news_stop_event, self.blur_stop_event,self.audio_stop_event,self.freeze_stop_event,self.gs_replace_stop_event,self.lut_stop_event = threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event()  
        self.grid_rowconfigure(0, weight=1)
        self.video_stop_event, self.image_stop_event, self.ai_matting_stop_event, self.ab_image_stop_event, self.news_stop_event = threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event()
        self.grid_columnconfigure(0, weight=1)
        self.main_tabview = ctk.CTkTabview(self)
        self.main_tabview.pack(expand=True, fill="both", padx=10, pady=10)
        self.main_tabview.add("视频处理")
        self.main_tabview.add("图片处理")
        self.main_tabview.add("AI抠像")
        self.main_tabview.add("AB图文")
        self.main_tabview.add("长视频分割")
        self.main_tabview.add("视频截图片")
        self.main_tabview.add("NEWS绿幕")
        self.main_tabview.add("NEWS虚化")
        self.main_tabview.add("绿幕替换")
        self.main_tabview.add("定格")
        self.main_tabview.add("卡秒")
        self.main_tabview.add("加滤镜")
        self.main_tabview.add("音频提取")
        self.setup_video_workflow()
        self.setup_image_workflow()
        self.setup_ai_matting_workflow()
        self.setup_ab_image_workflow()
        self.setup_news_greenscreen_workflow()
        self.setup_video_splitter_workflow()
        self.setup_frame_extractor_workflow()
        self.setup_audio_extraction_workflow()
        self.setup_freeze_workflow()
        self.setup_cut_workflow()
        self.setup_news_blur_workflow()
        self.setup_gs_replace_workflow()
        self.setup_lut_workflow()
        self.hw_info_frame = ctk.CTkFrame(self, height=30, border_width=1)
        self.hw_info_frame.pack(side="bottom", fill="x", padx=10, pady=(0,10))
        self.cpu_info_label = ctk.CTkLabel(self.hw_info_frame, text="CPU: 正在检测...", font=("", 10))
        self.cpu_info_label.pack(side="left", padx=10)
        self.gpu_info_label = ctk.CTkLabel(self.hw_info_frame, text="GPU: 正在检测...", font=("", 10))
        self.gpu_info_label.pack(side="left", padx=10)
        self.is_gpu_available = False
        threading.Thread(target=self._detect_and_display_hardware, daemon=True).start()
        self.load_settings()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    # ==============================================================================
    # --- 加滤镜 (新功能) ---
    # ==============================================================================
    def setup_lut_workflow(self):
        """创建批量添加滤镜功能的UI界面"""
        tab = self.main_tabview.tab("加滤镜")

        # --- 1. 路径设置 ---
        ctk.CTkLabel(tab, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,5))
        self.create_folder_selection_row(tab, "视频文件夹:", "选择包含视频的文件夹 (可含子文件夹)", "lut_video_folder_entry")
        
        # 特殊处理滤镜文件夹选择，选择后自动刷新列表
        filter_frame = self.create_folder_selection_row(tab, "滤镜文件夹:", "选择包含.cube滤镜文件的文件夹", "lut_filter_folder_entry", return_frame=True)
        select_button = filter_frame.winfo_children()[-1] # 获取 "选择..." 按钮
        select_button.configure(command=lambda e=self.lut_filter_folder_entry, t="选择滤镜文件夹...": self._populate_lut_filter_list(e, t))

        self.create_folder_selection_row(tab, "输出文件夹:", "选择处理结果的存放位置", "lut_output_folder_entry")

        # --- 2. 滤镜选择 ---
        ctk.CTkLabel(tab, text="2. 指定滤镜 (可多选，不选则全部随机)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20,5))
        self.lut_scroll_frame = ctk.CTkScrollableFrame(tab, height=150)
        self.lut_scroll_frame.pack(fill="x", expand=False, padx=10, pady=5)
        self.lut_checkboxes = {} # 用于存储复选框控件

        # --- 3. 开始处理 ---
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(20, 10))
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.lut_start_button = ctk.CTkButton(button_frame, text="开始批量添加滤镜", height=40, command=self.start_lut_processing)
        self.lut_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.lut_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_lut_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.lut_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- 4. 日志区域 ---
        self.lut_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.lut_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def _populate_lut_filter_list(self, entry, title):
        """当用户选择滤镜文件夹后，动态生成复选框列表"""
        path = filedialog.askdirectory(title=title)
        if not path: return
        entry.delete(0, "end"); entry.insert(0, path)

        # 清空旧的复选框
        for widget in self.lut_scroll_frame.winfo_children():
            widget.destroy()
        self.lut_checkboxes.clear()
        
        try:
            # 扫描文件夹中的.cube文件
            cube_files = [f for f in os.listdir(path) if f.lower().endswith('.cube')]
            if not cube_files:
                ctk.CTkLabel(self.lut_scroll_frame, text="此文件夹中未找到.cube文件").pack()
                return
            
            # 为每个文件创建复选框
            for filename in sorted(cube_files):
                cb = ctk.CTkCheckBox(self.lut_scroll_frame, text=filename)
                cb.pack(anchor="w", padx=10, pady=2)
                self.lut_checkboxes[filename] = cb

        except Exception as e:
            ctk.CTkLabel(self.lut_scroll_frame, text=f"读取文件夹失败: {e}").pack()
            
    def log_lut(self, message, clear=False):
        self.after(0, self._update_log, self.lut_log_textbox, message, clear)

    def start_lut_processing(self):
        self.lut_start_button.configure(state="disabled")
        self.lut_stop_button.configure(state="normal")
        self.lut_stop_event.clear()
        self.log_lut("", clear=True)
        threading.Thread(target=self.run_lut_logic, daemon=True).start()

    def stop_lut_processing(self):
        self.log_lut("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.lut_stop_event.set()
        self.lut_stop_button.configure(state="disabled")

    def _reset_lut_buttons(self):
        self.lut_start_button.configure(state="normal")
        self.lut_stop_button.configure(state="disabled")

    def run_lut_logic(self):
        try:
            video_dir = self.lut_video_folder_entry.get()
            filter_dir = self.lut_filter_folder_entry.get()
            output_dir = self.lut_output_folder_entry.get()

            if not all([video_dir, filter_dir, output_dir]):
                self.log_lut("❌ 错误: 所有文件夹路径都必须填写。")
                return

            # 决定使用哪些滤镜
            selected_filters = [name for name, cb in self.lut_checkboxes.items() if cb.get() == 1]
            all_available_filters = list(self.lut_checkboxes.keys())
            
            filters_to_use = selected_filters if selected_filters else all_available_filters

            if not filters_to_use:
                self.log_lut("❌ 错误: 滤镜文件夹中没有找到任何 .cube 文件，或者没有选择任何指定滤镜。")
                return
            
            self.log_lut(f"▶️ 将从以下 {len(filters_to_use)} 个滤镜中随机选择使用:")
            for f in filters_to_use[:5]: self.log_lut(f"  - {f}") # 最多显示5个
            if len(filters_to_use) > 5: self.log_lut("  - ...")

            # 扫描视频文件
            video_files = []
            for dirpath, _, filenames in os.walk(video_dir):
                for filename in filenames:
                    if filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
                        video_files.append(os.path.join(dirpath, filename))
            
            if not video_files:
                self.log_lut("ℹ️ 在指定的视频文件夹中未找到任何视频文件。")
                return

            self.log_lut(f"\n🔍 找到 {len(video_files)} 个视频文件，开始处理...")
            
            for i, video_path in enumerate(video_files):
                if self.lut_stop_event.is_set():
                    self.log_lut("🔴 任务已中止。")
                    break
                
                # 为每个视频随机选择一个滤镜
                chosen_filter_name = random.choice(filters_to_use)
                lut_path = os.path.join(filter_dir, chosen_filter_name)
                
                # 构建输出路径
                relative_path = os.path.relpath(os.path.dirname(video_path), video_dir)
                target_output_dir = os.path.join(output_dir, relative_path)
                if not os.path.exists(target_output_dir): os.makedirs(target_output_dir)
                
                output_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_{os.path.splitext(chosen_filter_name)[0]}.mp4"
                output_path = os.path.join(target_output_dir, output_filename)

                self.log_lut(f"\n--- [任务 {i+1}/{len(video_files)}] ---")
                self.log_lut(f"  视频: {os.path.basename(video_path)}")
                self.log_lut(f"  滤镜: {chosen_filter_name}")
                
                self._lut_worker(video_path, output_path, lut_path)
                
            if not self.lut_stop_event.is_set():
                self.log_lut("\n🎉 所有任务处理完毕！")

        except Exception as e:
            self.log_lut(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_lut_buttons)

    def _lut_worker(self, video_path, output_path, lut_path):
        """
        (最终修正版) 使用 FFmpeg 应用LUT滤镜，并对所有路径进行最终的标准化和转义处理。
        """
        self.log_lut(f"  -> 使用FFmpeg引擎处理滤镜...")
        
        ffmpeg_path = self._find_executable("ffmpeg")
        if not ffmpeg_path:
            self.log_lut("  ❌ 错误: 找不到 ffmpeg.exe。")
            return False

        # --- 核心修正点 1：对路径进行最终的清理和标准化 ---
        # 使用 os.path.normpath 清理路径中的 '..' 或 '.'
        # 然后统一替换为 '/', 保证跨平台兼容性
        safe_video_path = os.path.normpath(video_path).replace('\\', '/')
        safe_output_path = os.path.normpath(output_path).replace('\\', '/')
        
        # --- 核心修正点 2：专门为FFmpeg滤镜路径进行转义 ---
        # 首先，统一斜杠
        escaped_lut_path = str(lut_path).replace('\\', '/')
        # 其次，对Windows盘符后的冒号进行转义，防止FFmpeg误解析
        if ':' in escaped_lut_path:
            escaped_lut_path = escaped_lut_path.replace(':', '\\:', 1)

        filter_option = f"lut3d=file='{escaped_lut_path}'"

        base_command = [
            ffmpeg_path,
            '-y',
            '-hide_banner', '-loglevel', 'error',
            '-i', safe_video_path,
            '-vf', filter_option,
            '-c:a', 'copy',
        ]

        try:
            if self.is_gpu_available:
                self.log_lut("  -> 尝试使用GPU (h264_nvenc) 编码...")
                gpu_command = base_command + ['-c:v', 'h264_nvenc', safe_output_path]
                subprocess.run(gpu_command, check=True, capture_output=True, text=True, encoding='utf-8')
            else:
                raise Exception("GPU not available, fallback to CPU")
        except Exception as e:
            self.log_lut("  -> 警告: GPU编码失败或不可用，回退到CPU (libx264) 编码。")
            try:
                cpu_command = base_command + ['-c:v', 'libx264', '-preset', 'medium', safe_output_path]
                subprocess.run(cpu_command, check=True, capture_output=True, text=True, encoding='utf-8')
            except subprocess.CalledProcessError as e_cpu:
                error_msg = e_cpu.stderr.strip()
                self.log_lut(f"  ❌ CPU处理失败: FFmpeg 错误日志如下:\n{error_msg}")
                return False
            except Exception as e_cpu_unknown:
                self.log_lut(f"  ❌ CPU处理失败: 发生未知错误: {e_cpu_unknown}")
                return False

        self.log_lut(f"  ✅ 成功输出到: {os.path.basename(output_path)}")
        return True
    # ==============================================================================
    # --- 绿幕替换 (新功能) ---
    # ==============================================================================
    def setup_gs_replace_workflow(self):
        """创建绿幕替换功能的UI界面"""
        tab = self.main_tabview.tab("绿幕替换")

        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="绿幕视频批量合成工具")
        scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # --- 路径设置 ---
        ctk.CTkLabel(scrollable_frame, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10,5))
        self.create_folder_selection_row(scrollable_frame, "背景视频文件夹:", "选择作为背景的视频文件夹", "gs_replace_bg_folder_entry")
        self.create_folder_selection_row(scrollable_frame, "绿幕视频文件夹:", "选择包含绿幕素材的视频文件夹", "gs_replace_gs_folder_entry")
        self.create_folder_selection_row(scrollable_frame, "输出文件夹:", "选择处理结果的存放位置", "gs_replace_output_folder_entry")

        # --- 参数设置 ---
        ctk.CTkLabel(scrollable_frame, text="2. 功能开关", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20,5))
        switches_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        switches_frame.pack(fill="x", padx=10, pady=5)
        
        self.gs_replace_random_concat_switch = ctk.CTkSwitch(switches_frame, text="以绿幕时长为准，随机拼接背景视频")
        self.gs_replace_random_concat_switch.pack(anchor="w", pady=5)
        
        self.gs_replace_audio_switch = ctk.CTkSwitch(switches_frame, text="以绿幕视频的音频为主")
        self.gs_replace_audio_switch.pack(anchor="w", pady=5)
        self.gs_replace_audio_switch.select() # 默认开启

        # --- 开始处理 ---
        run_frame = ctk.CTkFrame(scrollable_frame)
        run_frame.pack(fill="x", padx=10, pady=(20, 10))
        ctk.CTkLabel(run_frame, text="3. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.gs_replace_start_button = ctk.CTkButton(button_frame, text="开始批量替换", height=40, command=self.start_gs_replace_processing)
        self.gs_replace_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.gs_replace_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_gs_replace_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.gs_replace_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- 日志区域 ---
        self.gs_replace_log_textbox = ctk.CTkTextbox(scrollable_frame, state="disabled", height=200, text_color="#A9A9A9")
        self.gs_replace_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def log_gs_replace(self, message, clear=False):
        self.after(0, self._update_log, self.gs_replace_log_textbox, message, clear)

    def start_gs_replace_processing(self):
        self.gs_replace_start_button.configure(state="disabled")
        self.gs_replace_stop_button.configure(state="normal")
        self.gs_replace_stop_event.clear()
        self.log_gs_replace("", clear=True)
        threading.Thread(target=self.run_gs_replace_logic, daemon=True).start()

    def stop_gs_replace_processing(self):
        self.log_gs_replace("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.gs_replace_stop_event.set()
        self.gs_replace_stop_button.configure(state="disabled")

    def _reset_gs_replace_buttons(self):
        self.gs_replace_start_button.configure(state="normal")
        self.gs_replace_stop_button.configure(state="disabled")

    def run_gs_replace_logic(self):
        try:
            bg_dir = self.gs_replace_bg_folder_entry.get()
            gs_dir = self.gs_replace_gs_folder_entry.get()
            output_dir = self.gs_replace_output_folder_entry.get()

            if not all([bg_dir, gs_dir, output_dir]):
                self.log_gs_replace("❌ 错误: 所有文件夹路径都必须填写。")
                return

            if not os.path.exists(output_dir): os.makedirs(output_dir)

            video_ext = ('.mp4', '.avi', '.mkv', '.mov')
            bg_videos = sorted([os.path.join(bg_dir, f) for f in os.listdir(bg_dir) if f.lower().endswith(video_ext)])
            gs_videos = sorted([os.path.join(gs_dir, f) for f in os.listdir(gs_dir) if f.lower().endswith(video_ext)])

            if not bg_videos or not gs_videos:
                self.log_gs_replace("❌ 错误: 背景视频文件夹或绿幕视频文件夹中没有找到视频文件。")
                return
            
            self.log_gs_replace(f"🔍 找到 {len(bg_videos)} 个背景视频和 {len(gs_videos)} 个绿幕视频。")
            
            is_random_concat = self.gs_replace_random_concat_switch.get() == 1
            use_gs_audio = self.gs_replace_audio_switch.get() == 1
            
            if is_random_concat:
                self.log_gs_replace("▶️ 已选择【随机拼接】模式。")
                # 随机拼接模式
                for i, gs_video_path in enumerate(gs_videos):
                    if self.gs_replace_stop_event.is_set(): break
                    self.log_gs_replace(f"\n--- [任务 {i+1}/{len(gs_videos)}] 正在处理绿幕视频: {os.path.basename(gs_video_path)} ---")
                    output_path = os.path.join(output_dir, f"processed_{os.path.basename(gs_video_path)}")
                    self._gs_replace_random_worker(bg_videos, gs_video_path, output_path, use_gs_audio)
            else:
                self.log_gs_replace("▶️ 已选择【顺序替换】模式。")
                # 顺序模式
                num_tasks = min(len(bg_videos), len(gs_videos))
                if num_tasks == 0:
                     self.log_gs_replace("❌ 视频文件不足，无法配对处理。")
                     return
                self.log_gs_replace(f"将处理 {num_tasks} 对视频。")

                for i in range(num_tasks):
                    if self.gs_replace_stop_event.is_set(): break
                    bg_video_path = bg_videos[i]
                    gs_video_path = gs_videos[i]
                    self.log_gs_replace(f"\n--- [任务 {i+1}/{num_tasks}] ---")
                    self.log_gs_replace(f"  背景: {os.path.basename(bg_video_path)}")
                    self.log_gs_replace(f"  绿幕: {os.path.basename(gs_video_path)}")
                    output_path = os.path.join(output_dir, f"processed_{os.path.basename(gs_video_path)}")
                    self._gs_replace_worker(bg_video_path, gs_video_path, output_path, use_gs_audio)
            
            if not self.gs_replace_stop_event.is_set():
                self.log_gs_replace("\n🎉 所有任务处理完毕！")
            else:
                self.log_gs_replace("\n🔴 任务被用户中止。")

        except Exception as e:
            self.log_gs_replace(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_gs_replace_buttons)

    def _gs_replace_worker(self, bg_path, gs_path, output_path, use_gs_audio, bg_clip_obj=None):
        from moviepy.editor import VideoFileClip, CompositeVideoClip
        from moviepy.video.fx import all as vfx
        """核心处理单个视频对的函数"""
        bg_clip, gs_clip, final_clip = None, None, None
        try:
            gs_clip = VideoFileClip(gs_path)
            # 如果没有传入背景剪辑对象，则从路径加载
            bg_clip = bg_clip_obj if bg_clip_obj else VideoFileClip(bg_path)
            
            # 统一视频尺寸为背景视频的尺寸
            target_size = bg_clip.size
            gs_clip_resized = gs_clip.resize(target_size)

            # MoviePy的chromakey效果，颜色阈值为180，模糊半径为0.02（相对值）
            keyed_gs_clip = gs_clip_resized.fx(vfx.mask_color, color=[0, 255, 0], thr=180, s=0.02)
            
            # 将抠像后的绿幕视频置于背景之上
            final_clip = CompositeVideoClip([bg_clip, keyed_gs_clip.set_position("center")])
            
            # 根据开关决定使用哪个音频
            if use_gs_audio:
                final_clip.audio = gs_clip.audio
                self.log_gs_replace("  -> 使用绿幕视频的音频。")
            else:
                final_clip.audio = bg_clip.audio
                self.log_gs_replace("  -> 使用背景视频的音频。")

            # 最终视频时长以绿幕视频为准
            final_clip = final_clip.set_duration(gs_clip.duration)
            
            final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
            self.log_gs_replace(f"  ✅ 成功合成视频: {os.path.basename(output_path)}")

        except Exception as e:
            self.log_gs_replace(f"  ❌ 处理失败: {e}")
        finally:
            # 确保所有剪辑对象都被关闭以释放内存
            if gs_clip: gs_clip.close()
            if bg_clip: bg_clip.close()
            if final_clip: final_clip.close()
    
    def _gs_replace_random_worker(self, bg_video_paths, gs_video_path, output_path, use_gs_audio):
        from moviepy.editor import VideoFileClip, concatenate_videoclips 
        """处理随机拼接模式下的单个绿幕视频"""
        gs_clip_info, concatenated_bg = None, None
        try:
            gs_clip_info = VideoFileClip(gs_video_path)
            target_duration = gs_clip_info.duration
            self.log_gs_replace(f"  -> 绿幕视频时长为 {target_duration:.2f} 秒，开始拼接背景...")

            clips_to_concat = []
            current_duration = 0
            
            # 随机打乱背景视频列表
            random.shuffle(bg_video_paths)
            
            # 循环拼接直到时长足够
            while current_duration < target_duration:
                for path in bg_video_paths:
                    if current_duration >= target_duration: break
                    try:
                        clip = VideoFileClip(path)
                        clips_to_concat.append(clip)
                        current_duration += clip.duration
                    except Exception:
                        self.log_gs_replace(f"  -> 警告: 加载背景视频 {os.path.basename(path)} 失败，跳过。")
            
            if not clips_to_concat:
                 self.log_gs_replace("  ❌ 无法加载任何背景视频来拼接。")
                 return
            
            # 合成一个长的背景视频
            concatenated_bg = concatenate_videoclips(clips_to_concat)
            self.log_gs_replace(f"  -> 背景拼接完成，总时长 {concatenated_bg.duration:.2f} 秒。")

            # 调用核心worker进行处理，直接传入拼接好的背景剪辑对象
            self._gs_replace_worker(None, gs_video_path, output_path, use_gs_audio, bg_clip_obj=concatenated_bg)

        finally:
            # 确保关闭所有临时剪辑
            if gs_clip_info: gs_clip_info.close()
            if concatenated_bg: concatenated_bg.close()
    # ==============================================================================
    # --- 定格 (新功能) ---
    # ==============================================================================
    def setup_freeze_workflow(self):
        """创建视频定格功能的UI界面"""
        tab = self.main_tabview.tab("定格")

        # --- 路径设置 ---
        ctk.CTkLabel(tab, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,5))
        self.create_folder_selection_row(tab, "源视频文件夹:", "选择包含视频的文件夹 (可含子文件夹)", "freeze_input_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择处理结果的存放位置", "freeze_output_folder_entry")

        # --- 参数设置 ---
        ctk.CTkLabel(tab, text="2. 设置参数", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20,5))
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(duration_frame, text="定格时长 (秒):", width=120, anchor="w").pack(side="left")
        self.freeze_duration_entry = ctk.CTkEntry(duration_frame)
        self.freeze_duration_entry.insert(0, "3") # 默认值
        self.freeze_duration_entry.pack(side="left", fill="x", expand=True)

        # --- 开始处理 ---
        run_frame = ctk.CTkFrame(tab)
        run_frame.pack(fill="x", padx=10, pady=(20, 10))
        ctk.CTkLabel(run_frame, text="3. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.freeze_start_button = ctk.CTkButton(button_frame, text="开始批量定格处理", height=40, command=self.start_freeze_processing)
        self.freeze_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.freeze_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_freeze_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.freeze_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- 日志区域 ---
        self.freeze_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.freeze_log_textbox.pack(expand=True, fill="both", padx=10, pady=(5,10))

    def log_freeze(self, message, clear=False):
        self.after(0, self._update_log, self.freeze_log_textbox, message, clear)

    def start_freeze_processing(self):
        self.freeze_start_button.configure(state="disabled")
        self.freeze_stop_button.configure(state="normal")
        self.freeze_stop_event.clear()
        self.log_freeze("", clear=True)
        threading.Thread(target=self.run_freeze_logic, daemon=True).start()

    def stop_freeze_processing(self):
        self.log_freeze("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.freeze_stop_event.set()
        self.freeze_stop_button.configure(state="disabled")

    def _reset_freeze_buttons(self):
        self.freeze_start_button.configure(state="normal")
        self.freeze_stop_button.configure(state="disabled")
        
    def _find_executable(self, name):
        """查找 ffmpeg 或 ffprobe 的路径"""
        executable_name = f"{name}.exe" if sys.platform.startswith("win") else name
        
        # 检查程序打包路径
        if getattr(sys, "frozen", False) and hasattr(sys, '_MEIPASS'):
            local_path = os.path.join(sys._MEIPASS, "ffmpeg", executable_name)
            if os.path.isfile(local_path):
                return local_path
        
        # 检查开发环境相对路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(current_dir, "ffmpeg", executable_name)
        if os.path.isfile(local_path):
            return local_path

        # 检查系统 PATH
        system_path = shutil.which(executable_name)
        if system_path:
            return system_path
            
        return None

    def run_freeze_logic(self):
        temp_folder = None
        try:
            input_dir = self.freeze_input_folder_entry.get()
            output_dir = self.freeze_output_folder_entry.get()
            
            if not all([input_dir, output_dir]):
                self.log_freeze("❌ 错误: 源视频文件夹和输出文件夹都必须填写。")
                return

            try:
                duration = float(self.freeze_duration_entry.get())
                if duration <= 0: raise ValueError
            except (ValueError, TypeError):
                self.log_freeze("❌ 错误: 定格时长必须是一个有效的正数。")
                return
            
            ffmpeg_path = self._find_executable("ffmpeg")
            ffprobe_path = self._find_executable("ffprobe")

            if not ffmpeg_path or not ffprobe_path:
                self.log_freeze("❌ 错误: 找不到 ffmpeg 或 ffprobe。请确保它们已安装或位于程序目录的'ffmpeg'子文件夹中。")
                return

            self.log_freeze("✅ FFmpeg 和 FFprobe 已找到，准备开始处理...")

            temp_folder = os.path.join(output_dir, "freeze_temp")
            if os.path.exists(temp_folder): shutil.rmtree(temp_folder)
            os.makedirs(temp_folder)

            processed_count = 0
            for dirpath, _, filenames in os.walk(input_dir):
                if self.freeze_stop_event.is_set(): break
                for filename in filenames:
                    if self.freeze_stop_event.is_set(): break
                    if not filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')): continue

                    input_path = os.path.join(dirpath, filename)
                    relative_dir = os.path.relpath(dirpath, input_dir)
                    target_output_dir = os.path.join(output_dir, relative_dir)
                    if not os.path.exists(target_output_dir): os.makedirs(target_output_dir)
                    output_path = os.path.join(target_output_dir, filename)

                    self.log_freeze(f"\n--- 正在处理: {filename} ---")
                    if self._freeze_worker(ffmpeg_path, ffprobe_path, input_path, output_path, duration, temp_folder):
                        processed_count += 1
            
            if self.freeze_stop_event.is_set():
                self.log_freeze("🔴 任务已由用户中止。")
            
            self.log_freeze(f"\n--- 批量处理完成 ---")
            self.log_freeze(f"共成功处理了 {processed_count} 个视频文件。")

        except Exception as e:
            self.log_freeze(f"发生未预料的严重错误: {e}")
        finally:
            if temp_folder and os.path.exists(temp_folder):
                try:
                    shutil.rmtree(temp_folder)
                    self.log_freeze("🗑️ 已清理临时文件夹。")
                except OSError as e:
                    self.log_freeze(f"⚠️ 清理临时文件夹失败: {e}")
            self.after(0, self._reset_freeze_buttons)

    def _freeze_worker(self, ffmpeg, ffprobe, input_path, output_path, freeze_duration, temp_folder):
        try:
            # 步骤1: 获取视频时长
            cmd_probe = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path]
            result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True)
            video_duration = float(result.stdout.strip())
            
            # 步骤2: 提取最后一帧
            # 使用唯一哈希值避免临时文件名冲突
            unique_id = hash(input_path)
            last_frame_img = os.path.join(temp_folder, f"frame_{unique_id}.png")
            # 定位到视频最后0.1秒处，大概率能取到最后一帧
            seek_time = max(0, video_duration - 0.1) 
            cmd_get_frame = [ffmpeg, "-y", "-ss", str(seek_time), "-i", input_path, "-vframes", "1", last_frame_img]
            subprocess.run(cmd_get_frame, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.log_freeze("  -> 步骤1: 成功提取最后一帧。")

            # 步骤3: 创建定格视频
            freeze_video_clip = os.path.join(temp_folder, f"freeze_{unique_id}.mp4")
            cmd_make_freeze = [
                ffmpeg, "-y", "-loop", "1", "-i", last_frame_img,
                "-c:v", "libx264", "-t", str(freeze_duration), "-pix_fmt", "yuv420p", "-an",
                freeze_video_clip
            ]
            subprocess.run(cmd_make_freeze, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.log_freeze(f"  -> 步骤2: 成功创建 {freeze_duration} 秒静音定格片段。")

            # 步骤4: 拼接原视频和定格视频
            cmd_concat = [
                ffmpeg, "-y", "-i", input_path, "-i", freeze_video_clip,
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v_out]",
                "-map", "[v_out]", "-map", "0:a?", "-c:a", "copy",
                output_path
            ]
            subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.log_freeze(f"  ✅ 成功: 已拼接并保存到 '{os.path.basename(output_path)}'")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore').strip().splitlines()[-5:]
            self.log_freeze(f"  ❌ FFmpeg处理失败: {' '.join(e.cmd)}")
            self.log_freeze("  -> FFmpeg错误信息 (末尾几行):\n" + "\n".join(error_msg))
            return False
        except Exception as e:
            self.log_freeze(f"  ❌ 处理中发生未知错误: {e}")
            return False    
       # ==============================================================================
    # --- 音频提取 (新功能) ---
    # ==============================================================================
    def setup_audio_extraction_workflow(self):
        """创建音频提取功能的UI界面"""
        tab = self.main_tabview.tab("音频提取")

        # --- 路径设置 ---
        ctk.CTkLabel(tab, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,5))
        self.create_folder_selection_row(tab, "源视频文件夹:", "选择包含视频的文件夹", "audio_input_folder_entry")
        self.create_folder_selection_row(tab, "音频输出文件夹:", "选择提取的MP3音频存放位置", "audio_output_folder_entry")

        # --- 参数设置 ---
        ctk.CTkLabel(tab, text="2. 设置参数", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20,5))
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(duration_frame, text="提取时长 (秒):", width=120, anchor="w").pack(side="left")
        self.audio_duration_entry = ctk.CTkEntry(duration_frame, placeholder_text="留空则提取完整音频")
        self.audio_duration_entry.pack(side="left", fill="x", expand=True)

        # --- 开始处理 ---
        run_frame = ctk.CTkFrame(tab)
        run_frame.pack(fill="x", padx=10, pady=(20, 10))
        ctk.CTkLabel(run_frame, text="3. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_audio_button = ctk.CTkButton(button_frame, text="开始批量提取音频", height=40, command=self.start_audio_extraction)
        self.start_audio_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.stop_audio_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_audio_extraction, state="disabled", fg_color="red", hover_color="darkred")
        self.stop_audio_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- 日志区域 ---
        self.audio_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.audio_log_textbox.pack(expand=True, fill="both", padx=10, pady=(5,10))

    def log_audio(self, message, clear=False):
        """向音频提取日志框记录信息"""
        self.after(0, self._update_log, self.audio_log_textbox, message, clear)

    def start_audio_extraction(self):
        """开始音频提取的线程"""
        self.start_audio_button.configure(state="disabled")
        self.stop_audio_button.configure(state="normal")
        self.audio_stop_event.clear()
        self.log_audio("", clear=True)
        threading.Thread(target=self.run_audio_extraction_logic, daemon=True).start()

    def stop_audio_extraction(self):
        """发送停止信号"""
        self.log_audio("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.audio_stop_event.set()
        self.stop_audio_button.configure(state="disabled")

    def _reset_audio_buttons(self):
        """重置开始/停止按钮的状态"""
        self.start_audio_button.configure(state="normal")
        self.stop_audio_button.configure(state="disabled")

    def run_audio_extraction_logic(self):
        """音频提取的主逻辑"""
        try:
            input_dir = self.audio_input_folder_entry.get()
            output_dir = self.audio_output_folder_entry.get()
            duration_str = self.audio_duration_entry.get()

            if not all([input_dir, output_dir]):
                self.log_audio("❌ 错误: 源视频文件夹和输出文件夹都必须填写。")
                return

            duration = None
            if duration_str:
                try:
                    duration = float(duration_str)
                    if duration <= 0:
                        self.log_audio("❌ 错误: 提取时长必须是一个正数。")
                        return
                except ValueError:
                    self.log_audio("❌ 错误: 提取时长必须是有效的数字。")
                    return
            
            video_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv'))]
            if not video_files:
                self.log_audio("ℹ️ 在源文件夹中未找到任何视频文件。")
                return

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            self.log_audio(f"🔍 扫描到 {len(video_files)} 个视频，准备开始提取...")
            processed_count = 0
            for i, filename in enumerate(video_files):
                if self.audio_stop_event.is_set():
                    self.log_audio("🔴 任务已由用户中止。")
                    break
                
                self.log_audio(f"\n--- [{i+1}/{len(video_files)}] 正在处理: {filename} ---")
                input_path = os.path.join(input_dir, filename)
                
                if self._audio_extraction_worker(input_path, output_dir, duration):
                    processed_count += 1
            
            self.log_audio(f"\n--- 批量处理完成 ---")
            self.log_audio(f"共成功提取了 {processed_count} 个音频文件。")

        except Exception as e:
            self.log_audio(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_audio_buttons)

    def _audio_extraction_worker(self, video_path, output_folder, duration):
        """处理单个视频文件的音频提取工作"""
        base_name, _ = os.path.splitext(os.path.basename(video_path))
        output_path = os.path.join(output_folder, f"{base_name}.mp3")
        
        if os.path.exists(output_path):
            self.log_audio(f"  -> 文件 {os.path.basename(output_path)} 已存在，跳过。")
            return True

        video_clip = None
        try:
            video_clip = VideoFileClip(video_path)
            if not video_clip.audio:
                self.log_audio(f"  -> 警告: 视频 '{os.path.basename(video_path)}' 不包含音频，已跳过。")
                return False

            audio_to_write = video_clip.audio
            
            # 如果指定了时长，则截取音频
            if duration is not None and duration > 0:
                self.log_audio(f"  -> 提取前 {duration:.2f} 秒的音频...")
                audio_to_write = audio_to_write.subclip(0, duration)

            audio_to_write.write_audiofile(output_path, logger=None)
            self.log_audio(f"  ✅ 成功提取到: {os.path.basename(output_path)}")
            return True

        except Exception as e:
            self.log_audio(f"  ❌ 处理文件 '{os.path.basename(video_path)}' 时出错: {e}")
            return False
        finally:
            if video_clip:
                if video_clip.audio:
                    video_clip.audio.close()
                video_clip.close()
     # ==============================================================================
    # --- 卡秒 (新功能整合) ---
    # ==============================================================================
    def setup_cut_workflow(self):
        tab = self.main_tabview.tab("卡秒")
        
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="视频跳剪处理器 (卡秒)")
        scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # --- 1. 路径设置 ---
        ctk.CTkLabel(scrollable_frame, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
        self.create_folder_selection_row(scrollable_frame, "源视频文件夹:", "选择包含视频的文件夹 (可含子文件夹)", "cut_input_folder_entry")
        self.create_folder_selection_row(scrollable_frame, "输出文件夹:", "选择处理结果的存放位置", "cut_output_folder_entry")

        # --- 2. 时间参数设置 ---
        ctk.CTkLabel(scrollable_frame, text="2. 设置卡秒时间点", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,0))
        self.create_widget_row(scrollable_frame, "播放到此时间点 (秒):", "cut_play_until", "2")
        self.create_widget_row(scrollable_frame, "跳转到此时间点 (秒):", "cut_resume_from", "6")

        # --- 3. FFmpeg 设置 (可选) ---
        ctk.CTkLabel(scrollable_frame, text="3. 高级设置 (可选)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,0))
        self.create_widget_row(scrollable_frame, "FFmpeg.exe 路径:", "cut_ffmpeg_path", "程序会自动查找，找不到时再手动指定", is_file=True)
        # 修改辅助函数，让其支持选择文件
        button = self.cut_ffmpeg_path_entry.master.winfo_children()[-1] # 获取 "..." 按钮
        button.configure(command=lambda e=self.cut_ffmpeg_path_entry: self.select_file_for_entry(e, "选择 ffmpeg.exe", [("Executable files", "*.exe"), ("All files", "*.*")]))


        # --- 4. 开始处理 ---
        run_frame = ctk.CTkFrame(scrollable_frame)
        run_frame.pack(fill="x", padx=5, pady=(20, 5))
        ctk.CTkLabel(run_frame, text="4. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.cut_start_button = ctk.CTkButton(button_frame, text="开始批量卡秒处理", height=40, command=self.start_cut_processing)
        self.cut_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.cut_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_cut_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.cut_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        self.cut_log_textbox = ctk.CTkTextbox(scrollable_frame, state="disabled", height=250, text_color="#A9A9A9")
        self.cut_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def log_cut(self, message, clear=False):
        self.after(0, self._update_log, self.cut_log_textbox, message, clear)

    def _cut_find_ffmpeg_path(self, custom_ffmpeg_path=None):
        ffmpeg_executable_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        if custom_ffmpeg_path and os.path.isfile(custom_ffmpeg_path):
            self.log_cut(f"信息: 使用用户指定的 FFmpeg: {custom_ffmpeg_path}")
            return custom_ffmpeg_path

        if getattr(sys, "frozen", False) and hasattr(sys, '_MEIPASS'):
            application_path = sys._MEIPASS
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
        
        local_ffmpeg_path = os.path.join(application_path, "ffmpeg", ffmpeg_executable_name)
        if os.path.isfile(local_ffmpeg_path):
            self.log_cut(f"信息: 在本地 'ffmpeg' 目录中找到 FFmpeg: {local_ffmpeg_path}")
            return local_ffmpeg_path

        system_path_ffmpeg = shutil.which(ffmpeg_executable_name)
        if system_path_ffmpeg:
            self.log_cut(f"信息: 在系统 PATH 中找到 FFmpeg: {system_path_ffmpeg}")
            return system_path_ffmpeg
            
        self.log_cut("错误: 找不到 FFmpeg ('{ffmpeg_executable_name}')。")
        self.log_cut("请确保 FFmpeg 已安装并添加到系统 PATH，或放置在 'ffmpeg' 文件夹中，或手动指定其路径。")
        return None

    def _cut_process_video(self, ffmpeg_path, input_path, output_path, start_time, end_time, jump_time):
        # 原封不动地移植了核心处理逻辑，仅将print改为logger
        if not os.path.exists(input_path):
            self.log_cut(f"错误: 找不到输入视频文件: {input_path}")
            return False
        
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as e:
                self.log_cut(f"错误: 创建输出子目录失败: {output_dir} - {e}")
                return False

        self.log_cut(f"\n信息: === 开始处理视频: '{os.path.basename(input_path)}' ===")
        self.log_cut(f"  将保留 {start_time:.2f}s 到 {end_time:.2f}s, 然后跳转到 {jump_time:.2f}s 继续。")

        filter_complex_str = (
            f"[0:v]trim=start={start_time}:end={end_time}[v_initial];"
            f"[0:v]trim=start={jump_time}[v_jumped];"
            f"[0:a]atrim=start={start_time}:end={end_time}[a_initial];"
            f"[0:a]atrim=start={jump_time}[a_jumped];"
            f"[v_initial][v_jumped]concat=n=2:v=1:a=0[out_v];"
            f"[a_initial][a_jumped]concat=n=2:v=0:a=1[out_a]"
        )
        command = [
            ffmpeg_path, "-hide_banner", "-loglevel", "error",
            "-i", input_path, "-filter_complex", filter_complex_str,
            "-map", "[out_v]", "-map", "[out_a]",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-strict", "-2", "-y", output_path,
        ]
        try:
            process = subprocess.run(command, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')
            self.log_cut(f"成功: 处理完成! 输出文件: {os.path.basename(output_path)}")
            return True
        except subprocess.CalledProcessError as e:
            self.log_cut(f"错误: FFmpeg 处理 '{os.path.basename(input_path)}' 失败。")
            if e.stderr: self.log_cut(f"  FFmpeg 错误输出:\n{e.stderr.strip()}")
            return False
        except Exception as e:
            self.log_cut(f"处理视频 '{os.path.basename(input_path)}' 时发生未知错误: {e}")
            return False

    def start_cut_processing(self):
        self.cut_start_button.configure(state="disabled")
        self.cut_stop_button.configure(state="normal")
        self.cut_stop_event.clear()
        self.log_cut("", clear=True)
        threading.Thread(target=self.run_cut_logic, daemon=True).start()

    def stop_cut_processing(self):
        self.log_cut("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.cut_stop_event.set()
        self.cut_stop_button.configure(state="disabled")

    def _reset_cut_buttons(self):
        self.cut_start_button.configure(state="normal")
        self.cut_stop_button.configure(state="disabled")
        
    def run_cut_logic(self):
        try:
            input_dir = self.cut_input_folder_entry.get()
            output_dir = self.cut_output_folder_entry.get()
            ffmpeg_path_user = self.cut_ffmpeg_path_entry.get()

            if not all([input_dir, output_dir]):
                self.log_cut("错误: 源视频文件夹和输出文件夹都必须填写。")
                return

            try:
                play_until = float(self.cut_play_until_entry.get())
                resume_from = float(self.cut_resume_from_entry.get())
                if play_until < 0 or resume_from <= play_until:
                    raise ValueError("时间点设置无效。")
            except ValueError:
                self.log_cut("错误: 时间点必须为有效数字，且跳转时间点必须大于播放时间点。")
                return
            
            ffmpeg_executable = self._cut_find_ffmpeg_path(ffmpeg_path_user)
            if not ffmpeg_executable:
                return

            self.log_cut(f"---开始扫描并处理视频 (保留 0s-{play_until:.2f}s, 跳转到 {resume_from:.2f}s)---")
            
            found_count, processed_count = 0, 0
            video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.mpeg', '.mpg')

            for dirpath, _, filenames in os.walk(input_dir):
                if self.cut_stop_event.is_set(): break
                for filename in filenames:
                    if self.cut_stop_event.is_set(): break
                    if not filename.lower().endswith(video_extensions): continue
                    
                    found_count += 1
                    input_video_path = os.path.join(dirpath, filename)
                    relative_dir = os.path.relpath(dirpath, input_dir)
                    target_output_dir = os.path.join(output_dir, relative_dir)
                    
                    base_name, ext = os.path.splitext(filename)
                    output_video_path = os.path.join(target_output_dir, f"{base_name}_processed{ext}")

                    if self._cut_process_video(ffmpeg_executable, input_video_path, output_video_path, 0.0, play_until, resume_from):
                        processed_count += 1
                
            if self.cut_stop_event.is_set():
                self.log_cut("🔴 任务已由用户中止。")
            
            self.log_cut(f"\n---批量处理完成---")
            self.log_cut(f"共找到视频文件: {found_count}")
            self.log_cut(f"成功处理视频文件: {processed_count}")

        except Exception as e:
            self.log_cut(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_cut_buttons)
    # ==============================================================================
    # --- NEWS虚化 (新功能整合) ---
    # ==============================================================================
    def setup_news_blur_workflow(self):
        tab = self.main_tabview.tab("NEWS虚化")
        
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="背景虚化画中画处理器")
        scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # --- 1. 路径设置 ---
        folders_frame = ctk.CTkFrame(scrollable_frame)
        folders_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(folders_frame, text="1. 选择文件夹", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,10))
        self.create_folder_selection_row(folders_frame, "源视频文件夹:", "选择包含视频的文件夹", "blur_input_folder_entry")
        self.create_folder_selection_row(folders_frame, "输出文件夹:", "选择处理结果的存放位置", "blur_output_folder_entry")
        
        # --- 2. 功能开关与偏移量设置 ---
        settings_frame = ctk.CTkFrame(scrollable_frame)
        settings_frame.pack(fill="x", padx=5, pady=10)
        ctk.CTkLabel(settings_frame, text="2. 功能开关与偏移量", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
        
        switches_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        switches_frame.pack(fill="x", padx=10, pady=5)
        self.blur_use_gpu_switch = ctk.CTkSwitch(switches_frame, text="启用GPU硬件加速")
        self.blur_use_gpu_switch.grid(row=0, column=0, sticky="w")
        self.blur_enable_pip_switch = ctk.CTkSwitch(switches_frame, text="启用画中画(PIP)")
        self.blur_enable_pip_switch.grid(row=1, column=0, sticky="w", pady=5)
        self.blur_enable_text_switch = ctk.CTkSwitch(switches_frame, text="启用自定义文案")
        self.blur_enable_text_switch.grid(row=2, column=0, sticky="w")
        self.blur_enable_pip_switch.configure(state="disabled") # <-- 新增：禁用开关
        self.blur_enable_pip_switch.deselect()

        offsets_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        offsets_frame.pack(fill="x", padx=5)
        self.create_widget_row(offsets_frame, "主视频下移像素:", "blur_offset_main", "20")
        self.create_widget_row(offsets_frame, "PIP上移像素:", "blur_offset_pip", "40")
        self.create_widget_row(offsets_frame, "文案上方间距:", "blur_offset_text", "30")
        self.blur_offset_pip_entry.configure(state="disabled")

        # --- 3. 文案配置 ---
        text_frame = ctk.CTkFrame(scrollable_frame)
        text_frame.pack(fill="x", padx=5, pady=10)
        ctk.CTkLabel(text_frame, text="3. 自定义文案配置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
        
        ctk.CTkLabel(text_frame, text="输入文案 (每个视频使用一行, 循环使用):").pack(anchor="w", padx=10, pady=(10, 2))
        self.blur_text_input_area = ctk.CTkTextbox(text_frame, height=100)
        self.blur_text_input_area.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        
        self.blur_font_list = self._news_get_fonts() # 可以复用之前的功能
        self.create_option_menu_row(text_frame, "选择字体 (zt文件夹):", "blur_font", self.blur_font_list, self.blur_font_list[0] if self.blur_font_list else "")
        self.create_color_picker_row(text_frame, "字体颜色:", "blur_font_color", "#FFFFFF")
        self.create_color_picker_row(text_frame, "背景颜色:", "blur_bg_color", "#000000")
        self.create_widget_row(text_frame, "字幕框宽度(px):", "blur_box_w", "600")
        self.create_widget_row(text_frame, "字幕框高度(px):", "blur_box_h", "100")
        self.create_widget_row(text_frame, "背景圆角半径(px):", "blur_corner_radius", "20")

        # --- 4. 开始处理 ---
        run_frame = ctk.CTkFrame(scrollable_frame)
        run_frame.pack(fill="x", padx=5, pady=10)
        ctk.CTkLabel(run_frame, text="4. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))

        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.blur_start_button = ctk.CTkButton(button_frame, text="设置模板并开始批量处理", height=40, command=self.start_blur_processing)
        self.blur_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.blur_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_blur_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.blur_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        self.blur_log_textbox = ctk.CTkTextbox(run_frame, state="disabled", height=200, text_color="#A9A9A9")
        self.blur_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
        ctk.CTkLabel(run_frame, text="重要提示：模板化处理假定所有视频的分辨率相同。", text_color="gray").pack(anchor="w", padx=10)
        
    def log_blur(self, message, clear=False):
        self.after(0, self._update_log, self.blur_log_textbox, message, clear)

    def _blur_select_roi(self, video_path, title):
        # This is the select_roi function from the new code, adapted as a class method.
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return None, "错误: 无法打开视频文件。"
        ret, frame = cap.read()
        if not ret: cap.release(); return None, "错误: 无法读取视频的第一帧。"
        self.withdraw()
        original_h, original_w = frame.shape[:2]
        MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT = 1280, 720
        scaling_factor = 1.0
        if original_w > MAX_DISPLAY_WIDTH or original_h > MAX_DISPLAY_HEIGHT:
            ratio = min(MAX_DISPLAY_WIDTH / original_w, MAX_DISPLAY_HEIGHT / original_h)
            display_w, display_h = int(original_w * ratio), int(original_h * ratio)
            scaling_factor = original_w / display_w
            display_frame = cv2.resize(frame, (display_w, display_h))
        else:
            display_frame = frame
        roi = cv2.selectROI(title, display_frame, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()
        self.deiconify()
        if roi and (roi != (0, 0, 0, 0)):
            original_roi = tuple(int(v * scaling_factor) for v in roi)
            return original_roi, f"已选择区域: x={original_roi[0]}, y={original_roi[1]}, 宽={original_roi[2]}, 高={original_roi[3]}"
        else:
            return None, "操作已取消，未选择有效区域。"

    def _blur_get_frame_at_0(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return None
        ret, frame = cap.read()
        cap.release()
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ret else None

    def _blur_create_text_image(self, text, box_w, box_h, font_path, font_color, bg_color, corner_radius):
        from PIL import Image, ImageDraw, ImageFont, ImageColor
        import numpy as np
        """
        (新版) 创建带自适应换行和字体缩放的文本图片。
        - 能够处理不含空格的长字符串。
        - 确保文本块在背景内精确居中。
        """
        # 准备一个临时的Image和Draw对象用于文本尺寸测量
        dummy_img = Image.new('RGB', (1,1))
        draw = ImageDraw.Draw(dummy_img)

        try:
            # 初始字体大小从一个较高的合理值开始 (例如，盒子高度的一半)
            font_size = box_h // 2
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            # 如果字体加载失败，使用默认字体
            font_size = 30
            font = ImageFont.load_default(size=font_size)
        
        padding = 15  # 在背景框内部留出一些边距
        target_text_w = box_w - padding * 2
        target_text_h = box_h - padding * 2

        wrapped_text = ""

        # --- 核心修改：自适应字体大小和换行的循环 ---
        while font_size > 5:
            font = font.font_variant(size=font_size)
            lines = []
            
            # 健壮的换行逻辑，能处理长单词
            words = text.split(' ')
            current_line = ""
            for word in words:
                # 检查单个词是否就超过了行宽
                if draw.textbbox((0, 0), word, font=font)[2] > target_text_w:
                    # 如果是，就逐字拆开这个长词
                    temp_word = ""
                    for char in word:
                        if draw.textbbox((0, 0), temp_word + char, font=font)[2] <= target_text_w:
                            temp_word += char
                        else:
                            lines.append(temp_word)
                            temp_word = char
                    current_line = temp_word # 长词的剩余部分成为新行
                else:
                    # 检查加上新词后是否超出行宽
                    if draw.textbbox((0, 0), current_line + " " + word, font=font)[2] <= target_text_w:
                        current_line += " " + word
                    else:
                        lines.append(current_line.strip())
                        current_line = word
            
            lines.append(current_line.strip())
            
            # 过滤掉可能产生的空行
            wrapped_text = "\n".join(filter(None, lines))

            # 测量换行后文本的总高度
            total_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
            text_h = total_bbox[3] - total_bbox[1]

            # 如果高度合适，就跳出循环
            if text_h <= target_text_h:
                break
            
            # 否则，缩小字体，继续尝试
            font_size -= 2
        
        # --- 绘制最终图片 ---
        # 创建带透明通道的背景图
        bg_image = Image.new('RGBA', (box_w, box_h), (255, 255, 255, 0))
        final_draw = ImageDraw.Draw(bg_image)

        # 绘制带圆角的背景色
        try:
            fill_color_rgb = ImageColor.getrgb(bg_color)
            final_fill = fill_color_rgb + (255,) # 添加255作为Alpha值，表示完全不透明
        except:
            final_fill = (0,0,0,255) # 颜色解析失败则默认为黑色
        
        final_draw.rounded_rectangle((0, 0, box_w, box_h), radius=corner_radius, fill=final_fill)

        # 重新精确测量最终文本的尺寸
        final_bbox = final_draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w = final_bbox[2] - final_bbox[0]
        text_h = final_bbox[3] - final_bbox[1]

        # --- 核心修改：精确居中定位 ---
        # (box_w - text_w) / 2  -> 水平居中
        # (box_h - text_h) / 2 - final_bbox[1] -> 垂直居中，减去顶边距(bearing)让视觉更居中
        position = ((box_w - text_w) / 2, (box_h - text_h) / 2 - final_bbox[1])
        
        # 在计算好的位置上绘制文本
        final_draw.multiline_text(position, wrapped_text, font=font, fill=font_color, align="center")

        return np.array(bg_image)

    def _blur_process_video(self, input_path, output_path, use_gpu, content_roi, pip_roi, text_config, offsets):
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
        import cv2
        # This is process_video_file, adapted as a class method.
        final_clip, original_clip = None, None
        try:
            original_clip = VideoFileClip(input_path)
            cx, cy, cw, ch = content_roi
            y_offset_main, y_offset_pip, y_offset_text = offsets['main'], offsets['pip'], offsets['text']
            
            cropped_part_for_bg = original_clip.crop(x1=cx, y1=cy, width=cw, height=ch)
            zoomed_background_source = cropped_part_for_bg.resize(original_clip.size)
            kernel_size = 99
            def blur_frame(image): return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
            blurred_background = zoomed_background_source.fl_image(blur_frame)

            sharp_foreground = original_clip.crop(x1=cx, y1=cy, width=cw, height=ch).set_position(('center', cy + y_offset_main))
            clips_to_compose = [blurred_background, sharp_foreground]

            if pip_roi:
                px, py, pw, ph = pip_roi
                first_frame = self._blur_get_frame_at_0(input_path)
                if first_frame is not None and (py + ph <= first_frame.shape[0]) and (px + pw <= first_frame.shape[1]):
                    pip_image = first_frame[py:py+ph, px:px+pw]
                    pip_clip = ImageClip(pip_image).set_duration(original_clip.duration).set_position((px, py - y_offset_pip))
                    clips_to_compose.append(pip_clip)
                else:
                    self.log_blur(f"警告：PIP区域无效或无法读取帧，已为文件 {os.path.basename(input_path)} 跳过PIP。")

            if text_config and text_config.get('text'):
                text_img_array = self._blur_create_text_image(
                    text_config['text'], text_config['box_w'], text_config['box_h'],
                    text_config['font_path'], text_config['font_color'], text_config['bg_color'],
                    text_config['corner_radius']
                )
                txt_clip = ImageClip(text_img_array).set_duration(original_clip.duration)
                text_x = 'center'
                text_y = cy + y_offset_main - text_config['box_h'] - y_offset_text
                txt_clip = txt_clip.set_position((text_x, text_y))
                clips_to_compose.append(txt_clip)

            final_clip = CompositeVideoClip(clips_to_compose, size=original_clip.size)
            if original_clip.audio: final_clip.audio = original_clip.audio

            codec = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
            try:
                final_clip.write_videofile(output_path, codec=codec, audio_codec="aac", fps=(original_clip.fps or 24), threads=8, logger=None)
            except Exception as e_gpu:
                if 'nvenc' in codec:
                    self.log_blur(f"  -> 警告: GPU编码失败 ({e_gpu})。正在回退到CPU编码。")
                    final_clip.write_videofile(output_path, codec='libx264', audio_codec="aac", fps=(original_clip.fps or 24), threads=8, logger=None)
                else: raise e_gpu
            return True, f"成功保存到: {os.path.basename(output_path)}"
        except Exception as e:
            return False, f"处理失败: {e}"
        finally:
            if original_clip: original_clip.close()
            # No need to close zoomed_background_source, it's a view of original_clip
            if final_clip: final_clip.close()
            
    def start_blur_processing(self):
        input_dir = self.blur_input_folder_entry.get()
        output_dir = self.blur_output_folder_entry.get()
        if not (input_dir and output_dir):
            tk_messagebox.showerror("错误", "请先选择源视频文件夹和输出文件夹！")
            return
            
        video_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
        if not video_files:
            tk_messagebox.showerror("错误", "在源文件夹中未找到任何视频文件！")
            return

        first_video_path = os.path.join(input_dir, video_files[0])
        self.log_blur(f"请为模板视频 '{video_files[0]}' 框选【视频内容】区域...", clear=True)
        self.update_idletasks()
        
        content_roi, msg = self._blur_select_roi(first_video_path, "设置模板 1/2: 框选【视频内容】区域")
        self.log_blur(msg)
        if not content_roi:
            self.log_blur("模板设置已取消，任务中止。"); return
            
        pip_roi = None
        if self.blur_enable_pip_switch.get():
            self.log_blur(f"请为模板视频 '{video_files[0]}' 框选【画中画(PIP)】区域...")
            self.update_idletasks()
            pip_roi, msg = self._blur_select_roi(first_video_path, "设置模板 2/2: 框选【画中画(PIP)】区域")
            self.log_blur(msg)
            if not pip_roi: self.log_blur("PIP模板未设置，后续将不添加画中画。")

        self.blur_start_button.configure(state="disabled")
        self.blur_stop_button.configure(state="normal")
        self.blur_stop_event.clear()
        
        threading.Thread(target=self.run_blur_logic, args=(video_files, content_roi, pip_roi), daemon=True).start()
    
    def stop_blur_processing(self):
        self.log_blur("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.blur_stop_event.set()
        self.blur_stop_button.configure(state="disabled")

    def _reset_blur_buttons(self):
        self.blur_start_button.configure(state="normal")
        self.blur_stop_button.configure(state="disabled")
        
    def run_blur_logic(self, video_files, content_roi, pip_roi):
        try:
            input_dir = self.blur_input_folder_entry.get()
            output_dir = self.blur_output_folder_entry.get()
            self.log_blur("\n★★★ 模板设置完成！即将对所有视频应用相同配置... ★★★")
            
            all_text_lines = self.blur_text_input_area.get("1.0", "end-1c").strip().split('\n')
            all_text_lines = [line.strip() for line in all_text_lines if line.strip()]
            
            font_file = self.blur_font_menu.get()
            try: base_path = sys._MEIPASS
            except Exception: base_path = os.path.abspath(os.path.dirname(__file__))
            full_font_path = os.path.join(base_path, "zt", font_file)

            if self.blur_enable_text_switch.get() and not (font_file and os.path.exists(full_font_path)):
                self.log_blur(f"错误: 已启用文案但选择的字体文件 '{font_file}' 无效或 'zt' 文件夹中不存在！")
                return

            text_base_config = {
                'box_w': int(self.blur_box_w_entry.get()), 'box_h': int(self.blur_box_h_entry.get()),
                'font_color': self.blur_font_color_value, 'bg_color': self.blur_bg_color_value,
                'font_path': full_font_path, 'corner_radius': int(self.blur_corner_radius_entry.get())
            }
            offsets_config = {
                'main': int(self.blur_offset_main_entry.get()),
                'pip': int(self.blur_offset_pip_entry.get()),
                'text': int(self.blur_offset_text_entry.get())
            }

            for i, filename in enumerate(video_files):
                if self.blur_stop_event.is_set():
                    self.log_blur("🔴 任务已由用户中止。"); break
                try:
                    self.log_blur(f"\n--- 处理进度: {i+1}/{len(video_files)} | 文件: {filename} ---")
                    input_path = os.path.join(input_dir, filename)
                    output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + "_processed.mp4")

                    current_text_config = None
                    if self.blur_enable_text_switch.get() and all_text_lines:
                        current_text_config = text_base_config.copy()
                        current_text_config['text'] = all_text_lines[i % len(all_text_lines)]
                        self.log_blur(f"添加文案: {current_text_config['text']}")
                    
                    success, message = self._blur_process_video(
                        input_path, output_path, self.blur_use_gpu_switch.get(),
                        content_roi, pip_roi,
                        current_text_config, offsets_config
                    )
                    self.log_blur(f"✔️ {message}" if success else f"❌ {message}")
                except Exception as e:
                    self.log_blur(f"处理文件 {filename} 时发生未知严重错误: {e}")
            
            if not self.blur_stop_event.is_set():
                self.log_blur("\n===================================\n🎉 所有任务处理完毕！🎉\n===================================")
        finally:
            self.after(0, self._reset_blur_buttons)    
  # ==============================================================================
    # --- NEWS绿幕 (新功能整合) ---
    # ==============================================================================
    # 将你原来的 setup_news_greenscreen_workflow 方法整个删除，然后粘贴下面的新版本

    def setup_news_greenscreen_workflow(self):
        tab = self.main_tabview.tab("NEWS绿幕")
        # 使用CTkScrollableFrame让内容过多时可以滚动
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="NEWS绿幕合成工具")
        scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # --- 1. 路径设置 (使用 .pack 布局) ---
        paths_frame = ctk.CTkFrame(scrollable_frame)
        paths_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(paths_frame, text="第一步: 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,10))
        self.create_folder_selection_row(paths_frame, "内容文件夹 (无绿幕):", "选择包含无绿幕视频的文件夹", "news_content_folder_entry")
        self.create_folder_selection_row(paths_frame, "模板文件夹 (带绿幕):", "选择包含绿幕模板视频的文件夹", "news_template_folder_entry")
        self.create_folder_selection_row(paths_frame, "输出文件夹:", "选择处理结果的存放位置", "news_output_folder_entry")

        # --- 2. 字幕配置 (使用 .pack 布局) ---
        text_frame = ctk.CTkFrame(scrollable_frame)
        text_frame.pack(fill="x", padx=5, pady=(10, 5))
        ctk.CTkLabel(text_frame, text="第二步: 字幕/文案配置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))
        
        ctk.CTkLabel(text_frame, text="输入文案 (每行对应一个任务):").pack(anchor="w", padx=10, pady=(10, 2))
        self.news_text_input_area = ctk.CTkTextbox(text_frame, height=120)
        self.news_text_input_area.pack(fill="x", expand=True, padx=10, pady=(0, 10))

        # 这些辅助函数内部使用 .pack()，现在可以正常工作了
        self.news_font_list = self._news_get_fonts()
        self.create_option_menu_row(text_frame, "选择字体 (zt文件夹):", "news_font", self.news_font_list, self.news_font_list[0] if self.news_font_list else "")
        self.create_color_picker_row(text_frame, "字体颜色:", "news_font_color", "#FFFFFF")
        self.create_color_picker_row(text_frame, "背景颜色:", "news_bg_color", "#000000")
        self.create_widget_row(text_frame, "字幕框宽度(px):", "news_box_w", "500")
        self.create_widget_row(text_frame, "字幕框高度(px):", "news_box_h", "100")
        self.create_widget_row(text_frame, "背景圆角半径(px):", "news_corner_radius", "20")
        self.create_widget_row(text_frame, "上方间距(px):", "news_y_offset", "30")

        # --- 3. 高级设置 (GPU) (使用 .pack 布局) ---
        gpu_frame = ctk.CTkFrame(scrollable_frame)
        gpu_frame.pack(fill="x", padx=5, pady=10)
        ctk.CTkLabel(gpu_frame, text="高级设置 (实验性功能)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        switch_frame = ctk.CTkFrame(gpu_frame, fg_color="transparent")
        switch_frame.pack(fill="x", padx=10, pady=5)
        self.news_use_gpu_switch = ctk.CTkSwitch(switch_frame, text="启用GPU加速 (仅加速视频编码)", command=self._news_toggle_gpu_options)
        self.news_use_gpu_switch.pack(side="left")
        
        self.news_gpu_codec_menu = ctk.CTkOptionMenu(switch_frame, values=[
            'h264_nvenc (NVIDIA)', 'h264_amf (AMD)', 'h264_qsv (Intel)', 'h264_videotoolbox (macOS)'
        ])
        self.news_gpu_codec_menu.pack(side="left", padx=20)
        self._news_toggle_gpu_options()

        # --- 4. 开始处理与日志 (使用 .pack 布局) ---
        run_frame = ctk.CTkFrame(scrollable_frame)
        run_frame.pack(expand=True, fill="both", padx=5, pady=5)
        ctk.CTkLabel(run_frame, text="第三步: 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)

        self.news_start_button = ctk.CTkButton(run_frame, text="设置模板并开始批量合成", height=40, command=self.start_news_greenscreen_processing)
        self.news_start_button.pack(fill="x", padx=10, pady=10)
        
        self.news_log_textbox = ctk.CTkTextbox(run_frame, state="disabled", height=200, text_color="#A9A9A9")
        self.news_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
        
    def log_news_greenscreen(self, message, clear=False):
        self.after(0, self._update_log, self.news_log_textbox, message, clear)

    def _news_toggle_gpu_options(self):
        is_on = self.news_use_gpu_switch.get() == 1
        self.news_gpu_codec_menu.configure(state="normal" if is_on else "disabled")

    def _news_get_fonts(self):
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(os.path.dirname(__file__))
        font_dir = os.path.join(base_path, "zt")
        if not os.path.exists(font_dir):
            os.makedirs(font_dir)
            return ["zt文件夹为空"]
        fonts = [f for f in os.listdir(font_dir) if f.lower().endswith(('.ttf', '.otf'))]
        return fonts if fonts else ["zt文件夹中没有字体"]

    def _news_get_display_frame(self, frame):
        MAX_DISPLAY_WIDTH, MAX_DISPLAY_HEIGHT = 1280, 720
        h, w = frame.shape[:2]
        if w > MAX_DISPLAY_WIDTH or h > MAX_DISPLAY_HEIGHT:
            ratio = min(MAX_DISPLAY_WIDTH / w, MAX_DISPLAY_HEIGHT / h)
            return cv2.resize(frame, (int(w * ratio), int(h * ratio)))
        return frame

    def _news_select_roi(self, video_path, title):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return None, "错误: 无法打开视频文件。"
        ret, frame = cap.read()
        if not ret:
            cap.release()
            return None, "错误: 无法读取视频的第一帧。"
        self.withdraw()
        original_h, original_w = frame.shape[:2]
        display_frame = self._news_get_display_frame(frame)
        display_h, display_w = display_frame.shape[:2]
        scaling_factor = original_w / display_w if display_w > 0 else 1
        
        roi = cv2.selectROI(title, display_frame, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()
        self.deiconify()
        
        if roi and (roi != (0, 0, 0, 0)):
            original_roi = tuple(int(v * scaling_factor) for v in roi)
            return original_roi, f"已选择区域: x={original_roi[0]}, y={original_roi[1]}, 宽={original_roi[2]}, 高={original_roi[3]}"
        else:
            return None, "操作已取消，未选择有效区域。"

    def _news_create_text_image(self, text, box_w, box_h, font_path, font_color, bg_color, corner_radius):
        # This is the create_text_image_with_autofit function, slightly adapted
        try: font = ImageFont.truetype(font_path, box_h)
        except IOError: font = ImageFont.load_default()
        
        font_size = box_h
        while font_size > 5:
            font = font.font_variant(size=font_size)
            words = text.split(' '); lines = []; line = ''
            padding = 10; target_text_w = box_w - padding * 2
            
            # This complex wrapping logic remains unchanged as per instructions
            for word in words:
                word_bbox = font.getbbox(word)
                if word_bbox[2] - word_bbox[0] > target_text_w:
                    temp_word = ''
                    for char in word:
                        char_bbox = font.getbbox(temp_word + char)
                        if char_bbox[2] - char_bbox[0] <= target_text_w: temp_word += char
                        else: lines.append(temp_word); temp_word = char
                    if temp_word: line = temp_word + ' '
                else:
                    line_bbox = font.getbbox(line + word)
                    if line_bbox[2] - line_bbox[0] <= target_text_w: line += word + ' '
                    else: lines.append(line.strip()); line = word + ' '
            lines.append(line.strip())
            wrapped_text = "\n".join(lines)
            
            bbox = ImageDraw.Draw(Image.new('RGB', (1,1))).multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
            text_h = bbox[3] - bbox[1]
            if text_h <= box_h - padding * 2: break
            font_size -= 1

        bg_image = Image.new('RGBA', (box_w, box_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(bg_image)
        try: fill_color_rgb = ImageColor.getrgb(bg_color)
        except: fill_color_rgb = (0,0,0)
        
        draw.rounded_rectangle((0, 0, box_w, box_h), radius=corner_radius, fill=fill_color_rgb + (255,))
        final_bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
        text_w, text_h = final_bbox[2] - final_bbox[0], final_bbox[3] - final_bbox[1]
        position = ((box_w - text_w) / 2, (box_h - text_h) / 2 - final_bbox[1]) # Adjusted for better vertical centering
        draw.multiline_text(position, wrapped_text, font=font, fill=font_color, align="center")
        return np.array(bg_image)

    def _news_process_video(self, content_path, template_path, output_path, content_roi, text_config, use_gpu=False, gpu_codec='libx264'):
        # This is the process_video_insertion function
        content_clip, template_clip, final_clip = None, None, None
        try:
            content_clip = VideoFileClip(content_path)
            template_clip = VideoFileClip(template_path)
            x, y, w, h = content_roi
            insert_clip = content_clip.crop(x1=x, y1=y, width=w, height=h)
            
            template_first_frame = template_clip.get_frame(0)
            hsv = cv2.cvtColor(template_first_frame, cv2.COLOR_RGB2HSV)
            lower_green, upper_green = np.array([35, 43, 46]), np.array([85, 255, 255])
            green_mask = cv2.inRange(hsv, lower_green, upper_green)
            kernel = np.ones((15, 15), np.uint8)
            cleaned_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours: return False, f"在模板 '{os.path.basename(template_path)}' 中未找到绿幕。"
            gx, gy, gw, gh = cv2.boundingRect(max(contours, key=cv2.contourArea))
            insert_clip_resized = insert_clip.resize((gw, gh))
            
            # Using mask_color is simple but less robust. Let's stick to it as per original code.
            #keyed_insert = insert_clip_resized.fx(mpy.vfx.mask_color, color=[0, 255, 0], thr=100, s=5)
            # A slightly better approach is to use the contour mask, but we follow the original.
            insert_clip_final = insert_clip_resized.set_position((gx, gy))

            final_duration = template_clip.duration
            clips_to_compose = [template_clip, insert_clip_final.set_duration(final_duration)]

            if text_config['text']:
                text_img_array = self._news_create_text_image(
                    text_config['text'], text_config['box_w'], text_config['box_h'],
                    text_config['font_path'], text_config['font_color'], text_config['bg_color'],
                    text_config['corner_radius']
                )
                txt_clip = ImageClip(text_img_array).set_duration(final_duration)
                text_x = (template_clip.w - text_config['box_w']) / 2
                text_y = gy - text_config['box_h'] - text_config['y_offset']
                txt_clip = txt_clip.set_position((text_x, text_y))
                clips_to_compose.append(txt_clip)

            final_clip = CompositeVideoClip(clips_to_compose, size=template_clip.size).set_duration(final_duration)
            if template_clip.audio: final_clip.audio = template_clip.audio.set_duration(final_duration)
            
            codec_to_use = gpu_codec if use_gpu and self.is_gpu_available else 'libx264'
            try:
                final_clip.write_videofile(output_path, codec=codec_to_use, audio_codec="aac", fps=(template_clip.fps or 24), threads=8, logger=None)
            except Exception as e_gpu:
                if 'nvenc' in codec_to_use: # If GPU fails, try CPU
                    self.log_news_greenscreen(f"  -> 警告: GPU编码失败 ({e_gpu})。正在回退到CPU编码。")
                    final_clip.write_videofile(output_path, codec='libx264', audio_codec="aac", fps=(template_clip.fps or 24), threads=8, logger=None)
                else:
                    raise e_gpu # Re-raise if it wasn't a GPU error
                    
            return True, f"成功保存到: {os.path.basename(output_path)}"
        except Exception as e:
            return False, f"处理失败: {e}"
        finally:
            if content_clip: content_clip.close()
            if template_clip: template_clip.close()
            if final_clip: final_clip.close()

    def start_news_greenscreen_processing(self):
        # The start button now only prepares and validates, then launches the thread.
        # ROI selection happens here, on the main thread, which is safer for GUI operations.
        content_dir = self.news_content_folder_entry.get()
        template_dir = self.news_template_folder_entry.get()
        output_dir = self.news_output_folder_entry.get()

        if not all([content_dir, template_dir, output_dir]):
            tk_messagebox.showerror("错误", "请选择所有三个文件夹！")
            return

        content_files = sorted([f for f in os.listdir(content_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
        if not content_files:
            tk_messagebox.showerror("错误", "内容文件夹中没有任何视频文件！")
            return
            
        first_content_path = os.path.join(content_dir, content_files[0])
        self.log_news_greenscreen(f"请为模板视频 '{content_files[0]}' 框选要嵌入的内容区域...")
        self.update_idletasks() # Ensure log message appears

        template_content_roi, msg = self._news_select_roi(first_content_path, "设置模板: 框选要嵌入的内容")
        self.log_news_greenscreen(msg)
        
        if not template_content_roi:
            self.log_news_greenscreen("模板设置已取消。")
            return

        # If ROI is selected, now we can start the background thread for the heavy lifting.
        self.news_start_button.configure(state="disabled", text="正在处理中...")
        self.news_stop_event.clear()
        
        # Pass the selected ROI to the processing thread
        threading.Thread(target=self.run_news_greenscreen_logic, args=(template_content_roi,), daemon=True).start()

    def run_news_greenscreen_logic(self, template_content_roi):
        # This function does the batch processing, now that the ROI is already defined.
        try:
            content_dir, template_dir, output_dir = self.news_content_folder_entry.get(), self.news_template_folder_entry.get(), self.news_output_folder_entry.get()
            font_file = self.news_font_menu.get()
            
            try: base_path = sys._MEIPASS
            except Exception: base_path = os.path.abspath(os.path.dirname(__file__))
            font_dir = os.path.join(base_path, "zt")
            full_font_path = os.path.join(font_dir, font_file)
            
            if not (font_file and os.path.exists(full_font_path)):
                self.log_news_greenscreen(f"错误: 选择的字体文件 '{font_file}' 无效或 'zt' 文件夹中不存在！")
                return

            all_text_lines = self.news_text_input_area.get("1.0", "end-1c").strip().split('\n')
            all_text_lines = [line.strip() for line in all_text_lines if line.strip()]
            self.log_news_greenscreen("="*50 + "\n任务开始...")
            
            use_gpu = self.news_use_gpu_switch.get() == 1
            gpu_codec = self.news_gpu_codec_menu.get().split(' ')[0]
            
            if use_gpu and self.is_gpu_available:
                self.log_news_greenscreen(f"*** GPU加速已启用, 编码器: {gpu_codec} ***")
            else:
                self.log_news_greenscreen("*** 将使用CPU进行编码 ***")

            content_files = sorted([f for f in os.listdir(content_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
            template_subfolders = sorted([d for d in os.listdir(template_dir) if os.path.isdir(os.path.join(template_dir, d))])

            if not template_subfolders:
                self.log_news_greenscreen("错误：模板文件夹中不包含任何子文件夹！")
                return
            
            self.log_news_greenscreen("\n★★★ 模板设置完成！即将开始矩阵式批量合成... ★★★")
            task_list = []
            for subfolder_name in template_subfolders:
                template_folder_path = os.path.join(template_dir, subfolder_name)
                template_files = sorted([f for f in os.listdir(template_folder_path) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
                if not template_files: continue
                for content_filename in content_files:
                    for template_filename in template_files:
                        task_list.append({'subfolder': subfolder_name, 'content': content_filename, 'template': template_filename})

            text_config = {
                'y_offset': int(self.news_y_offset_entry.get()), 'box_w': int(self.news_box_w_entry.get()),
                'box_h': int(self.news_box_h_entry.get()), 'font_color': self.news_font_color_value,
                'bg_color': self.news_bg_color_value, 'font_path': full_font_path,
                'corner_radius': int(self.news_corner_radius_entry.get())
            }

            for i, task in enumerate(task_list):
                if self.news_stop_event.is_set():
                    self.log_news_greenscreen("🔴 任务已由用户中止。")
                    break
                try:
                    self.log_news_greenscreen(f"\n--- 任务进度: {i+1}/{len(task_list)} ---")
                    content_path = os.path.join(content_dir, task['content'])
                    template_path = os.path.join(template_dir, task['subfolder'], task['template'])
                    output_subfolder_path = os.path.join(output_dir, task['subfolder'])
                    os.makedirs(output_subfolder_path, exist_ok=True)
                    output_basename = f"{os.path.splitext(task['content'])[0]}_on_{os.path.splitext(task['template'])[0]}.mp4"
                    output_path = os.path.join(output_subfolder_path, output_basename)
                    self.log_news_greenscreen(f"正在合成: '{task['content']}' -> '{task['template']}'")
                    
                    current_text = all_text_lines[i % len(all_text_lines)] if all_text_lines else ""
                    text_config['text'] = current_text
                    if current_text: self.log_news_greenscreen(f"添加文案: {current_text}")
                    
                    success, message = self._news_process_video(
                        content_path, template_path, output_path, 
                        template_content_roi, text_config, 
                        use_gpu, gpu_codec
                    )
                    self.log_news_greenscreen(f"✔️ {message}" if success else f"❌ {message}")
                except Exception as e:
                    self.log_news_greenscreen(f"处理文件 '{task['content']}' 时发生未知严重错误: {e}")
            
            if not self.news_stop_event.is_set():
                self.log_news_greenscreen("\n===================================\n🎉 所有任务处理完毕！🎉\n===================================")

        except Exception as e:
            self.log_news_greenscreen(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_news_greenscreen_buttons)

    def _reset_news_greenscreen_buttons(self):
        self.news_start_button.configure(state="normal", text="设置模板并开始批量合成")

    # 注意：这个新功能目前没有实现 "停止" 逻辑，
    # 但我们可以在run_news_greenscreen_logic的循环中检查 self.news_stop_event.is_set() 来支持它。
    # 我已在上面的代码中添加了这个检查。你还需要添加一个 stop 按钮和方法（如果需要的话）。
    # 为保持一致性，最好添加上。
    # (此处的实现已包含停止逻辑检查，但未包含停止按钮，您可以自行在UI中添加)
    def on_closing(self):
        self.save_settings()
        self.destroy()

    def _detect_and_display_hardware(self):
        try:
            self.cpu_info_label.configure(text=f"CPU: {platform.processor()}")
        except Exception:
            self.cpu_info_label.configure(text="CPU: 检测失败")
        gpu_name, self.is_gpu_available = "无兼容的NVIDIA GPU", False
        try:
            if 'CUDAExecutionProvider' in ort.get_available_providers():
                gpu_name, self.is_gpu_available = "NVIDIA GPU (CUDA可用)", True
        except Exception:
            gpu_name = "GPU检测失败 (onnxruntime问题)"
        self.gpu_info_label.configure(text=f"GPU: {gpu_name}")
        self.after(0, self._update_gpu_switch_status)

    def _update_gpu_switch_status(self):
        switches = [getattr(self, name, None) for name in ['ai_use_gpu_switch', 'video_use_gpu_switch']]
        for switch in switches:
            if switch:
                if self.is_gpu_available:
                    if not getattr(self, 'settings_loaded', False):
                        switch.select()
                    switch.configure(state="normal")
                else:
                    switch.deselect()
                    switch.configure(state="disabled")

    def create_folder_selection_row(self, parent, label_text, placeholder, attr_name, return_frame=False):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(10, 5))
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label_text, width=120, anchor="w").grid(row=0, column=0, padx=(0,10))
        entry = ctk.CTkEntry(frame, placeholder_text=placeholder)
        entry.grid(row=0, column=1, sticky="ew")
        setattr(self, attr_name, entry)
        open_button = ctk.CTkButton(frame, text="打开", width=60, command=lambda e=entry: self._open_folder_path(e.get()))
        open_button.grid(row=0, column=2, padx=5)
        select_button = ctk.CTkButton(frame, text="选择...", width=60, command=lambda e=entry, t=label_text: self.select_folder_for_entry(e, t))
        select_button.grid(row=0, column=3, padx=(0, 5))
        if return_frame:
            return frame

    def create_widget_row(self, parent, label, name, val, is_file=False):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label).grid(row=0, column=0, padx=(0,10), sticky="w")
        e = ctk.CTkEntry(f)
        e.grid(row=0, column=1, sticky="ew")
        e.insert(0, val)
        setattr(self, name + "_entry", e)
        if is_file:
            ctk.CTkButton(f, text="...", width=30, command=lambda e=e: self.select_file_for_entry(e, "选择字体文件", [("Font files", "*.otf *.ttf")])).grid(row=0, column=2, padx=(5,0))
    
    def create_color_picker_row(self, parent, label, name, val):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label).grid(row=0, column=0, padx=(0,10), sticky="w")
        b = ctk.CTkButton(f, text=val, fg_color=val.split('(')[0] if 'rgba' not in val else "gray")
        b.grid(row=0, column=1, sticky="ew")
        setattr(self, name + "_value", val)
        setattr(self, name + "_button", b)
        b.configure(command=lambda btn=b, attr=name: self._pick_color(btn, attr))

    def create_option_menu_row(self, parent, label, name, options, default):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=10, pady=2)
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label).grid(row=0, column=0, padx=(0,10), sticky="w")
        menu = ctk.CTkOptionMenu(f, values=options)
        menu.grid(row=0, column=1, sticky="ew")
        menu.set(default)
        setattr(self, name + "_menu", menu)

    def create_textbox_row(self, parent, label, name, default):
        ctk.CTkLabel(parent, text=label).pack(pady=(10,2), anchor="w", padx=10)
        tb = ctk.CTkTextbox(parent, height=120)
        tb.pack(fill="x", expand=True, padx=10, pady=(0,10))
        tb.insert("1.0", default)
        setattr(self, name + "_textbox", tb)

    def _pick_color(self, button_widget, attr_name):
        initial_color = button_widget.cget("text") if button_widget.cget("text").startswith("#") else "#ffffff"
        color = colorchooser.askcolor(color=initial_color, title="选择颜色")
        if color and color[1]:
            setattr(self, attr_name + "_value", color[1])
            button_widget.configure(text=color[1], fg_color=color[1])

    def select_folder_for_entry(self, entry, title):
        path = filedialog.askdirectory(title=title)
        if path: entry.delete(0, "end"); entry.insert(0, path)

    def select_file_for_entry(self, entry, title, types):
        path = filedialog.askopenfilename(title=title, filetypes=types)
        if path: entry.delete(0, "end"); entry.insert(0, path)

    def _open_folder_path(self, path):
        """
        (最终版) 跨平台、稳定地打开指定的文件夹路径，自动处理正反斜杠，完美支持中文。
        """
        path = os.path.normpath(path)
        
        if not path or not os.path.isdir(path):
            tk_messagebox.showerror("路径无效", f"文件夹路径为空或不存在:\n{path}")
            return
        
        try:
            if sys.platform == 'win32':
                # Windows系统：直接调用explorer，并且不再检查它的返回值 (移除 check=True)
                subprocess.run(['explorer', path])
                
            elif sys.platform == 'darwin':
                # macOS系统
                subprocess.run(['open', path], check=True) # macOS的open命令行为标准，可以保留check=True
            else:
                # Linux系统
                subprocess.run(['xdg-open', path], check=True) # xdg-open也一样
    
        except Exception as e:
            # 这个异常捕获现在只会在真正发生错误时（比如命令不存在）触发
            tk_messagebox.showerror("打开失败", f"无法打开文件夹：\n{path}\n\n错误: {e}")

    def log_video(self, message, clear=False): self.after(0, self._update_log, self.video_log_textbox, message, clear)
    def log_image(self, message, clear=False): self.after(0, self._update_log, self.image_log_textbox, message, clear)
    def log_ai_matting(self, message, clear=False): self.after(0, self._update_log, self.ai_matting_log_textbox, message, clear)
    def log_ab(self, message, clear=False): self.after(0, self._update_log, self.ab_log_textbox, message, clear)
    
    def _update_log(self, textbox, message, clear=False):
        textbox.configure(state="normal")
        if clear: textbox.delete("1.0", "end")
        textbox.insert("end", str(message) + "\n")
        textbox.see("end")
        textbox.configure(state="disabled")

    def setup_video_workflow(self):
        frame = self.main_tabview.tab("视频处理")
        tabview = ctk.CTkTabview(frame)
        tabview.pack(expand=True, fill="both", padx=5, pady=5)
        tab_main = tabview.add("主页")
        tab_settings = tabview.add("参数配置")
        self.setup_video_main_tab(tab_main)
        self.setup_video_settings_tab(tab_settings)

    def setup_image_workflow(self):
        frame = self.main_tabview.tab("图片处理")
        tabview = ctk.CTkTabview(frame)
        tabview.pack(expand=True, fill="both", padx=5, pady=5)
        tab_main = tabview.add("主页")
        tab_settings = tabview.add("参数配置")
        self.setup_image_main_tab(tab_main)
        self.setup_image_settings_tab(tab_settings)

    def setup_ai_matting_workflow(self):
        tab = self.main_tabview.tab("AI抠像")
        self.create_folder_selection_row(tab, "视频输入文件夹:", "选择包含待处理视频的文件夹", "ai_video_folder_entry")
        self.ai_bg_folder_row = self.create_folder_selection_row(tab, "背景图片文件夹:", "选择包含背景图片的文件夹 (pic)", "ai_bg_folder_entry", return_frame=True)
        self.create_folder_selection_row(tab, "输出文件夹:", "选择处理结果的存放位置", "ai_output_folder_entry")
        options_frame = ctk.CTkFrame(tab, fg_color="transparent"); options_frame.pack(fill="x", padx=10, pady=5)
        self.ai_use_gpu_switch = ctk.CTkSwitch(options_frame, text="使用GPU加速 (需NVIDIA显卡)"); self.ai_use_gpu_switch.pack(side="left", pady=10, padx=(0, 20))
        self.transparent_bg_switch = ctk.CTkSwitch(options_frame, text="输出透明背景视频 (不使用背景图片)", command=self._toggle_bg_folder_state); self.transparent_bg_switch.pack(side="left", pady=10, padx=20)
        self.delete_bg_switch = ctk.CTkSwitch(options_frame, text="处理后删除用过的背景图 (请谨慎！)"); self.delete_bg_switch.pack(side="left", pady=10, padx=20)
        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.pack(fill="x", padx=10, pady=10, expand=False); button_frame.grid_columnconfigure((0, 1), weight=1)
        self.start_ai_matting_button = ctk.CTkButton(button_frame, text="开始AI抠像处理", height=40, command=self.start_ai_matting); self.start_ai_matting_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.stop_ai_matting_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_ai_matting, state="disabled", fg_color="red", hover_color="darkred"); self.stop_ai_matting_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.ai_matting_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9"); self.ai_matting_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def setup_frame_extractor_workflow(self):
        """创建视频截图片功能的UI界面"""
        tab = self.main_tabview.tab("视频截图片")

        # --- UI控件 ---
        self.create_folder_selection_row(tab, "视频文件夹:", "选择包含视频的文件夹 (可含子文件夹)", "extractor_input_folder_entry")
        self.create_folder_selection_row(tab, "图片输出文件夹:", "选择截取图片的存放位置", "extractor_output_folder_entry")

        # 间隔时长输入
        interval_frame = ctk.CTkFrame(tab, fg_color="transparent")
        interval_frame.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(interval_frame, text="截图间隔 (秒):", width=120, anchor="w").pack(side="left")
        self.extractor_interval_entry = ctk.CTkEntry(interval_frame, placeholder_text="例如: 3 (代表每隔3秒截一张图)")
        self.extractor_interval_entry.pack(side="left", fill="x", expand=True)

        # 功能开关
        options_frame = ctk.CTkFrame(tab, fg_color="transparent")
        options_frame.pack(fill="x", padx=10, pady=15, anchor="w")
        
        self.extractor_resize_switch = ctk.CTkSwitch(options_frame, text="统一分辨率为 1080x1920 (竖屏)")
        self.extractor_resize_switch.pack(side="left", padx=(0, 20))
        self.extractor_resize_switch.select() # 默认开启

        self.extractor_use_gpu_switch = ctk.CTkSwitch(options_frame, text="使用GPU加速 (若有)")
        self.extractor_use_gpu_switch.pack(side="left")
        self.after(100, self._update_gpu_switch_status) # 更新GPU开关状态

        # --- 按钮和日志框 ---
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_extractor_button = ctk.CTkButton(button_frame, text="开始截图", height=40, command=self.start_frame_extraction)
        self.start_extractor_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.stop_extractor_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_frame_extraction, state="disabled", fg_color="red", hover_color="darkred")
        self.stop_extractor_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.extractor_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.extractor_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def setup_video_splitter_workflow(self):
        """创建长视频分割功能的UI界面"""
        tab = self.main_tabview.tab("长视频分割")

        # --- UI控件 ---
        self.create_folder_selection_row(tab, "长视频文件夹:", "选择包含长视频的文件夹", "splitter_input_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择分割后短视频的存放位置", "splitter_output_folder_entry")

        # 分割时长输入
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(duration_frame, text="分割时长 (秒):", width=120, anchor="w").pack(side="left")
        self.splitter_duration_entry = ctk.CTkEntry(duration_frame, placeholder_text="例如: 3  (代表每段3秒)")
        self.splitter_duration_entry.pack(side="left", fill="x", expand=True)

        # GPU加速开关
        self.splitter_use_gpu_switch = ctk.CTkSwitch(tab, text="使用GPU加速编码 (需NVIDIA显卡)")
        self.splitter_use_gpu_switch.pack(anchor="w", padx=10, pady=15)
        # 首次加载时更新GPU开关状态
        self.after(100, self._update_gpu_switch_status)


        # --- 按钮和日志框 ---
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_splitter_button = ctk.CTkButton(button_frame, text="开始分割视频", height=40, command=self.start_video_split)
        self.start_splitter_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        self.stop_splitter_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_video_split, state="disabled", fg_color="red", hover_color="darkred")
        self.stop_splitter_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.splitter_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.splitter_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def setup_ab_image_workflow(self):
        tab = self.main_tabview.tab("AB图文")
        # 【修改】将两个图片文件夹选择框合并为一个
        self.create_folder_selection_row(tab, "背景图片文件夹:", "选择包含A和B背景图片的文件夹", "ab_image_source_folder_entry")
        self.create_folder_selection_row(tab, "绿幕图片(父):", "选择包含多个绿幕子文件夹的目录", "ab_greenscreen_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择合成图片的输出位置", "ab_output_folder_entry")

        group_frame = ctk.CTkFrame(tab, fg_color="transparent")
        group_frame.pack(fill="x", padx=10, pady=(15,5))
        ctk.CTkLabel(group_frame, text="生成组数:", width=120, anchor="w").pack(side="left")
        self.ab_num_groups_entry = ctk.CTkEntry(group_frame, placeholder_text="输入一个整数, 例如 10")
        self.ab_num_groups_entry.pack(side="left", fill="x", expand=True)

        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0,1), weight=1)
        self.start_ab_button = ctk.CTkButton(button_frame, text="开始AB图文合成", height=40, command=self.start_ab_processing)
        self.start_ab_button.grid(row=0, column=0, padx=(0,5), sticky="ew")
        self.stop_ab_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_ab_processing, state="disabled", fg_color="red", hover_color="darkred")
        self.stop_ab_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        
        self.ab_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.ab_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def setup_video_main_tab(self, tab):
        self.create_folder_selection_row(tab, "视频文件夹:", "选择包含视频的文件夹", "video_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择视频处理结果的存放位置", "video_output_folder_entry")
        ctk.CTkLabel(tab, text="输入文案 (用'/'换行, 用'&'分隔块):").pack(anchor="w", padx=10, pady=(10, 0))
        self.video_text_input_box = ctk.CTkTextbox(tab, height=150); self.video_text_input_box.pack(fill="x", padx=10, pady=(5,10), expand=True)
        group_frame = ctk.CTkFrame(tab, fg_color="transparent"); group_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(group_frame, text="生成组数:", width=120, anchor="w").pack(side="left")
        self.video_num_groups_entry = ctk.CTkEntry(group_frame, placeholder_text="输入一个整数, 例如 5"); self.video_num_groups_entry.pack(side="left", fill="x", expand=True)
        self.video_use_gpu_switch = ctk.CTkSwitch(tab, text="使用GPU加速编码 (需NVIDIA显卡)"); self.video_use_gpu_switch.pack(anchor="w", padx=10, pady=5)
        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.pack(fill="x", padx=10, pady=10); button_frame.grid_columnconfigure((0,1), weight=1)
        self.start_video_button = ctk.CTkButton(button_frame, text="开始处理视频", height=40, command=self.start_video_processing); self.start_video_button.grid(row=0, column=0, padx=(0,5), sticky="ew")
        self.stop_video_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_video_processing, state="disabled", fg_color="red", hover_color="darkred"); self.stop_video_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        self.video_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9"); self.video_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def setup_image_main_tab(self, tab):
        self.create_folder_selection_row(tab, "图片文件夹:", "选择包含图片的文件夹", "image_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择图片处理结果的存放位置", "image_output_folder_entry")
        ctk.CTkLabel(tab, text="输入文案 (每行对应一张图):").pack(anchor="w", padx=10, pady=(10,0))
        self.image_text_input_box = ctk.CTkTextbox(tab, height=150); self.image_text_input_box.pack(fill="x", expand=True, padx=10, pady=(5,10))
        group_frame = ctk.CTkFrame(tab, fg_color="transparent"); group_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(group_frame, text="生成组数:", width=120, anchor="w").pack(side="left")
        self.image_num_groups_entry = ctk.CTkEntry(group_frame, placeholder_text="输入一个整数"); self.image_num_groups_entry.pack(side="left", fill="x", expand=True)
        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.pack(fill="x", padx=10, pady=10); button_frame.grid_columnconfigure((0,1), weight=1)
        self.start_image_button = ctk.CTkButton(button_frame, text="开始处理图片", height=40, command=self.start_image_processing); self.start_image_button.grid(row=0, column=0, padx=(0,5), sticky="ew")
        self.stop_image_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_image_processing, state="disabled", fg_color="red", hover_color="darkred"); self.stop_image_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        self.image_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9"); self.image_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
        
    def setup_video_settings_tab(self, tab):
        tab.grid_rowconfigure(0, weight=1); tab.grid_columnconfigure(0, weight=1)
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="视频字幕的所有参数均在此配置"); scrollable_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        shared_frame = ctk.CTkFrame(scrollable_frame, border_width=1); shared_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(shared_frame, text="--- 视频 · 共享样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        default_video_font_path = get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf'))
        self.create_widget_row(shared_frame, "字体文件:", "video_shared_font_file", default_video_font_path, True)
        self.create_widget_row(shared_frame, "字体大小:", "video_shared_size", "60")
        self.create_widget_row(shared_frame, "最大宽度比例:", "video_shared_max_width_ratio", "0.9")
        self.create_widget_row(shared_frame, "左右内边距:", "video_shared_padding_horizontal", "30")
        self.create_widget_row(shared_frame, "垂直内边距:", "video_shared_padding_vertical", "25")
        self.create_widget_row(shared_frame, "描边粗细:", "video_shared_stroke_width", "2")
        self.create_widget_row(shared_frame, "背景圆角半径:", "video_shared_corner_radius", "20")
        self.video_no_bg_switch = ctk.CTkSwitch(shared_frame, text="禁用所有字幕背景")
        self.video_no_bg_switch.pack(pady=10, padx=10, anchor="w")
        main_frame = ctk.CTkFrame(scrollable_frame, border_width=1); main_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(main_frame, text="--- 视频 · 主文案 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.create_widget_row(main_frame, "水平位置 (x):", "video_main_pos_x", "center")
        self.create_widget_row(main_frame, "垂直位置 (y):", "video_main_pos_y", "150")
        self.create_color_picker_row(main_frame, "文字颜色:", "video_main_color_text", "white")
        self.create_color_picker_row(main_frame, "描边颜色:", "video_main_color_stroke", "black")
        self.create_color_picker_row(main_frame, "背景颜色:", "video_main_color_bg", "rgba(0, 0, 0, 0.5)")
        for i in range(1, 3):
            sub_frame = ctk.CTkFrame(scrollable_frame, border_width=1); sub_frame.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(sub_frame, text=f"--- 视频 · 次文案 {i} ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
            defaults = [("20", "#FFD700", "black", "rgba(200,50,50,0.85)"), ("30", "white", "black", "rgba(50,50,50,0.7)")]
            self.create_widget_row(sub_frame, "相对Y轴偏移:", f"video_sub{i}_offset_y", defaults[i-1][0])
            self.create_color_picker_row(sub_frame, "文字颜色:", f"video_sub{i}_color_text", defaults[i-1][1])
            self.create_color_picker_row(sub_frame, "描边颜色:", f"video_sub{i}_color_stroke", defaults[i-1][2])
            self.create_color_picker_row(sub_frame, "背景颜色:", f"video_sub{i}_color_bg", defaults[i-1][3])
        self.preview_button = ctk.CTkButton(tab, text="生成视频字幕预览", command=self.generate_video_preview); self.preview_button.grid(row=1, column=0, pady=10, padx=5)
        self.preview_display_frame = ctk.CTkFrame(tab); self.preview_display_frame.grid_rowconfigure(1, weight=1); self.preview_display_frame.grid_columnconfigure(0, weight=1)
        self.close_preview_button = ctk.CTkButton(self.preview_display_frame, text="关闭预览", command=self.close_video_preview, width=120); self.close_preview_button.grid(row=0, column=0, pady=(5, 10))
        self.preview_label = ctk.CTkLabel(self.preview_display_frame, text="", text_color="gray"); self.preview_label.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        tab.grid_rowconfigure(2, weight=1); self.close_video_preview() 

    def setup_image_settings_tab(self, tab):
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="图片处理的所有参数均在此配置"); scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)
        font_frame = ctk.CTkFrame(scrollable_frame, border_width=1); font_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(font_frame, text="--- 图片 · 字体与颜色 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.image_no_bg_switch = ctk.CTkSwitch(font_frame, text="禁用文字背景")
        self.image_no_bg_switch.pack(pady=(5,10), padx=10, anchor="w")
        default_font_path = get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf'))
        self.create_widget_row(font_frame, "字体文件路径:", "image_font_path", default_font_path, True); self.create_widget_row(font_frame, "字体大小:", "image_font_size", "75"); self.create_color_picker_row(font_frame, "文字颜色:", "image_font_color", "#000000"); self.create_color_picker_row(font_frame, "背景颜色:", "image_font_background_color", "#ffffff")
        layout_frame = ctk.CTkFrame(scrollable_frame, border_width=1); layout_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(layout_frame, text="--- 图片 · 布局与样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.create_widget_row(layout_frame, "最大文本宽度比例:", "image_max_text_width_ratio", "0.85"); self.create_widget_row(layout_frame, "背景圆角半径:", "image_corner_radius", "15"); self.create_widget_row(layout_frame, "背景内边距:", "image_text_padding", "20"); self.create_option_menu_row(layout_frame, "块内文本对齐:", "image_text_align_in_block", ["left", "center", "right"], "center")
        list_frame = ctk.CTkFrame(scrollable_frame, border_width=1); list_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(list_frame, text="--- 图片 · 列表类配置 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        positions_default = "[\n  [0.5, 0.44],\n  [0.5, 0.6],\n  [0.5, 0.51],\n  [0.5, 0.4],\n  [0.5, 0.45],\n  [0.5, 0.63],\n  [0.5, 0.42],\n  [0.5, 0.44],\n  [0.5, 0.46],\n  [0.5, 0.48],\n  [0.5, 0.5],\n  [0.5, 0.52],\n  [0.5, 0.54],\n  [0.5, 0.56],\n  [0.5, 0.58],\n  [0.5, 0.60],\n  [0.5, 0.62],\n  [0.5, 0.64],\n  [0.5, 0.66]\n]"
        self.create_textbox_row(list_frame, "位置列表 (每行一对[x,y]):", "image_text_positions", positions_default); self.create_textbox_row(list_frame, "行间距选项 (逗号分隔):", "image_line_spacing_options", "25"); self.create_textbox_row(list_frame, "缩放/裁剪百分比 (逗号分隔):", "image_zoom_crop_percentages", "-3,-2,-1, 0, 10, 12,11,12,13,14")
        effects_frame = ctk.CTkFrame(scrollable_frame, border_width=1); effects_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(effects_frame, text="--- 图片 · 效果开关 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.image_flip_switch = ctk.CTkSwitch(effects_frame, text="允许随机水平翻转"); self.image_flip_switch.pack(pady=10); self.image_flip_switch.select()

# --- AI抠像 (AI Matting) ---
    def _toggle_bg_folder_state(self):
        is_transparent = self.transparent_bg_switch.get() == 1
        new_state = "disabled" if is_transparent else "normal"
        for widget in self.ai_bg_folder_row.winfo_children():
            widget.configure(state=new_state)

    def start_ai_matting(self):
        self.ai_matting_stop_event.clear()
        self.start_ai_matting_button.configure(state="disabled")
        self.stop_ai_matting_button.configure(state="normal")
        self.log_ai_matting("", clear=True)
        threading.Thread(target=self.run_ai_matting_logic, daemon=True).start()

    def stop_ai_matting(self):
        self.log_ai_matting("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.ai_matting_stop_event.set()
        self.stop_ai_matting_button.configure(state="disabled")

    def _reset_ai_matting_buttons(self):
        self.start_ai_matting_button.configure(state="normal")
        self.stop_ai_matting_button.configure(state="disabled")

    def run_ai_matting_logic(self):
        import rembg
        import onnxruntime as ort
        try:
            video_dir = self.ai_video_folder_entry.get()
            bg_dir = self.ai_bg_folder_entry.get()
            output_dir = self.ai_output_folder_entry.get()
            delete_after = self.delete_bg_switch.get()
            use_gpu = self.ai_use_gpu_switch.get() == 1
            transparent_output = self.transparent_bg_switch.get() == 1
            
            if not all([video_dir, output_dir]):
                self.log_ai_matting("❌ 错误：视频输入和输出文件夹必须填写。")
                return
            if not transparent_output and not bg_dir:
                self.log_ai_matting("❌ 错误：已选择替换背景模式，但背景图片文件夹未填写。")
                return
            
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if use_gpu and self.is_gpu_available else ['CPUExecutionProvider']
            self.log_ai_matting(f"🚀 已选择 {'GPU' if 'CUDAExecutionProvider' in providers else 'CPU'} 加速模式。")
            session = rembg.new_session(providers=providers)

            video_files = sorted([f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
            if not video_files:
                self.log_ai_matting("ℹ️ 信息：视频输入文件夹为空。")
                return

            if transparent_output:
                self.log_ai_matting(f"▶️ 检测到 {len(video_files)} 个视频，将进行透明背景处理。")
                for i, video_name in enumerate(video_files):
                    if self.ai_matting_stop_event.is_set():
                        self.log_ai_matting("🔴 任务已中止。")
                        break
                    input_path = os.path.join(video_dir, video_name)
                    output_name = f"{os.path.splitext(video_name)[0]}_transparent.mov"
                    output_path = os.path.join(output_dir, output_name)
                    self.log_ai_matting(f"\n--- [处理第 {i+1}/{len(video_files)} 个视频] ---")
                    result = self._ai_matting_worker(input_path, output_path, session, background_path=None)
                    if result == 'STOPPED':
                        self.log_ai_matting("🔴 任务在处理文件中途被中止。")
                        break
            else:
                background_files = sorted([f for f in os.listdir(bg_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))])
                if not background_files:
                    self.log_ai_matting("ℹ️ 信息：背景图片文件夹为空。")
                    return
                num_to_process = min(len(video_files), len(background_files))
                self.log_ai_matting(f"▶️ 发现 {len(video_files)} 个视频和 {len(background_files)} 张背景图片。将处理 {num_to_process} 对。")
                if delete_after:
                    self.log_ai_matting("⚠️ 警告：已启用“用后删除”功能。")
                
                for i in range(num_to_process):
                    if self.ai_matting_stop_event.is_set():
                        self.log_ai_matting("🔴 任务已中止。")
                        break
                    video_name, bg_name = video_files[i], background_files[i]
                    input_path, bg_path = os.path.join(video_dir, video_name), os.path.join(bg_dir, bg_name)
                    output_name = f"{os.path.splitext(video_name)[0]}_processed.mp4"
                    output_path = os.path.join(output_dir, output_name)
                    self.log_ai_matting(f"\n--- [处理第 {i+1}/{num_to_process} 对] ---")
                    result = self._ai_matting_worker(input_path, output_path, session, background_path=bg_path)
                    
                    if result == 'STOPPED':
                        self.log_ai_matting("🔴 任务在处理文件中途被中止。")
                        break
                    elif result is True and delete_after:
                        try:
                            os.remove(bg_path)
                            self.log_ai_matting(f"✅ 处理成功！已删除背景: {bg_name}")
                        except OSError as e:
                            self.log_ai_matting(f"❌ 视频处理成功，但删除背景图片 {bg_name} 时出错: {e}")
                    elif result is True:
                        self.log_ai_matting(f"✅ 处理成功！输出文件: {output_name}")
                    else:
                        self.log_ai_matting(f"❌ 处理视频 {video_name} 失败。")
            
            self.log_ai_matting("\n--- 所有任务已执行完毕 ---")
        except Exception as e:
            self.log_ai_matting(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_ai_matting_buttons)

    def _ai_matting_worker(self, input_path, output_path, session, background_path=None):
        from moviepy.editor import VideoFileClip, ImageSequenceClip
        from PIL import Image
        import cv2
        import rembg
        import numpy as np
        self.log_ai_matting(f"-> 正在处理视频: {os.path.basename(input_path)}")
        if background_path:
            self.log_ai_matting(f"-> 使用背景图片: {os.path.basename(background_path)}")
        else:
            self.log_ai_matting("-> 模式: 输出透明背景视频")
        
        original_clip, final_clip, final_clip_no_audio = None, None, None
        try:
            original_clip = VideoFileClip(input_path)
            audio, fps = original_clip.audio, original_clip.fps
            cap = cv2.VideoCapture(input_path)
            ret, first_frame = cap.read()
            if not ret:
                self.log_ai_matting("错误：无法读取视频的第一帧。")
                return False
            
            frame_height, frame_width, _ = first_frame.shape
            video_size = (frame_width, frame_height)
            background_pil = None
            
            if background_path:
                try:
                    background_pil = Image.open(background_path).convert("RGB")
                    if background_pil.size != video_size:
                        self.log_ai_matting(f"    注意：背景图片尺寸 {background_pil.size} 与视频尺寸 {video_size} 不符，正在自动缩放...")
                        background_pil = background_pil.resize(video_size, Image.Resampling.LANCZOS)
                except Exception as e:
                    self.log_ai_matting(f"错误：无法打开或处理背景图片 {background_path}。错误: {e}")
                    return False
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            processed_frames = []
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            for frame_count in range(1, total_frames + 1):
                if self.ai_matting_stop_event.is_set():
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                            self.log_ai_matting(f"  -> 已删除临时文件: {os.path.basename(output_path)}")
                        except OSError as e:
                            self.log_ai_matting(f"  -> 警告: 删除临时文件失败: {e}")
                    return 'STOPPED'
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                foreground_pil = rembg.remove(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), session=session)
                
                if background_pil:
                    composite_image = background_pil.copy()
                    composite_image.paste(foreground_pil, (0, 0), foreground_pil)
                    processed_frames.append(np.array(composite_image))
                else:
                    processed_frames.append(np.array(foreground_pil))
                
                if frame_count % 10 == 0 or frame_count == total_frames:
                    self.log_ai_matting(f"    进度: {frame_count}/{total_frames} 帧")
            
            cap.release()
            self.log_ai_matting("    帧处理完成。")
            
            if not processed_frames:
                return False
            
            final_clip = ImageSequenceClip(processed_frames, fps=fps)
            
            try:
                if audio:
                    final_clip = final_clip.set_audio(audio)
                    self.log_ai_matting(f"    正在写入文件 (带音频)...")
                else:
                    self.log_ai_matting(f"    源视频无音频，正在写入无声文件...")
                
                if background_path:
                    final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
                else:
                    final_clip.write_videofile(output_path, codec='prores_ks', audio_codec='pcm_s16le', logger=None, ffmpeg_params=['-pix_fmt', 'yuva444p10le'])
            except Exception as e:
                self.log_ai_matting(f"    警告：写入音频时出错 ({type(e).__name__})。正在尝试生成无声视频...")
                try:
                    final_clip_no_audio = final_clip.set_audio(None)
                    if background_path:
                        final_clip_no_audio.write_videofile(output_path, codec='libx264', logger=None)
                    else:
                        final_clip_no_audio.write_videofile(output_path, codec='prores_ks', logger=None, ffmpeg_params=['-pix_fmt', 'yuva444p10le'])
                    self.log_ai_matting("    成功生成无声视频。")
                except Exception as e2:
                    self.log_ai_matting(f"    错误：生成无声视频也失败了: {e2}")
                    return False
            
            return True
        finally:
            if 'cap' in locals() and cap.isOpened():
                cap.release()
            if original_clip: original_clip.close()
            if final_clip: final_clip.close()
            if final_clip_no_audio: final_clip_no_audio.close()
            self.log_ai_matting("    资源已释放。")
            
    # --- 视频处理 (Video Processing) ---
    def start_video_processing(self):
        self.video_stop_event.clear()
        self.start_video_button.configure(state="disabled")
        self.stop_video_button.configure(state="normal")
        self.log_video("", clear=True)
        threading.Thread(target=self.run_video_logic, daemon=True).start()

    def stop_video_processing(self):
        self.log_video("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.video_stop_event.set()
        self.stop_video_button.configure(state="disabled")

    def _reset_video_buttons(self):
        self.start_video_button.configure(state="normal")
        self.stop_video_button.configure(state="disabled")

    def run_video_logic(self):
        try:
            video_folder = self.video_folder_entry.get()
            output_folder = self.video_output_folder_entry.get()
            config = self.get_video_config_from_gui()
            all_input_text = self.video_text_input_box.get("1.0","end-1c")
            use_gpu = self.video_use_gpu_switch.get() == 1

            try:
                num_groups = int(self.video_num_groups_entry.get())
                assert num_groups > 0
            except (ValueError, AssertionError):
                self.log_video("错误: '生成组数' 必须是一个有效的正整数。")
                return
                
            if not all([video_folder, output_folder, config, all_input_text.strip()]):
                self.log_video("错误: 缺少视频/输出文件夹、配置或文案信息。")
                return

            text_lines = [line.strip() for line in all_input_text.splitlines() if line.strip()]
            if not text_lines:
                 self.log_video("错误: 文案信息不能为空。")
                 return
                 
            num_texts_per_group = len(text_lines)
            total_videos_needed = num_texts_per_group * num_groups
            
            all_available_videos = [f for f in os.listdir(video_folder) if f.lower().endswith(('.mp4','.mov','.avi'))]
            if len(all_available_videos) < total_videos_needed:
                self.log_video(f"错误: 视频不足！需要 {total_videos_needed} 个, 但只有 {len(all_available_videos)} 个。")
                return
            
            random.shuffle(all_available_videos)
            videos_to_process = all_available_videos[:total_videos_needed]
            
            if os.path.exists(output_folder):
                self.log_video(f"清空旧的结果文件夹: '{output_folder}'...")
                shutil.rmtree(output_folder)
            os.makedirs(output_folder)
            self.log_video(f"已创建新的空结果文件夹: '{output_folder}'")
            self.log_video(f"准备就绪: 将处理 {total_videos_needed} 个视频, 分成 {num_groups} 组。")
            self.log_video("!!! 警告：处理成功后，原始视频将被删除以防重复。请确保您有备份。 !!!")
            
            shared_style_config = config['shared_style']
            group_count = 0
            for i in range(0, len(videos_to_process), num_texts_per_group):
                if self.video_stop_event.is_set():
                    self.log_video("🔴 任务已中止。")
                    break
                group_count += 1
                video_chunk = videos_to_process[i:i+num_texts_per_group]
                group_folder = os.path.join(output_folder, f"group_{group_count}")
                os.makedirs(group_folder, exist_ok=True)
                self.log_video(f"\n---=== 开始处理第 {group_count} 组 ===---")
                
                for j, video_name in enumerate(video_chunk):
                    if self.video_stop_event.is_set():
                        self.log_video("🔴 任务在组内中止。")
                        break
                    if j >= len(text_lines):
                        break
                        
                    input_video_path = os.path.join(video_folder, video_name)
                    output_video_path = os.path.join(group_folder, f"processed_{video_name}")
                    text_line = text_lines[j]
                    
                    self.log_video(f"\n[{j+1}/{len(video_chunk)}] 正在处理...")
                    self.log_video(f"  - 视频: {video_name}")
                    
                    try:
                        text_parts = [part.strip() for part in text_line.split('&')]
                        self.log_video(f"  - 文案被分割为 {len(text_parts)} 部分: {text_parts}")
                        if self.video_stop_event.is_set():
                            break
                        
                        video_clip = VideoFileClip(input_video_path)
                        overlays = []
                        
                        main_text_config = config['main_text']
                        main_overlay = video_create_text_overlay(text_parts[0], shared_style_config, main_text_config, video_clip.size)
                        pos_config = main_text_config['position']
                        x_pos, y_pos = pos_config.get('x', 'center'), pos_config.get('y', 'center')
                        main_overlay = main_overlay.set_position((x_pos, y_pos) if x_pos != 'center' else ('center', y_pos))
                        overlays.append(main_overlay)
                        
                        main_y_position = main_overlay.pos(video_clip.size)[1]
                        last_clip_y, last_clip_height = main_y_position, main_overlay.size[1]
                        
                        if len(text_parts) > 1:
                            sub_texts_configs = config.get('sub_texts', [])
                            for k, sub_text in enumerate(text_parts[1:]):
                                if k >= len(sub_texts_configs):
                                    self.log_video(f"  - 警告: 第 {k+2} 部分文案没有对应的配置，将被忽略。")
                                    break
                                sub_text_config = sub_texts_configs[k]
                                sub_overlay = video_create_text_overlay(sub_text, shared_style_config, sub_text_config, video_clip.size)
                                y_offset = sub_text_config.get("relative_y_offset", 10)
                                new_y = last_clip_y + last_clip_height + y_offset
                                sub_overlay = sub_overlay.set_position(('center', new_y))
                                overlays.append(sub_overlay)
                                last_clip_y, last_clip_height = new_y, sub_overlay.size[1]
                        
                        final_clip = CompositeVideoClip([video_clip] + overlays).set_duration(video_clip.duration)
                        gpu_codec, cpu_codec = 'h264_nvenc', 'libx264'
                        
                        if use_gpu and self.is_gpu_available:
                            self.log_video(f"  -> 尝试使用GPU编码 ({gpu_codec})...")
                            try:
                                final_clip.write_videofile(output_video_path, codec=gpu_codec, audio_codec='aac', threads=4, preset='fast', logger=None)
                            except Exception:
                                self.log_video(f"  -> 警告: GPU编码失败。正在回退到CPU编码。")
                                final_clip.write_videofile(output_video_path, codec=cpu_codec, audio_codec='aac', threads=4, preset='medium', logger=None)
                        else:
                            self.log_video(f"  -> 使用CPU编码 ({cpu_codec})...")
                            final_clip.write_videofile(output_video_path, codec=cpu_codec, audio_codec='aac', threads=4, preset='medium', logger=None)

                        video_clip.close()
                        final_clip.close()
                        self.log_video(f"  -> 成功! 输出文件: {os.path.basename(output_video_path)}")
                        
                        gc.collect()
                        time.sleep(1) # 回收后短暂等待

                        try:
                            path_to_delete_str = os.path.normpath(str(input_video_path))
                            
                            # 1. 执行命令，但让程序自己判断成功与否 (check=False)
                            result = subprocess.run(
                                f'del "{path_to_delete_str}"',
                                shell=True,
                                check=False,  # <--- 关键修改：不自动检查错误
                                capture_output=True,
                                text=True
                            )
                            
                            # 2. 第一重确认：检查命令的返回码和错误输出
                            if result.returncode != 0 or result.stderr:
                                # 如果返回码不是0，或者标准错误有内容，都算失败
                                error_info = result.stderr.strip() or f"返回码: {result.returncode}"
                                self.log_video(f"  -> ❌ 删除命令执行失败: {error_info}")
                            else:
                                # 3. 第二重确认：再次检查文件是否真的不存在了
                                time.sleep(0.5) # 等待文件系统刷新
                                if not os.path.exists(input_video_path):
                                    self.log_video(f"  -> ✅ 源视频已删除 (已确认): {video_name}")
                                else:
                                    self.log_video(f"  -> ❌ 警告: 命令报告成功但文件依然存在！删除失败！")
                              
                        except Exception as e:
                            self.log_video(f"  -> ❌ 执行删除时发生未知异常: {e}")
                        # --- 结束：三重确认 - 终极删除方案 ---
                    except Exception as e:
                        self.log_video(f"  -> 错误: 处理视频 {video_name} 时发生严重错误: {e}")
                        if os.path.exists(output_video_path):
                            try:
                                os.remove(output_video_path)
                                self.log_video(f"  -> 已删除临时文件: {os.path.basename(output_video_path)}")
                            except OSError:
                                pass
            self.log_video("\n---=== 所有任务处理完毕！ ===---")
        except Exception as e:
            self.log_video(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_video_buttons)

    # --- 图片处理 (Image Processing) ---
    def start_image_processing(self):
        self.image_stop_event.clear()
        self.start_image_button.configure(state="disabled")
        self.stop_image_button.configure(state="normal")
        self.log_image("", clear=True)
        threading.Thread(target=self.run_image_logic, daemon=True).start()

    def stop_image_processing(self):
        self.log_image("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.image_stop_event.set()
        self.stop_image_button.configure(state="disabled")

    def _reset_image_buttons(self):
        self.start_image_button.configure(state="normal")
        self.stop_image_button.configure(state="disabled")

    def run_image_logic(self):
        try:
            image_folder = self.image_folder_entry.get()
            output_folder = self.image_output_folder_entry.get()
            all_input_text = self.image_text_input_box.get("1.0", "end-1c")
            config = self.get_image_config_from_gui()
            
            if not all([image_folder, output_folder, config, all_input_text.strip()]):
                self.log_image("错误: 请确保已选择所有文件/文件夹并已完成所有配置。")
                return
            
            num_groups = int(self.image_num_groups_entry.get())
            config["num"] = num_groups
            captions = [line.strip() for line in all_input_text.splitlines() if line.strip()]
            num_sets = config.get("num", 1)
            num_captions_per_set = len(captions)
            total_needed = num_sets * num_captions_per_set
            available_images = [f for f in os.listdir(image_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
            
            if len(available_images) < total_needed:
                self.log_image(f"错误: 图片不足！需要 {total_needed} 张, 但只有 {len(available_images)} 张。")
                return
            
            if os.path.exists(output_folder):
                self.log_image(f"清空旧的图片结果文件夹: '{output_folder}'...")
                shutil.rmtree(output_folder)
            os.makedirs(output_folder)
            self.log_image(f"已创建新的空图片结果文件夹: '{output_folder}'")
            
            random.shuffle(available_images)
            images_to_process = available_images[:total_needed]
            
            self.log_image(f"准备就绪: 将处理 {total_needed} 张图片, 分成 {num_sets} 组。")
            self.log_image("!!! 警告：处理成功后，原始图片将被删除以防重复。请确保您有备份。 !!!")
            
            total_processed_count, group_count = 0, 0
            for i in range(0, len(images_to_process), num_captions_per_set):
                if self.image_stop_event.is_set():
                    self.log_image("🔴 任务已中止。")
                    break
                group_count += 1
                image_chunk = images_to_process[i:i+num_captions_per_set]
                group_folder = os.path.join(output_folder, f"group_{group_count}")
                os.makedirs(group_folder, exist_ok=True)
                self.log_image(f"\n---=== 开始处理第 {group_count} 组图片 ===---")
                
                for j, img_name in enumerate(image_chunk):
                    source_path = os.path.join(image_folder, img_name)
                    output_path = os.path.join(group_folder, img_name)
                    if self.image_stop_event.is_set():
                        self.log_image("🔴 任务在组内中止。")
                        break
                    
                    caption = captions[j % len(captions)]
                    pos_config = random.choice(config.get("text_positions", [[0.5, 0.5]]))
                    
                    result = image_apply_text(source_path, caption, config, pos_config, output_path, self.log_image, self.image_stop_event)
                    
                    if result == 'STOPPED':
                        break
                    elif result is True:
                        try:
                            os.remove(source_path)
                            self.log_image(f"  🗑️ 已删除源图片: {img_name}")
                            total_processed_count += 1
                        except OSError as e:
                            self.log_image(f"  ❌ 删除源图片失败: {img_name} - {e}")
                    else:
                        if os.path.exists(output_path):
                            try: os.remove(output_path)
                            except OSError: pass
            
            self.log_image(f"\n---=== 图片处理完毕！总共处理并删除 {total_processed_count} 张图片 ===---")
            if total_processed_count > 0 and not self.image_stop_event.is_set():
                tk_messagebox.showinfo("图片处理完成", f"总共处理并删除了 {total_processed_count} 张图片。\n输出文件夹: '{output_folder}'")
        except Exception as e:
            self.log_image(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_image_buttons)

    # --- AB图文处理 (A/B Image Compositing) ---
    def start_ab_processing(self):
        self.ab_image_stop_event.clear()
        self.start_ab_button.configure(state="disabled")
        self.stop_ab_button.configure(state="normal")
        self.log_ab("", clear=True)
        threading.Thread(target=self.run_ab_logic, daemon=True).start()

    def stop_ab_processing(self):
        self.log_ab("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.ab_image_stop_event.set()
        self.stop_ab_button.configure(state="disabled")

    def _reset_ab_buttons(self):
        self.start_ab_button.configure(state="normal")
        self.stop_ab_button.configure(state="disabled")

    def run_ab_logic(self):
        try:
            # 1. 获取输入 (无变化)
            image_source_folder = self.ab_image_source_folder_entry.get()
            greenscreen_parent_folder = self.ab_greenscreen_folder_entry.get()
            output_folder = self.ab_output_folder_entry.get()

            if not all([image_source_folder, greenscreen_parent_folder, output_folder]):
                self.log_ab("❌ 错误: 所有文件夹路径都必须填写。")
                return

            try:
                num_groups = int(self.ab_num_groups_entry.get())
                if num_groups <= 0: raise ValueError
            except ValueError:
                self.log_ab("❌ 错误: '生成组数' 必须是一个有效的正整数。")
                return
            
            # 2. 扫描素材 (逻辑无变化)
            self.log_ab("正在扫描素材文件...")
            image_ext = ('.png', '.jpg', '.jpeg', '.webp')
            source_images = sorted([os.path.join(image_source_folder, f) for f in os.listdir(image_source_folder) if f.lower().endswith(image_ext)])
            
            greenscreen_subfolders = []
            for sub in os.listdir(greenscreen_parent_folder):
                sub_path = os.path.join(greenscreen_parent_folder, sub)
                if os.path.isdir(sub_path):
                    if any(f.lower().endswith(image_ext) for f in os.listdir(sub_path)):
                        greenscreen_subfolders.append(sub_path)
            
            self.log_ab(f"🔍 扫描结果: 发现背景图片 {len(source_images)} 张, 合规绿幕文件夹 {len(greenscreen_subfolders)} 个。")

            # 【修改】执行“预检”来计算完成所有轮次总共需要的背景图片数量
            if not greenscreen_subfolders:
                self.log_ab(f"❌ 错误: 未找到任何合规的绿幕图片子文件夹。")
                return

            images_needed_per_batch = 0
            for gs_folder in greenscreen_subfolders:
                images_needed_per_batch += len([f for f in os.listdir(gs_folder) if f.lower().endswith(image_ext)])
            
            if images_needed_per_batch == 0:
                self.log_ab("❌ 错误: 所有合规的绿幕文件夹都是空的。")
                return

            total_images_needed = images_needed_per_batch * num_groups

            if len(source_images) < total_images_needed:
                self.log_ab(f"❌ 错误: 背景图片素材不足！\n每轮(大组)需要 {images_needed_per_batch} 张, 共 {num_groups} 轮, 总计需要 {total_images_needed} 张图片。\n但当前只找到了 {len(source_images)} 张。")
                return
            
            # 3. 准备处理 (逻辑无变化)
            random.shuffle(source_images)
            greenscreen_subfolders.sort()

            if not os.path.exists(output_folder):
                os.makedirs(output_folder)

            self.log_ab(f"▶️ 准备就绪: 将生成 {num_groups} 大组，每组处理所有 {len(greenscreen_subfolders)} 个绿幕文件夹。")
            self.log_ab("⚠️ 警告: 处理成功后，原始背景图片将被删除！")

            # 4. 【修改】重构为新的三层循环逻辑
            # 外层循环: 控制生成的大组数量 (1, 2, 3...)
            for group_num in range(1, num_groups + 1):
                if self.ab_image_stop_event.is_set(): break
                
                self.log_ab(f"\n---=== 开始处理第 {group_num}/{num_groups} 大组 ===---")
                group_output_folder = os.path.join(output_folder, str(group_num))
                os.makedirs(group_output_folder, exist_ok=True)

                # 中层循环: 遍历每一个绿幕子文件夹
                for gs_folder in greenscreen_subfolders:
                    if self.ab_image_stop_event.is_set(): break
                    
                    folder_tag = os.path.basename(gs_folder)
                    self.log_ab(f"  -- 开始处理子文件夹: {folder_tag} --")
                    
                    current_gs_images = sorted([f for f in os.listdir(gs_folder) if f.lower().endswith(image_ext)])
                    
                    # 内层循环: 遍历子文件夹内的每一张绿幕图 (A, B, C...)
                    for gs_image_name in current_gs_images:
                        if self.ab_image_stop_event.is_set(): break
                        
                        if not source_images:
                            self.log_ab("  ❌ 致命错误: 背景图片已用尽，任务提前中止。")
                            self.ab_image_stop_event.set() # 强制停止所有循环
                            break
                        
                        bg_path = source_images.pop(0)
                        greenscreen_path = os.path.join(gs_folder, gs_image_name)
                        image_tag = os.path.splitext(gs_image_name)[0]
                        
                        # 新的文件命名方式，更清晰
                        output_filename = f"{folder_tag}-{image_tag}.png"
                        output_path = os.path.join(group_output_folder, output_filename)

                        self.log_ab(f"    - 正在合成: {os.path.basename(bg_path)} + {gs_image_name} -> {output_filename}")
                        
                        success = self._ab_worker(bg_path, greenscreen_path, output_path)
                        
                        # 成功一张就删除一张
                        if success:
                            try:
                                os.remove(bg_path)
                                self.log_ab(f"      ✅ 合成成功，已删除背景图: {os.path.basename(bg_path)}")
                            except OSError as e:
                                self.log_ab(f"      ⚠️ 警告: 合成成功，但删除图片时出错: {e}")
                        else:
                            self.log_ab(f"      ❌ 合成失败，背景图 {os.path.basename(bg_path)} 未被删除。")
                
                if self.ab_image_stop_event.is_set(): break

            if self.ab_image_stop_event.is_set():
                 self.log_ab("🔴 任务已中止。")
            else:
                self.log_ab("\n---=== 所有任务处理完毕！ ===---")
        except Exception as e:
            self.log_ab(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_ab_buttons)
    # --- 长视频分割 (Video Splitting) ---
    def log_splitter(self, message, clear=False):
        """向长视频分割日志框记录信息"""
        self.after(0, self._update_log, self.splitter_log_textbox, message, clear)

    def start_video_split(self):
        """开始视频分割的线程"""
        self.video_stop_event.clear() # 复用现有的停止事件
        self.start_splitter_button.configure(state="disabled")
        self.stop_splitter_button.configure(state="normal")
        self.log_splitter("", clear=True)
        threading.Thread(target=self.run_video_split_logic, daemon=True).start()

    def stop_video_split(self):
        """发送停止信号"""
        self.log_splitter("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.video_stop_event.set()
        self.stop_splitter_button.configure(state="disabled")

    def _reset_splitter_buttons(self):
        """重置开始/停止按钮的状态"""
        self.start_splitter_button.configure(state="normal")
        self.stop_splitter_button.configure(state="disabled")

    def run_video_split_logic(self):
        """视频分割的主逻辑"""
        try:
            input_folder = self.splitter_input_folder_entry.get()
            output_folder = self.splitter_output_folder_entry.get()
            use_gpu = self.splitter_use_gpu_switch.get() == 1

            if not all([input_folder, output_folder]):
                self.log_splitter("❌ 错误: 输入和输出文件夹都必须选择。")
                return

            try:
                split_duration = float(self.splitter_duration_entry.get())
                if split_duration <= 0: raise ValueError
            except (ValueError, TypeError):
                self.log_splitter("❌ 错误: 分割时长必须是一个有效的正数。")
                return

            self.log_splitter("正在扫描视频文件...")
            video_files = []
            for root, _, files in os.walk(input_folder):
                for file in files:
                    if file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                        video_files.append(os.path.join(root, file))
            
            if not video_files:
                self.log_splitter("ℹ️ 在指定文件夹及其子文件夹中未找到任何视频文件。")
                return

            self.log_splitter(f"🔍 扫描完成，共找到 {len(video_files)} 个视频文件待处理。")
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
                self.log_splitter(f"已创建输出文件夹: '{output_folder}'")

            total_clips_generated = 0
            for i, video_path in enumerate(video_files):
                if self.video_stop_event.is_set():
                    self.log_splitter("🔴 任务已中止。")
                    break
                
                self.log_splitter(f"\n---=== 开始处理第 {i+1}/{len(video_files)} 个视频: {os.path.basename(video_path)} ===---")
                
                # 调用worker函数处理单个视频
                clips_count = self._video_split_worker(video_path, output_folder, split_duration, use_gpu)
                if clips_count > 0:
                    total_clips_generated += clips_count
                    self.log_splitter(f"  ✅ 成功分割出 {clips_count} 个片段。")

            self.log_splitter(f"\n---=== 所有任务处理完毕！总共生成了 {total_clips_generated} 个短视频片段。 ===---")

        except Exception as e:
            self.log_splitter(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_splitter_buttons)
    # --- 视频截图片 (Frame Extraction) ---
    def log_extractor(self, message, clear=False):
        """向视频截图片日志框记录信息"""
        self.after(0, self._update_log, self.extractor_log_textbox, message, clear)

    def start_frame_extraction(self):
        """开始视频截图的线程"""
        self.video_stop_event.clear() # 复用现有的停止事件
        self.start_extractor_button.configure(state="disabled")
        self.stop_extractor_button.configure(state="normal")
        self.log_extractor("", clear=True)
        threading.Thread(target=self.run_frame_extraction_logic, daemon=True).start()

    def stop_frame_extraction(self):
        """发送停止信号"""
        self.log_extractor("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.video_stop_event.set()
        self.stop_extractor_button.configure(state="disabled")

    def _reset_extractor_buttons(self):
        """重置开始/停止按钮的状态"""
        self.start_extractor_button.configure(state="normal")
        self.stop_extractor_button.configure(state="disabled")

    def run_frame_extraction_logic(self):
        """视频截图的主逻辑"""
        try:
            input_folder = self.extractor_input_folder_entry.get()
            output_folder = self.extractor_output_folder_entry.get()
            use_gpu = self.extractor_use_gpu_switch.get() == 1
            resize_enabled = self.extractor_resize_switch.get() == 1

            if not all([input_folder, output_folder]):
                self.log_extractor("❌ 错误: 输入和输出文件夹都必须选择。")
                return

            try:
                interval = float(self.extractor_interval_entry.get())
                if interval <= 0: raise ValueError
            except (ValueError, TypeError):
                self.log_extractor("❌ 错误: 截图间隔必须是一个有效的正数。")
                return

            self.log_extractor("正在扫描视频文件...")
            video_files = []
            for root, _, files in os.walk(input_folder):
                for file in files:
                    if file.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                        video_files.append(os.path.join(root, file))
            
            if not video_files:
                self.log_extractor("ℹ️ 在指定文件夹及其子文件夹中未找到任何视频文件。")
                return

            self.log_extractor(f"🔍 扫描完成，共找到 {len(video_files)} 个视频文件待处理。")
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
                self.log_extractor(f"已创建输出文件夹: '{output_folder}'")

            total_frames_generated = 0
            for i, video_path in enumerate(video_files):
                if self.video_stop_event.is_set():
                    self.log_extractor("🔴 任务已中止。")
                    break
                
                self.log_extractor(f"\n---=== 开始处理第 {i+1}/{len(video_files)} 个视频: {os.path.basename(video_path)} ===---")
                
                # 调用worker函数处理单个视频
                frames_count = self._frame_extraction_worker(video_path, output_folder, interval, resize_enabled, use_gpu)
                if frames_count > 0:
                    total_frames_generated += frames_count
                    self.log_extractor(f"  ✅ 成功截取 {frames_count} 张图片。")

            self.log_extractor(f"\n---=== 所有任务处理完毕！总共生成了 {total_frames_generated} 张图片。 ===---")

        except Exception as e:
            self.log_extractor(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_extractor_buttons)

    def _frame_extraction_worker(self, video_path, output_folder, interval, resize_enabled, use_gpu):
        """处理单个视频文件的截图工作"""
        generated_count = 0
        target_resolution = (1080, 1920)
        try:
            # 使用 OpenCV 读视频帧，效率更高
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.log_extractor(f"  ❌ 错误: 无法打开视频文件 {os.path.basename(video_path)}")
                return 0

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            base_name = os.path.splitext(os.path.basename(video_path))[0]

            for t in np.arange(0, duration, interval):
                if self.video_stop_event.is_set(): break
                
                frame_id = int(t * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
                ret, frame = cap.read()
                
                if not ret: continue

                output_filename = f"{base_name}_frame_{generated_count+1:04d}.jpg"
                output_path = os.path.join(output_folder, output_filename)
                
                self.log_extractor(f"  - 正在截取第 {generated_count+1} 张图片 (时间点: {t:.2f}s)")
                
                if resize_enabled:
                    # 使用 Pillow 进行高质量缩放
                    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    # 使用 ImageOps.fit 来进行裁剪以适应目标比例，避免拉伸
                    resized_img = ImageOps.fit(pil_img, target_resolution, Image.Resampling.LANCZOS)
                    resized_img.save(output_path, "JPEG", quality=95)
                else:
                    cv2.imwrite(output_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                
                generated_count += 1
            
            # 处理不足一个间隔时，截取最后一帧
            if duration % interval != 0 and generated_count > 0:
                 cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
                 ret, frame = cap.read()
                 if ret:
                    self.log_extractor(f"  - 补全最后一帧...")
                    output_filename = f"{base_name}_frame_{generated_count+1:04d}_last.jpg"
                    output_path = os.path.join(output_folder, output_filename)
                    if resize_enabled:
                        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                        resized_img = ImageOps.fit(pil_img, target_resolution, Image.Resampling.LANCZOS)
                        resized_img.save(output_path, "JPEG", quality=95)
                    else:
                        cv2.imwrite(output_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                    generated_count += 1

            cap.release()

        except Exception as e:
            self.log_extractor(f"  ❌ 处理视频 {os.path.basename(video_path)} 时发生错误: {e}")
            if 'cap' in locals(): cap.release()
            return 0
        
        return generated_count
    def _video_split_worker(self, video_path, output_folder, duration, use_gpu):
        """处理单个视频文件的分割工作"""
        generated_count = 0
        try:
            with VideoFileClip(video_path) as video:
                total_duration = video.duration
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                
                for i in range(int(total_duration // duration)):
                    if self.video_stop_event.is_set(): break
                    
                    start_time = i * duration
                    end_time = start_time + duration
                    output_filename = f"{base_name}_part_{i+1:03d}.mp4"
                    output_path = os.path.join(output_folder, output_filename)
                    
                    self.log_splitter(f"  - 正在导出片段: {i+1:03d} ({start_time:.2f}s -> {end_time:.2f}s)")
                    
                    clip = video.subclip(start_time, end_time)
                    
                    codec = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
                    try:
                        # 【修改】在这里移除了 audio_codec='aac'，并添加了 audio=False 来实现静音
                        clip.write_videofile(output_path, codec=codec, audio=False, logger=None)
                        generated_count += 1
                    except Exception as e:
                        self.log_splitter(f"    ❌ 导出片段 {output_filename} 失败: {e}")
                        # 如果GPU失败，可以尝试用CPU重试
                        if 'nvenc' in codec:
                            self.log_splitter("    ... 尝试用CPU重新编码 ...")
                            try:
                                # 【修改】CPU重试时同样需要静音处理
                                clip.write_videofile(output_path, codec='libx264', audio=False, logger=None)
                                generated_count += 1
                            except Exception as e2:
                                self.log_splitter(f"    ❌ CPU重试失败: {e2}")

        except Exception as e:
            self.log_splitter(f"  ❌ 处理视频 {os.path.basename(video_path)} 时发生错误: {e}")
            return 0
        
        return generated_count    
    def _ab_worker(self, background_path, greenscreen_path, output_path):
        try:
            background_img = Image.open(background_path).convert("RGBA")
            greenscreen_img = Image.open(greenscreen_path).convert("RGBA")
            if background_img.size != greenscreen_img.size: greenscreen_img = greenscreen_img.resize(background_img.size, Image.Resampling.LANCZOS)
            gs_arr = np.array(greenscreen_img)
            green_color, threshold = np.array([0, 255, 0]), 170
            distances = np.sqrt(np.sum((gs_arr[:, :, :3] - green_color)**2, axis=2))
            mask = distances < threshold
            gs_arr[mask, 3] = 0
            processed_gs_img = Image.fromarray(gs_arr)
            background_img.paste(processed_gs_img, (0, 0), processed_gs_img)
            background_img.save(output_path, 'PNG')
            return True
        except Exception as e: self.log_ab(f"    ❌ 核心合成失败: {e}"); return False

    # --- 配置获取与预览 ---
    def get_video_config_from_gui(self):
        try:
            x_pos_val = self.video_main_pos_x_entry.get()
            x_pos = x_pos_val if x_pos_val.isalpha() else int(x_pos_val)
            shared_style_config = {"font_file": self.video_shared_font_file_entry.get(), "size": int(self.video_shared_size_entry.get()), "max_width_ratio": float(self.video_shared_max_width_ratio_entry.get()), "padding_horizontal": int(self.video_shared_padding_horizontal_entry.get()), "padding_vertical": int(self.video_shared_padding_vertical_entry.get()), "stroke_width": int(self.video_shared_stroke_width_entry.get()), "corner_radius": int(self.video_shared_corner_radius_entry.get()),"no_background": self.video_no_bg_switch.get() == 1}
            main_text_config = {"position": {"x": x_pos, "y": int(self.video_main_pos_y_entry.get())}, "colors": {"text": self.video_main_color_text_value, "stroke": self.video_main_color_stroke_value, "background": self.video_main_color_bg_value}}
            sub_texts_config = [{"relative_y_offset": int(self.video_sub1_offset_y_entry.get()), "colors": {"text": self.video_sub1_color_text_value, "stroke": self.video_sub1_color_stroke_value, "background": self.video_sub1_color_bg_value}}, {"relative_y_offset": int(self.video_sub2_offset_y_entry.get()), "colors": {"text": self.video_sub2_color_text_value, "stroke": self.video_sub2_color_stroke_value, "background": self.video_sub2_color_bg_value}}]
            return {"shared_style": shared_style_config, "main_text": main_text_config, "sub_texts": sub_texts_config}
        except Exception as e: self.log_video(f"视频配置错误: {e}"); return None

    def get_image_config_from_gui(self):
        try:
            pos_text = self.image_text_positions_textbox.get("1.0", "end-1c")
            pos_list = json.loads(pos_text.replace("'", "\""))
            zoom_text = self.image_zoom_crop_percentages_textbox.get("1.0", "end-1c"); zoom_list = [float(x.strip()) for x in zoom_text.split(',') if x.strip()]
            spacing_text = self.image_line_spacing_options_textbox.get("1.0", "end-1c"); spacing_list = [int(x.strip()) for x in spacing_text.split(',') if x.strip()]
            return {"font_path": self.image_font_path_entry.get(),"font_size": int(self.image_font_size_entry.get()), "font_color": list(ImageColor.getrgb(self.image_font_color_value)), "font_background_color": list(ImageColor.getrgb(self.image_font_background_color_value)),"text_positions": pos_list, "max_text_width_ratio": float(self.image_max_text_width_ratio_entry.get()), "line_spacing_options": spacing_list, "corner_radius": int(self.image_corner_radius_entry.get()),"text_padding": int(self.image_text_padding_entry.get()),"text_align_in_block": self.image_text_align_in_block_menu.get(),"zoom_crop_percentages": zoom_list, "allow_random_horizontal_flip": bool(self.image_flip_switch.get()),"no_background": self.image_no_bg_switch.get() == 1}
        except Exception as e: self.log_image(f"图片配置错误: {e}"); return None
    
    def generate_video_preview(self):
        self.preview_button.configure(state="disabled", text="正在生成...")
        self.update_idletasks()
        try:
            config = self.get_video_config_from_gui()
            if not config: self.preview_label.configure(image=None, text="配置无效，无法生成预览"); self.preview_display_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5); return
            preview_pil_image = Image.new('RGB', (1280, 720), (40, 40, 40)) 
            sample_text = "短文案&这是一个非常长的句子用于演示自动换行功能/这是手动换行&第三块/也支持手动换行"
            text_parts = [part.strip() for part in sample_text.split('&')]
            shared_style_config = config['shared_style']
            main_text_config = config['main_text']
            main_overlay_img = self._create_overlay_as_pillow_image(text_parts[0], shared_style_config, main_text_config, (1280, 720))
            pos_config = main_text_config['position']
            x_pos_val, y_pos = pos_config.get('x', 'center'), pos_config.get('y', 'center')
            paste_x = (preview_pil_image.width - main_overlay_img.width) // 2 if x_pos_val == 'center' else int(x_pos_val)
            paste_y = int(y_pos)
            preview_pil_image.paste(main_overlay_img, (paste_x, paste_y), main_overlay_img)
            last_clip_y, last_clip_height = paste_y, main_overlay_img.height
            sub_texts_configs = config.get('sub_texts', [])
            for k, sub_text in enumerate(text_parts[1:]):
                if k >= len(sub_texts_configs): break
                sub_text_config = sub_texts_configs[k]
                sub_overlay_img = self._create_overlay_as_pillow_image(sub_text, shared_style_config, sub_text_config, (1280, 720))
                y_offset = sub_text_config.get("relative_y_offset", 10)
                new_y = last_clip_y + last_clip_height + y_offset
                new_x = (preview_pil_image.width - sub_overlay_img.width) // 2
                preview_pil_image.paste(sub_overlay_img, (new_x, new_y), sub_overlay_img)
                last_clip_y, last_clip_height = new_y, sub_overlay_img.height
            PREVIEW_DISPLAY_SIZE = (720, 405)
            ctk_image = ctk.CTkImage(light_image=preview_pil_image, dark_image=preview_pil_image, size=PREVIEW_DISPLAY_SIZE)
            self.preview_label.configure(image=ctk_image, text="")
            self.preview_display_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        except Exception as e: 
            self.preview_label.configure(image=None, text=f"预览生成失败:\n{e}")
            self.preview_display_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)
        finally: 
            self.preview_button.configure(state="normal", text="生成视频字幕预览")

    def close_video_preview(self):
        self.preview_display_frame.grid_forget()

    def _create_overlay_as_pillow_image(self, text, shared_style, specific_config, video_size):
        video_width, _ = video_size; colors = specific_config['colors']; padding_horizontal = shared_style.get("padding_horizontal", 30)
        padding_vertical = shared_style.get('padding_vertical', 25); font_file = shared_style['font_file']; font_size = shared_style['size']
        stroke_width = shared_style.get('stroke_width', 0); corner_radius = shared_style.get('corner_radius', 0); max_width_ratio = shared_style.get('max_width_ratio', 0.9)
        # 新增：获取无背景开关状态
        no_background = shared_style.get('no_background', False)
        text_color = colors['text']; stroke_color = colors.get('stroke'); bg_color_str = colors.get('background', 'rgba(0,0,0,0)')
        try: font = ImageFont.truetype(font_file, font_size)
        except IOError: font = ImageFont.load_default()
        max_pixel_width = int(video_width * max_width_ratio); dummy_draw = ImageDraw.Draw(Image.new('RGB', (1,1)))
        probed_text = text.replace('/', '\n'); single_line_bbox = dummy_draw.multiline_textbbox((0,0), probed_text, font=font, align="center")
        single_line_width = single_line_bbox[2] - single_line_bbox[0]
        if single_line_width > max_pixel_width:
            manual_lines_raw = text.split('/'); final_lines = []
            for raw_line in manual_lines_raw:
                wrapped_lines, _, _ = image_wrap_text(dummy_draw, raw_line, font, max_pixel_width); final_lines.extend(wrapped_lines)
            text_for_drawing, align_for_drawing = '\n'.join(final_lines), 'center'
        else:
            text_for_drawing, align_for_drawing = probed_text, 'center'
        text_bbox = dummy_draw.multiline_textbbox((0, 0), text_for_drawing, font=font, align=align_for_drawing, stroke_width=stroke_width)
        actual_text_width, actual_text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        bg_width, bg_height = actual_text_width + (2 * padding_horizontal), actual_text_height + (2 * padding_vertical)
        bg_size = (int(bg_width), int(bg_height)); overlay_image = Image.new("RGBA", bg_size, (0, 0, 0, 0)); draw = ImageDraw.Draw(overlay_image)
        bg_rgb, bg_alpha = video_parse_rgba(bg_color_str); bg_fill_color = bg_rgb + (int(bg_alpha * 255),)
       
        # --- 主要修改点 ---
        if not no_background:
            bg_rgb, bg_alpha = video_parse_rgba(bg_color_str); bg_fill_color = bg_rgb + (int(bg_alpha * 255),)
            if corner_radius > 0: draw.rounded_rectangle(((0, 0), bg_size), int(corner_radius), fill=bg_fill_color)
            else: draw.rectangle(((0, 0), bg_size), fill=bg_fill_color)
        text_x, text_y = (bg_width - actual_text_width) / 2, (bg_height - actual_text_height) / 2
        draw.multiline_text((text_x, text_y - text_bbox[1]), text_for_drawing, fill=text_color, font=font, align=align_for_drawing, stroke_width=stroke_width, stroke_fill=stroke_color)
        return overlay_image
    
    def save_settings(self):
        """Saves all configurable fields to a JSON file."""
        settings = {
            'video_settings': {
                'text_input': self.video_text_input_box.get("1.0", "end-1c"),
                'num_groups': self.video_num_groups_entry.get(),
                'use_gpu': self.video_use_gpu_switch.get(),
                'shared_font_file': self.video_shared_font_file_entry.get(),
                'shared_size': self.video_shared_size_entry.get(),
                'shared_max_width_ratio': self.video_shared_max_width_ratio_entry.get(),
                'shared_padding_horizontal': self.video_shared_padding_horizontal_entry.get(),
                'shared_padding_vertical': self.video_shared_padding_vertical_entry.get(),
                'shared_stroke_width': self.video_shared_stroke_width_entry.get(),
                'shared_corner_radius': self.video_shared_corner_radius_entry.get(),
                'no_background': self.video_no_bg_switch.get(), 
                'main_pos_x': self.video_main_pos_x_entry.get(),
                'main_pos_y': self.video_main_pos_y_entry.get(),
                'main_color_text': self.video_main_color_text_value,
                'main_color_stroke': self.video_main_color_stroke_value,
                'main_color_bg': self.video_main_color_bg_value,
                'sub1_offset_y': self.video_sub1_offset_y_entry.get(),
                'sub1_color_text': self.video_sub1_color_text_value,
                'sub1_color_stroke': self.video_sub1_color_stroke_value,
                'sub1_color_bg': self.video_sub1_color_bg_value,
                'sub2_offset_y': self.video_sub2_offset_y_entry.get(),
                'sub2_color_text': self.video_sub2_color_text_value,
                'sub2_color_stroke': self.video_sub2_color_stroke_value,
                'sub2_color_bg': self.video_sub2_color_bg_value,
            },
            'image_settings': {
                'text_input': self.image_text_input_box.get("1.0", "end-1c"),
                'num_groups': self.image_num_groups_entry.get(),
                'font_path': self.image_font_path_entry.get(),
                'font_size': self.image_font_size_entry.get(),
                'font_color': self.image_font_color_value,
                'font_background_color': self.image_font_background_color_value,
                'max_text_width_ratio': self.image_max_text_width_ratio_entry.get(),
                'corner_radius': self.image_corner_radius_entry.get(),
                'text_padding': self.image_text_padding_entry.get(),
                'text_align_in_block': self.image_text_align_in_block_menu.get(),
                'text_positions': self.image_text_positions_textbox.get("1.0", "end-1c"),
                'line_spacing_options': self.image_line_spacing_options_textbox.get("1.0", "end-1c"),
                'zoom_crop_percentages': self.image_zoom_crop_percentages_textbox.get("1.0", "end-1c"),
                'allow_flip': self.image_flip_switch.get(),
                'no_background': self.image_no_bg_switch.get(),
            },
            'ai_settings': {
                'use_gpu': self.ai_use_gpu_switch.get(),
                'transparent_bg': self.transparent_bg_switch.get(),
                'delete_bg': self.delete_bg_switch.get(),
            },
            'ab_image_settings': {
                'num_groups': self.ab_num_groups_entry.get()
            },
            'video_splitter_settings': {
                'duration': self.splitter_duration_entry.get(),
                'use_gpu': self.splitter_use_gpu_switch.get()
            },
            # 【修正】在这里添加了之前缺失的逗号
            'frame_extractor_settings': {
                'interval': self.extractor_interval_entry.get(),
                'resize': self.extractor_resize_switch.get(),
                'use_gpu': self.extractor_use_gpu_switch.get()
            },
            'audio_extractor_settings': {
                'duration': self.audio_duration_entry.get()
            },
            'freeze_settings': {
                'duration': self.freeze_duration_entry.get()
            },
            'gs_replace_settings': {
                'random_concat': self.gs_replace_random_concat_switch.get(),
                'use_gs_audio': self.gs_replace_audio_switch.get()
            }
        }
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            # 在打包后的程序中，这个print不会显示，但可以在开发时看到
            print(f"Error saving settings: {e}")
    def load_settings(self):
        try:
            with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self.settings_loaded = True 
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings_loaded = False
            # 如果找不到配置文件，也要确保所有UI控件存在，以便后续代码不会报错
            if not hasattr(self, 'splitter_duration_entry'):
                # 这是一个技巧，确保即使在没有配置文件的情况下，后续对这些控件的操作也不会引发AttributeError
                # 您无需修改这部分，只需确保粘贴了完整的函数即可
                self.after(100, lambda: self.splitter_duration_entry.insert(0, '3'))
            return

        # 加载视频处理设置
        vs = settings.get('video_settings', {})
        self.video_text_input_box.delete("1.0", "end")
        self.video_text_input_box.insert("1.0", vs.get('text_input', '短文案&这是一个非常长的文案'))
        self.video_num_groups_entry.delete(0, 'end')
        self.video_num_groups_entry.insert(0, vs.get('num_groups', '1'))
        if vs.get('use_gpu', 0): self.video_use_gpu_switch.select() 
        else: self.video_use_gpu_switch.deselect()
        self.video_shared_font_file_entry.delete(0, 'end'); self.video_shared_font_file_entry.insert(0, vs.get('shared_font_file', ''))
        self.video_shared_size_entry.delete(0, 'end'); self.video_shared_size_entry.insert(0, vs.get('shared_size', '60'))
        self.video_shared_max_width_ratio_entry.delete(0, 'end'); self.video_shared_max_width_ratio_entry.insert(0, vs.get('shared_max_width_ratio', '0.9'))
        self.video_shared_padding_horizontal_entry.delete(0, 'end'); self.video_shared_padding_horizontal_entry.insert(0, vs.get('shared_padding_horizontal', '30'))
        self.video_shared_padding_vertical_entry.delete(0, 'end'); self.video_shared_padding_vertical_entry.insert(0, vs.get('shared_padding_vertical', '25'))
        self.video_shared_stroke_width_entry.delete(0, 'end'); self.video_shared_stroke_width_entry.insert(0, vs.get('shared_stroke_width', '2'))
        self.video_shared_corner_radius_entry.delete(0, 'end'); self.video_shared_corner_radius_entry.insert(0, vs.get('shared_corner_radius', '20'))
        # 新增下面几行
        if vs.get('no_background', 0):
            self.video_no_bg_switch.select()
        else:
            self.video_no_bg_switch.deselect()
        self.video_main_pos_x_entry.delete(0, 'end'); self.video_main_pos_x_entry.insert(0, vs.get('main_pos_x', 'center'))
        self.video_main_pos_y_entry.delete(0, 'end'); self.video_main_pos_y_entry.insert(0, vs.get('main_pos_y', '150'))
        self._update_color_widget('video_main_color_text', vs.get('main_color_text', 'white'))
        self._update_color_widget('video_main_color_stroke', vs.get('main_color_stroke', 'black'))
        self._update_color_widget('video_main_color_bg', vs.get('main_color_bg', 'rgba(0, 0, 0, 0.5)'))
        self.video_sub1_offset_y_entry.delete(0, 'end'); self.video_sub1_offset_y_entry.insert(0, vs.get('sub1_offset_y', '20'))
        self._update_color_widget('video_sub1_color_text', vs.get('sub1_color_text', '#FFD700'))
        self._update_color_widget('video_sub1_color_stroke', vs.get('sub1_color_stroke', 'black'))
        self._update_color_widget('video_sub1_color_bg', vs.get('sub1_color_bg', 'rgba(200,50,50,0.85)'))
        self.video_sub2_offset_y_entry.delete(0, 'end'); self.video_sub2_offset_y_entry.insert(0, vs.get('sub2_offset_y', '30'))
        self._update_color_widget('video_sub2_color_text', vs.get('sub2_color_text', 'white'))
        self._update_color_widget('video_sub2_color_stroke', vs.get('sub2_color_stroke', 'black'))
        self._update_color_widget('video_sub2_color_bg', vs.get('sub2_color_bg', 'rgba(50,50,50,0.7)'))

        # 加载图片处理设置
        imgs = settings.get('image_settings', {})
        self.image_text_input_box.delete("1.0", "end"); self.image_text_input_box.insert("1.0", imgs.get('text_input', '图片文案'))
        self.image_num_groups_entry.delete(0, 'end'); self.image_num_groups_entry.insert(0, imgs.get('num_groups', '1'))
        self.image_font_path_entry.delete(0, 'end'); self.image_font_path_entry.insert(0, imgs.get('font_path', ''))
        self.image_font_size_entry.delete(0, 'end'); self.image_font_size_entry.insert(0, imgs.get('font_size', '75'))
        self._update_color_widget('image_font_color', imgs.get('font_color', '#000000'))
        self._update_color_widget('image_font_background_color', imgs.get('font_background_color', '#ffffff'))
        self.image_max_text_width_ratio_entry.delete(0, 'end'); self.image_max_text_width_ratio_entry.insert(0, imgs.get('max_text_width_ratio', '0.85'))
        self.image_corner_radius_entry.delete(0, 'end'); self.image_corner_radius_entry.insert(0, imgs.get('corner_radius', '15'))
        self.image_text_padding_entry.delete(0, 'end'); self.image_text_padding_entry.insert(0, imgs.get('text_padding', '30'))
        self.image_text_align_in_block_menu.set(imgs.get('text_align_in_block', 'center'))
        self.image_text_positions_textbox.delete("1.0", "end"); self.image_text_positions_textbox.insert("1.0", imgs.get('text_positions', '[]'))
        self.image_line_spacing_options_textbox.delete("1.0", "end"); self.image_line_spacing_options_textbox.insert("1.0", imgs.get('line_spacing_options', '45'))
        self.image_zoom_crop_percentages_textbox.delete("1.0", "end"); self.image_zoom_crop_percentages_textbox.insert("1.0", imgs.get('zoom_crop_percentages', '0'))
        if imgs.get('allow_flip', True): self.image_flip_switch.select()
        else: self.image_flip_switch.deselect()
        # 新增下面几行
        if imgs.get('no_background', 0):
            self.image_no_bg_switch.select()
        else:
            self.image_no_bg_switch.deselect()
        # 加载 AI 抠像设置
        ais = settings.get('ai_settings', {})
        if ais.get('use_gpu', 0): self.ai_use_gpu_switch.select() 
        else: self.ai_use_gpu_switch.deselect()
        if ais.get('transparent_bg', 0): self.transparent_bg_switch.select()
        else: self.transparent_bg_switch.deselect()
        if ais.get('delete_bg', 0): self.delete_bg_switch.select()
        else: self.delete_bg_switch.deselect()
        self._toggle_bg_folder_state()

        # 加载 AB 图文设置
        ab_s = settings.get('ab_image_settings', {})
        self.ab_num_groups_entry.delete(0, 'end')
        self.ab_num_groups_entry.insert(0, ab_s.get('num_groups', '10'))
        
        # --- 【在这里新增下面的代码块】 ---
        # 加载长视频分割设置
        splitter_s = settings.get('video_splitter_settings', {})
        self.splitter_duration_entry.delete(0, 'end')
        self.splitter_duration_entry.insert(0, splitter_s.get('duration', '3'))
        if splitter_s.get('use_gpu', 0):
            self.splitter_use_gpu_switch.select()
        else:
            self.splitter_use_gpu_switch.deselect()
        # --- 【在这里新增下面的代码块】 ---
        # 加载视频截图片设置
        extractor_s = settings.get('frame_extractor_settings', {})
        self.extractor_interval_entry.delete(0, 'end')
        self.extractor_interval_entry.insert(0, extractor_s.get('interval', '3'))
        if extractor_s.get('resize', 1): # 默认为1(开启)
            self.extractor_resize_switch.select()
        else:
            self.extractor_resize_switch.deselect()
        if extractor_s.get('use_gpu', 0):
            self.extractor_use_gpu_switch.select()
        else:
            self.extractor_use_gpu_switch.deselect()
        audio_s = settings.get('audio_extractor_settings', {})
        self.audio_duration_entry.delete(0, 'end')
        self.audio_duration_entry.insert(0, audio_s.get('duration', ''))
        # 加载定格设置
        freeze_s = settings.get('freeze_settings', {})
        self.freeze_duration_entry.delete(0, 'end')
        self.freeze_duration_entry.insert(0, freeze_s.get('duration', '3'))
        # 加载绿幕替换设置
        gs_s = settings.get('gs_replace_settings', {})
        if gs_s.get('random_concat', 0): self.gs_replace_random_concat_switch.select()
        else: self.gs_replace_random_concat_switch.deselect()
        if gs_s.get('use_gs_audio', 1): self.gs_replace_audio_switch.select()
        else: self.gs_replace_audio_switch.deselect()
            
    def _update_color_widget(self, attr_name, color_value): setattr(self, attr_name + "_value", color_value); button = getattr(self, attr_name + "_button"); button.configure(text=str(color_value), fg_color="gray" if "rgba" in str(color_value) else color_value)

# ==============================================================================
# 应用程序启动入口
# ==============================================================================
if __name__ == "__main__":
    app = App()
    app.withdraw()
    splash = ctk.CTkToplevel(app)
    splash.title("启动中...")
    splash_width, splash_height = 350, 150
    screen_width, screen_height = app.winfo_screenwidth(), app.winfo_screenheight()
    x, y = int((screen_width / 2) - (splash_width / 2)), int((screen_height / 2) - (splash_height / 2))
    splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")
    splash.overrideredirect(True)
    ctk.CTkLabel(splash, text="程序正在启动，请稍候...", font=ctk.CTkFont(size=18)).pack(expand=True)
    def show_main_window():
        splash.destroy()
        app.deiconify()
    app.after(2000, show_main_window)
    app.mainloop()