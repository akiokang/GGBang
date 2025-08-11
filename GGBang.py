# GGBang_Final.py (v18.0 - Truly Complete, All Functions Restored)
#0704-适配IOS格式MOV
#0705-新增视频克隆
import ffmpeg
import customtkinter as ctk
from tkinter import filedialog, colorchooser, messagebox as tk_messagebox
import threading
import queue
import subprocess
import traceback
import time
import os
import gc
from pathlib import Path
import json
import random
import numpy as np
import re
import shutil
import sys
import socket
import struct
import requests
import subprocess
import platform
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip, ImageClip, ImageSequenceClip
from moviepy.video.fx import all as vfx
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageColor
import moviepy.config as cf
# --- iOS批量传输 全局配置 ---
MCAST_GRP = '224.0.0.167'
MCAST_PORT = 53317
DISCOVERY_DURATION = 50  # 搜索设备的秒数
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
    imagemagick_dir = os.path.dirname(imagemagick_path)
    os.environ['MAGICK_CODER_MODULE_PATH'] = os.path.join(imagemagick_dir, 'modules', 'coders')
    os.environ['MAGICK_CONFIGURE_PATH'] = imagemagick_dir
    print("已为ImageMagick的正常运行配置了必要的环境变量。")
else:
    # 这一行在打包后不应出现，仅用于开发时调试
    print("警告: 在预期的打包路径中未找到ImageMagick程序。")

# --- AI抠像功能需要的新库 ---
# --- AI抠像功能需要的新库 ---
try:
    import cv2

except ImportError:
    tk_messagebox.showerror("依赖缺失", "AI抠像功能所需的核心库 (opencv-python, mediapipe) 未安装。\n请运行: pip install opencv-python mediapipe")
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
    if isinstance(rgba_string, str) and rgba_string.startswith('rgba'):
        try:
            parts = re.findall(r"[-+]?\d*\.\d+|\d+", rgba_string)
            parts = [float(p) for p in parts]
            if len(parts) == 4: return tuple(int(p) for p in parts[:3]), parts[3]
        except (ValueError, TypeError): pass
    try: return ImageColor.getrgb(rgba_string), 1.0
    except ValueError: return (0,0,0), 0.5

def video_create_text_overlay(text, shared_style, specific_config, video_size):
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


# 【请用这个版本完整替换】
def image_wrap_text(draw, text, font, max_width):
    """
    【v2.0 健壮版】将文本按单词换行，确保单词不被拆分。
    """
    if not text.strip():
        return [], 0, []

    lines = []
    words = text.split(' ')
    current_line = ""

    for word in words:
        # 检查如果加上新单词是否会超长
        test_line = current_line + (" " if current_line else "") + word
        bbox = draw.textbbox((0, 0), test_line, font=font)

        if bbox[2] <= max_width:
            # 如果没超长，就继续加单词
            current_line = test_line
        else:
            # 如果超长了
            if current_line:
                # 先把已经成型的上一行存起来
                lines.append(current_line)
            # 新的一行从这个超长的单词开始
            current_line = word

    # 把最后一行也存起来
    if current_line:
        lines.append(current_line)

    if not lines:
        return [], 0, []

    # 计算所有行的宽度和高度
    widths = [draw.textbbox((0, 0), l, font=font)[2] for l in lines]
    # 修正高度计算，确保准确
    heights = [draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]

    return lines, max(widths), heights


# 【请用这个版本完整替换】
# 【请用这个版本完整替换您的 image_apply_text 函数】

def image_apply_text(img_path, text_line, config, pos_tuple, output_path, logger, stop_event):
    if stop_event.is_set(): return 'STOPPED'
    try:
        base_img = Image.open(img_path).convert("RGB")
    except Exception as e:
        logger(f"❌ 打开图片失败: {img_path} - {e}")
        return False

    img = image_preprocess(base_img, config, logger, os.path.basename(img_path))
    draw = ImageDraw.Draw(img)
    W, H = img.size

    text_parts = [part.strip() for part in text_line.split('&') if part.strip()]
    main_text = text_parts[0]
    sub_text = text_parts[1] if len(text_parts) > 1 else None

    def draw_single_text_block(draw_obj, text_content, block_config, shared_config, y_start_pos, center_x_pos=None):
        try:
            font_path = block_config.get("font_path") or shared_config["main_text"]["font_path"]
            font_size = block_config.get("font_size") or shared_config["main_text"]["font_size"]
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            logger(f"  -> 警告: 加载字体失败 ({e})，将使用默认字体。")
            font = ImageFont.load_default()

        max_w_ratio = shared_config.get("max_text_width_ratio", 0.8)
        padding = shared_config.get("text_padding", 10)
        align = shared_config.get("text_align_in_block", "center")
        radius = shared_config.get("corner_radius", 0)
        no_background = shared_config.get('no_background', False)

        font_color = tuple(block_config.get("font_color", [0, 0, 0]))
        bg_color = tuple(block_config.get("font_background_color", [255, 255, 255]))

        lines, block_w, line_heights = image_wrap_text(draw_obj, text_content, font, W * max_w_ratio)
        if not lines: return 0

        line_spacing = random.choice(shared_config.get("line_spacing_options", [10]))

        # 预计算总高度，用于整体定位
        total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
        total_block_height = total_text_height + (padding * 2 if not no_background else 0)

        # --- [核心修改] 开始：逐行绘制背景和文字 ---

        # block_x_start 是整个文本块（以最宽的一行为准）的理论左上角X坐标
        block_x_start = center_x_pos - (block_w / 2)
        current_y = y_start_pos

        for i, line in enumerate(lines):
            line_bbox = draw_obj.textbbox((0, 0), line, font=font)
            line_w = line_bbox[2] - line_bbox[0]

            # 计算当前行的实际起始X坐标
            line_x = block_x_start
            if align == 'center':
                line_x += (block_w - line_w) / 2
            elif align == 'right':
                line_x += block_w - line_w

            if not no_background:
                # 为当前行绘制独立的、紧贴的背景
                bg_coords = (
                    line_x - padding,
                    current_y - padding,
                    line_x + line_w + padding,
                    current_y + line_heights[i] + padding
                )
                if radius > 0:
                    draw_obj.rounded_rectangle(bg_coords, radius=radius, fill=bg_color)
                else:
                    draw_obj.rectangle(bg_coords, fill=bg_color)

            # 在背景之上绘制文字
            # 减去-bbox[1]是为了修正字体顶部的空白，让视觉更对齐
            draw_obj.text((line_x, current_y - line_bbox[1]), line, font=font, fill=font_color)

            # 累加当前行的高度和行间距，为下一行做准备
            current_y += line_heights[i] + line_spacing
        # --- [核心修改] 结束 ---

        # 返回这个文本块占用的总高度
        return total_block_height

    # --- 后续的定位逻辑保持不变 ---
    main_text_config = config["main_text"]

    try:
        main_font = ImageFont.truetype(main_text_config["font_path"], main_text_config.get("font_size", 32))
    except:
        main_font = ImageFont.load_default()

    main_lines, _, main_line_heights = image_wrap_text(draw, main_text, main_font,
                                                       W * config.get("max_text_width_ratio", 0.8))
    main_total_text_h = sum(main_line_heights) + random.choice(config.get("line_spacing_options", [10])) * (
                len(main_lines) - 1)

    sub_total_h = 0
    if sub_text:
        sub_text_config = config["sub_text"]
        try:
            sub_font = ImageFont.truetype(sub_text_config.get("font_path") or main_text_config["font_path"],
                                          sub_text_config.get("font_size") or main_text_config["font_size"])
        except:
            sub_font = ImageFont.load_default()
        sub_lines, _, sub_h_list = image_wrap_text(draw, sub_text, sub_font,
                                                   W * config.get("max_text_width_ratio", 0.8))
        sub_total_h = sum(sub_h_list) + random.choice(config.get("line_spacing_options", [10])) * (
                    len(sub_lines) - 1) + sub_text_config.get("relative_y_offset", 10)

    overall_height = main_total_text_h + sub_total_h
    center_x = W * pos_tuple[0]
    start_y_main = H * pos_tuple[1] - overall_height / 2

    main_block_height = draw_single_text_block(draw, main_text, main_text_config, config, start_y_main, center_x)

    if sub_text:
        sub_text_config = config["sub_text"]
        start_y_sub = start_y_main + main_block_height + sub_text_config.get("relative_y_offset", 10)
        draw_single_text_block(draw, sub_text, sub_text_config, config, start_y_sub, center_x)

    try:
        img.save(output_path)
        logger(f"  ✅ 已写入：{output_path}")
        return True
    except Exception as e:
        logger(f"❌ 保存图片失败: {output_path} - {e}")
        return False
# ==============================================================================
#  主GUI应用程序类
# ==============================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # __init__ 现在只负责最基础、最快速的初始化
        self.title("GGBang v19.0 (完整功能版)")
        self.geometry("950x1100")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.SETTINGS_FILE = get_persistent_settings_path("gui_settings.json")

        # 1. 先创建硬件信息显示UI的实例 (但先不显示)
        self.hw_info_frame = ctk.CTkFrame(self, height=30, border_width=1)
        self.cpu_info_label = ctk.CTkLabel(self.hw_info_frame, text="CPU: 正在检测...", font=("", 10))
        self.gpu_info_label = ctk.CTkLabel(self.hw_info_frame, text="GPU: 正在检测...", font=("", 10))

        # 2. 初始化所有必要的变量
        self.is_gpu_available = True
        self.selected_hex_color = None
        self.cropping_ref_point = []
        self.cropping_active = False
        self.selected_hsv_range = None

        # 3. 为所有功能创建停止事件
        self.distribution_stop_event = threading.Event()
        self.video_stop_event = threading.Event()
        self.image_stop_event = threading.Event()
        self.ab_image_stop_event = threading.Event()
        self.cut_stop_event = threading.Event()
        self.news_stop_event = threading.Event()
        self.blur_stop_event = threading.Event()
        self.audio_stop_event = threading.Event()
        self.ios_transfer_stop_event = threading.Event()
        self.lut_stop_event = threading.Event()
        self.composite_stop_event = threading.Event()
        self.video_clone_stop_event = threading.Event()
        self.dualscreen_stop_event = threading.Event()
        self.ios_discovery_stop_event = threading.Event()
        self.device_queue = queue.Queue()
        self.splitter_stop_event = threading.Event()
        self.uniform_resolution_stop_event = threading.Event()
        self.avatar_stop_event = threading.Event()
        self.porter_stop_event = threading.Event()
        self.img_to_video_stop_event = threading.Event()
        self.ITV_PRESETS_FILE = get_persistent_settings_path("img_to_video_presets.json")
        # 注意：原代码中有一些重复的事件定义，这里已为您整合
        self.active_ffmpeg_process = None
        try:
            # cv2.data.haarcascades 会自动指向OpenCV库中存放模型文件的正确路径
            cascade_path = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            if self.face_cascade.empty():
                print("警告: 人脸识别模型加载失败，'AI女巫'功能将不可用。")
                self.face_cascade = None
        except Exception as e:
            self.face_cascade = None
            print(f"加载人脸识别模型时出错: {e}")
    def setup_main_ui(self):
        """ 这是一个新函数，包含了所有耗时的UI创建和设置工作 """

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 创建主标签页视图
        self.main_tabview = ctk.CTkTabview(self)
        self.main_tabview.pack(expand=True, fill="both", padx=10, pady=10)

        # 添加所有功能标签页
        self.main_tabview.add("视频")
        self.main_tabview.add("图文")
        self.main_tabview.add("NEWS")
        self.main_tabview.add("AI美女/女巫")
        self.main_tabview.add("绿幕合成")
        self.main_tabview.add("卡秒")
        self.main_tabview.add("双屏")
        self.main_tabview.add("ios批量传输")

        self.setup_news_workflow()
        self.setup_ai_workflow()
        self.setup_graphic_workflow()
        # 调用所有功能的UI设置函数
        self.setup_master_video_workflow()
        self.setup_greenscreen_composite_workflow()
        self.setup_ios_transfer_workflow()
        self.setup_cut_workflow()
        self.setup_dualscreen_workflow()
        # 在所有主UI创建完毕后，再将底部的硬件信息栏打包显示出来
        self.hw_info_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.cpu_info_label.pack(side="left", padx=10)
        self.gpu_info_label.pack(side="left", padx=10)

        # 加载设置并设置窗口关闭行为
        self.load_settings()
        self._itv_populate_presets_dropdown()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ==============================================================================
    # --- AI总菜单 (新) ---
    # ==============================================================================
    def setup_ai_workflow(self):
        """创建“AI美女/女巫”主标签，并在其中嵌入所有AI相关的子标签页"""
        # 1. 获取主标签页
        ai_main_tab = self.main_tabview.tab("AI美女/女巫")

        # 2. 在内部创建子菜单的 Tabview
        ai_sub_tabview = ctk.CTkTabview(ai_main_tab)
        ai_sub_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        # 3. 添加所有需要的子标签页

        ai_sub_tabview.add("AI女巫")
        ai_sub_tabview.add("音频提取")
        ai_sub_tabview.add("视频克隆")

        # 4. 调用各个子功能的设置函数，并把对应的子标签页传递给它们

        self.setup_avatar_workflow(ai_sub_tabview.tab("AI女巫"))
        self.setup_audio_extraction_workflow(ai_sub_tabview.tab("音频提取"))
        self.setup_video_clone_workflow(ai_sub_tabview.tab("视频克隆"))
    # ==============================================================================
    # --- 视频总菜单 (新) ---
    # ==============================================================================
    def setup_master_video_workflow(self):
        """创建“视频”主标签，并在其中嵌入所有视频相关的子标签页"""
        # 1. 获取“视频”主标签页
        video_main_tab = self.main_tabview.tab("视频")

        # 2. 在内部创建子菜单的 Tabview
        video_sub_tabview = ctk.CTkTabview(video_main_tab)
        video_sub_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        # 3. 添加所有需要的子标签页
        video_sub_tabview.add("视频处理")
        video_sub_tabview.add("长视频分割")
        video_sub_tabview.add("统一分辨率")
        video_sub_tabview.add("加滤镜")

        # 4. 调用各个子功能的设置函数，并把对应的子标签页传递给它们
        self.setup_video_workflow(video_sub_tabview.tab("视频处理"))
        self.setup_video_splitter_workflow(video_sub_tabview.tab("长视频分割"))
        self.setup_uniform_resolution_workflow(video_sub_tabview.tab("统一分辨率"))
        self.setup_lut_workflow(video_sub_tabview.tab("加滤镜"))

    # ==============================================================================
    # --- 图文总菜单 (新) ---
    # ==============================================================================
    def setup_graphic_workflow(self):
        """创建“图文”主标签，并在其中嵌入所有图文相关的子标签页"""
        # 1. 获取“图文”主标签页
        graphic_main_tab = self.main_tabview.tab("图文")

        # 2. 在内部创建子菜单的 Tabview
        graphic_sub_tabview = ctk.CTkTabview(graphic_main_tab)
        graphic_sub_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        # 3. 添加所有需要的子标签页
        graphic_sub_tabview.add("图片处理")
        graphic_sub_tabview.add("AB图文")
        # 注意：我们之前已经将“视频截图片”移动到了“视频”菜单下，所以这里不再重复添加。
        # 如果您希望它出现在“图文”菜单下，请确保它已从“视频”菜单的设置中移除。
        # 假设我们现在要将它放在“图文”菜单下：
        graphic_sub_tabview.add("视频截图片")
        graphic_sub_tabview.add("图片分发")
        graphic_sub_tabview.add("健康类")
        graphic_sub_tabview.add("图转视频")

        # 4. 调用各个子功能的设置函数，并把对应的子标签页传递给它们
        self.setup_image_workflow(graphic_sub_tabview.tab("图片处理"))
        self.setup_ab_image_workflow(graphic_sub_tabview.tab("AB图文"))
        self.setup_frame_extractor_workflow(graphic_sub_tabview.tab("视频截图片"))
        self.setup_image_distribution_workflow(graphic_sub_tabview.tab("图片分发"))

        self.setup_health_image_workflow(graphic_sub_tabview.tab("健康类"))
        self.setup_img_to_video_workflow(graphic_sub_tabview.tab("图转视频"))

    # ==============================================================================
    # --- 【新增功能】图转视频 ---
    # ==============================================================================
    def setup_img_to_video_workflow(self, parent_tab):
        """创建“图转视频”功能的UI界面"""
        tab = parent_tab

        # --- 预设配置区 ---
        preset_frame = ctk.CTkFrame(tab)
        preset_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(preset_frame, text="标题/预设:", width=100).pack(side="left", padx=10)

        self.itv_preset_menu = ctk.CTkOptionMenu(preset_frame, values=[""], command=self._itv_load_preset)
        self.itv_preset_menu.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.itv_preset_title_entry = ctk.CTkEntry(preset_frame, placeholder_text="在此输入新标题以保存")
        self.itv_preset_title_entry.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.itv_save_preset_button = ctk.CTkButton(preset_frame, text="保存", width=60, command=self._itv_save_preset)
        self.itv_save_preset_button.pack(side="left", padx=(0, 10))

        # --- 路径与参数设置 ---
        self.create_folder_selection_row(tab, "图片文件夹:", "选择包含1,2,3...子文件夹的根目录",
                                         "itv_image_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择视频的保存位置", "itv_output_folder_entry")

        # --- 新增：生成组数输入框 ---
        self.create_widget_row(tab, "生成组数:", "itv_num_groups", "1").pack(fill="x", padx=10, pady=5)

        self.create_widget_row(tab, "时长规则(用.分隔):", "itv_durations", "", placeholder="例如: 4.5-2.2 (4秒1张, 5秒2张, 2秒1张)").pack(fill="x", padx=10, pady=5)

        # --- 按钮与日志 ---
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=20)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.itv_start_button = ctk.CTkButton(button_frame, text="开始生成视频", height=40,
                                              command=self.start_img_to_video_processing)
        self.itv_start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.itv_stop_button = ctk.CTkButton(button_frame, text="停止", height=40,
                                             command=lambda: self.img_to_video_stop_event.set(), state="disabled",
                                             fg_color="red", hover_color="darkred")
        self.itv_stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

        self.itv_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9AA")
        self.itv_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

        self._itv_populate_presets_dropdown()

    def log_itv(self, message, clear=False):
        self.after(0, self._update_log, self.itv_log_textbox, message, clear)

    def _itv_populate_presets_dropdown(self):
        try:
            with open(self.ITV_PRESETS_FILE, 'r', encoding='utf-8') as f:
                presets = json.load(f)
            titles = list(presets.keys())
            if not titles: titles = ["无预设"]
            self.itv_preset_menu.configure(values=titles)
            self.itv_preset_menu.set(titles[0])
            self._itv_load_preset(titles[0])
        except (FileNotFoundError, json.JSONDecodeError):
            self.itv_preset_menu.configure(values=["无预设"])
            self.itv_preset_menu.set("无预设")

    def _itv_save_preset(self):
        title = self.itv_preset_title_entry.get().strip()
        if not title:
            tk_messagebox.showwarning("提示", "请输入一个标题来保存预设。")
            return

        preset_data = {
            "image_folder": self.itv_image_folder_entry.get(),
            "output_folder": self.itv_output_folder_entry.get(),
            "durations": self.itv_durations_entry.get()
        }

        try:
            with open(self.ITV_PRESETS_FILE, 'r', encoding='utf-8') as f:
                presets = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            presets = {}

        presets[title] = preset_data

        with open(self.ITV_PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=4, ensure_ascii=False)

        self.log_itv(f"✅ 预设 '{title}' 已保存。")
        self.itv_preset_title_entry.delete(0, 'end')
        self._itv_populate_presets_dropdown()
        self.itv_preset_menu.set(title)

    def _itv_load_preset(self, preset_name):
        if preset_name == "无预设":
            return
        try:
            with open(self.ITV_PRESETS_FILE, 'r', encoding='utf-8') as f:
                presets = json.load(f)

            preset_data = presets.get(preset_name)
            if preset_data:
                self.itv_image_folder_entry.delete(0, 'end')
                self.itv_image_folder_entry.insert(0, preset_data.get("image_folder", ""))
                self.itv_output_folder_entry.delete(0, 'end')
                self.itv_output_folder_entry.insert(0, preset_data.get("output_folder", ""))
                self.itv_durations_entry.delete(0, 'end')
                self.itv_durations_entry.insert(0, preset_data.get("durations", ""))
                self.log_itv(f"ℹ️ 已加载预设 '{preset_name}'。")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.log_itv(f"❌ 加载预设失败: {e}")

    def start_img_to_video_processing(self):
        self.img_to_video_stop_event.clear()
        self.itv_start_button.configure(state="disabled")
        self.itv_stop_button.configure(state="normal")
        self.log_itv("", clear=True)
        threading.Thread(target=self.run_img_to_video_logic, daemon=True).start()

    def run_img_to_video_logic(self):
        try:
            # --- 新增：导入数学库用于动画计算 ---
            import math

            image_root_folder = self.itv_image_folder_entry.get()
            output_folder = self.itv_output_folder_entry.get()
            durations_str = self.itv_durations_entry.get()
            num_groups = self._safe_int_convert(self.itv_num_groups_entry.get(), 1)

            if not all([image_root_folder, output_folder, durations_str]):
                self.log_itv("❌ 错误: 图片文件夹、输出文件夹和时长都必须填写。")
                return

            # 解析时长规则 (逻辑不变)
            instructions = []
            try:
                parts = durations_str.strip().split('.')
                for part in parts:
                    if not part: continue
                    if '-' in part:
                        total_dur_str, num_images_str = part.split('-')
                        instructions.append((float(total_dur_str), int(num_images_str)))
                    else:
                        instructions.append((float(part), 1))
            except Exception as e:
                self.log_itv(f"❌ 错误: 时长格式无法解析。错误: {e}")
                return

            if not instructions: self.log_itv("❌ 错误: 未解析出任何有效指令。"); return
            if num_groups <= 0: self.log_itv("❌ 错误: 生成组数必须大于0。"); return

            ffmpeg_path = self._find_executable("ffmpeg")
            if not ffmpeg_path: self.log_itv("❌ 错误: 找不到 ffmpeg.exe，无法执行任务。"); return

            image_ext = ('.png', '.jpg', '.jpeg', '.webp')

            # 预检 (逻辑不变)
            self.log_itv("--- 任务预检开始 ---")
            all_checks_passed = True
            for i, (_, num_images) in enumerate(instructions):
                subfolder_name = str(i + 1)
                subfolder_path = os.path.join(image_root_folder, subfolder_name)
                if not os.path.isdir(subfolder_path):
                    self.log_itv(f"❌ 预检失败: 找不到子文件夹 '{subfolder_name}'。")
                    all_checks_passed = False;
                    break

                available_images = [f for f in os.listdir(subfolder_path) if f.lower().endswith(image_ext)]
                if len(available_images) < num_images * num_groups:
                    self.log_itv(f"❌ 预检失败: 子文件夹 '{subfolder_name}' 图片不足。")
                    self.log_itv(f"   需要 {num_images * num_groups} 张图片，但只有 {len(available_images)} 张。")
                    all_checks_passed = False;
                    break

            if not all_checks_passed:
                self.log_itv("--- 任务中止，请根据提示补充文件。 ---")
                return
            self.log_itv("✅ 预检通过，所有文件夹和图片数量充足。")

            # 外层循环，处理组 (逻辑不变)
            for i in range(num_groups):
                group_num = i + 1
                if self.img_to_video_stop_event.is_set(): self.log_itv("🔴 任务被用户中止。"); break
                self.log_itv(f"\n================== 开始生成第 {group_num}/{num_groups} 组视频 ==================")

                group_output_folder = os.path.join(output_folder, f"group-{group_num}")
                os.makedirs(group_output_folder, exist_ok=True)

                temp_dir = os.path.join(output_folder, f"temp_clips_group_{group_num}")
                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                os.makedirs(temp_dir)

                temp_clip_paths = []
                clip_counter = 0

                # --- 阶段一: 使用 MoviePy 生成带全新特效的临时片段 ---
                for idx, (total_duration, num_images) in enumerate(instructions):
                    if self.img_to_video_stop_event.is_set(): break
                    subfolder_name = str(idx + 1)
                    subfolder_path = os.path.join(image_root_folder, subfolder_name)
                    duration_per_image = total_duration / num_images

                    self.log_itv(
                        f"\n--- 处理指令 {idx + 1}: 从文件夹 '{subfolder_name}' 取 {num_images} 张图, 每张 {duration_per_image:.2f}s ---")

                    for _ in range(num_images):
                        if self.img_to_video_stop_event.is_set(): break
                        clip_counter += 1

                        available_images = [f for f in os.listdir(subfolder_path) if f.lower().endswith(image_ext)]
                        chosen_image_name = random.choice(available_images)
                        chosen_image_path = os.path.join(subfolder_path, chosen_image_name)
                        self.log_itv(f"  -> 随机选择图片: {chosen_image_name}")

                        temp_output_path = os.path.join(temp_dir, f"temp_{clip_counter:03d}.mp4")

                        final_clip_part = None
                        try:
                            self.log_itv(f"  -> 使用MoviePy生成平滑缩放动画...")

                            base_clip = ImageClip(chosen_image_path, duration=duration_per_image)

                            # --- 核心修改：全新的动画逻辑 ---

                            # 1. 预处理：计算缩放系数，让图片能铺满 1080x1920 的屏幕 (消除黑边)
                            img_w, img_h = base_clip.size
                            target_w, target_h = 1080, 1920
                            # 计算能覆盖目标的最小缩放比例
                            scale_factor = max(target_w / img_w, target_h / img_h)
                            fitted_clip = base_clip.resize(scale_factor)

                            # 2. 定义“先放大再缩小”的动画函数
                            # 我们使用 sin 函数来创造一个平滑的、从0到1再回到0的曲线
                            # t 是当前时间, duration_per_image 是片段总时长
                            def resize_func(t):
                                # 动画幅度，表示在中间点最大放大8%
                                amplitude = 0.08
                                # math.sin 在 0 到 pi 之间会画出一条完美的拱形曲线
                                zoom_factor = 1 + amplitude * math.sin(math.pi * t / duration_per_image)
                                return zoom_factor

                            # 3. 应用动画效果
                            animated_clip = fitted_clip.resize(resize_func)

                            # 4. 将动画剪辑放入最终画布中并居中
                            final_clip_part = CompositeVideoClip([animated_clip.set_position("center")],
                                                                 size=(1080, 1920))
                            final_clip_part.duration = duration_per_image
                            final_clip_part.fps = 30

                            # 写入临时文件
                            final_clip_part.write_videofile(temp_output_path, codec="libx264", preset='ultrafast',
                                                            threads=4, logger=None)

                            temp_clip_paths.append(temp_output_path)
                            os.remove(chosen_image_path)
                            self.log_itv(f"  -> ✅ 片段 {clip_counter} 编码成功，并已删除源图片。")

                        except Exception as e:
                            self.log_itv(f"  -> ❌ 错误: MoviePy编码片段失败: {e}")
                            traceback.print_exc()
                            continue
                        finally:
                            if 'base_clip' in locals() and base_clip: base_clip.close()
                            if 'final_clip_part' in locals() and final_clip_part: final_clip_part.close()
                            gc.collect()

                if self.img_to_video_stop_event.is_set():
                    shutil.rmtree(temp_dir);
                    continue

                # --- 阶段二: 高速拼接 (逻辑不变) ---
                self.log_itv("\n--- 所有片段处理完毕，开始高速拼接最终视频... ---")

                concat_list_path = os.path.join(temp_dir, "concat_list.txt")
                with open(concat_list_path, 'w', encoding='utf-8') as f:
                    for path in temp_clip_paths:
                        safe_path = os.path.normpath(path).replace('\\', '/')
                        f.write(f"file '{safe_path}'\n")

                preset_title = self.itv_preset_menu.get().replace(" ", "_")
                output_filename = f"{preset_title}_{int(time.time())}.mp4"
                final_output_path = os.path.join(group_output_folder, output_filename)

                concat_command_string = f'"{ffmpeg_path}" -y -f concat -safe 0 -i "{concat_list_path}" -c copy "{final_output_path}"'

                try:
                    subprocess.run(concat_command_string, shell=True, check=True, capture_output=True, text=True,
                                   encoding='utf-8', errors='ignore')
                    self.log_itv(f"✅ 第 {group_num} 组视频生成完毕！已保存至: {final_output_path}")
                except subprocess.CalledProcessError as e_concat:
                    self.log_itv(f"  -> ❌ 错误: FFmpeg拼接失败: {e_concat.stderr.strip()}")

                shutil.rmtree(temp_dir)

            if not self.img_to_video_stop_event.is_set():
                self.log_itv("\n🎉🎉🎉 所有组别任务处理完毕！ 🎉🎉🎉")

        except Exception as e:
            self.log_itv(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.itv_start_button.configure(state="normal")
            self.itv_stop_button.configure(state="disabled")
    # ==============================================================================
    # --- 【新增功能】健康类图文处理 ---
    # ==============================================================================
    def setup_health_image_workflow(self, parent_tab):
        """创建“健康类”图文功能的UI界面，复刻自图片处理，但移除了单一模式。"""
        tab = parent_tab
        # 路径设置
        self.create_folder_selection_row(tab, "图片文件夹 (内含子文件夹):", "选择包含多个图片子文件夹的根目录",
                                         "health_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择图片处理结果的存放位置",
                                         "health_output_folder_entry")

        # 文案输入
        ctk.CTkLabel(tab, text="输入文案 (每行对应一个子文件夹):").pack(anchor="w", padx=10, pady=(10, 0))
        self.health_text_input_box = ctk.CTkTextbox(tab, height=150)
        self.health_text_input_box.pack(fill="x", expand=True, padx=10, pady=(5, 10))

        # 组数与手机序号
        group_frame = ctk.CTkFrame(tab, fg_color="transparent")
        group_frame.pack(fill="x", padx=10, pady=5)
        self.create_widget_row(group_frame, "生成组数:", "health_num_groups", "1").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(group_frame, "手机序号(用.分隔):", "health_phone_serial", "",
                               placeholder="例如: A-1.A-2.B-1").pack(fill="x", padx=10, pady=2)

        self.health_num_groups_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.health_num_groups_entry, self.health_phone_serial_entry))
        self.health_phone_serial_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.health_phone_serial_entry, self.health_num_groups_entry))

        # 按钮
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.start_health_button = ctk.CTkButton(button_frame, text="开始处理健康类图片", height=40,
                                                 command=self.start_health_image_processing)
        self.start_health_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.stop_health_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                command=self.stop_health_image_processing, state="disabled",
                                                fg_color="red", hover_color="darkred")
        self.stop_health_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # 日志
        self.health_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.health_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def log_health(self, message, clear=False):
        self.after(0, self._update_log, self.health_log_textbox, message, clear)

    def start_health_image_processing(self):
        self.image_stop_event.clear()  # 复用同一个停止事件
        self.start_health_button.configure(state="disabled")
        self.stop_health_button.configure(state="normal")
        self.log_health("", clear=True)
        threading.Thread(target=self.run_health_image_logic, daemon=True).start()

    def stop_health_image_processing(self):
        self.log_health("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.image_stop_event.set()
        self.stop_health_button.configure(state="disabled")

    def _reset_health_buttons(self):
        self.start_health_button.configure(state="normal")
        self.stop_health_button.configure(state="disabled")

    def run_health_image_logic(self):
        try:
            # 1. 获取所有UI输入
            image_folder = self.health_folder_entry.get()
            output_folder = self.health_output_folder_entry.get()
            all_input_text = self.health_text_input_box.get("1.0", "end-1c")
            config = self.get_image_config_from_gui()  # 复用原有的图片参数配置
            captions = [line.strip() for line in all_input_text.splitlines() if line.strip()]

            # 2. 基础校验
            if not all([image_folder, output_folder, config, captions]):
                self.log_health("错误: 请确保已选择图片文件夹、输出文件夹、完成参数配置并且文案不为空。")
                return

            # 3. 校验输入结构：子文件夹数量必须与文案行数匹配
            self.log_health("正在扫描输入文件夹的结构...")
            subfolders = sorted([d for d in os.listdir(image_folder) if os.path.isdir(os.path.join(image_folder, d))])

            if len(subfolders) != len(captions):
                self.log_health(f"❌ 错误: 文件夹数量与文案行数不匹配！")
                self.log_health(f"   - 检测到 {len(subfolders)} 个子文件夹: {subfolders}")
                self.log_health(f"   - 输入了 {len(captions)} 行文案。")
                self.log_health(f"   - 请确保两者数量完全一致。")
                return

            self.log_health(
                f"✅ 文件夹与文案数量校验通过: {len(subfolders)} 个子文件夹将与 {len(captions)} 行文案一一对应。")

            # 4. 确定生成组数
            num_groups_str = self.health_num_groups_entry.get().strip()
            phone_serials_str = self.health_phone_serial_entry.get().strip()
            group_names, num_groups = [], 0

            if phone_serials_str:
                group_names = [name.strip() for name in phone_serials_str.split('.') if name.strip()]
                if not group_names: self.log_health("错误: 手机序号输入无效。"); return
                num_groups = len(group_names)
            elif num_groups_str:
                try:
                    num_groups = int(num_groups_str)
                    if num_groups <= 0: raise ValueError
                    group_names = [f"group_{i + 1}" for i in range(num_groups)]
                except (ValueError, TypeError):
                    self.log_health("错误: '生成组数' 必须是一个有效的正整数。"); return
            else:
                self.log_health("错误: '生成组数' 或 '手机序号' 必须填写一个。"); return

            # 5. 【核心校验】检查每个子文件夹内的图片数量是否满足组数需求
            self.log_health(f"▶️ 正在校验每个子文件夹内的图片数量是否满足 {num_groups} 组的需求...")
            validation_passed = True
            image_ext = ('.png', '.jpg', '.jpeg', '.webp')

            for subfolder_name in subfolders:
                subfolder_path = os.path.join(image_folder, subfolder_name)
                try:
                    images_in_subfolder = [f for f in os.listdir(subfolder_path) if f.lower().endswith(image_ext)]
                    image_count = len(images_in_subfolder)

                    if image_count < num_groups:
                        self.log_health(f"❌ 校验失败: 子文件夹 '{subfolder_name}' 图片数量不足。")
                        self.log_health(f"   - 需要: {num_groups} 张图片 (以满足 {num_groups} 组的需求)")
                        self.log_health(f"   - 实际: 只有 {image_count} 张图片。")
                        validation_passed = False
                except FileNotFoundError:
                    self.log_health(f"❌ 校验失败: 找不到名为 '{subfolder_name}' 的子文件夹。")
                    validation_passed = False

            if not validation_passed:
                self.log_health("▶️ 请补充图片或减少“生成组数/手机序号”后重试。任务已中止。")
                return

            self.log_health("✅ 图片数量校验通过，所有子文件夹均满足要求。")

            # 6. 准备输出文件夹和开始处理
            if os.path.exists(output_folder): shutil.rmtree(output_folder)
            os.makedirs(output_folder)

            self.log_health(f"▶️ 准备就绪: 将生成 {num_groups} 大组。")
            self.log_health("⚠️ 警告: 处理成功后，用过的原始图片将被删除！")

            total_processed_count = 0

            # 7. 主处理循环
            for group_name in group_names:
                if self.image_stop_event.is_set(): self.log_health("🔴 任务已中止."); break

                group_output_folder = os.path.join(output_folder, group_name)
                os.makedirs(group_output_folder, exist_ok=True)
                self.log_health(f"\n---=== 开始处理组: {group_name} ===---")

                # 按顺序遍历文案和子文件夹进行一一对应处理
                for idx, caption in enumerate(captions):
                    if self.image_stop_event.is_set(): break

                    subfolder_name = subfolders[idx]
                    subfolder_path = os.path.join(image_folder, subfolder_name)

                    # 从对应的子文件夹中随机选择一张图片
                    available_images = [f for f in os.listdir(subfolder_path) if f.lower().endswith(image_ext)]
                    if not available_images:
                        self.log_health(
                            f"  -> 警告: 子文件夹 '{subfolder_name}' 已无可用图片，跳过文案 '{caption[:20]}...'")
                        continue

                    chosen_image_name = random.choice(available_images)
                    source_path = os.path.join(subfolder_path, chosen_image_name)

                    output_filename = f"{subfolder_name}_{idx + 1}.png"
                    output_path = os.path.join(group_output_folder, output_filename)
                    pos_config = random.choice(config.get("text_positions", [[0.5, 0.5]]))

                    self.log_health(f"  - (文案: {caption[:10]}...) -> (图片: {subfolder_name}/{chosen_image_name})")

                    result = image_apply_text(source_path, caption, config, pos_config, output_path, self.log_health,
                                              self.image_stop_event)

                    if result == 'STOPPED':
                        break
                    elif result is True:
                        try:
                            os.remove(source_path)
                            self.log_health(f"    ✅ 合成成功，已删除源图片: {chosen_image_name}");
                            total_processed_count += 1
                        except OSError as e:
                            self.log_health(f"    ❌ 删除源图片失败: {chosen_image_name} - {e}")

                if self.image_stop_event.is_set(): break

            if not self.image_stop_event.is_set():
                self.log_health(f"\n---=== 处理完毕！总共处理并删除 {total_processed_count} 张图片 ===---")

        except Exception as e:
            self.log_health(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_health_buttons)
    # ==============================================================================
    # --- 【新增功能】图片分发 ---
    # ==============================================================================
    def setup_image_distribution_workflow(self, parent_tab):
        """创建“图片分发”功能的UI界面"""
        tab = parent_tab
        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # --- 1. 路径设置 ---
        self.create_folder_selection_row(main_frame, "图片文件夹:", "选择包含待分发图片的文件夹",
                                         "dist_image_folder_entry")
        self.create_folder_selection_row(main_frame, "输出文件夹:", "选择分发后图片的存放位置",
                                         "dist_output_folder_entry")

        # --- 2. 手机序号设置 ---
        self.create_widget_row(main_frame, "手机序号:", "dist_phone_serial", "",
                               placeholder="例如: A-1.A-2.B-1 (用.分隔)").pack(fill="x", padx=10, pady=(15, 5))

        # --- 3. 开始处理与日志 ---
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(20, 10))
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.dist_start_button = ctk.CTkButton(button_frame, text="开始分发图片", height=40,
                                               command=self.start_distribution_processing)
        self.dist_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.dist_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                              command=self.stop_distribution_processing, state="disabled",
                                              fg_color="red", hover_color="darkred")
        self.dist_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.dist_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.dist_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def log_distribution(self, message, clear=False):
        """向图片分发模块日志框记录信息"""
        self.after(0, self._update_log, self.dist_log_textbox, message, clear)

    def start_distribution_processing(self):
        """启动图片分发处理的线程"""
        self.distribution_stop_event.clear()
        self.dist_start_button.configure(state="disabled")
        self.dist_stop_button.configure(state="normal")
        self.log_distribution("开始处理...", clear=True)
        threading.Thread(target=self.run_distribution_logic, daemon=True).start()

    def stop_distribution_processing(self):
        """发送停止信号"""
        self.log_distribution("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.distribution_stop_event.set()
        self.dist_stop_button.configure(state="disabled")

    def _reset_distribution_buttons(self):
        """重置按钮状态"""
        self.dist_start_button.configure(state="normal")
        self.dist_stop_button.configure(state="disabled")

    def run_distribution_logic(self):
        """图片分发功能的主逻辑"""
        try:
            image_folder = self.dist_image_folder_entry.get()
            output_folder = self.dist_output_folder_entry.get()
            serials_str = self.dist_phone_serial_entry.get()

            if not all([image_folder, output_folder, serials_str]):
                self.log_distribution("❌ 错误: 图片文件夹、输出文件夹和手机序号都必须填写。")
                return

            serial_list = [s.strip() for s in serials_str.split('.') if s.strip()]
            if not serial_list:
                self.log_distribution("❌ 错误: 手机序号输入无效。")
                return

            num_serials = len(serial_list)
            self.log_distribution(f"▶️ 手机序号解析成功，需要分发 {num_serials} 张图片。")

            image_ext = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
            available_images = [f for f in os.listdir(image_folder) if f.lower().endswith(image_ext)]

            if len(available_images) < num_serials:
                self.log_distribution(
                    f"❌ 错误: 图片数量不足！需要 {num_serials} 张，但文件夹中只有 {len(available_images)} 张。")
                return

            self.log_distribution(f"🔍 扫描到 {len(available_images)} 张可用图片，准备开始分发...")
            self.log_distribution("⚠️ 警告：分发成功后，原始图片将被删除！")

            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
            os.makedirs(output_folder)

            # 随机化图片列表以确保每次抽取的都不同
            random.shuffle(available_images)
            images_to_distribute = available_images[:num_serials]

            for i, serial_name in enumerate(serial_list):
                if self.distribution_stop_event.is_set():
                    self.log_distribution("🔴 任务已中止。")
                    break

                image_name = images_to_distribute[i]
                source_path = os.path.join(image_folder, image_name)

                # 创建以手机序号命名的子文件夹
                dest_folder = os.path.join(output_folder, serial_name)
                os.makedirs(dest_folder, exist_ok=True)

                dest_path = os.path.join(dest_folder, image_name)

                self.log_distribution(f"  -> 正在分发 '{image_name}' 到文件夹 '{serial_name}'...")

                try:
                    # 复制文件
                    shutil.copy2(source_path, dest_path)
                    # 复制成功后，删除原文件
                    os.remove(source_path)
                    self.log_distribution(f"  ✅ 分发并删除原图成功。")
                except Exception as e:
                    self.log_distribution(f"  ❌ 处理文件 '{image_name}' 时出错: {e}")
                    # 如果出错，跳过这个文件的处理
                    continue

            if not self.distribution_stop_event.is_set():
                self.log_distribution(f"\n🎉 所有任务处理完毕！共 {num_serials} 张图片被成功分发。")

        except Exception as e:
            self.log_distribution(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_distribution_buttons)
    # ==============================================================================
    # --- NEWS 总菜单 (新) ---
    # ==============================================================================
    def setup_news_workflow(self):
        """创建“NEWS”主标签页，并在其中嵌入子标签页"""
        # 获取我们刚刚在 setup_main_ui 中创建的 "NEWS" 主标签页
        news_main_tab = self.main_tabview.tab("NEWS")

        # 在这个主标签页内部，创建一个新的、用于子菜单的CTkTabview
        news_sub_tabview = ctk.CTkTabview(news_main_tab)
        news_sub_tabview.pack(expand=True, fill="both", padx=5, pady=5)

        # 添加子标签页
        news_sub_tabview.add("NEWS绿幕")
        news_sub_tabview.add("NEWS虚化")
        news_sub_tabview.add("搬运")

        # 现在，我们将原有的setup函数的目标从主标签页改为新的子标签页
        # 注意，我们传递了子标签页的引用作为参数
        self.setup_news_greenscreen_workflow(news_sub_tabview.tab("NEWS绿幕"))
        self.setup_news_blur_workflow(news_sub_tabview.tab("NEWS虚化"))
        self.setup_porter_workflow(news_sub_tabview.tab("搬运"))
    # ==============================================================================
    # --- 【新增功能】搬运 ---
    # ==============================================================================
    def setup_porter_workflow(self, parent_tab):
        """创建“搬运”功能的UI界面 (修正了布局调用)"""
        tab = parent_tab
        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        path_frame = ctk.CTkFrame(main_frame)
        path_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(path_frame, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                           pady=(5, 10))
        self.create_folder_selection_row(path_frame, "A文件夹 (底片):", "选择作为底片的视频文件夹",
                                         "porter_dir_a_entry")
        self.create_folder_selection_row(path_frame, "B文件夹 (素材):", "选择作为随机素材的视频文件夹",
                                         "porter_dir_b_entry")
        self.create_folder_selection_row(path_frame, "输出文件夹:", "选择处理后视频的存放位置",
                                         "porter_output_dir_entry")

        params_frame = ctk.CTkFrame(main_frame)
        params_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(params_frame, text="2. 效果参数配置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                                 pady=(5, 0))

        grid_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=10, pady=5)
        grid_frame.grid_columnconfigure((0, 1), weight=1)  # 左右两列等宽

        # --- 核心修复：调用 create_widget_row 后，再对其返回的框架使用 .grid() ---
        self.create_widget_row(grid_frame, "预处理-裁剪前N秒:", "porter_preprocess_trim", "0",
                               placeholder="0为关闭").grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.create_widget_row(grid_frame, "A视频内容缩放:", "porter_zoom", "1.5").grid(row=1, column=0, sticky="ew",
                                                                                        padx=(0, 10))
        self.create_widget_row(grid_frame, "拉伸条高度 (%):", "porter_stretch_h", "1").grid(row=2, column=0,
                                                                                            sticky="ew", padx=(0, 10))
        self.create_widget_row(grid_frame, "拉伸条透明度 (%):", "porter_stretch_o", "50").grid(row=3, column=0,
                                                                                               sticky="ew",
                                                                                               padx=(0, 10))

        self.create_widget_row(grid_frame, "旋转层透明度 (%):", "porter_rotate_o", "20").grid(row=0, column=1,
                                                                                              sticky="ew", padx=(10, 0))
        self.create_widget_row(grid_frame, "旋转层速度 (1-100):", "porter_rotate_s", "20").grid(row=1, column=1,
                                                                                                sticky="ew",
                                                                                                padx=(10, 0))
        self.create_widget_row(grid_frame, "旋转层音频音量 (%):", "porter_rotate_a_vol", "50").grid(row=2, column=1,
                                                                                                    sticky="ew",
                                                                                                    padx=(10, 0))
        self.create_widget_row(grid_frame, "最终对比度:", "porter_contrast", "1.1").grid(row=3, column=1, sticky="ew",
                                                                                         padx=(10, 0))
        self.create_widget_row(grid_frame, "最终亮度:", "porter_brightness", "0.03").grid(row=4, column=0, sticky="ew",
                                                                                          padx=(0, 10))
        self.create_widget_row(grid_frame, "最终饱和度:", "porter_saturation", "1.2").grid(row=4, column=1, sticky="ew",
                                                                                           padx=(10, 0))

        # --- 新增GPU开关 ---
        self.porter_use_gpu_switch = ctk.CTkSwitch(grid_frame, text="启用GPU加速编码 (NVIDIA)")
        self.porter_use_gpu_switch.grid(row=5, column=0, columnspan=2, pady=(10, 0), sticky="w")
        # --- 新增结束 ---

        run_frame = ctk.CTkFrame(main_frame)
        run_frame.pack(fill="x", padx=10, pady=(10, 5))
        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.porter_start_button = ctk.CTkButton(button_frame, text="开始批量处理", height=40,
                                                 command=self.start_porter_processing)
        self.porter_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.porter_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                command=self.stop_porter_processing, state="disabled", fg_color="red",
                                                hover_color="darkred")
        self.porter_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.porter_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.porter_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def log_porter(self, message, clear=False):
        self.after(0, self._update_log, self.porter_log_textbox, message, clear)

    def start_porter_processing(self):
        self.porter_stop_event.clear()
        self.porter_start_button.configure(state="disabled")
        self.porter_stop_button.configure(state="normal")
        self.log_porter("开始处理...", clear=True)
        threading.Thread(target=self.run_porter_logic, daemon=True).start()

    def stop_porter_processing(self):
        self.log_porter("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.porter_stop_event.set()
        self.porter_stop_button.configure(state="disabled")

    def _reset_porter_buttons(self):
        self.porter_start_button.configure(state="normal")
        self.porter_stop_button.configure(state="disabled")

    def _porter_worker(self, base_video_path, material_path_1, material_path_2, output_path, params, use_gpu):
        """应用新的时长控制逻辑和智能音频混合，确保输出时长精确匹配并能处理无音频的视频"""
        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            self.log_porter("  ❌ 错误: 找不到 ffmpeg 或 ffprobe。");
            return False

        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW

        # --- 智能音频检查辅助函数 ---
        def has_audio(video_path):
            try:
                cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                             "-of", "default=noprint_wrappers=1:nokey=1", os.path.normpath(video_path)]
                result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True,
                                        creationflags=creation_flags)
                return bool(result.stdout.strip())
            except subprocess.CalledProcessError:
                return False

        try:
            # 获取视频尺寸和时长
            safe_ffprobe = f'"{os.path.normpath(ffprobe_path)}"'
            cmd_duration_a = f'{safe_ffprobe} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{os.path.normpath(base_video_path)}"'
            cmd_dims_a = f'{safe_ffprobe} -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "{os.path.normpath(base_video_path)}"'
            duration_a = float(subprocess.run(cmd_duration_a, shell=True, check=True, capture_output=True, text=True,
                                              creationflags=creation_flags).stdout.strip())
            res_str = subprocess.run(cmd_dims_a, shell=True, check=True, capture_output=True, text=True,
                                     creationflags=creation_flags).stdout.strip()
            width_a, height_a = map(int, res_str.split('x'))

            # 时长控制逻辑
            trim_duration = params.get('p_trim', 0)
            final_duration = min(duration_a, trim_duration) if trim_duration > 0 else duration_a
            if final_duration <= 0:
                self.log_porter("  ❌ 错误: 最终计算时长为0或负数，无法处理。");
                return False
            self.log_porter(f"  -> 将使用视频前 {final_duration:.2f} 秒进行合成。")

            # 构建FFmpeg命令
            safe_ffmpeg = f'"{os.path.normpath(ffmpeg_path)}"'
            safe_base_path = f'"{os.path.normpath(base_video_path)}"'
            safe_mat1_path = f'"{os.path.normpath(material_path_1)}"'
            safe_mat2_path = f'"{os.path.normpath(material_path_2)}"'
            safe_output_path = f'"{os.path.normpath(output_path)}"'

            inputs = f"-i {safe_base_path} -stream_loop -1 -i {safe_mat1_path} -stream_loop -1 -i {safe_mat2_path}"

            # 视频滤镜链 (保持不变)
            stretch_bar_height = max(1, int(height_a * params['p_stretch_h']))
            video_filter = (
                f"[0:v]scale=iw*{params['p_zoom']}:ih*{params['p_zoom']},crop=iw/{params['p_zoom']}:ih/{params['p_zoom']}[base_zoomed];"
                f"[1:v]scale={width_a}:{stretch_bar_height}[material_stretched];"
                f"[material_stretched]format=rgba,colorchannelmixer=aa={params['p_stretch_o']}[material_final];"
                f"[base_zoomed][material_final]overlay=(W-w)/2:(H-h)/2[composite];"
                f"[composite]eq=contrast={params['p_contrast']}:brightness={params['p_brightness']}:saturation={params['p_saturation']}[main_composite];"
                f"[2:v]scale={width_a}:{height_a}[b_scaled];"
                f"[b_scaled]rotate='t*{params['p_rotate_s']}':c=none:fillcolor=none[b_rotating];"
                f"[b_rotating]format=rgba,colorchannelmixer=aa={params['p_rotate_o']}[b_rotating_final];"
                f"[main_composite][b_rotating_final]overlay=(W-w)/2:(H-h)/2[v_out]"
            )

            # --- 智能音频处理 ---
            has_audio_base = has_audio(base_video_path)
            has_audio_rot = has_audio(material_path_2)
            audio_filter_part = ""
            map_args = ""
            audio_codec_args = ""

            if has_audio_base and has_audio_rot:
                self.log_porter("  -> 检测到双音频流，将进行混合处理。")
                audio_filter_part = f";[2:a]volume={params['p_rotate_a_vol']}[a_rot_vol];[0:a][a_rot_vol]amix=inputs=2:duration=first[a_out]"
                map_args = '-map "[v_out]" -map "[a_out]"'
                audio_codec_args = "-c:a aac -b:a 192k"
            elif has_audio_base:
                self.log_porter("  -> 仅检测到底片视频有音频，将保留该音频。")
                map_args = '-map "[v_out]" -map 0:a'
                audio_codec_args = "-c:a copy"
            elif has_audio_rot:
                self.log_porter("  -> 仅检测到旋转层视频有音频，将调整音量后使用。")
                audio_filter_part = f";[2:a]volume={params['p_rotate_a_vol']}[a_out]"
                map_args = '-map "[v_out]" -map "[a_out]"'
                audio_codec_args = "-c:a aac -b:a 192k"
            else:
                self.log_porter("  -> 未检测到音频流，将输出静音视频。")
                map_args = '-map "[v_out]"'
                audio_codec_args = "-an"

            filter_complex = f"{video_filter}{audio_filter_part}"

            def build_command(is_gpu):
                video_codec = "-c:v h264_nvenc -preset fast -cq 23" if is_gpu else "-c:v libx264 -preset medium -crf 23"
                return (f'{safe_ffmpeg} -y {inputs} -filter_complex "{filter_complex}" {map_args} '
                        f'-t {final_duration} {video_codec} {audio_codec_args} {safe_output_path}')

            try:
                if use_gpu:
                    self.log_porter("  -> 正在尝试使用GPU编码...")
                    command_string = build_command(is_gpu=True)
                    subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True,
                                   encoding='utf-8', errors='ignore', creationflags=creation_flags)
                else:
                    raise ValueError("Skipping to CPU")
            except (subprocess.CalledProcessError, ValueError):
                if use_gpu:
                    self.log_porter("  -> 警告: GPU编码失败，自动回退到CPU编码...")
                else:
                    self.log_porter("  -> 正在使用CPU编码...")
                command_string = build_command(is_gpu=False)
                subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8',
                               errors='ignore', creationflags=creation_flags)
            return True
        except Exception as e:
            self.log_porter(f"  ❌ FFmpeg处理失败: {e}")
            if hasattr(e, 'stderr'): self.log_porter(f"  -> {e.stderr}")
            return False
    def run_porter_logic(self):
        try:
            dir_a, dir_b, output_dir = self.porter_dir_a_entry.get(), self.porter_dir_b_entry.get(), self.porter_output_dir_entry.get()
            if not all([os.path.isdir(dir_a), os.path.isdir(dir_b)]):
                self.log_porter("错误: 请确保A文件夹和B文件夹的路径正确且存在！");
                return
            os.makedirs(output_dir, exist_ok=True)

            params = {
                'p_zoom': self._safe_float_convert(self.porter_zoom_entry.get(), 1.5),
                'p_stretch_h': self._safe_float_convert(self.porter_stretch_h_entry.get(), 1.0) / 100.0,
                'p_stretch_o': self._safe_float_convert(self.porter_stretch_o_entry.get(), 50.0) / 100.0,
                'p_rotate_o': self._safe_float_convert(self.porter_rotate_o_entry.get(), 20.0) / 100.0,
                'p_rotate_s': self._safe_float_convert(self.porter_rotate_s_entry.get(), 20.0),
                'p_rotate_a_vol': self._safe_float_convert(self.porter_rotate_a_vol_entry.get(), 50.0) / 100.0,
                'p_contrast': self._safe_float_convert(self.porter_contrast_entry.get(), 1.1),
                'p_brightness': self._safe_float_convert(self.porter_brightness_entry.get(), 0.03),
                'p_saturation': self._safe_float_convert(self.porter_saturation_entry.get(), 1.2),
                # 读取裁剪秒数
                'p_trim': self._safe_float_convert(self.porter_preprocess_trim_entry.get(), 0.0)
            }

            use_gpu = self.porter_use_gpu_switch.get() == 1 and self.is_gpu_available
            self.log_porter(f"--- [模式] 将使用 {'GPU' if use_gpu else 'CPU'} 进行编码 ---")

            VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv']
            videos_a = [os.path.join(dir_a, f) for f in os.listdir(dir_a) if
                        os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
            videos_b = [os.path.join(dir_b, f) for f in os.listdir(dir_b) if
                        os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
            if not videos_a or not videos_b:
                self.log_porter("错误: A或B文件夹中没有找到任何视频文件！");
                return

            for i, base_video_path in enumerate(videos_a):
                if self.porter_stop_event.is_set(): self.log_porter("🔴 任务已中止。"); break

                material_path_1 = random.choice(videos_b)
                material_path_2 = random.choice(videos_b)

                output_filename = f"processed_{os.path.basename(base_video_path)}"
                output_path = os.path.join(output_dir, output_filename)

                self.log_porter(
                    f"\n--- [任务 {i + 1}/{len(videos_a)}] 正在处理: {os.path.basename(base_video_path)} ---")

                if self._porter_worker(base_video_path, material_path_1, material_path_2, output_path, params, use_gpu):
                    self.log_porter("  ✅ 处理成功。")
                else:
                    self.log_porter("  ❌ 处理失败。")

            if not self.porter_stop_event.is_set():
                self.log_porter("\n🎉 所有任务处理完毕！")

        except Exception as e:
            self.log_porter(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_porter_buttons)

    # ==============================================================================
    # --- ios批量传输 功能 (最终健壮版) ---
    # ==============================================================================
    def setup_ios_transfer_workflow(self):
        """创建“ios批量传输”功能的UI界面"""
        tab = self.main_tabview.tab("ios批量传输")
        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        main_frame.grid_columnconfigure(0, weight=1);
        main_frame.grid_columnconfigure(1, weight=1);
        main_frame.grid_rowconfigure(1, weight=1)
        folder_frame = ctk.CTkFrame(main_frame);
        folder_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5, padx=5)
        ctk.CTkLabel(folder_frame, text="第一步: 选择来源文件夹", font=ctk.CTkFont(weight="bold")).pack(anchor="w",
                                                                                                        padx=10,
                                                                                                        pady=(5,
                                                                                                              10))
        self.create_folder_selection_row(folder_frame, "来源文件夹:", "选择包含以设备名命名的子文件夹的目录",
                                         "ios_source_folder_entry")
        discover_frame = ctk.CTkFrame(main_frame);
        discover_frame.grid(row=1, column=0, sticky="nsew", pady=5, padx=(5, 2));
        discover_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(discover_frame, text="第二步: 搜索iOS设备", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        discover_button_frame = ctk.CTkFrame(discover_frame, fg_color="transparent");
        discover_button_frame.pack(fill="x", padx=20, pady=5);
        discover_button_frame.grid_columnconfigure((0, 1), weight=1)
        self.ios_discover_btn = ctk.CTkButton(discover_button_frame, text=f"开始搜索 ({DISCOVERY_DURATION}秒)",
                                              command=self.start_ios_discovery);
        self.ios_discover_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.ios_cancel_discover_btn = ctk.CTkButton(discover_button_frame, text="取消搜索",
                                                     command=self.stop_ios_discovery, state="disabled",
                                                     fg_color="orange", hover_color="#E07A00");
        self.ios_cancel_discover_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.ios_device_frame = ctk.CTkScrollableFrame(discover_frame, label_text="发现的设备");
        self.ios_device_frame.pack(fill="both", expand=True, pady=10, padx=10)
        transfer_frame = ctk.CTkFrame(main_frame);
        transfer_frame.grid(row=1, column=1, sticky="nsew", pady=5, padx=(2, 5))
        ctk.CTkLabel(transfer_frame, text="第三步: 开始传输", font=ctk.CTkFont(weight="bold")).pack(pady=10)
        self.ios_transfer_btn = ctk.CTkButton(transfer_frame, text="启动批量传输", height=50,
                                              command=self.start_ios_batch_transfer);
        self.ios_transfer_btn.pack(pady=50, padx=20, fill="x")
        log_frame = ctk.CTkFrame(main_frame);
        log_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5, padx=5);
        log_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_frame, text="实时日志", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.ios_log_textbox = ctk.CTkTextbox(log_frame, wrap="word", height=150, state="disabled",
                                              text_color="#A9A9A9");
        self.ios_log_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        self.discovered_devices = {}

    def log_ios_transfer(self, message, clear=False):
        """线程安全地向日志框添加消息"""
        self.after(0, self._update_log, self.ios_log_textbox, message, clear)

    def start_ios_discovery(self):
        """启动设备发现线程，并管理按钮状态"""
        self.ios_discovery_stop_event.clear()
        self.ios_discover_btn.configure(state="disabled")
        self.ios_cancel_discover_btn.configure(state="normal")
        for widget in self.ios_device_frame.winfo_children():
            widget.destroy()
        self.discovered_devices = {}
        self.log_ios_transfer("--- 开始搜索网络中的iOS设备... ---", clear=True)
        discovery_thread = threading.Thread(target=self._ios_discover_devices_thread, daemon=True)
        discovery_thread.start()
        self.after(100, self._ios_update_ui_from_queue)

    # ==============================================================================
    # --- 【新增功能】AI女巫 (大头照) ---
    # ==============================================================================
    def setup_avatar_workflow(self, parent_tab):
        """创建“AI女巫”功能的UI界面"""
        tab = parent_tab
        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        ctk.CTkLabel(main_frame, text="功能说明：自动识别人脸，并将头部区域放大为特写，制作大头照风格视频。",
                     wraplength=800, justify="left").pack(anchor="w", padx=10, pady=(5, 10))

        path_frame = ctk.CTkFrame(main_frame)
        path_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(path_frame, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                           pady=(5, 10))
        self.create_folder_selection_row(path_frame, "视频文件夹:", "选择包含人物视频的文件夹 (可含子文件夹)",
                                         "avatar_input_folder_entry")
        self.create_folder_selection_row(path_frame, "输出文件夹:", "选择处理后视频的存放位置",
                                         "avatar_output_folder_entry")

        params_frame = ctk.CTkFrame(main_frame)
        params_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(params_frame, text="2. 效果配置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                             pady=(5, 0))

        effects_frame = ctk.CTkFrame(params_frame, fg_color="transparent")
        effects_frame.pack(fill="x", padx=10, pady=5)
        effects_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(effects_frame, text="画面缩放系数:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.avatar_zoom_entry = ctk.CTkEntry(effects_frame, placeholder_text="数值越小,脸越大")
        self.avatar_zoom_entry.insert(0, "2.0")
        self.avatar_zoom_entry.grid(row=0, column=1, sticky="ew")

        ctk.CTkLabel(effects_frame, text="对比度:").grid(row=0, column=2, sticky="w", padx=(20, 10))
        self.avatar_contrast_entry = ctk.CTkEntry(effects_frame)
        self.avatar_contrast_entry.insert(0, "1.0")
        self.avatar_contrast_entry.grid(row=0, column=3, sticky="ew")

        ctk.CTkLabel(effects_frame, text="亮度:").grid(row=1, column=0, sticky="w", pady=(10, 0), padx=(0, 10))
        self.avatar_brightness_entry = ctk.CTkEntry(effects_frame)
        self.avatar_brightness_entry.insert(0, "0.0")
        self.avatar_brightness_entry.grid(row=1, column=1, sticky="ew", pady=(10, 0))

        ctk.CTkLabel(effects_frame, text="饱和度:").grid(row=1, column=2, sticky="w", pady=(10, 0), padx=(20, 10))
        self.avatar_saturation_entry = ctk.CTkEntry(effects_frame)
        self.avatar_saturation_entry.insert(0, "1.0")
        self.avatar_saturation_entry.grid(row=1, column=3, sticky="ew", pady=(10, 0))

        self.avatar_mirror_switch = ctk.CTkSwitch(effects_frame, text="启用画面镜像 (水平翻转)")
        self.avatar_mirror_switch.grid(row=2, column=0, columnspan=2, pady=(15, 0), sticky="w")

        # --- 核心修改：增加GPU加速开关 ---
        self.avatar_use_gpu_switch = ctk.CTkSwitch(effects_frame, text="启用GPU加速编码 (NVIDIA)")
        self.avatar_use_gpu_switch.grid(row=2, column=2, columnspan=2, pady=(15, 0), sticky="w")

        # --- 修改结束 ---

        run_frame = ctk.CTkFrame(main_frame)
        run_frame.pack(fill="x", padx=10, pady=(10, 5))
        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.avatar_start_button = ctk.CTkButton(button_frame, text="开始批量生成大头照", height=40,
                                                 command=self.start_avatar_processing)
        self.avatar_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.avatar_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                command=self.stop_avatar_processing, state="disabled",
                                                fg_color="red", hover_color="darkred")
        self.avatar_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.avatar_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.avatar_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def log_avatar(self, message, clear=False):
        self.after(0, self._update_log, self.avatar_log_textbox, message, clear)

    def start_avatar_processing(self):
        self.avatar_stop_event.clear()
        self.avatar_start_button.configure(state="disabled")
        self.avatar_stop_button.configure(state="normal")
        self.log_avatar("开始处理...", clear=True)
        threading.Thread(target=self.run_avatar_logic, daemon=True).start()

    def stop_avatar_processing(self):
        self.log_avatar("🔴 发送立即中止信号...")
        self.avatar_stop_event.set()  # 仍然设置事件，以停止Python端的循环

        # 检查是否存在正在运行的FFmpeg进程
        if self.active_ffmpeg_process:
            try:
                self.log_avatar("  -> 正在强制终止FFmpeg子进程...")
                self.active_ffmpeg_process.kill()  # kill()会立即终止进程
                self.log_avatar("  -> FFmpeg进程已终止。")
            except Exception as e:
                self.log_avatar(f"  -> 终止进程时出错: {e}")

        self.avatar_stop_button.configure(state="disabled")

    def _reset_avatar_buttons(self):
        self.avatar_start_button.configure(state="normal")
        self.avatar_stop_button.configure(state="disabled")

    def _avatar_worker(self, input_path, output_path, zoom, mirror, contrast, brightness, saturation, use_gpu):
        """【最终修正版】使用OpenCV识别人脸，并用FFmpeg管道进行处理 (增加GPU编码选项)"""
        cap = None
        proc = None
        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                self.log_avatar(f"警告：无法打开 '{os.path.basename(input_path)}'")
                return False

            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            aspect_ratio = frame_width / frame_height
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps == 0: fps = 25

            ret, first_frame = cap.read()
            if not ret:
                self.log_avatar(f"警告：无法读取 '{os.path.basename(input_path)}' 的第一帧")
                return False

            gray_frame = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
            if self.face_cascade:
                faces = self.face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=7,
                                                           minSize=(50, 50))
            else:
                faces = []

            if len(faces) == 0:
                self.log_avatar(f"警告：在 '{os.path.basename(input_path)}' 第一帧未检测到人脸，跳过此视频。")
                return False

            fx, fy, fw, fh = faces[0]
            face_center_x, face_center_y = fx + fw // 2, fy + fh // 2
            crop_h = int(fh * zoom)
            crop_w = int(crop_h * aspect_ratio)
            crop_w, crop_h = min(crop_w, frame_width), min(crop_h, frame_height)
            x1 = max(0, face_center_x - crop_w // 2)
            y1 = max(0, face_center_y - crop_h // 2)
            x2, y2 = x1 + crop_w, y1 + crop_h
            if x2 > frame_width: x1 -= (x2 - frame_width)
            if y2 > frame_height: y1 -= (y2 - frame_height)
            x1, y1 = max(0, x1), max(0, y1)
            crop_w = min(crop_w, frame_width - x1)
            crop_h = min(crop_h, frame_height - y1)

            self.log_avatar(f"  -> 定位到人脸，应用等比裁剪区域: x={x1}, y={y1}, w={crop_w}, h={crop_h}")

            filters = []
            if mirror:
                filters.append("hflip")
            filters.append(f"eq=contrast={contrast}:brightness={brightness}:saturation={saturation}")
            filter_str = ",".join(filters)

            ffmpeg_path = self._find_executable('ffmpeg')

            # --- 核心修改：根据use_gpu选择编码器 ---
            video_codec = 'h264_nvenc' if use_gpu else 'libx264'
            preset = 'fast' if use_gpu else 'medium'
            self.log_avatar(f"  -> 将使用 {('GPU' if use_gpu else 'CPU')} 的 {video_codec} 编码器。")
            # --- 修改结束 ---

            command = [
                ffmpeg_path, '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{frame_width}x{frame_height}', '-pix_fmt', 'bgr24',
                '-r', str(fps), '-i', '-', '-i', os.path.normpath(input_path),
                '-filter_complex', f"[0:v]{filter_str}[v_out]",
                '-map', '[v_out]', '-map', '1:a?',
                '-c:v', video_codec,  # 使用选择的编码器
                '-c:a', 'copy',
                '-preset', preset,
                '-crf' if not use_gpu else '-cq', '23',  # CRF用于CPU, CQ用于GPU
                os.path.normpath(output_path)
            ]

            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW
            self.active_ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, creationflags=creation_flags,
                                                          stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
            proc = self.active_ffmpeg_process
            self.log_avatar(f"  -> 正在逐帧处理并写入文件...")

            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            for i in range(frame_count):
                if self.avatar_stop_event.is_set(): break
                ret, frame = cap.read()
                if not ret: break
                cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
                resized = cv2.resize(cropped, (frame_width, frame_height), interpolation=cv2.INTER_LANCZOS4)
                try:
                    proc.stdin.write(resized.tobytes())
                except (IOError, BrokenPipeError):
                    self.log_avatar("  -> FFmpeg进程提前关闭，停止写入。")
                    break

            self.log_avatar(f"  -> 视频帧写入完成，等待FFmpeg结束编码...")
            stdout_data, stderr_data = proc.communicate()

            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    returncode=proc.returncode,
                    cmd=command,
                    stderr=stderr_data.decode('utf-8', errors='ignore') if stderr_data else "No stderr output."
                )

            return True
        except subprocess.CalledProcessError as e:
            self.log_avatar(f"  ❌ FFmpeg 处理失败: {os.path.basename(input_path)}")
            self.log_avatar(f"     FFmpeg错误: {e.stderr.strip()}")
            return False
        except Exception as e:
            self.log_avatar(f"  ❌ 处理时发生未知错误: {e}")
            return False
        finally:
            if cap: cap.release()
            self.active_ffmpeg_process = None
    def run_avatar_logic(self):
        try:
            input_dir = self.avatar_input_folder_entry.get()
            output_dir = self.avatar_output_folder_entry.get()
            zoom = self._safe_float_convert(self.avatar_zoom_entry.get(), 2.0)
            mirror = self.avatar_mirror_switch.get() == 1
            contrast = self._safe_float_convert(self.avatar_contrast_entry.get(), 1.0)
            brightness = self._safe_float_convert(self.avatar_brightness_entry.get(), 0.0)
            saturation = self._safe_float_convert(self.avatar_saturation_entry.get(), 1.0)
            # --- 核心修改：读取GPU开关状态 ---
            use_gpu = self.avatar_use_gpu_switch.get() == 1 and self.is_gpu_available
            # --- 修改结束 ---
            self.log_avatar(
                f"--- [诊断] 准备处理。GPU开关状态: {self.avatar_use_gpu_switch.get() == 1}, 程序检测到的GPU可用性 (is_gpu_available): {self.is_gpu_available} ---")
            if not all([input_dir, output_dir]):
                self.log_avatar("❌ 错误: 源视频文件夹和输出文件夹都必须填写。");
                return

            if not self.face_cascade:
                self.log_avatar("❌ 致命错误: 人脸识别模型未成功加载，无法执行此功能。")
                return

            video_files = [f for f in os.listdir(input_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
            if not video_files:
                self.log_avatar("ℹ️ 在指定文件夹中未找到任何视频文件。");
                return

            if os.path.exists(output_dir): shutil.rmtree(output_dir)
            os.makedirs(output_dir)
            self.log_avatar(f"🔍 找到 {len(video_files)} 个视频文件，准备开始处理...")

            processed_count = 0
            for i, filename in enumerate(video_files):
                if self.avatar_stop_event.is_set():
                    self.log_avatar("🔴 任务已中止。");
                    break

                self.log_avatar(f"\n--- [任务 {i + 1}/{len(video_files)}] 正在处理: {filename} ---")
                input_path = os.path.join(input_dir, filename)
                output_path = os.path.join(output_dir, f"avatar_{filename}")

                # --- 核心修改：传递use_gpu参数 ---
                if self._avatar_worker(input_path, output_path, zoom, mirror, contrast, brightness, saturation,
                                       use_gpu):
                    self.log_avatar(f"  ✅ 成功输出到: avatar_{filename}")
                    processed_count += 1

            if not self.avatar_stop_event.is_set():
                self.log_avatar(f"\n🎉 所有任务处理完毕！共成功处理 {processed_count} 个文件。")

        except Exception as e:
            self.log_avatar(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_avatar_buttons)




    # ==============================================================================
    # --- 【新增功能】统一分辨率 ---
    # ==============================================================================
    def setup_uniform_resolution_workflow(self, parent_tab):
        """创建“统一分辨率”功能的UI界面"""
        tab = parent_tab

        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        ctk.CTkLabel(main_frame,
                     text="功能说明：将任意分辨率的视频，智能缩放为1080x1920竖屏视频。\n如果原始视频是横屏，将使用虚化的背景进行填充。",
                     wraplength=800, justify="left").pack(anchor="w", padx=10, pady=(5, 15))

        # --- 1. 路径设置 ---
        self.create_folder_selection_row(main_frame, "源视频文件夹:", "选择包含待处理视频的文件夹 (可含子文件夹)",
                                         "uniform_res_input_folder_entry")
        self.create_folder_selection_row(main_frame, "输出文件夹:", "选择处理后视频的存放位置",
                                         "uniform_res_output_folder_entry")

        # --- 2. 开始处理与日志 ---
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=(20, 10))
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.uniform_res_start_button = ctk.CTkButton(button_frame, text="开始批量处理", height=40,
                                                      command=self.start_uniform_resolution_processing)
        self.uniform_res_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.uniform_res_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                     command=self.stop_uniform_resolution_processing,
                                                     state="disabled", fg_color="red", hover_color="darkred")
        self.uniform_res_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.uniform_res_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.uniform_res_log_textbox.pack(expand=True, fill="both", padx=10, pady=(10, 5))

    def log_uniform_res(self, message, clear=False):
        """向统一分辨率模块日志框记录信息"""
        self.after(0, self._update_log, self.uniform_res_log_textbox, message, clear)

    def start_uniform_resolution_processing(self):
        """启动处理的线程"""
        self.uniform_resolution_stop_event.clear()
        self.uniform_res_start_button.configure(state="disabled")
        self.uniform_res_stop_button.configure(state="normal")
        self.log_uniform_res("开始处理...", clear=True)
        threading.Thread(target=self.run_uniform_resolution_logic, daemon=True).start()

    def stop_uniform_resolution_processing(self):
        """发送停止信号"""
        self.log_uniform_res("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.uniform_resolution_stop_event.set()
        self.uniform_res_stop_button.configure(state="disabled")

    def _reset_uniform_resolution_buttons(self):
        """重置按钮状态"""
        self.uniform_res_start_button.configure(state="normal")
        self.uniform_res_stop_button.configure(state="disabled")

    def _uniform_resolution_worker(self, input_path, output_path, target_wh=(1080, 1920)):
        """使用FFmpeg subprocess实现智能背景虚化缩放"""
        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            self.log_uniform_res(f"  ❌ 错误: 找不到 ffmpeg 或 ffprobe。")
            return False

        try:
            target_w, target_h = target_wh
            target_aspect = target_w / target_h

            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            safe_ffprobe_path = f'"{os.path.normpath(ffprobe_path)}"'
            safe_input_path = f'"{os.path.normpath(input_path)}"'

            cmd_probe_str = f'{safe_ffprobe_path} -v error -select_streams v:0 -show_entries stream=width,height -of json {safe_input_path}'
            result = subprocess.run(cmd_probe_str, shell=True, check=True, capture_output=True, text=True,
                                    encoding='utf-8', creationflags=creation_flags)
            stream_info = json.loads(result.stdout)['streams'][0]

            source_w, source_h = int(stream_info['width']), int(stream_info['height'])
            source_aspect = source_w / source_h

            if abs(source_aspect - target_aspect) < 0.01:
                self.log_uniform_res(f"  -> 宽高比匹配，直接缩放。")
                filter_str = f'"scale={target_w}:{target_h}"'
            else:
                self.log_uniform_res(f"  -> 宽高比不匹配，应用背景虚化处理。")
                filter_str = (
                    f'"[0:v]split[bg_src][fg_src];'
                    f'[bg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=50:1[bg_blurred];'
                    f'[fg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fg_scaled];'
                    f'[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2"'
                )

            safe_ffmpeg_path = f'"{os.path.normpath(ffmpeg_path)}"'
            safe_output_path = f'"{os.path.normpath(output_path)}"'

            command_string = f'{safe_ffmpeg_path} -y -i {safe_input_path} -vf {filter_str} -c:v libx264 -preset medium -c:a aac -b:a 192k {safe_output_path}'

            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)
            return True

        except subprocess.CalledProcessError as e:
            self.log_uniform_res(f"  ❌ 智能缩放失败: {os.path.basename(input_path)}")
            self.log_uniform_res(f"     FFmpeg错误: {e.stderr.strip()}")
            return False
        except Exception as e:
            self.log_uniform_res(f"  ❌ 智能缩放时发生未知错误: {e}")
            return False

    def run_uniform_resolution_logic(self):
        """统一分辨率功能的主逻辑"""
        try:
            input_dir = self.uniform_res_input_folder_entry.get()
            output_dir = self.uniform_res_output_folder_entry.get()

            if not all([input_dir, output_dir]):
                self.log_uniform_res("❌ 错误: 源视频文件夹和输出文件夹都必须填写。");
                return

            video_files = [os.path.join(r, f) for r, d, fs in os.walk(input_dir) for f in fs if
                           f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
            if not video_files:
                self.log_uniform_res("ℹ️ 在指定文件夹中未找到任何视频文件。");
                return

            if not os.path.exists(output_dir): os.makedirs(output_dir)
            self.log_uniform_res(f"🔍 找到 {len(video_files)} 个视频文件，准备开始处理...")

            processed_count = 0
            for i, video_path in enumerate(video_files):
                if self.uniform_resolution_stop_event.is_set():
                    self.log_uniform_res("🔴 任务已中止。");
                    break

                self.log_uniform_res(
                    f"\n--- [任务 {i + 1}/{len(video_files)}] 正在处理: {os.path.basename(video_path)} ---")
                output_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}_resized.mp4"
                output_path = os.path.join(output_dir, output_filename)

                if self._uniform_resolution_worker(video_path, output_path):
                    self.log_uniform_res(f"  ✅ 成功输出到: {output_filename}")
                    processed_count += 1

            if not self.uniform_resolution_stop_event.is_set():
                self.log_uniform_res(f"\n🎉 所有任务处理完毕！共成功处理 {processed_count} 个文件。")

        except Exception as e:
            self.log_uniform_res(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_uniform_resolution_buttons)
    def stop_ios_discovery(self):
        """发送停止信号给搜索线程"""
        self.log_ios_transfer("--- 正在取消搜索... ---")
        self.ios_discovery_stop_event.set()
        self.ios_cancel_discover_btn.configure(state="disabled")

    def _reset_ios_discovery_buttons(self):
        """将搜索相关的按钮重置为初始状态"""
        self.ios_discover_btn.configure(state="normal")
        self.ios_cancel_discover_btn.configure(state="disabled")

    def _ios_update_ui_from_queue(self):
        """在主线程中运行，定时检查队列并更新UI"""
        while not self.device_queue.empty():
            try:
                name, address = self.device_queue.get_nowait()
                if name not in self.discovered_devices:
                    self.discovered_devices[name] = address
                    self.log_ios_transfer(f"  -> 发现设备: {name} ({address})")
                    device_label = ctk.CTkLabel(self.ios_device_frame, text=f"📱 {name} ({address})")
                    device_label.pack(anchor="w", padx=10, pady=2)
            except queue.Empty:
                break

        if not self.ios_discovery_stop_event.is_set():
            self.after(100, self._ios_update_ui_from_queue)

    def _ios_discover_devices_thread(self):
        """在后台线程中运行，只负责监听和将结果放入队列"""
        end_time = time.time() + DISCOVERY_DURATION
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', MCAST_PORT))
            mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            while time.time() < end_time and not self.ios_discovery_stop_event.is_set():
                try:
                    sock.settimeout(0.5)
                    data, addr = sock.recvfrom(1024)
                    message = json.loads(data.decode('utf-8'))
                    name, ip, port = message.get('name'), message.get('ip'), message.get('port')
                    if name and ip and port:
                        self.device_queue.put((name, f"{ip}:{port}"))
                except socket.timeout:
                    continue
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            self.log_ios_transfer("错误: 端口已被占用。脚本是否已在运行?")
        except Exception as e:
            self.log_ios_transfer(f"设备发现线程出错: {e}")
        finally:
            self.ios_discovery_stop_event.set()
            self.after(0, lambda: self._reset_ios_discovery_buttons())
            self.after(0,
                       lambda: self.log_ios_transfer(f"--- 搜索结束。共发现 {len(self.discovered_devices)} 台设备。 ---"))

    def start_ios_batch_transfer(self):
        """启动批量传输的主函数"""
        if not self.ios_source_folder_entry.get():
            self.log_ios_transfer("错误: 请先选择来源文件夹!")
            return
        if not self.discovered_devices:
            self.log_ios_transfer("错误: 未发现任何设备，请先搜索!")
            return

        self.ios_transfer_btn.configure(state="disabled")
        self.log_ios_transfer("\n================ 开始批量传输 ===============")

        transfer_thread = threading.Thread(target=self._ios_batch_transfer_thread, daemon=True)
        transfer_thread.start()

    def _ios_batch_transfer_thread(self):
        """批量传输的实际工作线程"""
        source_folder = self.ios_source_folder_entry.get()
        try:
            subfolders = [d for d in os.listdir(source_folder) if os.path.isdir(os.path.join(source_folder, d))]
        except FileNotFoundError:
            self.log_ios_transfer(f"严重错误: 来源文件夹不存在: {source_folder}")
            self.after(0, lambda: self.ios_transfer_btn.configure(state="normal"))
            return

        transfer_threads = []
        for folder_name in subfolders:
            if folder_name in self.discovered_devices:
                device_address = self.discovered_devices[folder_name]
                folder_path = os.path.join(source_folder, folder_name)
                files_to_send = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if
                                 os.path.isfile(os.path.join(folder_path, f))]

                if files_to_send:
                    t = threading.Thread(target=self._ios_transfer_files_to_device,
                                         args=(folder_name, device_address, files_to_send), daemon=True)
                    transfer_threads.append(t)
                    t.start()
                else:
                    self.log_ios_transfer(f"注意: 文件夹 '{folder_name}' 为空，跳过。")
            else:
                self.log_ios_transfer(f"警告: 文件夹 '{folder_name}' 存在，但网络上未发现同名设备。")

        for t in transfer_threads:
            t.join()

        self.log_ios_transfer("\n================ 所有任务已完成 ===============")
        self.after(0, lambda: self.ios_transfer_btn.configure(state="normal"))

    def _ios_transfer_files_to_device(self, device_name, address, file_list):
        """为单个设备发送所有文件 (修正为原始的二进制流发送方式)"""
        self.log_ios_transfer(f"--- 开始向设备 '{device_name}' ({address}) 发送文件 ---")
        base_url = f'http://{address}/upload'
        success_count, fail_count = 0, 0

        for f_path in file_list:
            if self.ios_transfer_stop_event.is_set(): break

            filename = os.path.basename(f_path)
            headers = {'X-File-Name': filename.encode('utf-8')}

            try:
                with open(f_path, 'rb') as f:
                    response = requests.post(base_url, data=f, headers=headers, timeout=90)

                if response.status_code == 200:
                    self.log_ios_transfer(f"  [成功] {filename} -> {device_name}")
                    success_count += 1
                else:
                    self.log_ios_transfer(
                        f"  [失败] {filename} -> {device_name} (服务器返回: {response.status_code} {response.text})")
                    fail_count += 1
            except requests.exceptions.RequestException as e:
                self.log_ios_transfer(f"  [错误] {filename} -> {device_name} (连接或传输失败: {e})")
                fail_count += 1

        self.log_ios_transfer(f"--- 设备 '{device_name}' 传输完成: {success_count} 成功, {fail_count} 失败 ---")
    def log_ios_transfer(self, message, clear=False):
        self.after(0, self._update_log, self.ios_log_textbox, message, clear)

    def start_ios_discovery(self):
        self.ios_discovery_stop_event.clear()
        self.ios_discover_btn.configure(state="disabled")
        self.ios_cancel_discover_btn.configure(state="normal")
        for widget in self.ios_device_frame.winfo_children(): widget.destroy()
        self.discovered_devices = {}
        self.log_ios_transfer("--- 开始搜索网络中的iOS设备... ---", clear=True)

        # 启动后台的“生产者”线程
        discovery_thread = threading.Thread(target=self._ios_discover_devices_thread, daemon=True)
        discovery_thread.start()

        # 启动前台的“消费者”UI轮询器
        self.after(100, self._ios_update_ui_from_queue)

    def stop_ios_discovery(self):
        self.log_ios_transfer("--- 正在取消搜索... ---")
        self.ios_discovery_stop_event.set()
        self.ios_cancel_discover_btn.configure(state="disabled")

    def _reset_ios_discovery_buttons(self):
        self.ios_discover_btn.configure(state="normal")
        self.ios_cancel_discover_btn.configure(state="disabled")

    def _ios_update_ui_from_queue(self):
        """【消费者】在主线程中运行，定时检查队列并更新UI"""
        # 处理队列中的所有当前消息
        while not self.device_queue.empty():
            try:
                name, address = self.device_queue.get_nowait()
                if name not in self.discovered_devices:
                    self.discovered_devices[name] = address
                    self.log_ios_transfer(f"  -> 发现设备: {name} ({address})")
                    device_label = ctk.CTkLabel(self.ios_device_frame, text=f"📱 {name} ({address})")
                    device_label.pack(anchor="w", padx=10, pady=2)
            except queue.Empty:
                break

        # 检查是否需要继续轮询
        if not self.ios_discovery_stop_event.is_set():
            self.after(100, self._ios_update_ui_from_queue)  # 100ms后再次检查

    def _ios_discover_devices_thread(self):
        """【生产者】在后台线程中运行，只负责监听和将结果放入队列"""
        end_time = time.time() + DISCOVERY_DURATION
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', MCAST_PORT))
            mreq = struct.pack("4sl", socket.inet_aton(MCAST_GRP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            while time.time() < end_time and not self.ios_discovery_stop_event.is_set():
                try:
                    sock.settimeout(0.5)
                    data, addr = sock.recvfrom(1024)
                    message = json.loads(data.decode('utf-8'))
                    name, ip, port = message.get('name'), message.get('ip'), message.get('port')
                    if name and ip and port:
                        self.device_queue.put((name, f"{ip}:{port}"))
                except socket.timeout:
                    continue  # 超时是正常的，继续循环检查停止信号
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            self.log_ios_transfer("错误: 端口已被占用。脚本是否已在运行?")
        except Exception as e:
            self.log_ios_transfer(f"设备发现线程出错: {e}")
        finally:
            self.ios_discovery_stop_event.set()  # 确保轮询器最终会停止
            self.after(0, lambda: self._reset_ios_discovery_buttons())
            self.after(0, lambda: self.log_ios_transfer(
                f"--- 搜索结束。共发现 {len(self.discovered_devices)} 台设备。 ---"))

    # ... (start_ios_batch_transfer, _ios_batch_transfer_thread, 和 _ios_transfer_files_to_device 函数保持不变)
    # ==============================================================================
    # --- 【新增功能】双屏处理模块 ---
    # ==============================================================================

    def setup_dualscreen_workflow(self):
        """创建“双屏”拼接功能的UI界面"""
        tab = self.main_tabview.tab("双屏")

        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # --- 1. 路径设置 ---
        path_frame = ctk.CTkFrame(main_frame)
        path_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(path_frame, text="文件路径设置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                            pady=(5, 10))
        self.create_folder_selection_row(path_frame, "A文件夹 (上/右):", "选择视频文件夹A (可含子文件夹)",
                                         "dualscreen_folder_a_entry")
        self.create_folder_selection_row(path_frame, "B文件夹 (下/左):", "选择视频文件夹B",
                                         "dualscreen_folder_b_entry")
        self.create_folder_selection_row(path_frame, "输出文件夹:", "选择处理结果的存放位置",
                                         "dualscreen_output_folder_entry")

        # --- 2. 模式设置 ---
        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.pack(fill="x", pady=15, anchor="w", padx=10)

        self.dualscreen_portrait_switch = ctk.CTkSwitch(settings_frame, text="竖屏模式 (左右拼接)")
        self.dualscreen_portrait_switch.pack(side="left", padx=(0, 20))

        self.dualscreen_use_gpu_switch = ctk.CTkSwitch(settings_frame, text="启用GPU加速编码 (NVIDIA)")
        self.dualscreen_use_gpu_switch.pack(side="left")
        # --- 3. 开始处理与日志 ---
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(15, 5))
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.dualscreen_start_button = ctk.CTkButton(button_frame, text="开始双屏合成", height=40,
                                                     command=self.start_dualscreen_processing)
        self.dualscreen_start_button.grid(row=0, column=0, padx=(10, 5), sticky="ew")
        self.dualscreen_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                    command=lambda: self.video_stop_event.set(), state="disabled",
                                                    fg_color="red", hover_color="darkred")
        self.dualscreen_stop_button.grid(row=0, column=1, padx=(5, 10), sticky="ew")

        self.dualscreen_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.dualscreen_log_textbox.pack(expand=True, fill="both", pady=(10, 5), padx=10)

    def log_dualscreen(self, message, clear=False):
        """向双屏模块日志框记录信息"""
        self.after(0, self._update_log, self.dualscreen_log_textbox, message, clear)
    def start_dualscreen_processing(self):
        """启动双屏处理的线程"""
        self.video_stop_event.clear()
        self.dualscreen_start_button.configure(state="disabled")
        self.dualscreen_stop_button.configure(state="normal")
        # 使用新的日志函数来清空日志并显示第一条信息
        self.log_dualscreen("处理开始...", clear=True)
        threading.Thread(target=self.run_dualscreen_logic, daemon=True).start()

    def _dualscreen_worker_moviepy(self, path_a, path_b, output_path, use_gpu):
        """【MoviePy 终极手动合成方案】使用 CompositeVideoClip 手动布局，确保拼接成功。"""
        self.log_dualscreen("    -> 启动 MoviePy 手动合成引擎...")
        clip_a, clip_b, final_clip = None, None, None
        try:
            # 1. 加载视频文件
            self.log_dualscreen("        -> 正在加载媒体文件...")
            clip_a = VideoFileClip(path_a)
            clip_b = VideoFileClip(path_b)

            # 2. 以A视频的尺寸作为最终输出的画布尺寸
            W, H = clip_a.size
            self.log_dualscreen(f"        -> 最终画布尺寸确定为: {W}x{H}")

            # 3. 准备A视频片段：精确裁剪出上半部分
            # crop 的参数 (x1, y1, x2, y2) 定义了要保留的区域
            a_top = vfx.crop(clip_a, x1=0, y1=0, x2=W, y2=H / 2)
            # a_top 将默认放置在画布的 (0,0) 位置，即顶部

            # 4. 准备B视频片段：处理成能精确填充下半部分的片段
            # 首先将B视频缩放，使其宽度与A视频相同
            clip_b_resized = clip_b.resize(width=W)
            # 然后从缩放后的B视频的垂直中心，裁剪出一个高度为A一半的片段
            b_bottom_piece = vfx.crop(clip_b_resized, y_center=clip_b_resized.h / 2, width=W, height=H / 2)

            # 关键：手动设置这个片段的位置，让它位于画布的下半部分
            b_bottom_positioned = b_bottom_piece.set_position(('center', H / 2))
            self.log_dualscreen("        -> 已分别准备好A的上半部分和B的下半部分")

            # 5. 手动合成：创建一个指定尺寸的空白画布，然后按顺序将准备好的片段“贴”上去
            final_clip = CompositeVideoClip(
                clips=[a_top, b_bottom_positioned],  # 将A和B的片段放入
                size=(W, H)  # 明确指定最终视频的尺寸
            )

            # 6. 将A视频的音频赋给最终的合成视频
            if clip_a.audio:
                final_clip.audio = clip_a.audio

            # 7. 设置最终视频的时长
            final_clip.duration = min(clip_a.duration, clip_b.duration)

            # 8. 写入文件
            self.log_dualscreen("    -> MoviePy 正在渲染输出视频...")
            codec = 'h2b64_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
            final_clip.write_videofile(output_path, codec=codec, audio_codec="aac", preset='medium', threads=4,
                                       logger=None)

            self.log_dualscreen("    -> MoviePy 手动合成引擎处理成功！")
            return True

        except Exception as e:
            self.log_dualscreen(f"  ❌ MoviePy 引擎处理失败: {e}")
            import traceback
            self.log_dualscreen(traceback.format_exc())  # 打印详细错误以供调试
            return False
        finally:
            # 关键步骤：确保所有视频文件都被关闭，释放内存和文件句柄
            if clip_a: clip_a.close()
            if clip_b: clip_b.close()
            if final_clip: final_clip.close()
    def _dualscreen_worker(self, path_a, path_b, output_path, is_portrait_mode, use_gpu):
        """【调度函数】根据模式选择不同的处理引擎。"""

        # --- 如果是竖屏模式，则调用全新的、更稳定的 MoviePy 引擎 ---
        if is_portrait_mode:
            return self._dualscreen_worker_moviepy(path_a, path_b, output_path, use_gpu)

        # --- 如果是横屏模式，继续使用之前稳定运行的 FFmpeg 逻辑 ---
        else:
            self.log_dualscreen("  -> 应用横屏模式 (FFmpeg 堆叠)")
            ffmpeg_path = self._find_executable("ffmpeg")
            ffprobe_path = self._find_executable("ffprobe")
            if not ffmpeg_path or not ffprobe_path:
                self.log_dualscreen("错误：找不到 ffmpeg.exe 或 ffprobe.exe")
                return False

            try:
                creation_flags = 0
                if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

                # 横屏模式的 FFmpeg 命令
                filter_complex_v = "[0:v]scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720,setsar=1[top];[1:v]scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720,setsar=1[bottom];[top][bottom]vstack=inputs=2[v]"

                # 此处省略了音频检测和参数构建，以保持简洁，实际应使用您文件中完整的横屏逻辑
                # 为确保完整性，我们粘贴完整的横屏逻辑
                def has_audio(video_path):
                    try:
                        cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries",
                                     "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1",
                                     os.path.normpath(video_path)]
                        return bool(subprocess.run(cmd_probe, check=True, capture_output=True, text=True,
                                                   creationflags=creation_flags).stdout.strip())
                    except:
                        return False

                IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
                path_a_is_image = path_a.lower().endswith(IMAGE_EXT)
                path_b_is_image = path_b.lower().endswith(IMAGE_EXT)
                has_audio_a = not path_a_is_image and has_audio(path_a)
                has_audio_b = not path_b_is_image and has_audio(path_b)

                input_args = []
                if path_a_is_image: input_args.extend(['-loop', '1'])
                input_args.extend(['-i', os.path.normpath(path_a)])
                if path_b_is_image: input_args.extend(['-loop', '1'])
                input_args.extend(['-i', os.path.normpath(path_b)])

                audio_filter_part = ""
                map_args = ['-map', '[v]']
                audio_codec_args = []

                if has_audio_a and has_audio_b:
                    audio_filter_part, map_args, audio_codec_args = ";[0:a][1:a]amerge=inputs=2[a_out]", ['-map', '[v]',
                                                                                                          '-map',
                                                                                                          '[a_out]'], [
                        '-ac', '2', '-c:a', 'aac']
                elif has_audio_a:
                    map_args.extend(['-map', '0:a?']); audio_codec_args = ['-c:a', 'copy']
                elif has_audio_b:
                    map_args.extend(['-map', '1:a?']); audio_codec_args = ['-c:a', 'copy']
                else:
                    audio_codec_args = ['-an']

                full_filter_complex = filter_complex_v + audio_filter_part
                video_codec = 'h264_nvenc' if use_gpu else 'libx264'

                command = [ffmpeg_path, '-y', *input_args, '-filter_complex', full_filter_complex, *map_args, '-c:v',
                           video_codec, '-preset', 'fast', *audio_codec_args, '-shortest',
                           os.path.normpath(output_path)]
                subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                               creationflags=creation_flags)
                return True
            except Exception as e:
                self.log_dualscreen(f"  ❌ 横屏模式处理失败: {e}")
                return False
    def _dualscreen_worker(self, path_a, path_b, output_path, is_portrait_mode, use_gpu):
        """【终极修复版 v6】竖屏模式采用“画布覆盖法”处理A视频，彻底规避元数据导致的画面位移问题。"""
        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            self.log_dualscreen("错误：找不到 ffmpeg.exe 或 ffprobe.exe")
            return False

        # --- 如果不是竖屏模式，则使用原来的横屏逻辑 (此部分已验证无误) ---
        if not is_portrait_mode:
            # ... 此处省略了完整的横屏模式代码，以突出重点，请确保您文件中的这部分是完整的 ...
            # 为确保函数完整性，我们再次包含完整的横屏逻辑
            self.log_dualscreen("  -> 应用横屏模式 (堆叠)")
            # --- 横屏模式的完整逻辑 ---
            try:
                creation_flags = 0
                if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

                def has_audio(video_path):
                    try:
                        cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries",
                                     "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1",
                                     os.path.normpath(video_path)]
                        return bool(subprocess.run(cmd_probe, check=True, capture_output=True, text=True,
                                                   creationflags=creation_flags).stdout.strip())
                    except:
                        return False

                IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
                path_a_is_image = path_a.lower().endswith(IMAGE_EXT)
                path_b_is_image = path_b.lower().endswith(IMAGE_EXT)
                has_audio_a = not path_a_is_image and has_audio(path_a)
                has_audio_b = not path_b_is_image and has_audio(path_b)

                input_args = []
                if path_a_is_image: input_args.extend(['-loop', '1'])
                input_args.extend(['-i', os.path.normpath(path_a)])
                if path_b_is_image: input_args.extend(['-loop', '1'])
                input_args.extend(['-i', os.path.normpath(path_b)])

                filter_complex_v = "[0:v]scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720,setsar=1[top];[1:v]scale=1080:720:force_original_aspect_ratio=increase,crop=1080:720,setsar=1[bottom];[top][bottom]vstack=inputs=2[v]"
                audio_filter_part = ""
                map_args = ['-map', '[v]']
                audio_codec_args = []

                if has_audio_a and has_audio_b:
                    audio_filter_part, map_args, audio_codec_args = ";[0:a][1:a]amerge=inputs=2[a_out]", ['-map', '[v]',
                                                                                                          '-map',
                                                                                                          '[a_out]'], [
                        '-ac', '2', '-c:a', 'aac']
                elif has_audio_a:
                    map_args.extend(['-map', '0:a?']); audio_codec_args = ['-c:a', 'copy']
                elif has_audio_b:
                    map_args.extend(['-map', '1:a?']); audio_codec_args = ['-c:a', 'copy']
                else:
                    audio_codec_args = ['-an']

                full_filter_complex = filter_complex_v + audio_filter_part
                video_codec = 'h264_nvenc' if use_gpu else 'libx264'

                command = [ffmpeg_path, '-y', *input_args, '-filter_complex', full_filter_complex, *map_args, '-c:v',
                           video_codec, '-preset', 'fast', *audio_codec_args, '-shortest',
                           os.path.normpath(output_path)]
                subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                               creationflags=creation_flags)
                return True
            except Exception as e:
                self.log_dualscreen(f"  ❌ 横屏模式处理失败: {e}")
                return False
            # --- 横屏逻辑结束 ---

        # --- 全新的竖屏模式处理逻辑 ---
        self.log_dualscreen("  -> 应用终极版竖屏模式 (画布覆盖法)")

        temp_a_top, temp_b_bottom, concat_list_file = None, None, None
        try:
            creation_flags = 0
            if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

            self.log_dualscreen("    1/4: 获取A视频的精确尺寸和时长...")
            cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height,duration", "-of", "csv=p=0", os.path.normpath(path_a)]
            result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True, creationflags=creation_flags)
            w_str, h_str, dur_str = result.stdout.strip().split(',')
            width, height, duration = int(w_str), int(h_str), float(dur_str)
            self.log_dualscreen(f"        -> A视频信息: {width}x{height}, 时长: {duration:.2f}s")

            output_dir = os.path.dirname(output_path)
            base_name = os.path.splitext(os.path.basename(output_path))[0]
            temp_a_top = os.path.join(output_dir, f"{base_name}_temp_a.mp4")
            temp_b_bottom = os.path.join(output_dir, f"{base_name}_temp_b.mp4")
            concat_list_file = os.path.join(output_dir, f"{base_name}_concat.txt")

            # --- 核心修改点：使用画布覆盖法生成A的上半部分 ---
            self.log_dualscreen("    2/4: 生成A视频的上半部分 (画布覆盖法)...")
            cmd_a = [
                ffmpeg_path, '-y',
                # 输入1: 创建一个指定尺寸和时长的黑色画布
                '-f', 'lavfi', '-i', f"color=c=black:s={width}x{height // 2}:d={duration}",
                # 输入2: 原始A视频
                '-i', os.path.normpath(path_a),
                # 滤镜：将A视频[1:v]覆盖到黑色画布[0:v]的(0,0)位置
                '-filter_complex', "[0:v][1:v]overlay=0:0[out]",
                # 映射输出：使用滤镜结果[out]作为视频，使用A视频的原始音频[1:a]
                '-map', '[out]', '-map', '1:a?',
                '-c:a', 'copy',
                '-shortest',  # 确保最终时长以A视频为准
                temp_a_top
            ]
            subprocess.run(cmd_a, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            # 3. 生成 B 的下半部分视频 (无声) - 此方法稳定，保持不变
            self.log_dualscreen("    3/4: 生成B视频的下半部分...")
            cmd_b = [
                ffmpeg_path, '-y', '-i', os.path.normpath(path_b),
                '-vf', f"scale={width}:{height},crop={width}:{height // 2}:0:{height // 2},setsar=1",
                '-an',
                temp_b_bottom
            ]
            subprocess.run(cmd_b, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            # 4. 创建拼接列表文件并执行拼接
            self.log_dualscreen("    4/4: 拼接最终视频...")
            with open(concat_list_file, 'w', encoding='utf-8') as f:
                f.write(f"file '{os.path.basename(temp_a_top)}'\n")
                f.write(f"file '{os.path.basename(temp_b_bottom)}'\n")

            video_codec = 'h264_nvenc' if use_gpu else 'libx264'
            cmd_concat = [
                ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_file,
                '-c:v', video_codec, '-preset', 'fast' if use_gpu else 'medium',
                '-c:a', 'copy',
                os.path.normpath(output_path)
            ]
            subprocess.run(cmd_concat, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            return True

        except Exception as e:
            error_msg = f"处理失败: {e}"
            if hasattr(e, 'stderr') and e.stderr:
                error_msg += f"\nFFmpeg 错误: {e.stderr.decode('utf-8', 'ignore').strip()}"
            self.log_dualscreen(f"  ❌ {error_msg}")
            return False

        finally:
            # 清理所有临时文件
            for temp_file in [temp_a_top, temp_b_bottom, concat_list_file]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass
    def run_dualscreen_logic(self):
        """【修改版】双屏合成的主逻辑，支持视频和图片文件。"""
        try:
            folder_a = self.dualscreen_folder_a_entry.get()
            folder_b = self.dualscreen_folder_b_entry.get()
            output_folder = self.dualscreen_output_folder_entry.get()
            is_portrait = self.dualscreen_portrait_switch.get() == 1
            use_gpu = self.dualscreen_use_gpu_switch.get() == 1 and self.is_gpu_available

            self.log_dualscreen("🔍 正在扫描媒体文件(视频和图片)...")

            if not all([folder_a, folder_b, output_folder]):
                self.log_dualscreen("❌ 错误: 所有文件夹路径都必须填写。")
                self.after(0, lambda: self.dualscreen_start_button.configure(state="normal"))
                self.after(0, lambda: self.dualscreen_stop_button.configure(state="disabled"))
                return

            # 定义支持的媒体格式
            SUPPORTED_FORMATS = ('.mp4', '.mov', '.avi', '.mkv', '.png', '.jpg', '.jpeg', '.webp')

            media_files_a = []
            for root, _, files in os.walk(folder_a):
                for file in files:
                    if file.lower().endswith(SUPPORTED_FORMATS):
                        media_files_a.append(os.path.join(root, file))

            media_files_b = []
            if os.path.exists(folder_b):
                for file in os.listdir(folder_b):
                    if file.lower().endswith(SUPPORTED_FORMATS):
                        media_files_b.append(os.path.join(folder_b, file))

            if not media_files_a or not media_files_b:
                self.log_dualscreen("❌ 错误: 文件夹A或B中没有找到任何有效的视频或图片文件。")
                self.after(0, lambda: self.dualscreen_start_button.configure(state="normal"))
                self.after(0, lambda: self.dualscreen_stop_button.configure(state="disabled"))
                return

            self.log_dualscreen(f"✅ 扫描完成：找到A媒体 {len(media_files_a)} 个，B媒体 {len(media_files_b)} 个。")
            random.shuffle(media_files_a)
            random.shuffle(media_files_b)

            num_to_process = min(len(media_files_a), len(media_files_b))
            self.log_dualscreen(f"将处理 {num_to_process} 对媒体文件。")
            os.makedirs(output_folder, exist_ok=True)  # 确保输出目录存在

            for i in range(num_to_process):
                if self.video_stop_event.is_set():
                    self.log_dualscreen("🔴 任务已由用户中止。")
                    break

                path_a = media_files_a[i]
                path_b = media_files_b[i]

                basename_a = os.path.splitext(os.path.basename(path_a))[0]
                basename_b = os.path.splitext(os.path.basename(path_b))[0]
                output_filename = f"{basename_a}_vs_{basename_b}.mp4"
                output_path = os.path.join(output_folder, output_filename)

                self.log_dualscreen(f"\n--- [任务 {i + 1}/{num_to_process}] ---")
                self.log_dualscreen(
                    f"  A ({'图片' if path_a.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) else '视频'}): {os.path.basename(path_a)}")
                self.log_dualscreen(
                    f"  B ({'图片' if path_b.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) else '视频'}): {os.path.basename(path_b)}")

                if self._dualscreen_worker(path_a, path_b, output_path, is_portrait, use_gpu):
                    self.log_dualscreen(f"  ✅ 成功输出到: {output_filename}")
                else:
                    self.log_dualscreen(f"  ❌ 处理失败，请查看日志获取详细错误信息。")

            self.log_dualscreen("\n--- 🎉 所有任务处理完毕！ ---")

        except Exception as e:
            error_string = traceback.format_exc()
            print(f"--- [后台线程发生致命错误] ---\n{error_string}\n---------------------------")
            self.log_dualscreen(f"❌ 发生致命错误: {e}")

        finally:
            # --- 核心修改：使用lambda来修正after函数的调用语法 ---
            self.after(0, lambda: self.dualscreen_start_button.configure(state="normal"))
            self.after(0, lambda: self.dualscreen_stop_button.configure(state="disabled"))
            # -
    # ==============================================================================
    # --- FFmpeg 高性能视频处理模块 (最终、完整、经过验证的版本) ---
    # ==============================================================================

    def _ffmpeg_escape_path(self, path):
        """为FFmpeg滤镜中使用的Windows路径进行最可靠的转义。"""
        escaped_path = path.replace('\\', '/')
        if len(escaped_path) > 1 and escaped_path[1] == ':':
            escaped_path = escaped_path[0] + '\\' + escaped_path[1:]
        return escaped_path

    def _ffmpeg_format_color(self, color_string):
        """将多种颜色格式转换为FFmpeg drawtext滤镜可接受的 '#RRGGBBAA' 格式"""
        if isinstance(color_string, str) and color_string.startswith("rgba"):
            try:
                parts = re.findall(r"[-+]?\d*\.\d+|\d+", color_string)
                r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                a = int(float(parts[3]) * 255)
                return f'#{r:02x}{g:02x}{b:02x}{a:02x}'
            except:
                return '#000000FF'
        elif isinstance(color_string, str) and color_string.startswith("#"):
            return f'{color_string}FF' if len(color_string) == 7 else color_string
        else:
            try:
                rgb = ImageColor.getrgb(color_string)
                return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}FF'
            except:
                return '#FFFFFFFF'

    def _ffmpeg_prepare_text(self, text, font_path, font_size, max_pixel_width):
        """使用PIL预处理文本：处理手动换行'/'，并进行自动换行。"""
        text = text.replace('\\', '\\\\').replace('%', '%%').replace(':', '\\:').replace("'", "’")
        manual_lines = text.split('/')
        final_lines = []
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            font = ImageFont.load_default()

        dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

        for line in manual_lines:
            if not line.strip(): continue
            wrapped_lines, _, _ = image_wrap_text(dummy_draw, line, font, max_pixel_width)
            final_lines.extend(wrapped_lines)

        final_text = "\n".join(final_lines)
        bbox = dummy_draw.multiline_textbbox((0, 0), final_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        return final_text, (text_width, text_height)

    def _create_ffmpeg_drawtext_filter(self, text, font_path, font_size, max_width_ratio, no_background, box_padding,
                                       stroke_width, colors, position, temp_dir):
        """【最终中文键名版】使用中文键名来读取配置，并构建滤镜。"""

        # 使用中文键名更新调试信息
        self.log_video(
            f"  - [调试信息] 滤镜创建参数: size={font_size}, stroke={stroke_width}, no_bg={no_background}, text_color={colors.get('文字颜色')}")

        max_pixel_width = int(1080 * max_width_ratio)
        processed_text, (text_w, text_h) = self._ffmpeg_prepare_text(text, font_path, font_size, max_pixel_width)

        try:
            temp_text_file = os.path.join(temp_dir, f"temp_text_{random.randint(1000, 9999)}.txt")
            with open(temp_text_file, 'w', encoding='utf-8') as f:
                f.write(processed_text)
        except Exception as e:
            self.log_video(f"  -> 错误: 创建临时文本文件失败: {e}")
            return None, 0, None

        params = {
            'fontfile': self._ffmpeg_escape_path(font_path),
            'textfile': self._ffmpeg_escape_path(temp_text_file),
            'reload': '1',
            'fontsize': str(font_size),
            'x': position['x'],
            'y': position['y']
        }

        # --- 核心修改：全部使用中文键名来读取colors字典 ---
        params['fontcolor'] = self._ffmpeg_format_color(colors['文字颜色'])

        if stroke_width > 0:
            params['borderw'] = str(stroke_width)
            params['bordercolor'] = self._ffmpeg_format_color(colors.get('描边颜色', 'black'))

        if not no_background:
            params['box'] = '1'
            params['boxcolor'] = self._ffmpeg_format_color(colors.get('背景颜色', '#FFFFFF'))
            params['boxborderw'] = str(box_padding)

        filter_string = "drawtext=" + ":".join([f"{k}={v}" for k, v in params.items()])

        return filter_string, text_h + (box_padding * 2), temp_text_file

    def start_video_processing_ffmpeg(self):
        """启动FFmpeg高性能处理流程的线程"""
        self.video_stop_event.clear()
        # 确保按钮指向的是这个新的启动函数
        self.start_video_button.configure(command=self.start_video_processing_ffmpeg, state="disabled")
        self.stop_video_button.configure(state="normal")
        self.log_video("", clear=True)
        threading.Thread(target=self.run_video_logic_ffmpeg, daemon=True).start()

    def _create_ffmpeg_drawtext_filter(self, text, font_path, font_size, max_width_ratio, no_background, box_padding,
                                       stroke_width, colors, position, temp_dir):
        """【最终修正版】使用中文键名来读取配置，并构建滤镜。"""

        # --- 核心修改：全部使用中文键名 ---
        self.log_video(
            f"  - [调试信息] 滤镜创建参数: size={font_size}, stroke={stroke_width}, no_bg={no_background}, text_color={colors.get('文字颜色')}")

        max_pixel_width = int(1080 * max_width_ratio)
        processed_text, (text_w, text_h) = self._ffmpeg_prepare_text(text, font_path, font_size, max_pixel_width)

        try:
            temp_text_file = os.path.join(temp_dir, f"temp_text_{random.randint(1000, 9999)}.txt")
            with open(temp_text_file, 'w', encoding='utf-8') as f:
                f.write(processed_text)
        except Exception as e:
            self.log_video(f"  -> 错误: 创建临时文本文件失败: {e}")
            return None, 0, None

        params = {
            'fontfile': self._ffmpeg_escape_path(font_path),
            'textfile': self._ffmpeg_escape_path(temp_text_file),
            'reload': '1',
            'fontsize': str(font_size),
            'x': position['x'],
            'y': position['y']
        }

        # --- 核心修改：全部使用中文键名来读取colors字典 ---
        params['fontcolor'] = self._ffmpeg_format_color(colors['文字颜色'])

        if stroke_width > 0:
            params['borderw'] = str(stroke_width)
            params['bordercolor'] = self._ffmpeg_format_color(colors.get('描边颜色', 'black'))

        if not no_background:
            params['box'] = '1'
            params['boxcolor'] = self._ffmpeg_format_color(colors.get('背景颜色', '#00000080'))
            params['boxborderw'] = str(box_padding)

        filter_string = "drawtext=" + ":".join([f"{k}={v}" for k, v in params.items()])

        return filter_string, text_h + (box_padding * 2), temp_text_file

    # ==============================================================================
    # --- 【最终方案】MoviePy渲染 + FFmpeg合成 混合模式 ---
    # ==============================================================================

    def _create_overlay_image_with_moviepy(self, text, shared_style, specific_config, video_size, output_png_path):
        """
        【兼容旧版MoviePy】使用MoviePy创建高质量的文字叠加层，并将其保存为透明PNG图片。
        """
        overlay_clip = None
        try:
            # 步骤 1: 创建 MoviePy 剪辑对象 (这部分不变)
            adapted_shared_style = {
                'font_file': shared_style.get('字体文件'), 'size': shared_style.get('字体大小'),
                'max_width_ratio': shared_style.get('最大宽度比例'),
                'padding_horizontal': shared_style.get('左右内边距'),
                'padding_vertical': shared_style.get('垂直内边距'), 'stroke_width': shared_style.get('描边粗细'),
                'corner_radius': shared_style.get('背景圆角半径'), 'no_background': shared_style.get('禁用背景')
            }
            chinese_colors = specific_config.get('颜色', {})
            english_colors = {
                'text': chinese_colors.get('文字颜色'), 'stroke': chinese_colors.get('描边颜色'),
                'background': chinese_colors.get('背景颜色')
            }
            adapted_specific_config = {'colors': english_colors}

            overlay_clip = video_create_text_overlay(text, adapted_shared_style, adapted_specific_config, video_size)

            # --- 核心修改：使用Pillow手动保存带透明通道的PNG ---
            # 检查剪辑是否有遮罩（即透明部分）
            if overlay_clip.mask is not None:
                # 获取t=0时刻的RGB帧和Alpha遮罩帧
                rgb_frame = overlay_clip.get_frame(0)
                alpha_frame = overlay_clip.mask.get_frame(0)

                # 将MoviePy的numpy数组转换为Pillow图像对象
                img_rgb = Image.fromarray(rgb_frame)

                # 将0-1范围的alpha值转换为0-255，并创建为'L'模式（灰度）的Pillow图像
                img_alpha = Image.fromarray((alpha_frame * 255).astype('uint8'), mode='L')

                # 创建一个RGBA图像，并将alpha通道放进去
                img_rgba = img_rgb.convert('RGBA')
                img_rgba.putalpha(img_alpha)

                # 保存最终的带透明背景的PNG
                img_rgba.save(output_png_path, 'PNG')
            else:
                # 如果没有透明通道，直接保存帧
                overlay_clip.save_frame(output_png_path, t=0)

            overlay_clip.close()

            img = Image.open(output_png_path)
            size = img.size
            img.close()
            return size

        except Exception as e:
            if overlay_clip:
                overlay_clip.close()
            self.log_video(f"  -> 错误: 使用MoviePy创建叠加图片失败: {e}")
            return None
    def start_video_processing_hybrid(self):
        """启动混合模式处理流程的线程"""
        self.video_stop_event.clear()
        self.start_video_button.configure(command=self.start_video_processing_hybrid, state="disabled")  # 确保按钮指向正确
        self.stop_video_button.configure(state="normal")
        self.log_video("", clear=True)
        threading.Thread(target=self.run_video_logic_hybrid, daemon=True).start()

    # 请将这个新函数添加到 App 类的任意位置
    def _toggle_image_processing_mode(self):
        """根据“单一模式”开关的状态，切换图片处理UI的输入控件。"""
        if self.image_single_mode_switch.get() == 1:  # 如果单一模式开启
            # 禁用旧的输入
            self.image_folder_entry.configure(state="disabled")
            self.image_num_groups_entry.configure(state="disabled")
            self.image_phone_serial_entry.configure(state="disabled")
            # 启用新的输入
            for widget in self.single_base_folder_row.winfo_children():
                widget.configure(state="normal")
        else:  # 如果单一模式关闭
            # 启用旧的输入
            self.image_folder_entry.configure(state="normal")
            self.image_num_groups_entry.configure(state="normal")
            # 根据手机序号框的内容决定是否启用组数框
            self._update_exclusive_entry_state(self.image_phone_serial_entry, self.image_num_groups_entry)
            # 禁用新的输入
            for widget in self.single_base_folder_row.winfo_children():
                widget.configure(state="disabled")
    def run_video_logic_hybrid(self):
        try:
            config = self.get_video_config_from_gui()
            if not config: self.after(0, self._reset_video_buttons); return

            video_folder = self.video_folder_entry.get()
            output_folder = self.video_output_folder_entry.get()
            all_input_text = self.video_text_input_box.get("1.0", "end-1c")
            use_gpu = self.video_use_gpu_switch.get() == 1
            is_remix_mode = self.video_random_remix_switch.get() == 1

            text_lines = [line.strip() for line in all_input_text.splitlines() if line.strip()]
            if not text_lines:
                self.log_video("错误: 文案输入为空。");
                self.after(0, self._reset_video_buttons);
                return

            durations_str = self.video_durations_entry.get()
            durations_list = [self._safe_float_convert(d, 0) for d in durations_str.split('.') if d.strip()]

            all_original_videos = [os.path.join(video_folder, f) for f in os.listdir(video_folder) if
                                   f.lower().endswith(('.mp4', '.mov', '.avi'))]
            if not all_original_videos:
                self.log_video("错误: 视频文件夹中没有任何视频文件。");
                return

            # --- 统一的模式判断与预检逻辑 ---
            group_names = []
            num_groups_str = self.video_num_groups_entry.get().strip()
            phone_serials_str = self.video_phone_serial_entry.get().strip()
            if phone_serials_str:
                group_names = [name.strip() for name in phone_serials_str.split('.') if name.strip()]
                if not group_names: self.log_video("错误: 手机序号输入无效。"); self.after(0,
                                                                                          self._reset_video_buttons); return
                self.log_video(f"手机序号模式激活，将创建 {len(group_names)} 个指定名称的文件夹。")
            elif num_groups_str:
                try:
                    num_groups = self._safe_int_convert(num_groups_str, 0)
                    if num_groups <= 0: raise ValueError
                    group_names = [f"group_{i + 1}" for i in range(num_groups)]
                    self.log_video(f"组数模式激活，将创建 {len(group_names)} 个文件夹。")
                except ValueError:
                    self.log_video("错误: '生成组数' 必须是一个有效的正整数。");
                    self.after(0,
                               self._reset_video_buttons);
                    return
            else:
                self.log_video("错误: '生成组数' 或 '手机序号' 必须填写一个。");
                self.after(0, self._reset_video_buttons);
                return

            # 只有在顺序模式下，才需要严格检查视频数量
            if not is_remix_mode:
                total_videos_needed = len(group_names) * len(text_lines)
                if len(all_original_videos) < total_videos_needed:
                    self.log_video(
                        f"错误: 视频不足！需要 {total_videos_needed} 个, 但只有 {len(all_original_videos)} 个。");
                    self.after(0, self._reset_video_buttons);
                    return

            if os.path.exists(output_folder): shutil.rmtree(output_folder)
            os.makedirs(output_folder)

            random.shuffle(all_original_videos)
            video_pool = list(all_original_videos)

            # --- 核心修复：统一的主处理循环 ---
            for idx, group_name in enumerate(group_names):
                if self.video_stop_event.is_set(): break

                group_folder = os.path.join(output_folder, group_name)
                os.makedirs(group_folder, exist_ok=True)
                self.log_video(f"\n---=== 开始处理组: {group_name} ===---")

                # 内层循环，遍历每一行文案
                for j, text_line in enumerate(text_lines):
                    if self.video_stop_event.is_set(): break

                    input_video_path = None
                    temp_files_for_this_task = []
                    is_current_task_remix = False
                    originals_to_delete_in_remix = []  # 新增: 保存本次混剪用到的原始视频

                    # 彻底修复误删文件的关键点
                    try:
                        if is_remix_mode:
                            # 混剪模式：为当前文案动态生成一个混剪视频
                            if j >= len(durations_list):
                                self.log_video(
                                    f"  -> 警告: 时长列表数量少于文案行数，第 {j + 1} 条文案缺少对应时长，已跳过。")
                                continue
                            target_duration = durations_list[j] + 1
                            # 修改: 接收返回的第三个值
                            input_video_path, temp_files_from_remix, originals_to_delete_in_remix = self._create_random_remix_clip(
                                target_duration,
                                video_pool,
                                group_folder,
                                self.log_video)
                            if not input_video_path:
                                self.log_video(f"  ❌ 错误: 为文案 '{text_line[:10]}...' 创建混剪视频失败，跳过此任务。")
                                continue
                            temp_files_for_this_task.extend(temp_files_from_remix)
                            temp_files_for_this_task.append(input_video_path)  # 混剪出的视频也是临时文件
                            is_current_task_remix = True
                        else:
                            # 顺序模式：按顺序取一个视频
                            video_index = idx * len(text_lines) + j
                            # 检查video_pool是否足够
                            if video_index >= len(video_pool):
                                self.log_video(
                                    f"  ❌ 错误: 视频池中视频不足，无法继续。需要索引 {video_index}，但池大小为 {len(video_pool)}。")
                                # 强制停止所有后续任务
                                self.video_stop_event.set()
                                break
                            input_video_path = video_pool[video_index]

                        # 准备时长参数
                        duration_param = ""
                        if durations_list and not is_remix_mode:
                            current_duration = durations_list[j % len(durations_list)]
                            if current_duration > 0:
                                adjusted_duration = current_duration
                                duration_param = f"-to {adjusted_duration}"
                                self.log_video(f"  -> 将应用时长: {adjusted_duration}s")

                        # 统一调用处理函数
                        output_name = f"{group_name}_{j + 1}.mp4"
                        self._apply_text_to_video(input_video_path, group_folder, output_name, text_line, config,
                                                  use_gpu,
                                                  duration_param, temp_files_for_this_task)

                    except Exception as e:
                        self.log_video(
                            f"  -> ❌ 处理视频 {os.path.basename(input_video_path)} 时发生致命错误，文件未被删除。")

                    else:
                        # 仅在 try 块没有发生任何错误时，才执行这里的代码
                        if not is_remix_mode and input_video_path and os.path.exists(input_video_path):
                            try:
                                os.remove(input_video_path)
                                self.log_video(f"  -> ✅ 源视频已删除: {os.path.basename(input_video_path)}")
                            except OSError as e:
                                self.log_video(f"  -> ❌ 删除源视频时发生异常: {e}")

                        # 新增: 混剪模式下的删除逻辑
                        elif is_remix_mode:
                            self.log_video(f"  -> [混剪] 正在删除本次混剪使用过的源视频...")
                            for original_path in originals_to_delete_in_remix:
                                if os.path.exists(original_path):
                                    try:
                                        os.remove(original_path)
                                        # 同时从主视频池中移除，防止后续任务出错
                                        if original_path in video_pool:
                                            video_pool.remove(original_path)
                                        self.log_video(f"    -> ✅ 已删除: {os.path.basename(original_path)}")
                                    except OSError as e:
                                        self.log_video(
                                            f"    -> ❌ 删除源视频 {os.path.basename(original_path)} 时发生异常: {e}")

            if not self.video_stop_event.is_set():
                self.log_video("\n---=== 所有任务处理完毕！ ===---")
        except Exception as e:
            self.log_video(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_video_buttons)
    def _apply_text_to_video(self, input_video_path, group_folder, video_name, text_line, config, use_gpu,
                             duration_param, temp_files_to_delete):
        """【最终修正版】将原有的单个视频处理逻辑封装起来，并修复所有已知错误"""
        output_video_path = os.path.join(group_folder, f"processed_{os.path.splitext(video_name)[0]}.mp4")
        self.log_video(f"\n- 正在处理: {os.path.basename(input_video_path)}")

        overlay_pngs_info = []
        try:
            corrected_video_path, temp_orientation_file = self._preprocess_video_orientation(input_video_path,
                                                                                             group_folder,
                                                                                             self.log_video)
            if temp_orientation_file:
                temp_files_to_delete.append(temp_orientation_file)

            if not corrected_video_path:
                self.log_video(f"  -> 预处理失败，跳过视频。")
                # 抛出异常以确保上层逻辑能捕获到失败状态
                raise RuntimeError("Video preprocessing failed.")

            text_parts = [p.strip() for p in text_line.split('&') if p.strip()]
            if text_parts:
                self.log_video("  -> 步骤1: 使用MoviePy生成高质量叠加图片...")
                for k, text_part in enumerate(text_parts):
                    part_config = config['主文案'] if k == 0 else config['次文案'][k - 1]
                    png_path = os.path.join(group_folder, f"overlay_{k}_{random.randint(1000, 9999)}.png")
                    # 使用更可靠的 Pillow 引擎创建图片对象
                    overlay_pil_image = self._create_overlay_as_pillow_image(text_part, config['共享样式'], part_config,
                                                                             (1080, 1920))
                    # 保存图片文件
                    overlay_pil_image.save(png_path, 'PNG')
                    # 获取尺寸
                    size = overlay_pil_image.size
                    if not size: raise ValueError(f"文案块 {k + 1} 图片生成失败")
                    overlay_pngs_info.append({'path': png_path, 'size': size, 'config': part_config})

            safe_ffmpeg_path = f'"{os.path.normpath(self._find_executable("ffmpeg"))}"'
            safe_corrected_video_path = f'"{os.path.normpath(corrected_video_path)}"'
            safe_output_path = f'"{os.path.normpath(output_video_path)}"'

            ffmpeg_inputs = [f'-i {safe_corrected_video_path}']
            for png_info in overlay_pngs_info:
                ffmpeg_inputs.append(f'-i "{os.path.normpath(png_info["path"])}"')

            if not overlay_pngs_info:
                command_string = f'{safe_ffmpeg_path} -y -i {safe_corrected_video_path} -c copy {safe_output_path}'
            else:
                filter_chains, last_stream, last_y, last_h = [], "[0:v]", 0, 0
                for k, png_info in enumerate(overlay_pngs_info):
                    size, part_config = png_info['size'], png_info['config']
                    y_pos = part_config['位置']['垂直位置 (y)'] if k == 0 else last_y + last_h + part_config[
                        '相对Y轴偏移']
                    x_pos_val = part_config['位置']['水平位置 (x)'] if k == 0 else 'center'
                    x_pos = "(W-w)/2" if str(x_pos_val) == 'center' else str(x_pos_val)
                    output_tag = "[v_out]" if k == len(overlay_pngs_info) - 1 else f"[v{k + 1}]"
                    filter_chains.append(f"{last_stream}[{k + 1}:v]overlay={x_pos}:{y_pos}{output_tag}")
                    last_stream, last_y, last_h = f"[v{k + 1}]", y_pos, size[1]

                filter_complex_string = ";".join(filter_chains)
                output_codec = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
                command_string = f'{safe_ffmpeg_path} -y {" ".join(ffmpeg_inputs)} {duration_param} -filter_complex "{filter_complex_string}" -map "[v_out]" -map 0:a? -c:v {output_codec} -preset fast -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart {safe_output_path}'

            self.log_video(f"  -> 步骤2: 使用FFmpeg高速合成...");
            creation_flags = 0
            if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

            # 彻底修复编码问题的关键点
            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8',
                           errors='ignore', creationflags=creation_flags)

            self.log_video(f"  -> 成功! 输出文件: {os.path.basename(output_video_path)}")

        except Exception as e:
            self.log_video(f"  -> 错误: {e}")
            # traceback.print_exc() # 调试时可以取消注释
            # 抛出异常，让调用它的上层函数知道处理失败了
            raise e
        finally:
            files_to_clean = temp_files_to_delete + [item['path'] for item in overlay_pngs_info]
            for f in files_to_clean:
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def _freeze_worker(self, ffmpeg, ffprobe, input_path, output_path, freeze_duration, temp_folder):
        try:
            if not ffprobe:
                self.log_composite("  -> 错误: 缺少 ffprobe 路径，无法添加定格。")
                return False

            # --- 核心修复：为所有 subprocess.run 定义并应用 creationflags ---
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            # 调用 1: 获取视频时长
            cmd_probe = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of",
                         "default=noprint_wrappers=1:nokey=1", input_path]
            result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True, creationflags=creation_flags)
            video_duration = float(result.stdout.strip())

            # 调用 2: 提取最后一帧
            unique_id = hash(input_path)
            last_frame_img = os.path.join(temp_folder, f"frame_{unique_id}.png")
            seek_time = max(0, video_duration - 0.1)
            cmd_get_frame = [ffmpeg, "-y", "-ss", str(seek_time), "-i", input_path, "-vframes", "1", last_frame_img]
            subprocess.run(cmd_get_frame, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=creation_flags)
            self.log_composite("  -> [定格] 步骤1: 成功提取最后一帧。")

            # 调用 3: 创建定格视频
            freeze_video_clip = os.path.join(temp_folder, f"freeze_{unique_id}.mp4")
            cmd_make_freeze = [
                ffmpeg, "-y", "-loop", "1", "-i", last_frame_img,
                "-c:v", "libx264", "-t", str(freeze_duration), "-pix_fmt", "yuv420p", "-an",
                freeze_video_clip
            ]
            subprocess.run(cmd_make_freeze, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=creation_flags)
            self.log_composite(f"  -> [定格] 步骤2: 成功创建 {freeze_duration} 秒静音定格片段。")

            # 调用 4: 检查原视频是否有音频
            cmd_probe_audio = [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                               "-of", "default=noprint_wrappers=1:nokey=1", input_path]
            audio_result = subprocess.run(cmd_probe_audio, check=True, capture_output=True, text=True,
                                          creationflags=creation_flags)
            has_audio = bool(audio_result.stdout.strip())

            cmd_concat = []
            if has_audio:
                filter_str = "[0:v][1:v]concat=n=2:v=1[v];[0:a]anull[a]"
                map_v_str, map_a_str = "[v]", "[a]"
                cmd_concat = [
                    ffmpeg, "-y", "-i", input_path, "-i", freeze_video_clip,
                    "-filter_complex", f"{filter_str}",
                    "-map", map_v_str, "-map", map_a_str, "-c:a", "aac",
                    output_path
                ]
            else:  # 如果原视频没有音频
                cmd_concat = [
                    ffmpeg, "-y", "-i", input_path, "-i", freeze_video_clip,
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]",
                    output_path
                ]

            # 调用 5: 拼接最终视频
            subprocess.run(cmd_concat, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=creation_flags)
            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore').strip()
            self.log_composite(f"  ❌ [定格] FFmpeg处理失败:\n" + error_msg)
            return False
        except Exception as e:
            self.log_composite(f"  ❌ [定格] 处理中发生未知错误: {e}")
            return False
        finally:
            # --- 核心修复：在这里统一清理所有临时文件 ---
            if last_frame_img and os.path.exists(last_frame_img):
                try:
                    os.remove(last_frame_img)
                except OSError as e:
                    self.log_composite(f"  -> 警告: 清理临时帧图片失败: {e}")
            if freeze_video_clip and os.path.exists(freeze_video_clip):
                try:
                    os.remove(freeze_video_clip)
                except OSError as e:
                    self.log_composite(f"  -> 警告: 清理临时定格视频失败: {e}")
    def log_composite(self, message, clear=False):
        self.after(0, self._update_log, self.composite_log_textbox, message, clear)

    def setup_greenscreen_composite_workflow(self):
        """创建“绿幕合成”功能的UI界面 (恢复混剪开关并修正布局)"""
        tab = self.main_tabview.tab("绿幕合成")

        main_frame = ctk.CTkFrame(tab, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        path_frame = ctk.CTkFrame(main_frame)
        path_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(path_frame, text="操作步骤", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                        pady=(5, 10))
        self.create_folder_selection_row(path_frame, "1. 选择绿幕文件夹:", "...", "gs_composite_source_folder_entry")
        self.create_folder_selection_row(path_frame, "2. 选择背景文件夹:", "...", "gs_composite_bg_folder_entry")
        self.create_folder_selection_row(path_frame, "3. 选择输出文件夹:", "...", "gs_composite_output_folder_entry")

        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.pack(fill="x", pady=(15, 5), ipady=10)
        settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(settings_frame, text="生成组数:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.composite_num_groups_entry = ctk.CTkEntry(settings_frame)
        self.composite_num_groups_entry.insert(0, "1")
        self.composite_num_groups_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(settings_frame, text="手机序号(用.分隔):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.composite_phone_serial_entry = ctk.CTkEntry(settings_frame, placeholder_text="例如: A-1.A-2.B-1")
        self.composite_phone_serial_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        self.composite_num_groups_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.composite_num_groups_entry, self.composite_phone_serial_entry))
        self.composite_phone_serial_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.composite_phone_serial_entry, self.composite_num_groups_entry))

        # --- [核心修改] 恢复“随机拼接”开关 ---
        self.composite_remix_switch = ctk.CTkSwitch(settings_frame, text="开启随机拼接模式 (背景由多片段合成)")
        self.composite_remix_switch.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="w")
        # --- 修改结束 ---

        calibrate_button = ctk.CTkButton(settings_frame, text="校准颜色 (推荐)", command=self.composite_calibrate_color)
        calibrate_button.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.composite_color_status_label = ctk.CTkLabel(settings_frame, text="颜色: 默认标准绿", text_color="orange")
        self.composite_color_status_label.grid(row=3, column=1, padx=10, pady=5, sticky="w")

        # ... 后续其他UI控件保持不变 ...
        ctk.CTkLabel(settings_frame, text="相似度 (0.01-1.0):").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.gs_composite_similarity_slider = ctk.CTkSlider(settings_frame, from_=0.01, to=1.0, number_of_steps=99)
        self.gs_composite_similarity_slider.set(0.2)
        self.gs_composite_similarity_slider.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(settings_frame, text="边缘羽化 (0.0-1.0):").grid(row=5, column=0, padx=10, pady=5, sticky="w")
        self.gs_composite_blend_slider = ctk.CTkSlider(settings_frame, from_=0.0, to=1.0, number_of_steps=100)
        self.gs_composite_blend_slider.set(0.1)
        self.gs_composite_blend_slider.grid(row=5, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(settings_frame, text="去绿边强度 (0.0-1.0):").grid(row=6, column=0, padx=10, pady=5, sticky="w")
        self.gs_composite_despill_slider = ctk.CTkSlider(settings_frame, from_=0.0, to=1.0, number_of_steps=100)
        self.gs_composite_despill_slider.set(0.5)
        self.gs_composite_despill_slider.grid(row=6, column=1, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(settings_frame, text="输出质量 (CRF/CQ):").grid(row=7, column=0, padx=10, pady=5, sticky="w")
        self.gs_composite_quality_slider = ctk.CTkSlider(settings_frame, from_=18, to=30, number_of_steps=12)
        self.gs_composite_quality_slider.set(24)
        self.gs_composite_quality_slider.grid(row=7, column=1, padx=10, pady=5, sticky="ew")
        self.gs_composite_use_gs_audio_switch = ctk.CTkSwitch(settings_frame,
                                                              text="使用绿幕视频的音频 (默认使用背景音频)")
        self.gs_composite_use_gs_audio_switch.grid(row=9, column=0, columnspan=2, padx=10, pady=(15, 5), sticky="w")
        self.gs_composite_gpu_switch = ctk.CTkSwitch(settings_frame, text="启用GPU加速编码")
        self.gs_composite_gpu_switch.grid(row=10, column=0, padx=10, pady=(15, 5), sticky="w")
        self.composite_freeze_switch = ctk.CTkSwitch(settings_frame, text="开启结尾定格")
        self.composite_freeze_switch.grid(row=11, column=0, padx=10, pady=(10, 5), sticky="w")
        freeze_entry_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        freeze_entry_frame.grid(row=11, column=1, sticky="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(freeze_entry_frame, text="定格时长(秒):").pack(side="left")
        self.composite_freeze_duration_entry = ctk.CTkEntry(freeze_entry_frame, width=60)
        self.composite_freeze_duration_entry.insert(0, "3")
        self.composite_freeze_duration_entry.pack(side="left", padx=5)

        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(15, 5))
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.composite_start_button = ctk.CTkButton(button_frame, text="开始高速合成", height=40,
                                                    command=self.start_composite_processing)
        self.composite_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.composite_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                   command=self.stop_composite_processing, state="disabled",
                                                   fg_color="red", hover_color="darkred")
        self.composite_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.composite_log_textbox = ctk.CTkTextbox(main_frame, state="disabled", text_color="#A9A9A9")
        self.composite_log_textbox.pack(expand=True, fill="both", pady=(10, 5))

    def _create_random_remix_background(self, bg_video_pool, target_duration, temp_dir):
        """为混剪模式生成一个随机拼接的背景视频 (修改版：返回用过的原始文件列表)"""
        self.log_composite(f"  -> [混剪] 开始为 {target_duration:.2f}s 的时长随机拼接背景...")
        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            self.log_composite("  ❌ [混剪] 错误: 找不到 ffmpeg 或 ffprobe。")
            return None, [], []  # 返回三个值

        creation_flags = 0
        if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

        concat_list_path = os.path.join(temp_dir, f"remix_list_{random.randint(1000, 9999)}.txt")
        temp_files_created = [concat_list_path]
        original_videos_used = []  # <--- 新增：用于记录用过的原始文件
        current_duration = 0

        local_video_pool = list(bg_video_pool)
        random.shuffle(local_video_pool)

        with open(concat_list_path, 'w', encoding='utf-8') as f:
            while current_duration < target_duration:
                if not local_video_pool:
                    self.log_composite("    -> [混剪] 背景素材不足，开始重复使用...")
                    local_video_pool = list(bg_video_pool)
                    random.shuffle(local_video_pool)
                    if not local_video_pool: self.log_composite("    -> [混剪] 致命错误：背景池为空。"); break

                video_to_use = local_video_pool.pop(0)
                try:
                    cmd_probe = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", os.path.normpath(video_to_use)]
                    result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True,
                                            creationflags=creation_flags)
                    clip_duration = float(result.stdout.strip())
                    if clip_duration <= 0: continue

                    # <--- 核心修改：记录用过的原始文件 --->
                    original_videos_used.append(video_to_use)

                    safe_path = os.path.normpath(video_to_use).replace('\\', '/')
                    f.write(f"file '{safe_path}'\n")
                    self.log_composite(
                        f"    -> [混剪] 添加片段: {os.path.basename(video_to_use)} ({clip_duration:.2f}s)")
                    current_duration += clip_duration
                except Exception as e:
                    self.log_composite(f"    -> [混剪] 警告: 处理背景片段 {os.path.basename(video_to_use)} 失败: {e}")
                    if video_to_use in original_videos_used:
                        original_videos_used.remove(video_to_use)  # 如果失败，就从已用列表移除
                    continue

        remix_output_path = os.path.join(temp_dir, f"remix_bg_{random.randint(1000, 9999)}.mp4")
        temp_files_created.append(remix_output_path)

        command = [
            ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', concat_list_path,
            '-t', str(target_duration), '-c:v', 'copy', '-an', os.path.normpath(remix_output_path)
        ]

        try:
            self.log_composite("  -> [混剪] 正在调用FFmpeg高速拼接背景视频...")
            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)
            self.log_composite(f"  -> ✅ [混剪] 成功生成临时背景视频。")
            # <--- 核心修改：返回三个值 --->
            return remix_output_path, temp_files_created, original_videos_used
        except subprocess.CalledProcessError as e:
            self.log_composite(f"  ❌ [混剪] FFmpeg 拼接失败:\n{e.stderr.strip()}")
            # <--- 核心修改：返回三个值 --->
            return None, temp_files_created, []
    def start_video_processing_ffmpeg(self):
        self.video_stop_event.clear()
        self.start_video_button.configure(state="disabled")
        self.stop_video_button.configure(state="normal")
        self.log_video("", clear=True)
        # 启动一个新线程来运行我们全新的FFmpeg逻辑
        threading.Thread(target=self.run_video_logic_ffmpeg, daemon=True).start()

    def get_video_config_from_gui(self):
        """【最终健壮版】确保从所有UI控件中正确读取配置值，并使用中文键名。"""
        try:
            # --- 读取共享样式，使用 self 调用安全转换函数 ---
            shared_style_config = {
                "字体文件": self.video_shared_font_file_entry.get(),
                "字体大小": self._safe_int_convert(self.video_shared_size_entry.get(), 60),
                "最大宽度比例": self._safe_float_convert(self.video_shared_max_width_ratio_entry.get(), 0.9),
                "左右内边距": self._safe_int_convert(self.video_shared_padding_horizontal_entry.get(), 30),
                "垂直内边距": self._safe_int_convert(self.video_shared_padding_vertical_entry.get(), 25),
                "描边粗细": self._safe_int_convert(self.video_shared_stroke_width_entry.get(), 2),
                "背景圆角半径": self._safe_int_convert(self.video_shared_corner_radius_entry.get(), 20),
                "禁用背景": self.video_no_bg_switch.get() == 1
            }

            x_pos_val = self.video_main_pos_x_entry.get().strip()
            x_pos = x_pos_val if x_pos_val.lower() == 'center' else self._safe_int_convert(x_pos_val, 0)

            main_text_config = {
                "位置": {
                    "水平位置 (x)": x_pos,
                    "垂直位置 (y)": self._safe_int_convert(self.video_main_pos_y_entry.get(), 150)
                },
                "颜色": {
                    "文字颜色": self.video_main_color_text_value,
                    "描边颜色": self.video_main_color_stroke_value,
                    "背景颜色": self.video_main_color_bg_value
                }
            }

            sub_texts_config = [
                {
                    "相对Y轴偏移": self._safe_int_convert(self.video_sub1_offset_y_entry.get(), 20),
                    "颜色": {
                        "文字颜色": self.video_sub1_color_text_value,
                        "描边颜色": self.video_sub1_color_stroke_value,
                        "背景颜色": self.video_sub1_color_bg_value
                    }
                },
                {
                    "相对Y轴偏移": self._safe_int_convert(self.video_sub2_offset_y_entry.get(), 30),
                    "颜色": {
                        "文字颜色": self.video_sub2_color_text_value,
                        "描边颜色": self.video_sub2_color_stroke_value,
                        "背景颜色": self.video_sub2_color_bg_value
                    }
                }
            ]

            return {"共享样式": shared_style_config, "主文案": main_text_config, "次文案": sub_texts_config}

        except Exception as e:
            self.log_video(f"❌ 视频配置错误: {e}. 请检查'参数配置'中的所有输入是否正确。")
            return None

    def run_video_logic_ffmpeg(self):
        """【高性能模式-Airdrop兼容最终修复版】"""
        try:
            config = self.get_video_config_from_gui()
            if not config:
                self.after(0, self._reset_video_buttons)
                return

            video_folder = self.video_folder_entry.get()
            output_folder = self.video_output_folder_entry.get()
            all_input_text = self.video_text_input_box.get("1.0", "end-1c")
            use_gpu = self.video_use_gpu_switch.get() == 1
            num_groups = int(self.video_num_groups_entry.get())

            text_lines = [line.strip() for line in all_input_text.splitlines() if line.strip()]
            if not text_lines:
                self.log_video("错误: 文案输入为空。")
                self.after(0, self._reset_video_buttons)
                return

            num_texts_per_group = len(text_lines)
            total_videos_needed = num_texts_per_group * num_groups
            all_available_videos = [f for f in os.listdir(video_folder) if f.lower().endswith(('.mp4', '.mov', '.avi'))]
            if len(all_available_videos) < total_videos_needed:
                self.log_video(f"错误: 视频不足！需要 {total_videos_needed} 个, 但只有 {len(all_available_videos)} 个。")
                self.after(0, self._reset_video_buttons)
                return
            random.shuffle(all_available_videos)
            videos_to_process = all_available_videos[:total_videos_needed]
            if os.path.exists(output_folder): shutil.rmtree(output_folder)
            os.makedirs(output_folder)
            self.log_video("🚀 已切换到FFmpeg高性能模式。")

            shared_style = config['共享样式']
            group_count = 0
            for i in range(0, len(videos_to_process), num_texts_per_group):
                if self.video_stop_event.is_set(): break
                group_count += 1
                video_chunk = videos_to_process[i:i + num_texts_per_group]
                group_folder = os.path.join(output_folder, f"group_{group_count}")
                os.makedirs(group_folder, exist_ok=True)
                self.log_video(f"\n---=== 开始处理第 {group_count} 组 ===---")

                for j, video_name in enumerate(video_chunk):
                    if self.video_stop_event.is_set(): break
                    input_video_path = os.path.join(video_folder, video_name)
                    output_video_path = os.path.join(group_folder, f"processed_{os.path.splitext(video_name)[0]}.mp4")
                    text_line = text_lines[j]
                    self.log_video(f"\n[{j + 1}/{len(video_chunk)}] 正在处理: {video_name}")

                    temp_video_file = None
                    temp_text_files = []
                    try:
                        corrected_video_path, temp_video_file = self._preprocess_video_orientation(
                            input_video_path, group_folder, self.log_video
                        )
                        if not corrected_video_path:
                            self.log_video(f"  -> 预处理失败，跳过视频: {video_name}")
                            continue

                        text_parts = [part.strip() for part in text_line.split('&') if part.strip()]
                        all_filters = []
                        current_y_bottom = 0

                        if text_parts:
                            # 将第一部分（或全部内容）作为主文案
                            main_text = text_parts[0]
                            main_config = config['主文案']
                            x_pos_val = main_config['位置']['水平位置 (x)']
                            x_pos_str = str(x_pos_val)
                            current_y = main_config['位置']['垂直位置 (y)']
                            main_pos = {'x': f"(w-text_w)/2" if x_pos_str == 'center' else x_pos_str,
                                        'y': str(current_y)}
                            main_filter, main_box_h, temp_txt = self._create_ffmpeg_drawtext_filter(
                                main_text, shared_style['字体文件'], shared_style['字体大小'],
                                shared_style['最大宽度比例'], shared_style['禁用背景'],
                                shared_style['垂直内边距'], shared_style['描边粗细'],
                                main_config['颜色'], main_pos, group_folder
                            )
                            if main_filter: all_filters.append(main_filter)
                            if temp_txt: temp_text_files.append(temp_txt)
                            current_y_bottom = current_y + main_box_h

                            # 如果存在'&'且分割出了多个部分，则处理次文案
                            if len(text_parts) > 1:
                                sub_configs = config.get('次文案', [])
                                # 从第二部分开始作为次文案
                                for k, sub_text in enumerate(text_parts[1:]):
                                    if k >= len(sub_configs): break
                                    sub_config = sub_configs[k]
                                    current_y = current_y_bottom + sub_config['相对Y轴偏移']
                                    sub_pos = {'x': '(w-text_w)/2', 'y': str(current_y)}
                                    sub_filter, sub_box_h, temp_txt = self._create_ffmpeg_drawtext_filter(
                                        sub_text, shared_style['字体文件'], shared_style['字体大小'],
                                        shared_style['最大宽度比例'], shared_style['禁用背景'],
                                        shared_style['垂直内边距'], shared_style['描边粗细'],
                                        sub_config['颜色'], sub_pos, group_folder
                                    )
                                    if sub_filter: all_filters.append(sub_filter)
                                    if temp_txt: temp_text_files.append(temp_txt)
                                    current_y_bottom = current_y + sub_box_h

                        vf_string = ",".join(all_filters) if all_filters else "null"

                        safe_ffmpeg_path = str(self._find_executable("ffmpeg")).replace('\\', '/')
                        safe_corrected_video_path = str(corrected_video_path).replace('\\', '/')
                        safe_output_video_path = str(output_video_path).replace('\\', '/')

                        output_codec = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
                        preset = 'fast'

                        # 【兼容性修复】在这里加入 -pix_fmt yuv420p 和 -movflags +faststart
                        command_string = (
                            f'"{safe_ffmpeg_path}" -y -i "{safe_corrected_video_path}" '
                            f'-vf "{vf_string}" '
                            f'-c:v {output_codec} -preset {preset} -pix_fmt yuv420p '
                            f'-c:a aac -b:a 192k -movflags +faststart '
                            f'"{safe_output_video_path}"'
                        )

                        self.log_video(f"  -> 使用FFmpeg引擎高速处理...")
                        creation_flags = 0
                        if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW
                        subprocess.run(command_string, shell=True, check=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, creationflags=creation_flags)
                        self.log_video(f"  -> 成功! 输出文件: {os.path.basename(output_video_path)}")

                        os.remove(input_video_path)
                        self.log_video(f"  -> ✅ 源视频已删除: {video_name}")

                    except Exception as e:
                        self.log_video(f"  -> 错误: FFmpeg处理视频 {video_name} 时发生严重错误: {e}")
                        if hasattr(e, 'stderr') and e.stderr:
                            self.log_video(
                                f"  -> [FFmpeg错误日志]: {e.stderr.decode('utf-8', errors='ignore').strip()}")
                    finally:
                        if temp_video_file and os.path.exists(temp_video_file):
                            os.remove(temp_video_file)
                        for txt_file in temp_text_files:
                            if os.path.exists(txt_file):
                                os.remove(txt_file)
                        if temp_text_files or temp_video_file:
                            self.log_video(f"  - 已清理临时文件。")

            self.log_video("\n---=== 所有任务处理完毕！ ===---")
        except Exception as e:
            self.log_video(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_video_buttons)
    def _ffmpeg_escape_path(self, path):
        """
        【终极转义V3版】为FFmpeg滤镜中使用的Windows路径进行最彻底和可靠的转义。
        这是为了在 shell=True 环境下，构建一个绝对不会出错的命令字符串。
        """
        # 1. 首先，将所有的反斜杠 \ 统一替换为正斜杠 /
        escaped_path = path.replace('\\', '/')

        # 2. 然后，将路径中的冒号 : 无条件地转义为 \:
        #    在Python中，为了在字符串中得到一个反斜杠，需要写成 \\
        escaped_path = escaped_path.replace(':', '\\:')

        # 3. 最后，在整个转义后的路径字符串两边，加上单引号
        return f"'{escaped_path}'"

    def _composite_get_video_files(self, folder_path):
        """递归地从文件夹中获取所有支持格式的视频文件路径。"""
        SUPPORTED_VIDEO_FORMATS = ('.mp4', '.avi', '.mov', '.mkv', '.flv')
        video_files = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(SUPPORTED_VIDEO_FORMATS):
                    video_files.append(os.path.join(root, file))
        return video_files

    def _ghost_freeze_worker(self, ffmpeg, ffprobe, input_path, output_path, freeze_duration):
        """【最终修正版】忠实地实现用户提供的“幽灵定格”逻辑，以音频时长驱动视频定格"""
        try:
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            safe_ffmpeg = f'"{os.path.normpath(ffmpeg)}"'
            safe_ffprobe = f'"{os.path.normpath(ffprobe)}"'
            safe_input_path = f'"{os.path.normpath(input_path)}"'
            safe_output_path = f'"{os.path.normpath(output_path)}"'

            # 1. 获取原视频的时长
            cmd_probe_duration_str = f'{safe_ffprobe} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {safe_input_path}'
            result = subprocess.run(cmd_probe_duration_str, shell=True, check=True, capture_output=True, text=True,
                                    creationflags=creation_flags)
            original_duration = float(result.stdout.strip())

            # 2. 计算最终的目标总时长
            target_duration = original_duration + freeze_duration

            # 3. 检查是否存在音频流
            cmd_probe_audio_str = f'{safe_ffprobe} -v error -select_streams a -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 {safe_input_path}'
            audio_result = subprocess.run(cmd_probe_audio_str, shell=True, check=True, capture_output=True, text=True,
                                          creationflags=creation_flags)
            has_audio = bool(audio_result.stdout.strip())

            command_string = ""
            if has_audio:
                self.log_composite(f"  -> [幽灵定格] 检测到音频，使用apad填充至 {target_duration:.2f}s...")
                # 核心逻辑：使用apad滤镜将音频[0:a]填充到目标总时长，视频流(-c:v copy)直接复制
                # FFmpeg会自动用视频最后一帧填充多出来的时长
                filter_complex = f'"[0:a]apad,atrim=0:{target_duration}[a_padded]"'
                command_string = f'{safe_ffmpeg} -y -i {safe_input_path} -filter_complex {filter_complex} -map 0:v -map "[a_padded]" -c:v copy -c:a aac {safe_output_path}'
            else:
                self.log_composite(f"  -> [幽灵定格] 未检测到音频，创建 {target_duration:.2f}s 的静音音轨...")
                # 核心逻辑：创建一个指定长度的虚拟静音源，与原始视频流合并
                command_string = f'{safe_ffmpeg} -y -i {safe_input_path} -f lavfi -t {target_duration} -i anullsrc=r=44100:cl=stereo -map 0:v -map 1:a -c:v copy -c:a aac -shortest {safe_output_path}'

            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)
            return True

        except subprocess.CalledProcessError as e:
            self.log_composite(f"  ❌ [幽灵定格] FFmpeg处理失败:\n{e.stderr.strip()}")
            return False
        except Exception as e:
            self.log_composite(f"  ❌ [幽灵定格] 处理中发生未知错误: {e}")
            return False
        finally:
            # 这个函数只负责生成最终文件，临时文件的清理由调用它的 run_composite_logic 负责
            pass
    def start_composite_processing(self):
        self.composite_start_button.configure(state="disabled")
        self.composite_stop_button.configure(state="normal")
        self.composite_stop_event.clear()
        self.log_composite("开始处理...", clear=True)
        threading.Thread(target=self.run_composite_logic, daemon=True).start()

    def stop_composite_processing(self):
        self.log_composite("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.composite_stop_event.set()
        self.composite_stop_button.configure(state="disabled")

    def _reset_composite_buttons(self):
        self.composite_start_button.configure(state="normal")
        self.composite_stop_button.configure(state="disabled")

    def _composite_select_color_callback(self, event, x, y, flags, param):
        """鼠标回调函数，用于处理框选操作 (FFmpeg适配版)"""
        frame = param['frame']
        clone = frame.copy()

        if event == cv2.EVENT_LBUTTONDOWN:
            self.cropping_ref_point = [(x, y)]
            self.cropping_active = True
        elif event == cv2.EVENT_LBUTTONUP:
            self.cropping_ref_point.append((x, y))
            self.cropping_active = False
            cv2.rectangle(clone, self.cropping_ref_point[0], self.cropping_ref_point[1], (0, 255, 0), 2)
            cv2.imshow("image", clone)
            if len(self.cropping_ref_point) == 2:
                x0, y0 = min(self.cropping_ref_point[0][0], self.cropping_ref_point[1][0]), min(
                    self.cropping_ref_point[0][1], self.cropping_ref_point[1][1])
                x1, y1 = max(self.cropping_ref_point[0][0], self.cropping_ref_point[1][0]), max(
                    self.cropping_ref_point[0][1], self.cropping_ref_point[1][1])
                roi = frame[y0:y1, x0:x1]
                if roi.size == 0: return

                # 计算BGR平均值
                avg_bgr = np.mean(roi, axis=(0, 1))
                # 将BGR转为RGB顺序的Hex字符串
                hex_color = f"#{int(avg_bgr[2]):02x}{int(avg_bgr[1]):02x}{int(avg_bgr[0]):02x}"

                self.log_composite(f"框选区域的平均颜色BGR值为: {avg_bgr.astype(int)}, 转换为Hex: {hex_color}")

                # 保存这个计算出的精准颜色值
                self.selected_hex_color = hex_color  # 使用新属性来存储
                self.after(0, lambda: self.composite_color_status_label.configure(text=f"颜色: 已校准为 {hex_color}",
                                                                                  text_color="green"))
                cv2.waitKey(1000)
                cv2.destroyAllWindows()

    def composite_calibrate_color(self):
        source_folder = self.gs_composite_source_folder_entry.get()
        if not source_folder:
            tk_messagebox.showerror("错误", "请先在“步骤1”中选择“绿幕文件夹”！")
            return
        source_videos = self._composite_get_video_files(source_folder)
        if not source_videos:
            tk_messagebox.showerror("错误", "在“绿幕文件夹”中找不到任何视频文件用于校准。")
            return

        video_for_calibration = random.choice(source_videos)
        tk_messagebox.showinfo("校准提示",
                               f"将使用以下视频的第一帧进行颜色校准：\n{os.path.basename(video_for_calibration)}\n请在弹出的图片上框选一小块纯绿色区域。")
        cap = cv2.VideoCapture(video_for_calibration)
        if not cap.isOpened():
            tk_messagebox.showerror("错误", "无法打开用于校准的视频文件。")
            return
        ret, frame = cap.read()
        cap.release()
        if not ret:
            tk_messagebox.showerror("错误", "无法读取视频的第一帧。")
            return

        cv2.namedWindow("image")
        cv2.putText(frame, "Drag a box on the green area, then release. Press 'q' to quit.", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        param = {'frame': frame}
        cv2.setMouseCallback("image", self._composite_select_color_callback, param)
        while True:
            cv2.imshow("image", frame)
            if cv2.waitKey(1) & 0xFF == ord("q") or cv2.getWindowProperty("image", cv2.WND_PROP_VISIBLE) < 1:
                break
        cv2.destroyAllWindows()

    def run_composite_logic(self):
        """【全新随机逻辑版 + 删除源文件】绿幕合成 (集成了随机配对和随机混剪)"""
        temp_files_to_clean = []
        try:
            # 1. --- 获取所有UI配置 ---
            source_folder = self.gs_composite_source_folder_entry.get()
            bg_folder = self.gs_composite_bg_folder_entry.get()
            output_folder = self.gs_composite_output_folder_entry.get()
            is_remix_mode = self.composite_remix_switch.get() == 1  # 读取新开关的状态

            # 获取通用参数 (这部分不变)
            key_color = (self.selected_hex_color if self.selected_hex_color else "#00FF00").lstrip('#')
            similarity = self.gs_composite_similarity_slider.get()
            blend = self.gs_composite_blend_slider.get()
            despill_amount = self.gs_composite_despill_slider.get()
            quality_val = int(self.gs_composite_quality_slider.get())
            use_gpu = self.gs_composite_gpu_switch.get() == 1 and self.is_gpu_available
            use_gs_audio = self.gs_composite_use_gs_audio_switch.get() == 1
            do_freeze = self.composite_freeze_switch.get() == 1
            freeze_duration = self._safe_float_convert(self.composite_freeze_duration_entry.get(),
                                                       0) if do_freeze else 0

            # 2. --- 基础校验 ---
            if not all([source_folder, bg_folder, output_folder]): self.log_composite(
                "❌ 错误: 所有文件夹路径都必须选择！"); return
            source_videos = self._composite_get_video_files(source_folder)
            background_videos = self._composite_get_video_files(bg_folder)
            if not source_videos: self.log_composite("❌ 错误: 绿幕文件夹中没有找到视频文件。"); return
            if not background_videos: self.log_composite("❌ 错误: 背景文件夹中没有找到视频文件。"); return
            ffmpeg_path = self._find_executable("ffmpeg");
            ffprobe_path = self._find_executable("ffprobe")
            if not ffmpeg_path or not ffprobe_path: self.log_composite(
                "❌ 错误: 找不到 ffmpeg.exe 或 ffprobe.exe"); return

            # 3. --- 解析组数/手机序号 ---
            num_groups_str = self.composite_num_groups_entry.get().strip()
            phone_serials_str = self.composite_phone_serial_entry.get().strip()
            group_names = []
            if phone_serials_str:
                group_names = [name.strip() for name in phone_serials_str.split('.') if name.strip()]
                if not group_names: self.log_composite("错误: 手机序号输入无效。"); return
            elif num_groups_str:
                try:
                    num_groups = int(num_groups_str);
                    if num_groups <= 0: raise ValueError
                    group_names = [f"group_{i + 1}" for i in range(num_groups)]
                except (ValueError, TypeError):
                    self.log_composite("错误: '生成组数' 必须是一个有效的正整数。");
                    return
            else:
                self.log_composite("错误: '生成组数' 或 '手机序号' 必须填写一个。");
                return

            self.log_composite(f"▶️ 模式: {'随机混剪 (拼接背景)' if is_remix_mode else '随机配对 (单个背景)'}")
            self.log_composite(
                f"▶️ 将为 {len(source_videos)} 个绿幕视频，生成 {len(group_names)} 组，总计 {len(source_videos) * len(group_names)} 个结果视频。")
            # <--- 新增：添加删除警告 --->
            if is_remix_mode:
                self.log_composite("⚠️ 警告: 随机拼接模式已启用，处理成功后，用过的原始背景视频将被删除！")

            # 4. --- 全新的主处理循环 ---
            total_tasks = len(source_videos) * len(group_names)
            task_count = 0

            # 外层循环：遍历组名
            for group_name in group_names:
                if self.composite_stop_event.is_set(): break
                group_output_folder = os.path.join(output_folder, group_name)
                os.makedirs(group_output_folder, exist_ok=True)
                self.log_composite(f"\n--- [开始处理组: {group_name}] ---")

                # 内层循环：遍历每一个绿幕视频
                for src_path in source_videos:
                    if self.composite_stop_event.is_set(): break
                    task_count += 1
                    self.log_composite(f"\n--- [总任务 {task_count}/{total_tasks}] ---")
                    self.log_composite(f"  绿幕: {os.path.basename(src_path)}")

                    bg_to_use = None
                    # <--- 新增：为删除逻辑初始化列表 --->
                    originals_to_delete_in_remix = []

                    try:
                        # 这是核心区别点：根据开关选择不同的背景生成方式
                        if is_remix_mode:
                            # 检查背景素材是否足够
                            if not background_videos:
                                self.log_composite(f"  -> ❌ 错误: 背景素材库已用尽，无法继续混剪，任务中止。")
                                self.composite_stop_event.set()  # 强制停止所有后续任务
                                break

                            # 开关ON: 随机拼接模式
                            cmd_probe_gs = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                                            "default=noprint_wrappers=1:nokey=1", os.path.normpath(src_path)]
                            result = subprocess.run(cmd_probe_gs, check=True, capture_output=True, text=True)
                            gs_duration = float(result.stdout.strip())
                            if gs_duration <= 0: self.log_composite(f"  -> 警告: 绿幕视频时长为0，已跳过。"); continue

                            # <--- 核心修改：接收第三个返回值 --->
                            bg_to_use, temp_files_from_remix, originals_to_delete_in_remix = self._create_random_remix_background(
                                background_videos,
                                gs_duration,
                                group_output_folder)
                            temp_files_to_clean.extend(temp_files_from_remix)
                            if not bg_to_use: self.log_composite(f"  -> ❌ 错误: 无法创建混剪背景，跳过此任务。"); continue

                        else:
                            # 开关OFF: 随机配对模式
                            bg_to_use = random.choice(background_videos)
                            self.log_composite(f"  -> 随机配对背景: {os.path.basename(bg_to_use)}")

                        # 定义输出文件名
                        src_basename = os.path.splitext(os.path.basename(src_path))[0]
                        bg_basename = os.path.splitext(os.path.basename(bg_to_use))[0]
                        output_filename = f"{src_basename}_on_{bg_basename}.mp4"
                        output_filepath = os.path.join(group_output_folder, output_filename)

                        # 调用统一的合成函数
                        self._perform_single_composite(
                            ffmpeg_path, ffprobe_path, bg_to_use, src_path, output_filepath,
                            key_color, similarity, blend, despill_amount, quality_val,
                            use_gpu, use_gs_audio, do_freeze, freeze_duration
                        )

                        # <--- 核心修改：在这里执行删除逻辑 --->
                        if is_remix_mode:
                            self.log_composite("  -> [混剪] 正在删除本次使用过的源背景视频...")
                            for original_path in originals_to_delete_in_remix:
                                if original_path in background_videos:
                                    try:
                                        os.remove(original_path)
                                        background_videos.remove(original_path)  # 从主素材池移除
                                        self.log_composite(f"    -> 🗑️ 已删除: {os.path.basename(original_path)}")
                                    except OSError as e:
                                        self.log_composite(
                                            f"    -> ❌ 删除源文件 {os.path.basename(original_path)} 失败: {e}")

                    except Exception as e:
                        self.log_composite(f"  ❌ 任务失败: {e}")
                    finally:
                        # 如果是混剪模式，bg_to_use是临时文件，需要清理
                        if is_remix_mode and bg_to_use and os.path.exists(bg_to_use):
                            temp_files_to_clean.append(bg_to_use)

            if self.composite_stop_event.is_set():
                self.log_composite("🔴 任务已中止。")
            else:
                self.log_composite("\n--- 🎉 所有任务处理完毕！ ---")

        except Exception as e:
            self.log_composite(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.log_composite("\n--- [任务结束] 正在清理所有临时文件... ---")
            cleaned_count = 0
            for f in temp_files_to_clean:
                if f and os.path.exists(f):
                    try:
                        os.remove(f);
                        cleaned_count += 1
                    except OSError:
                        pass
            self.log_composite(f"--- 清理完毕 ({cleaned_count}个文件) ---")
            self.after(0, self._reset_composite_buttons)

    def _perform_single_composite(self, ffmpeg_path, ffprobe_path, bg_path, src_path, output_filepath, key_color,
                                  similarity, blend, despill_amount, quality_val, use_gpu, use_gs_audio, do_freeze,
                                  freeze_duration):
        """将单个合成操作封装成一个函数，方便复用"""
        try:
            creation_flags = 0
            if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW
            safe_ffprobe_path = f'"{os.path.normpath(ffprobe_path)}"'
            safe_bg_path = f'"{os.path.normpath(bg_path)}"'
            safe_src_path = f'"{os.path.normpath(src_path)}"'

            cmd_probe_bg_str = f'{safe_ffprobe_path} -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 {safe_bg_path}'
            bg_res_str = subprocess.run(cmd_probe_bg_str, shell=True, check=True, capture_output=True, text=True,
                                        creationflags=creation_flags).stdout.strip()
            bg_w, bg_h = map(int, bg_res_str.split(','))
            cmd_probe_src_str = f'{safe_ffprobe_path} -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 {safe_src_path}'
            src_res_str = subprocess.run(cmd_probe_src_str, shell=True, check=True, capture_output=True, text=True,
                                         creationflags=creation_flags).stdout.strip()
            src_w, src_h = map(int, src_res_str.split(','))

            target_w, target_h = max(bg_w, src_w), max(bg_h, src_h)
            if bg_w != src_w or bg_h != src_h: self.log_composite(
                f"  -> 检测到分辨率不匹配。将统一到 {target_w}x{target_h} 进行合成。")

            filters = [
                f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[bg]",
                f"[1:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2[src]",
                f"[src]chromakey=0x{key_color}:{similarity:.2f}:{blend:.2f}[keyed_fg]",
                f"[keyed_fg]despill=type=green:mix={despill_amount:.2f}[clean_fg]",
                f"[bg][clean_fg]overlay[v]"
            ]
            filter_complex = ";".join(filters)
            safe_output_path = f'"{os.path.normpath(output_filepath)}"'
            audio_map_str = '-map 1:a?' if use_gs_audio else '-map 0:a?'

            # --- 最新修复方案 ---
            # 既然 'copy' 会在处理有问题的音频流时卡住, 我们现在强制将其重新编码为标准的AAC格式。
            # 这样做更稳定，可以避免卡顿。-b:a 192k 用于确保良好的音质。
            audio_codec_str = '-c:a aac -b:a 192k'
            # --- 修复结束 ---

            self.log_composite(
                "  -> 已选择使用【绿幕视频】的音频。" if use_gs_audio else "  -> 使用【背景视频】的音频。(混剪模式下可能为静音)")

            codec_str = f"-c:v h264_nvenc -preset fast -cq {quality_val}" if use_gpu else f"-c:v libx264 -preset medium -crf {quality_val}"

            # 将 audio_codec_str 加入到最终的命令中
            command_string = f'"{ffmpeg_path}" -y -i {safe_bg_path} -i {safe_src_path} -filter_complex "{filter_complex}" -map "[v]" {audio_map_str} {audio_codec_str} -shortest {codec_str} {safe_output_path}'

            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8',
                           creationflags=creation_flags)
            self.log_composite(f"  ✅ 成功合成: {os.path.basename(output_filepath)}")

            if do_freeze and freeze_duration > 0:
                self.log_composite(f"  -> 正在添加 {freeze_duration}秒 普通定格...")
                output_subfolder = os.path.dirname(output_filepath)
                temp_output_path = os.path.join(output_subfolder,
                                                f"temp_{random.randint(1000, 9999)}_{os.path.basename(output_filepath)}")
                if os.path.exists(temp_output_path): os.remove(temp_output_path)
                os.rename(output_filepath, temp_output_path)
                freeze_success = self._freeze_worker(ffmpeg_path, ffprobe_path, temp_output_path, output_filepath,
                                                     freeze_duration, output_subfolder)
                if freeze_success:
                    self.log_composite("  -> ✅ 普通定格添加成功。")
                else:
                    self.log_composite("  -> ❌ 普通定格添加失败，已保留未定格视频。");
                    os.rename(temp_output_path,
                              output_filepath)
                if os.path.exists(temp_output_path): os.remove(temp_output_path)

        except subprocess.CalledProcessError as e:
            self.log_composite(f"  ❌ FFmpeg 处理失败:\n{e.stderr.strip()}")

    # ==============================================================================
    # --- 加滤镜 (新功能) ---
    # ==============================================================================
    def setup_lut_workflow(self, parent_tab):
        """创建批量添加滤镜功能的UI界面"""
        tab = parent_tab

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
        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW

        try:
            if self.is_gpu_available:
                self.log_lut("  -> 尝试使用GPU (h264_nvenc) 编码...")
                gpu_command = base_command + ['-c:v', 'h264_nvenc', safe_output_path]
                subprocess.run(gpu_command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                               creationflags=creation_flags)
            else:
                raise Exception("GPU not available, fallback to CPU")
        except Exception as e:
            self.log_lut("  -> 警告: GPU编码失败或不可用，回退到CPU (libx264) 编码。")
            try:
                cpu_command = base_command + ['-c:v', 'libx264', '-preset', 'medium', safe_output_path]
                subprocess.run(cpu_command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                               creationflags=creation_flags)
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

    # ==============================================================================
    # --- 视频克隆 (新功能) ---
    # ==============================================================================
    def setup_video_clone_workflow(self,parent_tab):
        """创建视频克隆功能的UI界面"""
        tab = parent_tab

        ctk.CTkLabel(tab, text="功能说明：将原视频按“正放->倒放->正放”顺序循环拼接，直至达到指定的总时长。",
                     wraplength=400).pack(anchor="w", padx=10, pady=(10, 10))

        # --- 路径设置 ---
        ctk.CTkLabel(tab, text="1. 设置路径", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                    pady=(5, 5))
        self.create_folder_selection_row(tab, "原视频文件夹:", "选择包含视频的文件夹 (可含子文件夹)",
                                         "clone_input_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择处理结果的存放位置", "clone_output_folder_entry")

        # --- 参数设置 ---
        ctk.CTkLabel(tab, text="2. 设置参数", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                    pady=(15, 5))
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(duration_frame, text="目标总时长 (秒):", width=120, anchor="w").pack(side="left")
        self.clone_total_duration_entry = ctk.CTkEntry(duration_frame, placeholder_text="例如: 13")
        self.clone_total_duration_entry.insert(0, "15")  # 默认值
        self.clone_total_duration_entry.pack(side="left", fill="x", expand=True)

        # --- 开始处理 ---
        run_frame = ctk.CTkFrame(tab)
        run_frame.pack(fill="x", padx=10, pady=(20, 10))
        ctk.CTkLabel(run_frame, text="3. 开始处理", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10,
                                                                                          pady=5)

        button_frame = ctk.CTkFrame(run_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.clone_start_button = ctk.CTkButton(button_frame, text="开始批量克隆视频", height=40,
                                                command=self.start_video_clone_processing)
        self.clone_start_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.clone_stop_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                               command=self.stop_video_clone_processing, state="disabled",
                                               fg_color="red", hover_color="darkred")
        self.clone_stop_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- 日志区域 ---
        self.clone_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.clone_log_textbox.pack(expand=True, fill="both", padx=10, pady=(5, 10))

    def log_video_clone(self, message, clear=False):
        self.after(0, self._update_log, self.clone_log_textbox, message, clear)

    def start_video_clone_processing(self):
        self.video_clone_stop_event.clear()
        self.clone_start_button.configure(state="disabled")
        self.clone_stop_button.configure(state="normal")
        self.log_video_clone("", clear=True)
        threading.Thread(target=self.run_video_clone_logic, daemon=True).start()

    def stop_video_clone_processing(self):
        self.log_video_clone("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.video_clone_stop_event.set()
        self.clone_stop_button.configure(state="disabled")

    def _reset_video_clone_buttons(self):
        self.clone_start_button.configure(state="normal")
        self.clone_stop_button.configure(state="disabled")
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
    def run_video_clone_logic(self):
        try:
            input_dir = self.clone_input_folder_entry.get()
            output_dir = self.clone_output_folder_entry.get()

            if not all([input_dir, output_dir]):
                self.log_video_clone("❌ 错误: 原视频文件夹和输出文件夹都必须填写。")
                return

            try:
                total_duration = float(self.clone_total_duration_entry.get())
                if total_duration <= 0: raise ValueError
            except (ValueError, TypeError):
                self.log_video_clone("❌ 错误: 目标总时长必须是一个有效的正数。")
                return

            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

            video_files = []
            for dirpath, _, filenames in os.walk(input_dir):
                for filename in filenames:
                    if self.video_clone_stop_event.is_set(): break
                    if filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
                        video_files.append(os.path.join(dirpath, filename))
                if self.video_clone_stop_event.is_set(): break

            if not video_files:
                self.log_video_clone("ℹ️ 在指定的视频文件夹中未找到任何视频文件。")
                return

            self.log_video_clone(f"🔍 找到 {len(video_files)} 个视频文件，准备开始处理...")

            processed_count = 0
            for i, video_path in enumerate(video_files):
                if self.video_clone_stop_event.is_set(): break

                relative_dir = os.path.relpath(os.path.dirname(video_path), input_dir)
                target_output_dir = os.path.join(output_dir, relative_dir)
                if not os.path.exists(target_output_dir): os.makedirs(target_output_dir)

                base_name, ext = os.path.splitext(os.path.basename(video_path))
                output_path = os.path.join(target_output_dir, f"{base_name}_cloned{ext}")

                self.log_video_clone(
                    f"\n--- [任务 {i + 1}/{len(video_files)}] 正在处理: {os.path.basename(video_path)} ---")

                success = self._video_clone_worker(video_path, output_path, total_duration)
                if success:
                    processed_count += 1
                    # --- 新增的删除逻辑 ---
                    try:
                        self.log_video_clone(f"  -> 正在删除用过的原视频: {os.path.basename(video_path)}")
                        os.remove(video_path)
                        self.log_video_clone(f"  🗑️  原视频已成功删除。")
                    except OSError as e:
                        self.log_video_clone("\n" + "=" * 50)
                        self.log_video_clone(f"  ❌ 警告: 视频处理成功，但删除原视频失败！")
                        self.log_video_clone(f"  -> 文件路径: {video_path}")
                        self.log_video_clone(f"  -> 失败原因: {e}")
                        self.log_video_clone(
                            f"  -> 可能原因：请检查程序是否有此文件夹的删除权限，或文件是否被其他程序占用。")
                        self.log_video_clone("=" * 50 + "\n")
                    # --- 删除逻辑结束 ---

            if self.video_clone_stop_event.is_set():
                self.log_video_clone("🔴 任务已由用户中止。")
            else:
                self.log_video_clone(f"\n--- 🎉 批量处理完成 ---")
                self.log_video_clone(f"共成功处理了 {processed_count} 个视频文件。")

        except Exception as e:
            self.log_video_clone(f"发生未预料的严重错误: {e}")
        finally:
            self.after(0, self._reset_video_clone_buttons)

    def _video_clone_worker(self, video_path, output_path, total_duration):
        """【FFmpeg 高性能健壮版】核心处理函数：正放->倒放->正放->裁剪，兼容有声/无声视频"""
        try:
            ffmpeg_path = self._find_executable("ffmpeg")
            if not ffmpeg_path:
                self.log_video_clone("  ❌ 错误: 找不到 ffmpeg.exe，无法处理视频。")
                return False

            ffprobe_path = self._find_executable("ffprobe")
            if not ffprobe_path:
                self.log_video_clone("  ❌ 错误: 找不到 ffprobe.exe，无法获取视频信息。")
                return False

            normalized_path = os.path.normpath(video_path)

            # 1. 获取原视频时长
            cmd_probe_duration = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                                  "default=noprint_wrappers=1:nokey=1", normalized_path]
            duration_result = subprocess.run(cmd_probe_duration, check=True, capture_output=True, text=True)
            video_duration = float(duration_result.stdout.strip())

            # 2. 新增：检测视频是否包含音频流
            self.log_video_clone("  -> 正在检测音频流...")
            cmd_probe_audio = [ffprobe_path, "-v", "error", "-select_streams", "a", "-show_entries",
                               "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", normalized_path]
            audio_result = subprocess.run(cmd_probe_audio, capture_output=True, text=True)
            has_audio = bool(audio_result.stdout.strip())

            log_msg = "检测到音频流" if has_audio else "未检测到音频流 (静音视频)"
            self.log_video_clone(f"  -> {log_msg}。视频时长: {video_duration:.2f}s, 目标时长: {total_duration:.2f}s。")

            # 3. 根据目标时长和有无音频，选择不同策略
            if total_duration <= video_duration:
                self.log_video_clone("  -> 策略: 直接裁剪原视频。")
                command = [ffmpeg_path, '-y', '-i', normalized_path, '-t', str(total_duration), '-c:v', 'libx264',
                           '-preset', 'medium']
                if has_audio:
                    command.extend(['-c:a', 'aac', '-b:a', '192k'])
                else:
                    command.append('-an')  # -an 表示禁用音频
                command.append(output_path)
            else:
                self.log_video_clone("  -> 策略: 正-反-正拼接后裁剪。")
                if has_audio:
                    # 对于有声视频，构建包含音视频处理的滤镜
                    filter_complex = "[0:v]reverse[rv];[0:a]areverse[ra];[0:v][0:a][rv][ra][0:v][0:a]concat=n=3:v=1:a=1[v_out][a_out]"
                    maps = ['-map', '[v_out]', '-map', '[a_out]']
                    audio_opts = ['-c:a', 'aac', '-b:a', '192k']
                else:
                    # 对于静音视频，构建只处理视频的滤镜
                    filter_complex = "[0:v]reverse[rv];[0:v][rv][0:v]concat=n=3:v=1:a=0[v_out]"
                    maps = ['-map', '[v_out]']
                    audio_opts = ['-an']  # 禁用音频输出

                command = [ffmpeg_path, '-y', '-i', normalized_path, '-filter_complex', filter_complex]
                command.extend(maps)
                command.extend(['-t', str(total_duration), '-c:v', 'libx264', '-preset', 'medium'])
                command.extend(audio_opts)
                command.append(output_path)

            self.log_video_clone("  -> 正在执行 FFmpeg 命令...")
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            self.log_video_clone(f"  ✅ 成功: 已处理并保存到 '{os.path.basename(output_path)}'")
            return True

        except subprocess.CalledProcessError as e:
            error_log = e.stderr.strip()
            self.log_video_clone(f"  ❌ FFmpeg 处理失败:\n{error_log}\n")
            return False
        except Exception as e:
            self.log_video_clone(f"  ❌ 处理中发生未知错误: {e}")
            return False
       # ==============================================================================
    # --- 音频提取 (新功能) ---
    # ==============================================================================
    def setup_audio_extraction_workflow(self, parent_tab):
        """创建音频提取功能的UI界面"""
        tab = parent_tab

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
        self.create_widget_row(scrollable_frame, "播放到此时间点 (秒):", "cut_play_until", "2").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(scrollable_frame, "跳转到此时间点 (秒):", "cut_resume_from", "6").pack(fill="x", padx=10, pady=2)

        # --- 3. FFmpeg 设置 (可选) ---
        ctk.CTkLabel(scrollable_frame, text="3. 高级设置 (可选)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(15,0))
        self.create_widget_row(scrollable_frame, "FFmpeg.exe 路径:", "cut_ffmpeg_path", "程序会自动查找，找不到时再手动指定", is_file=True).pack(fill="x", padx=10, pady=2)
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
        """
        【新版】完全采纳用户提供的脚本逻辑来处理单个视频的跳剪。
        """
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
        self.log_cut(f"  将保留视频从 {start_time:.2f} 秒到 {end_time:.2f} 秒，")
        self.log_cut(f"  然后跳转并拼接从 {jump_time:.2f} 秒开始到末尾的内容。")

        # --- 完全采纳自您提供的脚本 ---
        filter_complex_str = (
            f"[0:v]trim=start={start_time}:end={end_time},setpts=PTS-STARTPTS[v_initial];"
            f"[0:v]trim=start={jump_time}[v_jumped];"
            f"[0:a]atrim=start={start_time}:end={end_time},asetpts=PTS-STARTPTS[a_initial];"
            f"[0:a]atrim=start={jump_time}[a_jumped];"
            f"[v_initial][v_jumped]concat=n=2:v=1:a=0[out_v];"
            f"[a_initial][a_jumped]concat=n=2:v=0:a=1[out_a]"
        )
        command = [
            ffmpeg_path, "-hide_banner", "-loglevel", "error",
            "-i", input_path,
            "-filter_complex", filter_complex_str,
            "-map", "[out_v]", "-map", "[out_a]",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-strict", "-2",
            "-y", output_path,
        ]
        # --- 逻辑结束 ---

        try:
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            subprocess.run(command, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                           encoding='utf-8', creationflags=creation_flags)
            self.log_cut(f"成功: 处理完成! 输出文件: {os.path.basename(output_path)}")
            return True
        except subprocess.CalledProcessError as e:
            self.log_cut(f"错误: FFmpeg 处理 '{os.path.basename(input_path)}' 失败。")
            if e.stderr:
                self.log_cut(f"  FFmpeg 错误输出:\n{e.stderr.strip()}")
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
                # 直接使用用户输入的原始值
                play_until = float(self.cut_play_until_entry.get())
                resume_from = float(self.cut_resume_from_entry.get())
                if play_until < 0 or resume_from <= play_until:
                    raise ValueError("时间点设置无效。")
            except (ValueError, TypeError):
                self.log_cut("错误: 时间点必须为有效数字，且跳转时间点必须严格大于播放时间点。")
                return

            ffmpeg_executable = self._cut_find_ffmpeg_path(ffmpeg_path_user)
            if not ffmpeg_executable:
                return

            self.log_cut(f"---开始扫描并处理视频 (保留 0s-{play_until:.2f}s, 跳转到 {resume_from:.2f}s)---")

            found_count, processed_count = 0, 0
            video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.mpeg', '.mpg')

            # 采纳您新脚本中的 os.walk 逻辑，遍历所有子文件夹
            for dirpath, _, filenames in os.walk(input_dir):
                if self.cut_stop_event.is_set(): break
                for filename in filenames:
                    if self.cut_stop_event.is_set(): break

                    # 自动跳过已处理过的文件
                    if "_processed" in filename:
                        continue
                    if not filename.lower().endswith(video_extensions):
                        continue

                    found_count += 1
                    input_video_path = os.path.join(dirpath, filename)

                    # 保持子文件夹结构
                    relative_dir = os.path.relpath(dirpath, input_dir)
                    target_output_dir = os.path.join(output_dir, relative_dir)

                    base_name, ext = os.path.splitext(filename)
                    output_video_path = os.path.join(target_output_dir, f"{base_name}_processed{ext}")

                    if self._cut_process_video(ffmpeg_executable, input_video_path, output_video_path, 0.0, play_until,
                                               resume_from):
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
    def setup_news_blur_workflow(self,parent_tab):
        tab = parent_tab

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
        self.create_widget_row(settings_frame, "预裁剪时长(秒):", "blur_crop_duration", "4", placeholder="0或留空则不裁剪").pack(fill="x", padx=10, pady=2)

        # --- 核心修复：修改UI布局，分两行显示 ---
        effects_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        effects_frame.pack(fill="x", padx=10, pady=5)

        self.blur_mirror_switch = ctk.CTkSwitch(effects_frame, text="内容镜像")
        self.blur_mirror_switch.pack(anchor="w", pady=(5, 10))

        zoom_frame = ctk.CTkFrame(effects_frame, fg_color="transparent")
        zoom_frame.pack(fill="x")
        ctk.CTkLabel(zoom_frame, text="内容放大倍数:", width=120, anchor="w").pack(side="left")
        self.blur_zoom_entry = ctk.CTkEntry(zoom_frame, placeholder_text="例如: 1.2")
        self.blur_zoom_entry.insert(0, "1.0")
        self.blur_zoom_entry.pack(side="left", fill="x", expand=True)

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
        self.create_widget_row(offsets_frame, "主视频下移像素:", "blur_offset_main", "20").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(offsets_frame, "PIP上移像素:", "blur_offset_pip", "40").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(offsets_frame, "文案上方间距:", "blur_offset_text", "30").pack(fill="x", padx=10, pady=2)
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
        self.create_color_picker_row(text_frame, "背景颜色:", "blur_bg_color", "#FFFFFF")
        self.create_widget_row(text_frame, "字幕框宽度(px):", "blur_box_w", "600").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(text_frame, "字幕框高度(px):", "blur_box_h", "100").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(text_frame, "背景圆角半径(px):", "blur_corner_radius", "20").pack(fill="x", padx=10, pady=2)

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

    def _blur_process_video(self, input_path, output_path, use_gpu, content_roi, pip_roi, text_config, offsets,
                            crop_duration=0, mirror_content=False, zoom_factor=1.0):
        """【最终健壮版】重构滤镜链，彻底解决 'unconnected' 错误"""
        temp_text_image_path = None
        try:
            ffmpeg_path = self._find_executable("ffmpeg")
            ffprobe_path = self._find_executable("ffprobe")
            if not ffmpeg_path or not ffprobe_path: return False, "找不到 ffmpeg.exe 或 ffprobe.exe"

            self.log_blur("  -> 使用ffprobe获取视频信息...")
            norm_input_path = os.path.normpath(input_path)
            cmd_probe = [ffprobe_path, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                         "-of", "csv=p=0", norm_input_path]
            creation_flags = 0
            if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True, creationflags=creation_flags)
            video_w, video_h = map(int, result.stdout.strip().split(','))

            output_dir = os.path.dirname(output_path)
            if text_config and text_config.get('text'):
                self.log_blur("  -> 正在生成文字静态图层...")
                text_img_array = self._blur_create_text_image(text_config['text'], text_config['box_w'],
                                                              text_config['box_h'], text_config['font_path'],
                                                              text_config['font_color'], text_config['bg_color'],
                                                              text_config['corner_radius'])
                temp_text_image = Image.fromarray(text_img_array)
                temp_text_image_path = os.path.join(output_dir, f"temp_text_{random.randint(1000, 9999)}.png")
                temp_text_image.save(temp_text_image_path)

            self.log_blur("  -> 正在构建FFmpeg滤镜链...")
            command = [ffmpeg_path, '-y']
            if crop_duration > 0:
                command.extend(['-t', str(crop_duration)])
            command.extend(['-i', norm_input_path])
            if temp_text_image_path:
                command.extend(['-i', os.path.normpath(temp_text_image_path)])

            cx, cy, cw, ch = content_roi
            y_offset_main, y_offset_text = offsets['main'], offsets['text']

            # --- 核心逻辑修复：重构滤镜链 ---
            filters = []
            filters.append("[0:v]split=2[fg_src][bg_src]")

            foreground_chain = f"[fg_src]crop={cw}:{ch}:{cx}:{cy}"
            if zoom_factor > 1.0:
                self.log_blur(f"  -> 应用放大: {zoom_factor:.2f}倍")
                foreground_chain += f",scale=iw*{zoom_factor}:ih*{zoom_factor},crop={cw}:{ch}"
            if mirror_content:
                self.log_blur("  -> 应用内容镜像")
                foreground_chain += ",hflip"
            foreground_chain += "[sharp_fg]"
            filters.append(foreground_chain)

            background_chain = f"[bg_src]crop={cw}:{ch}:{cx}:{cy}"
            if zoom_factor > 1.0: background_chain += f",scale=iw*{zoom_factor}:ih*{zoom_factor},crop={cw}:{ch}"
            if mirror_content: background_chain += ",hflip"
            background_chain += f",scale={video_w}:{video_h},setsar=1,gblur=sigma=50[blurred_bg]"
            filters.append(background_chain)

            # 确定主合成的输出流名称
            main_comp_output_tag = "[v_out]" if not temp_text_image_path else "[comp1]"
            main_fg_y = cy + y_offset_main
            filters.append(f"[blurred_bg][sharp_fg]overlay=(W-w)/2:{main_fg_y}{main_comp_output_tag}")

            # 如果有文字，则进行第二次叠加
            if temp_text_image_path:
                text_input_idx_str = "1"
                text_x = '(W-w)/2'
                text_y = cy + y_offset_main - text_config['box_h'] - y_offset_text
                filters.append(f"[comp1][{text_input_idx_str}:v]overlay={text_x}:{text_y}[v_out]")

            filter_complex_string = ";".join(filters)
            # --- 修复结束 ---

            command.extend(['-filter_complex', filter_complex_string])
            command.extend(['-map', "[v_out]", '-map', '0:a?'])

            codec_to_use = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
            command.extend(['-c:v', codec_to_use, '-preset', 'medium', '-c:a', 'aac', '-b:a', '192k'])
            command.append(os.path.normpath(output_path))

            self.log_blur("  -> 正在调用FFmpeg核心进行高速合成...")
            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            return True, f"成功保存到: {os.path.basename(output_path)}"

        except subprocess.CalledProcessError as e:
            return False, f"FFmpeg 处理失败:\n{e.stderr.strip()}\n"
        except Exception as e:
            return False, f"处理失败: {e}"
        finally:
            if temp_text_image_path and os.path.exists(temp_text_image_path):
                os.remove(temp_text_image_path)

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

            all_text_lines = [line.strip() for line in
                              self.blur_text_input_area.get("1.0", "end-1c").strip().split('\n') if line.strip()]

            if self.blur_enable_text_switch.get() and not all_text_lines:
                self.log_blur("错误: 已启用文案，但文案输入为空。")
                return

            num_tasks = len(video_files)
            if self.blur_enable_text_switch.get():
                num_tasks = min(len(video_files), len(all_text_lines))

            self.log_blur(f"\n★★★ 模板设置完成！检测到 {len(video_files)} 个视频，将处理 {num_tasks} 个任务。 ★★★")

            try:
                duration_str = self.blur_crop_duration_entry.get()
                original_duration = float(duration_str) if duration_str.strip() else 0
                if original_duration > 0:
                    crop_duration = original_duration + 1
                    self.log_blur(
                        f"信息: 预裁剪时长已自动加1秒以修正偏差 ({original_duration:.2f}s -> {crop_duration:.2f}s)")
                else:
                    crop_duration = 0
            except (ValueError, TypeError):
                self.log_blur("警告: 预裁剪时长输入无效，将不进行裁剪。")
                crop_duration = 0

            # --- 核心修改：获取镜像和放大参数 ---
            mirror_content = self.blur_mirror_switch.get() == 1
            try:
                zoom_factor = float(self.blur_zoom_entry.get())
                if zoom_factor < 1.0: zoom_factor = 1.0
            except (ValueError, TypeError):
                zoom_factor = 1.0
            # --- 修改结束 ---

            font_file = self.blur_font_menu.get()
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(os.path.dirname(__file__))
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
                'pip': 0,
                'text': int(self.blur_offset_text_entry.get())
            }

            for i in range(num_tasks):
                if self.blur_stop_event.is_set():
                    self.log_blur("🔴 任务已由用户中止。");
                    break

                filename = video_files[i]
                try:
                    self.log_blur(f"\n--- 处理进度: {i + 1}/{num_tasks} | 文件: {filename} ---")
                    input_path = os.path.join(input_dir, filename)
                    output_path = os.path.join(output_dir, os.path.splitext(filename)[0] + "_processed.mp4")

                    current_text_config = None
                    if self.blur_enable_text_switch.get():
                        current_text_config = text_base_config.copy()
                        current_text_config['text'] = all_text_lines[i]
                        self.log_blur(f"添加文案: {current_text_config['text']}")

                    # --- 核心修改：传递新的参数 ---
                    success, message = self._blur_process_video(
                        input_path, output_path, self.blur_use_gpu_switch.get(),
                        content_roi, None,  # pip_roi 已被禁用，传递 None
                        current_text_config, offsets_config, crop_duration,
                        mirror_content, zoom_factor
                    )
                    self.log_blur(f"✔️ {message}" if success else f"❌ {message}")
                except Exception as e:
                    self.log_blur(f"处理文件 {filename} 时发生未知严重错误: {e}")

            if not self.blur_stop_event.is_set():
                self.log_blur(
                    "\n===================================\n🎉 所有任务处理完毕！🎉\n===================================")
        except Exception as e:
            self.log_blur(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_blur_buttons)
  # ==============================================================================
    # --- NEWS绿幕 (新功能整合) ---
    # ==============================================================================
    # 将你原来的 setup_news_greenscreen_workflow 方法整个删除，然后粘贴下面的新版本

    def setup_news_greenscreen_workflow(self,parent_tab):
        tab = parent_tab
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
        self.create_widget_row(paths_frame, "预裁剪时长(秒):", "news_crop_duration", "4", placeholder="0或留空则不裁剪").pack(fill="x", padx=10, pady=2)
        # --- 核心修复：修改UI布局，分两行显示 ---
        effects_frame = ctk.CTkFrame(paths_frame, fg_color="transparent")
        effects_frame.pack(fill="x", padx=10, pady=5)

        self.news_mirror_switch = ctk.CTkSwitch(effects_frame, text="内容镜像")
        self.news_mirror_switch.pack(anchor="w", pady=(5, 10))

        zoom_frame = ctk.CTkFrame(effects_frame, fg_color="transparent")
        zoom_frame.pack(fill="x")
        ctk.CTkLabel(zoom_frame, text="内容放大倍数:", width=120, anchor="w").pack(side="left")
        self.news_zoom_entry = ctk.CTkEntry(zoom_frame, placeholder_text="例如: 1.2")
        self.news_zoom_entry.insert(0, "1.0")
        self.news_zoom_entry.pack(side="left", fill="x", expand=True)
        # --- 2. 字幕配置 (使用 .pack 布局) ---
        text_frame = ctk.CTkFrame(scrollable_frame)
        text_frame.pack(fill="x", padx=5, pady=(10, 5))
        ctk.CTkLabel(text_frame, text="第二步: 字幕/文案配置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,0))

        # --- 修复结束 ---
        ctk.CTkLabel(text_frame, text="输入文案 (每行对应一个任务):").pack(anchor="w", padx=10, pady=(10, 2))
        self.news_text_input_area = ctk.CTkTextbox(text_frame, height=120)
        self.news_text_input_area.pack(fill="x", expand=True, padx=10, pady=(0, 10))

        # 这些辅助函数内部使用 .pack()，现在可以正常工作了
        self.news_font_list = self._news_get_fonts()
        self.create_option_menu_row(text_frame, "选择字体 (zt文件夹):", "news_font", self.news_font_list, self.news_font_list[0] if self.news_font_list else "")
        self.create_color_picker_row(text_frame, "字体颜色:", "news_font_color", "#FFFFFF")
        self.create_color_picker_row(text_frame, "背景颜色:", "news_bg_color", "#FFFFFF")
        self.create_widget_row(text_frame, "字幕框宽度(px):", "news_box_w", "500").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(text_frame, "字幕框高度(px):", "news_box_h", "100").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(text_frame, "背景圆角半径(px):", "news_corner_radius", "20").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(text_frame, "上方间距(px):", "news_y_offset", "30").pack(fill="x", padx=10, pady=2)

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

    def _news_process_video(self, content_path, template_path, output_path, content_roi, text_config, use_gpu=False,
                            gpu_codec='libx264', crop_duration=0, mirror_content=False, zoom_factor=1.0):
        """【终极修复版】使用内存管道技术，彻底解决中文路径问题"""
        temp_text_image_path = None
        try:
            ffmpeg_path = self._find_executable("ffmpeg")
            if not ffmpeg_path:
                return False, "找不到 ffmpeg.exe"

            # --- 核心修复：使用内存管道技术提取第一帧 ---
            self.log_news_greenscreen("  -> 使用FFmpeg提取模板视频第一帧到内存...")

            command_extract = [
                ffmpeg_path,
                '-i', os.path.normpath(template_path),
                '-frames:v', '1',  # 只提取1帧
                '-f', 'image2pipe',  # 指定输出格式为管道
                '-vcodec', 'png',  # 指定输出编码为PNG
                '-'  # '-' 代表输出到 stdout (标准输出)
            ]

            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            # 执行命令并捕获标准输出
            result = subprocess.run(command_extract, check=True, capture_output=True, creationflags=creation_flags)

            # 将从管道接收到的二进制数据转换为Numpy数组
            image_data = np.frombuffer(result.stdout, np.uint8)
            # 使用OpenCV从内存中的Numpy数组解码出图像
            template_first_frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

            if template_first_frame is None:
                return False, "无法从内存数据中解码出图像帧。"
            # --- 修复结束 ---

            template_height, template_width, _ = template_first_frame.shape
            hsv = cv2.cvtColor(template_first_frame, cv2.COLOR_BGR2HSV)
            lower_green, upper_green = np.array([35, 43, 46]), np.array([85, 255, 255])
            green_mask = cv2.inRange(hsv, lower_green, upper_green)
            kernel = np.ones((15, 15), np.uint8)
            cleaned_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return False, f"在模板 '{os.path.basename(template_path)}' 中未找到可识别的绿幕区域。"

            gx, gy, gw, gh = cv2.boundingRect(max(contours, key=cv2.contourArea))
            self.log_news_greenscreen(f"  -> 已定位绿幕区域: x={gx}, y={gy}, w={gw}, h={gh}")

            if text_config and text_config.get('text'):
                self.log_news_greenscreen("  -> 正在生成文字图层...")
                text_img_array = self._news_create_text_image(
                    text_config['text'], text_config['box_w'], text_config['box_h'],
                    text_config['font_path'], text_config['font_color'], text_config['bg_color'],
                    text_config['corner_radius']
                )
                temp_text_image = Image.fromarray(text_img_array)
                temp_text_image_path = os.path.join(os.path.dirname(output_path),
                                                    f"temp_text_{random.randint(1000, 9999)}.png")
                temp_text_image.save(temp_text_image_path)

            # 为最终的合成命令也准备好带引号的安全路径
            safe_ffmpeg_path = f'"{os.path.normpath(ffmpeg_path)}"'
            safe_content_path = f'"{os.path.normpath(content_path)}"'
            safe_template_path_final = f'"{os.path.normpath(template_path)}"'
            safe_output_path = f'"{os.path.normpath(output_path)}"'
            safe_text_path = f'"{os.path.normpath(temp_text_image_path)}"' if temp_text_image_path else ""

            inputs_str = f"-i {safe_content_path} -i {safe_template_path_final}"
            if temp_text_image_path:
                inputs_str += f" -i {safe_text_path}"

            crop_str = f"-t {crop_duration}" if crop_duration > 0 else ""

            # --- 核心修改：构建新的、包含镜像和放大逻辑的FFmpeg滤镜链 ---
            filters = []
            content_x, content_y, content_w, content_h = content_roi

            # 1. 裁剪出原始的内容区域
            filters.append(f"[0:v]crop={content_w}:{content_h}:{content_x}:{content_y}[cropped_content]")

            last_content_stream = "[cropped_content]"

            # 2. 如果需要放大，应用缩放和中心裁剪滤镜
            if zoom_factor > 1.0:
                self.log_news_greenscreen(f"  -> 应用放大: {zoom_factor:.2f}倍")
                # iw, ih 代表当前流的输入宽度和高度
                filters.append(f"{last_content_stream}scale=iw*{zoom_factor}:ih*{zoom_factor}[zoomed]")
                filters.append(f"[zoomed]crop={content_w}:{content_h}[centered_zoom]")
                last_content_stream = "[centered_zoom]"

            # 3. 如果需要镜像，应用水平翻转滤镜
            if mirror_content:
                self.log_news_greenscreen("  -> 应用内容镜像")
                filters.append(f"{last_content_stream}hflip[flipped]")
                last_content_stream = "[flipped]"

            # 4. 将最终处理好的内容，缩放到绿幕区域大小
            filters.append(f"{last_content_stream}scale={gw}:{gh}[content_ready]")

            # 5. 将内容叠加到模板上
            filters.append(f"[1:v][content_ready]overlay={gx}:{gy}[video_composited]")

            # 6. 添加文字图层 (逻辑不变)
            last_final_stream = "[video_composited]"
            final_map = last_final_stream
            if temp_text_image_path:
                text_x = (template_width - text_config['box_w']) / 2
                text_y = gy - text_config['box_h'] - text_config['y_offset']
                filters.append(f"{last_final_stream}[2:v]overlay={text_x}:{text_y},format=yuv420p[v_out]")
                final_map = "[v_out]"
            else:
                filters.append(f"{last_final_stream},format=yuv420p[v_out]")
                final_map = "[v_out]"

            filter_complex_string = ";".join(filters)
            # --- 修改结束 ---

            map_str = f'-map "{final_map}" -map 1:a?'
            codec_to_use = gpu_codec if use_gpu and self.is_gpu_available else 'libx264'
            codec_str = f"-c:v {codec_to_use} -preset medium -c:a aac -b:a 192k"

            ffprobe_path = self._find_executable("ffprobe")
            duration_str = ""
            if ffprobe_path:
                try:
                    safe_ffprobe_path = f'"{os.path.normpath(ffprobe_path)}"'
                    cmd_probe_str = f'{safe_ffprobe_path} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{os.path.normpath(template_path)}"'
                    duration_result = subprocess.run(cmd_probe_str, shell=True, check=True, capture_output=True,
                                                     text=True, creationflags=creation_flags).stdout.strip()
                    duration_str = f"-t {duration_result}"
                except:
                    pass

            command_string = f'{safe_ffmpeg_path} -y {crop_str} {inputs_str} -filter_complex "{filter_complex_string}" {map_str} {codec_str} {duration_str} {safe_output_path}'

            self.log_news_greenscreen("  -> 正在调用FFmpeg核心进行高速合成...")
            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)

            return True, f"成功保存到: {os.path.basename(output_path)}"

        except subprocess.CalledProcessError as e:
            error_log = e.stderr.strip()
            return False, f"FFmpeg 处理失败:\n{error_log}\n"
        except Exception as e:
            return False, f"处理失败: {e}"
        finally:
            if temp_text_image_path and os.path.exists(temp_text_image_path):
                try:
                    os.remove(temp_text_image_path)
                except OSError:
                    pass
            # 因为不再创建第一帧的临时文件，所以也不需要清理了
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
        try:
            content_dir = self.news_content_folder_entry.get()
            template_dir = self.news_template_folder_entry.get()
            output_dir = self.news_output_folder_entry.get()
            # --- 核心修改：获取时长后自动加1 ---
            try:
                duration_str = self.news_crop_duration_entry.get()
                original_duration = float(duration_str) if duration_str.strip() else 0
                if original_duration > 0:
                    crop_duration = original_duration + 1
                    self.log_news_greenscreen(
                        f"信息: 预裁剪时长已自动加1秒以修正偏差 ({original_duration:.2f}s -> {crop_duration:.2f}s)")
                else:
                    crop_duration = 0
            except (ValueError, TypeError):
                self.log_news_greenscreen("警告: 预裁剪时长输入无效，将不进行裁剪。")
                crop_duration = 0
            # --- 修改结束 ---
            # --- 获取所有配置参数 (逻辑不变) ---
            font_file = self.news_font_menu.get()
            try:
                duration_str = self.news_crop_duration_entry.get()
                crop_duration = float(duration_str) if duration_str and float(duration_str) > 0 else 0
            except (ValueError, TypeError):
                crop_duration = 0

            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(os.path.dirname(__file__))
            full_font_path = os.path.join(base_path, "zt", font_file)

            if not (font_file and os.path.exists(full_font_path)):
                self.log_news_greenscreen(f"错误: 选择的字体文件 '{font_file}' 无效或 'zt' 文件夹中不存在！")
                return

            all_text_lines = [line.strip() for line in
                              self.news_text_input_area.get("1.0", "end-1c").strip().split('\n') if line.strip()]
            if not all_text_lines:
                self.log_news_greenscreen("错误: 文案输入为空，无法进行一对一匹配。")
                return

            use_gpu = self.news_use_gpu_switch.get() == 1
            gpu_codec = self.news_gpu_codec_menu.get().split(' ')[0]
            if use_gpu and self.is_gpu_available:
                self.log_news_greenscreen(f"*** GPU加速已启用, 编码器: {gpu_codec} ***")
            else:
                self.log_news_greenscreen("*** 将使用CPU进行编码 ***")

            # --- 核心修复：恢复正确的文件夹扫描和矩阵式任务列表构建逻辑 ---
            video_ext = ('.mp4', '.mov', '.avi', '.mkv')
            content_files = sorted([f for f in os.listdir(content_dir) if f.lower().endswith(video_ext)])

            # 1. 扫描模板文件夹下的子文件夹
            template_subfolders = sorted(
                [d for d in os.listdir(template_dir) if os.path.isdir(os.path.join(template_dir, d))])

            if not content_files:
                self.log_news_greenscreen("错误：内容文件夹中没有任何视频文件！")
                return
            if not template_subfolders:
                self.log_news_greenscreen("错误：模板文件夹中不包含任何子文件夹！")
                return

            # 2. 构建包含所有组合的任务列表
            task_list = []
            for subfolder_name in template_subfolders:
                template_folder_path = os.path.join(template_dir, subfolder_name)
                template_files = sorted([f for f in os.listdir(template_folder_path) if f.lower().endswith(video_ext)])
                if not template_files: continue
                # 对于每个内容视频，都与当前子文件夹的所有模板视频进行配对
                for content_filename in content_files:
                    for template_filename in template_files:
                        task_list.append({
                            'subfolder': subfolder_name,
                            'content': content_filename,
                            'template': template_filename
                        })

            if not task_list:
                self.log_news_greenscreen("错误：在模板子文件夹中未找到任何视频文件。")
                return

            # 3. 以任务总数和文案总数中的较小者，确定最终处理数量
            num_tasks = min(len(task_list), len(all_text_lines))
            self.log_news_greenscreen(
                f"\n★★★ 模板设置完成！检测到 {len(task_list)} 个潜在合成任务和 {len(all_text_lines)} 行文案，将处理 {num_tasks} 个任务。 ★★★")
            # --- 修复结束 ---
            # --- 新增：从UI获取镜像和放大参数 ---
            mirror_content = self.news_mirror_switch.get() == 1
            try:
                zoom_factor = float(self.news_zoom_entry.get())
                if zoom_factor < 1.0: zoom_factor = 1.0
            except (ValueError, TypeError):
                zoom_factor = 1.0
            # --- 新增结束 ---
            text_config = {
                'y_offset': int(self.news_y_offset_entry.get()), 'box_w': int(self.news_box_w_entry.get()),
                'box_h': int(self.news_box_h_entry.get()), 'font_color': self.news_font_color_value,
                'bg_color': self.news_bg_color_value, 'font_path': full_font_path,
                'corner_radius': int(self.news_corner_radius_entry.get())
            }

            for i in range(num_tasks):
                if self.news_stop_event.is_set():
                    self.log_news_greenscreen("🔴 任务已由用户中止。")
                    break

                try:
                    # 从任务列表中按顺序取出一个任务
                    task = task_list[i]
                    current_text = all_text_lines[i]

                    self.log_news_greenscreen(f"\n--- 任务进度: {i + 1}/{num_tasks} ---")
                    content_path = os.path.join(content_dir, task['content'])
                    template_path = os.path.join(template_dir, task['subfolder'], task['template'])

                    # 构建正确的输出路径
                    output_subfolder_path = os.path.join(output_dir, task['subfolder'])
                    os.makedirs(output_subfolder_path, exist_ok=True)
                    output_basename = f"{os.path.splitext(task['content'])[0]}_on_{os.path.splitext(task['template'])[0]}.mp4"
                    output_path = os.path.join(output_subfolder_path, output_basename)

                    self.log_news_greenscreen(f"正在合成: '{task['content']}' -> '{task['template']}'")
                    self.log_news_greenscreen(f"添加文案: {current_text}")

                    text_config['text'] = current_text
                    success, message = self._news_process_video(
                        content_path, template_path, output_path,
                        template_content_roi, text_config,
                        use_gpu, gpu_codec, crop_duration,
                        mirror_content, zoom_factor
                    )
                    self.log_news_greenscreen(f"✔️ {message}" if success else f"❌ {message}")
                except Exception as e:
                    self.log_news_greenscreen(f"处理任务 {i + 1} 时发生未知严重错误: {e}")

            if not self.news_stop_event.is_set():
                self.log_news_greenscreen(
                    "\n===================================\n🎉 所有任务处理完毕！🎉\n===================================")

        except Exception as e:
            self.log_news_greenscreen(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
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
        # --- 彻底禁用有问题的自动检测，直接相信我们的手动配置 ---
        self.is_gpu_available = True

        # 更新UI显示，让它看起来正常
        try:
            cpu_text = f"CPU: {platform.processor()}"
        except Exception:
            cpu_text = "CPU: 检测失败"

        gpu_text = "GPU: NVIDIA GPU (强制启用模式)"

        self.after(0, lambda: self.cpu_info_label.configure(text=cpu_text))
        self.after(0, lambda: self.gpu_info_label.configure(text=gpu_text))
        self.after(0, self._update_gpu_switch_status)
    def _update_gpu_switch_status(self):
        switches = [getattr(self, name, None) for name in [

            'video_use_gpu_switch',
            'avatar_use_gpu_switch',
            'gs_composite_gpu_switch',
            'news_use_gpu_switch',
            'blur_use_gpu_switch',
            'dualscreen_use_gpu_switch',
            'splitter_use_gpu_switch',
            'extractor_use_gpu_switch'
        ]]
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

    def create_widget_row(self, parent, label, name, val, is_file=False, placeholder=None):
        f = ctk.CTkFrame(parent, fg_color="transparent")

        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label, width=120, anchor="w").grid(row=0, column=0, padx=(0,10), sticky="w")
        e = ctk.CTkEntry(f, placeholder_text=placeholder) # <-- 增加placeholder_text
        e.grid(row=0, column=1, sticky="ew")
        e.insert(0, val)
        setattr(self, name + "_entry", e)
        if is_file:
            ctk.CTkButton(f, text="...", width=30, command=lambda e=e: self.select_file_for_entry(e, "选择字体文件", [("Font files", "*.otf *.ttf")])).grid(row=0, column=2, padx=(5,0))
        return f
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

    def _safe_int_convert(self, value_str, default=0):
        """安全地将字符串转为整数，如果字符串为空或无效则返回默认值。"""
        if not isinstance(value_str, str) or not value_str.strip():
            return default
        try:
            return int(value_str.strip())
        except (ValueError, TypeError):
            return default

    def _safe_float_convert(self, value_str, default=0.0):
        """安全地将字符串转为浮点数，如果字符串为空或无效则返回默认值。"""
        if not isinstance(value_str, str) or not value_str.strip():
            return default
        try:
            return float(value_str.strip())
        except (ValueError, TypeError):
            return default

    def _update_exclusive_entry_state(self, changed_widget, other_widget):
        """当一个输入框有内容时，禁用并清空另一个输入框"""
        if changed_widget.get().strip():
            other_widget.delete(0, 'end')
            other_widget.configure(state="disabled")
        else:
            other_widget.configure(state="normal")
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
    def log_ab(self, message, clear=False): self.after(0, self._update_log, self.ab_log_textbox, message, clear)

    def _update_log(self, textbox, message, clear=False):
        textbox.configure(state="normal")
        if clear: textbox.delete("1.0", "end")
        textbox.insert("end", str(message) + "\n")
        textbox.see("end")
        textbox.configure(state="disabled")

    def setup_video_workflow(self, parent_tab):
        frame = parent_tab
        tabview = ctk.CTkTabview(frame)
        tabview.pack(expand=True, fill="both", padx=5, pady=5)
        tab_main = tabview.add("主页")
        tab_settings = tabview.add("参数配置")
        self.setup_video_main_tab(tab_main)
        self.setup_video_settings_tab(tab_settings)

    def setup_image_workflow(self,parent_tab):
        frame = parent_tab
        tabview = ctk.CTkTabview(frame)
        tabview.pack(expand=True, fill="both", padx=5, pady=5)
        tab_main = tabview.add("主页")
        tab_settings = tabview.add("参数配置")
        self.setup_image_main_tab(tab_main)
        self.setup_image_settings_tab(tab_settings)

    # ==============================================================================
    # --- AI抠像 (AI Matting) ---
    # ==============================================================================










    def setup_frame_extractor_workflow(self, parent_tab):
        """创建视频截图片功能的UI界面"""
        tab = parent_tab

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

    def setup_video_splitter_workflow(self, parent_tab):
        """创建长视频分割功能的UI界面 (增加预裁剪和智能缩放开关)"""
        tab = parent_tab

        # --- UI控件 ---
        self.create_folder_selection_row(tab, "长视频文件夹:", "选择包含长视频的文件夹 (可含子文件夹)",
                                         "splitter_input_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择分割后短视频的存放位置",
                                         "splitter_output_folder_entry")

        # 分割时长输入
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkLabel(duration_frame, text="分割时长 (秒):", width=150, anchor="w").pack(side="left")
        self.splitter_duration_entry = ctk.CTkEntry(duration_frame, placeholder_text="例如: 3  (代表每段3秒)")
        self.splitter_duration_entry.pack(side="left", fill="x", expand=True)

        # --- 核心修复：确保所有开关都被正确创建 ---
        options_frame = ctk.CTkFrame(tab, fg_color="transparent")
        options_frame.pack(fill="x", padx=10, pady=15, anchor="w")

        self.splitter_crop_switch = ctk.CTkSwitch(options_frame, text="启用预裁剪 (处理前先框选区域)")
        self.splitter_crop_switch.pack(side="left", padx=(0, 20))

        self.splitter_smart_resize_switch = ctk.CTkSwitch(options_frame, text="智能缩放为1080x1920 (背景虚化填充)")
        self.splitter_smart_resize_switch.pack(side="left", padx=(0, 20))

        self.splitter_use_gpu_switch = ctk.CTkSwitch(options_frame, text="使用GPU加速编码 (分割时有效)")
        self.splitter_use_gpu_switch.pack(side="left")
        # --- 修复结束 ---

        # --- 按钮和日志框 ---
        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_splitter_button = ctk.CTkButton(button_frame, text="开始分割视频", height=40,
                                                   command=self.start_video_split)
        self.start_splitter_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.stop_splitter_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                                  command=self.stop_video_split, state="disabled", fg_color="red",
                                                  hover_color="darkred")
        self.stop_splitter_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        self.splitter_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.splitter_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def _smart_resize_worker(self, input_path, output_path, target_wh):
        """【最终修正版】改用subprocess手动构建命令，以支持中文路径并隐藏黑框"""

        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            self.log_splitter(f"  ❌ 错误: 找不到 ffmpeg 或 ffprobe，无法进行智能缩放。")
            return False

        try:
            target_w, target_h = target_wh
            target_aspect = target_w / target_h

            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            # --- 使用 subprocess 和 shell=True 的方式来获取视频信息 ---
            safe_ffprobe_path = f'"{os.path.normpath(ffprobe_path)}"'
            safe_input_path = f'"{os.path.normpath(input_path)}"'

            cmd_probe_str = f'{safe_ffprobe_path} -v error -select_streams v:0 -show_entries stream=width,height,codec_type -of json {safe_input_path}'
            result = subprocess.run(cmd_probe_str, shell=True, check=True, capture_output=True, text=True,
                                    encoding='utf-8', creationflags=creation_flags)
            stream_info = json.loads(result.stdout)['streams'][0]

            source_w, source_h = int(stream_info['width']), int(stream_info['height'])
            source_aspect = source_w / source_h

            # --- 手动构建 FFmpeg 命令字符串 ---
            safe_ffmpeg_path = f'"{os.path.normpath(ffmpeg_path)}"'
            safe_output_path = f'"{os.path.normpath(output_path)}"'

            if abs(source_aspect - target_aspect) < 0.01:
                self.log_splitter(f"  -> 宽高比匹配，直接缩放。")
                filter_str = f'"scale={target_w}:{target_h}"'
            else:
                self.log_splitter(f"  -> 宽高比不匹配，应用背景虚化处理。")
                filter_str = (
                    f'"[0:v]split[bg_src][fg_src];'
                    f'[bg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=50:1[bg_blurred];'
                    f'[fg_src]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fg_scaled];'
                    f'[bg_blurred][fg_scaled]overlay=(W-w)/2:(H-h)/2"'
                )

            command_string = f'{safe_ffmpeg_path} -y -i {safe_input_path} -vf {filter_str} -c:v libx264 -preset medium -c:a aac -b:a 192k {safe_output_path}'

            subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)
            return True

        except subprocess.CalledProcessError as e:
            self.log_splitter(f"  ❌ 智能缩放失败: {os.path.basename(input_path)}")
            self.log_splitter(f"     FFmpeg错误: {e.stderr.strip()}")
            return False
        except Exception as e:
            self.log_splitter(f"  ❌ 智能缩放时发生未知错误: {e}")
            return False
    def setup_ab_image_workflow(self,parent_tab):
        tab = parent_tab
        self.create_folder_selection_row(tab, "背景图片文件夹:", "选择包含A和B背景图片的文件夹",
                                         "ab_image_source_folder_entry")
        self.create_folder_selection_row(tab, "绿幕图片(父):", "选择包含多个绿幕子文件夹的目录",
                                         "ab_greenscreen_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择合成图片的输出位置", "ab_output_folder_entry")

        # --- 核心修复：确保手机序号输入框被创建并绑定事件 ---
        group_frame = ctk.CTkFrame(tab, fg_color="transparent")
        group_frame.pack(fill="x", padx=10, pady=(15, 5))
        self.create_widget_row(group_frame, "生成组数:", "ab_num_groups", "10").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(group_frame, "手机序号(用.分隔):", "ab_phone_serial", "",
                               placeholder="例如: A-1.A-2.B-1").pack(fill="x", padx=10, pady=2)

        # 绑定互斥事件
        self.ab_num_groups_entry.bind("<KeyRelease>",
                                      lambda event: self._update_exclusive_entry_state(self.ab_num_groups_entry,
                                                                                       self.ab_phone_serial_entry))
        self.ab_phone_serial_entry.bind("<KeyRelease>",
                                        lambda event: self._update_exclusive_entry_state(self.ab_phone_serial_entry,
                                                                                         self.ab_num_groups_entry))
        # --- 修复结束 ---

        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.start_ab_button = ctk.CTkButton(button_frame, text="开始AB图文合成", height=40,
                                             command=self.start_ab_processing)
        self.start_ab_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.stop_ab_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_ab_processing,
                                            state="disabled", fg_color="red", hover_color="darkred")
        self.stop_ab_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.ab_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.ab_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)
    def setup_video_main_tab(self, tab):
        self.create_folder_selection_row(tab, "视频文件夹:", "选择包含视频的文件夹", "video_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择视频处理结果的存放位置", "video_output_folder_entry")
        duration_frame = ctk.CTkFrame(tab, fg_color="transparent")
        duration_frame.pack(fill="x", padx=10, pady=5, anchor="w")
        ctk.CTkLabel(duration_frame, text="视频时长秒(用点.分隔):", width=120, anchor="w").pack(side="left")
        self.video_durations_entry = ctk.CTkEntry(duration_frame, placeholder_text="例: 5,6,5 (与文案数量对应)")
        self.video_durations_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(tab, text="输入文案 (用'/'换行, 用'&'分隔块):").pack(anchor="w", padx=10, pady=(10, 0))
        self.video_text_input_box = ctk.CTkTextbox(tab, height=150); self.video_text_input_box.pack(fill="x", padx=10, pady=(5,10), expand=True)

        # --- 核心修改：增加手机序号输入框并绑定事件 ---
        group_frame = ctk.CTkFrame(tab, fg_color="transparent")
        group_frame.pack(fill="x", padx=10, pady=5)
        self.create_widget_row(group_frame, "生成组数:", "video_num_groups", "1").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(group_frame, "手机序号(用.分隔):", "video_phone_serial", "",
                               placeholder="例如: A-1.A-2.B-1").pack(fill="x", padx=10, pady=2)

        # 绑定互斥事件
        self.video_num_groups_entry.bind("<KeyRelease>",
                                         lambda event: self._update_exclusive_entry_state(self.video_num_groups_entry,
                                                                                          self.video_phone_serial_entry))
        self.video_phone_serial_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.video_phone_serial_entry, self.video_num_groups_entry))
        # --- 修改结束 ---
        # --- 新增：随机混剪开关 ---
        switches_frame = ctk.CTkFrame(tab, fg_color="transparent")
        switches_frame.pack(fill="x", padx=10, pady=5, anchor="w")

        self.video_random_remix_switch = ctk.CTkSwitch(switches_frame, text="随机混剪模式")
        self.video_random_remix_switch.grid(row=0, column=0, sticky="w", padx=(0, 20))
        # --- 修改结束 ---
        self.video_use_gpu_switch = ctk.CTkSwitch(tab, text="使用GPU加速编码 (需NVIDIA显卡)"); self.video_use_gpu_switch.pack(anchor="w", padx=10, pady=5)
        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.pack(fill="x", padx=10, pady=10); button_frame.grid_columnconfigure((0,1), weight=1)
        self.start_video_button = ctk.CTkButton(button_frame, text="开始处理视频", height=40, command=self.start_video_processing_hybrid); self.start_video_button.grid(row=0, column=0, padx=(0,5), sticky="ew")
        self.stop_video_button = ctk.CTkButton(button_frame, text="停止处理", height=40, command=self.stop_video_processing, state="disabled", fg_color="red", hover_color="darkred"); self.stop_video_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        self.video_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9"); self.video_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

    def _create_random_remix_clip(self, target_duration, available_videos, temp_dir, logger):
        """【最终版 - FFmpeg核心 - 即时修正MOV】根据目标时长，随机抽取、修正并拼接视频片段"""
        logger(f"  -> [混剪] 目标时长: {target_duration:.2f}s。开始构建FFmpeg混剪任务...")

        ffmpeg_path = self._find_executable("ffmpeg")
        ffprobe_path = self._find_executable("ffprobe")
        if not ffmpeg_path or not ffprobe_path:
            logger("  ❌ 错误: 找不到 ffmpeg.exe 或 ffprobe.exe")
            return None, [], []

        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW

        concat_list_path = os.path.join(temp_dir, f"concat_list_{random.randint(1000, 9999)}.txt")
        clips_info = []
        temp_files_created_this_run = []
        original_videos_used = []  # 新增：用于追踪本次混剪使用过的原始视频
        current_duration = 0
        video_pool = list(available_videos)

        try:
            while current_duration < target_duration:
                if not video_pool:
                    logger("    -> [警告] 所有可用视频都已尝试过，无法继续拼接。")
                    break

                original_video_path = random.choice(video_pool)

                try:
                    # --- 核心修复：在这里对每一个选中的视频进行“即时”预处理 ---
                    corrected_path, temp_file = self._preprocess_video_orientation(original_video_path, temp_dir,
                                                                                   logger)

                    if not corrected_path:
                        logger(
                            f"    -> [警告] 预处理视频 {os.path.basename(original_video_path)} 失败，将从视频池中移除。")
                        video_pool.remove(original_video_path)
                        continue

                    if temp_file:
                        temp_files_created_this_run.append(temp_file)

                    cmd_probe = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", os.path.normpath(corrected_path)]
                    result = subprocess.run(cmd_probe, check=True, capture_output=True, text=True,
                                            creationflags=creation_flags)
                    clip_duration = float(result.stdout.strip())

                    if clip_duration <= 0: raise ValueError("视频时长为0或无效")

                    # 新增：如果视频被成功选用，就将其原始路径加入待删除列表
                    if original_video_path not in original_videos_used:
                        original_videos_used.append(original_video_path)

                    remaining_needed = target_duration - current_duration

                    if clip_duration >= remaining_needed:
                        clips_info.append({'path': corrected_path, 'duration': remaining_needed})
                        logger(
                            f"    -> 添加片段: {os.path.basename(original_video_path)} (裁剪为 {remaining_needed:.2f}s)")
                        current_duration += remaining_needed
                        break
                    else:
                        clips_info.append({'path': corrected_path, 'duration': None})
                        logger(f"    -> 添加片段: {os.path.basename(original_video_path)} (完整 {clip_duration:.2f}s)")
                        current_duration += clip_duration
                        video_pool.remove(original_video_path)

                except Exception as e:
                    logger(
                        f"    -> [警告] 加载或处理视频 {os.path.basename(original_video_path)} 失败: {e}，将从视频池中移除。")
                    if original_video_path in video_pool:
                        video_pool.remove(original_video_path)
                    continue

            if not clips_info:
                logger("  -> [错误] 未能收集到任何有效的视频片段用于混剪。")
                return None, temp_files_created_this_run, []

            with open(concat_list_path, 'w', encoding='utf-8') as f:
                for info in clips_info:
                    safe_path = os.path.normpath(info['path']).replace('\\', '/')
                    f.write(f"file '{safe_path}'\n")
                    if info['duration'] is not None:
                        f.write(f"outpoint {info['duration']:.3f}\n")

            temp_output_path = os.path.join(temp_dir, f"remix_{random.randint(1000, 9999)}.mp4")
            command = [
                ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                '-i', concat_list_path, '-c', 'copy', '-an',
                os.path.normpath(temp_output_path)
            ]

            self.log_video(f"  -> [混剪] 正在调用FFmpeg核心进行高速拼接...")
            subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                           creationflags=creation_flags)
            self.log_video(f"  -> [混剪] 成功生成临时混剪视频。")
            return temp_output_path, temp_files_created_this_run, original_videos_used

        except subprocess.CalledProcessError as e:
            self.log_video(f"  ❌ FFmpeg 拼接失败:\n{e.stderr.strip()}")
            return None, temp_files_created_this_run, []
        finally:
            if os.path.exists(concat_list_path): os.remove(concat_list_path)

    # 请用这个版本完整替换你的 setup_image_main_tab 函数
    def setup_image_main_tab(self, tab):
        # --- 新增：单一模式开关 ---
        mode_switch_frame = ctk.CTkFrame(tab, fg_color="transparent")
        mode_switch_frame.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(mode_switch_frame, text="处理模式:", width=120, anchor="w").pack(side="left")
        self.image_single_mode_switch = ctk.CTkSwitch(
            mode_switch_frame,
            text="单一模式 (使用单一底片文件夹)",
            command=self._toggle_image_processing_mode  # 绑定切换函数
        )
        self.image_single_mode_switch.pack(anchor="w")

        # --- 新增：单一底片文件夹输入行 ---
        self.single_base_folder_row = self.create_folder_selection_row(
            tab,
            "单一底片文件夹:",
            "选择包含多个子文件夹的底片目录",
            "image_single_base_folder_entry",
            return_frame=True
        )
        # self.single_base_folder_row 已经被 create_folder_selection_row pack 过了

        # --- 原有的UI控件 ---
        self.create_folder_selection_row(tab, "图片文件夹:", "选择包含图片的文件夹", "image_folder_entry")
        self.create_folder_selection_row(tab, "输出文件夹:", "选择图片处理结果的存放位置", "image_output_folder_entry")

        ctk.CTkLabel(tab, text="输入文案 (每行对应一张图):").pack(anchor="w", padx=10, pady=(10, 0))
        self.image_text_input_box = ctk.CTkTextbox(tab, height=150)
        self.image_text_input_box.pack(fill="x", expand=True, padx=10, pady=(5, 10))

        group_frame = ctk.CTkFrame(tab, fg_color="transparent")
        group_frame.pack(fill="x", padx=10, pady=5)
        self.create_widget_row(group_frame, "生成组数:", "image_num_groups", "1").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(group_frame, "手机序号(用.分隔):", "image_phone_serial", "",
                               placeholder="例如: A-1.A-2.B-1").pack(fill="x", padx=10, pady=2)

        self.image_num_groups_entry.bind("<KeyRelease>",
                                         lambda event: self._update_exclusive_entry_state(self.image_num_groups_entry,
                                                                                          self.image_phone_serial_entry))
        self.image_phone_serial_entry.bind("<KeyRelease>", lambda event: self._update_exclusive_entry_state(
            self.image_phone_serial_entry, self.image_num_groups_entry))

        button_frame = ctk.CTkFrame(tab, fg_color="transparent")
        button_frame.pack(fill="x", padx=10, pady=10)
        button_frame.grid_columnconfigure((0, 1), weight=1)
        self.start_image_button = ctk.CTkButton(button_frame, text="开始处理图片", height=40,
                                                command=self.start_image_processing)
        self.start_image_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.stop_image_button = ctk.CTkButton(button_frame, text="停止处理", height=40,
                                               command=self.stop_image_processing, state="disabled", fg_color="red",
                                               hover_color="darkred")
        self.stop_image_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        self.image_log_textbox = ctk.CTkTextbox(tab, state="disabled", text_color="#A9A9A9")
        self.image_log_textbox.pack(expand=True, fill="both", padx=10, pady=10)

        # --- 新增：初始化UI状态 ---
        self._toggle_image_processing_mode()
    def setup_video_settings_tab(self, tab):
        tab.grid_rowconfigure(0, weight=1); tab.grid_columnconfigure(0, weight=1)
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="视频字幕的所有参数均在此配置"); scrollable_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        shared_frame = ctk.CTkFrame(scrollable_frame, border_width=1); shared_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(shared_frame, text="--- 视频 · 共享样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        default_video_font_path = get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf'))
        self.create_widget_row(shared_frame, "字体文件:", "video_shared_font_file", default_video_font_path, True).pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "字体大小:", "video_shared_size", "60").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "最大宽度比例:", "video_shared_max_width_ratio", "0.9").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "左右内边距:", "video_shared_padding_horizontal", "30").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "垂直内边距:", "video_shared_padding_vertical", "25").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "描边粗细:", "video_shared_stroke_width", "2").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(shared_frame, "背景圆角半径:", "video_shared_corner_radius", "20").pack(fill="x", padx=10, pady=2)
        self.video_no_bg_switch = ctk.CTkSwitch(shared_frame, text="禁用所有字幕背景")
        self.video_no_bg_switch.pack(pady=10, padx=10, anchor="w")
        # --- 在这里添加新开关 ---
        self.video_line_by_line_bg_switch = ctk.CTkSwitch(shared_frame, text="启用逐行背景 (解决缩进)")
        self.video_line_by_line_bg_switch.pack(pady=(0, 10), padx=10, anchor="w")
        # --- 添加结束 ---

        main_frame = ctk.CTkFrame(scrollable_frame, border_width=1); main_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(main_frame, text="--- 视频 · 主文案 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.create_widget_row(main_frame, "水平位置 (x):", "video_main_pos_x", "center").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(main_frame, "垂直位置 (y):", "video_main_pos_y", "150").pack(fill="x", padx=10, pady=2)
        self.create_color_picker_row(main_frame, "文字颜色:", "video_main_color_text", "white")
        self.create_color_picker_row(main_frame, "描边颜色:", "video_main_color_stroke", "black")
        self.create_color_picker_row(main_frame, "背景颜色:", "video_main_color_bg", "rgba(0, 0, 0, 0.5)")
        for i in range(1, 3):
            sub_frame = ctk.CTkFrame(scrollable_frame, border_width=1); sub_frame.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(sub_frame, text=f"--- 视频 · 次文案 {i} ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
            defaults = [("20", "#FFD700", "black", "rgba(200,50,50)"), ("30", "white", "black", "rgba(50,50,50)")]
            self.create_widget_row(sub_frame, "相对Y轴偏移:", f"video_sub{i}_offset_y", defaults[i-1][0]).pack(fill="x", padx=10, pady=2)
            self.create_color_picker_row(sub_frame, "文字颜色:", f"video_sub{i}_color_text", defaults[i-1][1])
            self.create_color_picker_row(sub_frame, "描边颜色:", f"video_sub{i}_color_stroke", defaults[i-1][2])
            self.create_color_picker_row(sub_frame, "背景颜色:", f"video_sub{i}_color_bg", defaults[i-1][3])
        self.preview_button = ctk.CTkButton(tab, text="生成视频字幕预览", command=self.generate_video_preview); self.preview_button.grid(row=1, column=0, pady=10, padx=5)
        self.preview_display_frame = ctk.CTkFrame(tab); self.preview_display_frame.grid_rowconfigure(1, weight=1); self.preview_display_frame.grid_columnconfigure(0, weight=1)
        self.close_preview_button = ctk.CTkButton(self.preview_display_frame, text="关闭预览", command=self.close_video_preview, width=120); self.close_preview_button.grid(row=0, column=0, pady=(5, 10))
        self.preview_label = ctk.CTkLabel(self.preview_display_frame, text="", text_color="gray"); self.preview_label.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        tab.grid_rowconfigure(2, weight=1); self.close_video_preview()

    def setup_image_settings_tab(self, tab):
        scrollable_frame = ctk.CTkScrollableFrame(tab, label_text="图片处理的所有参数均在此配置")
        scrollable_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # --- 主文案框架 (复用原有的字体与颜色) ---
        main_frame = ctk.CTkFrame(scrollable_frame, border_width=1)
        main_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(main_frame, text="--- 图片 · 主文案样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.image_no_bg_switch = ctk.CTkSwitch(main_frame, text="禁用文字背景")
        self.image_no_bg_switch.pack(pady=(5, 10), padx=10, anchor="w")
        default_font_path = get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf'))
        self.create_widget_row(main_frame, "字体文件路径:", "image_font_path", default_font_path, True).pack(fill="x", padx=10, pady=2)
        self.create_widget_row(main_frame, "字体大小:", "image_font_size", "75").pack(fill="x", padx=10, pady=2)
        self.create_color_picker_row(main_frame, "文字颜色:", "image_font_color", "#FFFFFF")
        self.create_color_picker_row(main_frame, "背景颜色:", "image_font_background_color", "#FFFFFF")

        # --- 新增：次文案框架 ---
        sub_frame = ctk.CTkFrame(scrollable_frame, border_width=1)
        sub_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(sub_frame, text="--- 图片 · 次文案样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.create_widget_row(sub_frame, "相对Y轴偏移:", "image_sub_offset_y", "20").pack(fill="x", padx=10, pady=2)
        self.create_color_picker_row(sub_frame, "文字颜色:", "image_sub_color_text", "#FFD700")
        self.create_color_picker_row(sub_frame, "背景颜色:", "image_sub_color_bg", "#FFFFFF")

        # --- 布局与样式框架 (保持不变) ---
        layout_frame = ctk.CTkFrame(scrollable_frame, border_width=1)
        layout_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(layout_frame, text="--- 图片 · 共享布局与样式 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.create_widget_row(layout_frame, "最大文本宽度比例:", "image_max_text_width_ratio", "0.85").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(layout_frame, "背景圆角半径:", "image_corner_radius", "15").pack(fill="x", padx=10, pady=2)
        self.create_widget_row(layout_frame, "背景内边距:", "image_text_padding", "20").pack(fill="x", padx=10, pady=2)
        self.create_option_menu_row(layout_frame, "块内文本对齐:", "image_text_align_in_block",
                                    ["left", "center", "right"], "center")

        # --- 列表类配置框架 (保持不变) ---
        list_frame = ctk.CTkFrame(scrollable_frame, border_width=1)
        list_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(list_frame, text="--- 图片 · 随机化配置 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        positions_default = "[\n  [0.5, 0.44],\n  [0.5, 0.6],\n  [0.5, 0.51]\n]"
        self.create_textbox_row(list_frame, "位置列表 (每行一对[x,y]):", "image_text_positions", positions_default)
        self.create_textbox_row(list_frame, "行间距选项 (逗号分隔):", "image_line_spacing_options", "25")
        self.create_textbox_row(list_frame, "缩放/裁剪百分比 (逗号分隔):", "image_zoom_crop_percentages", "0")
        effects_frame = ctk.CTkFrame(scrollable_frame, border_width=1)
        effects_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(effects_frame, text="--- 图片 · 效果开关 ---", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.image_flip_switch = ctk.CTkSwitch(effects_frame, text="允许随机水平翻转")
        self.image_flip_switch.pack(pady=10)
        self.image_flip_switch.select()
# --- AI抠像 (AI Matting) ---
    def _toggle_bg_folder_state(self):
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
        """
        AI抠像主逻辑线程 (rembg 高质量版)
        """
        session = None
        try:
            video_dir = self.ai_video_folder_entry.get()
            images_dir = self.ai_bg_folder_entry.get()
            output_dir = self.ai_output_folder_entry.get()

            # 从新的UI控件读取参数
            use_gpu = self.ai_use_gpu_switch.get() == 1
            use_alpha_matting = self.ai_alpha_matting_switch.get() == 1
            fg_threshold = int(self.ai_fg_threshold_slider.get())
            bg_threshold = int(self.ai_bg_threshold_slider.get())

            if not all([video_dir, images_dir, output_dir]):
                self.log_ai_matting("❌ 错误：所有三个文件夹路径都必须填写。")
                return

            self.log_ai_matting(
                f"▶️ 模式: {'GPU' if use_gpu else 'CPU'} | Alpha Matting: {'启用' if use_alpha_matting else '关闭'}")
            self.log_ai_matting("▶️ 正在初始化 rembg 高质量人像分割模型...")

            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if use_gpu and self.is_gpu_available else [
                'CPUExecutionProvider']
            try:
                session = rembg.new_session(providers=providers)
                self.log_ai_matting("✅ 模型初始化成功。")
            except Exception as e:
                self.log_ai_matting(f"❌ 模型初始化失败: {e}")
                self.log_ai_matting("   请确认您已正确安装 rembg[gpu] 和 onnxruntime-gpu，并且NVIDIA驱动和CUDA环境正常。")
                return

            video_files = sorted(
                [f for f in os.listdir(video_dir) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
            image_files = sorted(
                [f for f in os.listdir(images_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))])

            if not video_files: self.log_ai_matting("ℹ️ 视频输入文件夹为空。"); return
            if not image_files: self.log_ai_matting("ℹ️ 背景图片文件夹为空。"); return

            total_tasks = len(video_files) * len(image_files)
            self.log_ai_matting(
                f"🔍 扫描到 {len(video_files)} 个视频和 {len(image_files)} 张背景图片，将执行 {total_tasks} 个合成任务。")

            task_count = 0
            for video_name in video_files:
                if self.ai_matting_stop_event.is_set(): break
                for image_name in image_files:
                    if self.ai_matting_stop_event.is_set(): break
                    task_count += 1

                    self.log_ai_matting(f"\n--- [任务 {task_count}/{total_tasks}] ---")
                    self.log_ai_matting(f"  视频: {video_name}")
                    self.log_ai_matting(f"  背景: {image_name}")

                    input_video_path = os.path.join(video_dir, video_name)
                    background_image_path = os.path.join(images_dir, image_name)
                    output_filename = f"{os.path.splitext(video_name)[0]}_on_{os.path.splitext(image_name)[0]}.mp4"
                    output_path = os.path.join(output_dir, output_filename)

                    # 核心修复：确保这里调用的是新版 worker 函数 _ai_matting_worker
                    result = self._ai_matting_worker(
                        input_video_path, output_path, session,
                        fg_threshold, bg_threshold, use_alpha_matting,
                        use_gpu, background_image_path
                    )
                    if result == 'STOPPED':
                        break

            if self.ai_matting_stop_event.is_set():
                self.log_ai_matting("\n🔴 任务已由用户中止。")
            else:
                self.log_ai_matting("\n--- 🎉 所有任务已执行完毕 ---")

        except Exception as e:
            self.log_ai_matting(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.after(0, self._reset_ai_matting_buttons)

    def _ai_matting_worker(self, input_path, output_path, session, fg_threshold, bg_threshold, use_alpha_matting,
                           use_gpu_encoding, background_path=None):
        """
        【rembg 高性能版】采用内存直通管道，rembg抠图 -> FFmpeg合成，全程GPU加速。
        """
        self.log_ai_matting(f"  -> 正在处理视频: {os.path.basename(input_path)}")
        if background_path: self.log_ai_matting(f"  -> 使用背景图片: {os.path.basename(background_path)}")

        ffmpeg_path = self._find_executable('ffmpeg')
        if not ffmpeg_path:
            self.log_ai_matting("  ❌ 错误：找不到 ffmpeg.exe");
            return False

        cap = None
        proc = None
        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened(): raise IOError("无法打开视频文件。")

            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.log_ai_matting(f"    视频信息: {total_frames} 帧, {frame_width}x{frame_height}, {fps:.2f} FPS")
            self.log_ai_matting(f"    注意：AI模型加载和首帧处理可能需要较长时间，请耐心等待...")

            # --- FFmpeg命令准备 ---
            command = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{frame_width}x{frame_height}', '-pix_fmt', 'rgba',  # 从管道接收RGBA数据
                '-r', str(fps), '-i', '-',
            ]
            # FFmpeg需要接收三个输入: 0=管道(前景), 1=背景图, 2=原视频(用于音频)
            command.extend(['-i', os.path.normpath(background_path)])
            command.extend(['-i', os.path.normpath(input_path)])

            # 使用 overlay 滤镜将前景(0)叠加在背景(1)上
            command.extend(['-filter_complex', '[1:v][0:v]overlay=0:0[vid]'])

            # 映射最终的视频流[vid]和原视频的音频流[2:a]
            command.extend(['-map', '[vid]', '-map', '2:a?'])

            # 根据GPU开关选择视频编码器
            video_codec = 'h264_nvenc' if use_gpu_encoding and self.is_gpu_available else 'libx264'
            preset = 'fast' if use_gpu_encoding else 'medium'
            quality_param = '-cq' if use_gpu_encoding else '-crf'

            command.extend(['-c:v', video_codec, '-preset', preset, quality_param, '23', '-pix_fmt', 'yuv420p'])
            command.extend(['-c:a', 'aac', '-b:a', '192k'])
            command.append(os.path.normpath(output_path))

            creation_flags = 0
            if sys.platform == 'win32': creation_flags = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=creation_flags)

            # --- 逐帧处理并写入内存管道 ---
            for frame_count in range(total_frames):
                if self.ai_matting_stop_event.is_set():
                    proc.kill();
                    return 'STOPPED'

                ret, frame = cap.read()
                if not ret: break

                # 1. 使用 rembg 获取高质量遮罩 (rembg处理BGR格式的Numpy数组)
                mask_np = rembg.remove(
                    frame, session=session, only_mask=True,
                    alpha_matting=use_alpha_matting,
                    alpha_matting_foreground_threshold=fg_threshold,
                    alpha_matting_background_threshold=bg_threshold
                )

                # 2. 将原始帧和遮罩合并为RGBA格式的Numpy数组
                rgba_frame = np.dstack((frame, mask_np))

                # 3. 将RGBA数据直接写入FFmpeg管道
                try:
                    proc.stdin.write(rgba_frame.tobytes())
                except (IOError, BrokenPipeError):
                    self.log_ai_matting("  -> FFmpeg进程提前关闭，停止写入。")
                    break

                if (frame_count + 1) % 15 == 0 or (frame_count + 1) == total_frames:
                    self.log_ai_matting(f"    AI抠像进度: {frame_count + 1}/{total_frames} 帧")

            self.log_ai_matting("    ✅ 所有帧已送入管道，等待FFmpeg编码完成...")
            stdout_data, stderr_data = proc.communicate()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, command,
                                                    stderr=stderr_data.decode('utf-8', 'ignore'))

            self.log_ai_matting(f"    ✅ FFmpeg合成成功！")
            return True

        except Exception as e:
            if isinstance(e, subprocess.CalledProcessError):
                self.log_ai_matting(f"  ❌ FFmpeg合成失败: {e.stderr}")
            else:
                self.log_ai_matting(f"  ❌ 处理过程中发生未知错误: {e}")
                traceback.print_exc()
            return False
        finally:
            if cap and cap.isOpened(): cap.release()

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

    def _preprocess_video_orientation(self, input_path, temp_dir, logger):
        """
        【最终可靠版】不再检测元数据，直接对所有.MOV文件执行修正。
        """
        # 检查文件扩展名，只对 .mov 文件进行处理
        if input_path.lower().endswith('.mov'):
            logger("\n--- [视频预处理] ---")
            logger(f"  - [规则] 检测到.MOV文件，.")

            try:
                # 查找ffmpeg路径
                ffmpeg_path = self._find_executable("ffmpeg")
                if not ffmpeg_path:
                    logger("  ❌ [致命错误] 找不到ffmpeg.exe，无法修正MOV文件。")
                    return None, None

                # 定义临时输出路径
                temp_output_path = os.path.join(temp_dir, f"corrected_{os.path.basename(input_path)}.mp4")

                # 构建您已验证成功的、最可靠的ffmpeg命令
                command = [
                    ffmpeg_path,
                    "-y",
                    "-i", input_path,
                    "-metadata:s:v:0", "rotate=0",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-c:a", "copy",
                    temp_output_path
                ]

                # 执行命令
                logger(f"  - [操作] 正在执行FFmpeg修正命令...")
                creation_flags = 0
                if sys.platform == 'win32':
                    # 如果是Windows，则使用“无窗口”标志
                    creation_flags = subprocess.CREATE_NO_WINDOW
                subprocess.run(command, shell=True, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=creation_flags)
                logger("  - ✅ 修正成功，后续将使用此临时文件。")

                # 返回新生成的临时文件路径
                return temp_output_path, temp_output_path

            except Exception as e:
                logger(f"  ❌ [致命错误] MOV文件修正过程中发生错误: {e}")
                if hasattr(e, 'stderr') and e.stderr:
                    logger(f"  - [FFmpeg错误日志]: {e.stderr.decode('utf-8', errors='ignore').strip()}")
                return None, None  # 修正失败

        else:
            # 如果不是.MOV文件，则假定其方向正常，直接跳过
            return input_path, None

    def _ffmpeg_format_color(self, color_string):
        """将多种颜色格式转换为FFmpeg drawtext滤镜可接受的 '#RRGGBBAA' 格式"""
        if color_string.startswith("rgba"):
            try:
                parts = re.findall(r"[-+]?\d*\.\d+|\d+", color_string)
                r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                a = int(float(parts[3]) * 255)
                return f'#{r:02x}{g:02x}{b:02x}{a:02x}'
            except:
                return '#000000FF'  # 解析失败则返回不透明黑色
        elif color_string.startswith("#"):
            # 如果是#RRGGBB格式，补上FF的alpha通道
            if len(color_string) == 7:
                return f'{color_string}FF'
            return color_string  # #RRGGBBAA格式或已经是带alpha的
        else:  # 处理颜色名字，如 'white'
            try:
                rgb = ImageColor.getrgb(color_string)
                return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}FF'
            except:
                return '#FFFFFFFF'  # 解析失败返回不透明白色



    def run_video_logic(self):
        try:
            video_folder = self.video_folder_entry.get()
            output_folder = self.video_output_folder_entry.get()
            config = self.get_video_config_from_gui()
            all_input_text = self.video_text_input_box.get("1.0", "end-1c")
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
            all_available_videos = [f for f in os.listdir(video_folder) if f.lower().endswith(('.mp4', '.mov', '.avi'))]
            if len(all_available_videos) < total_videos_needed:
                self.log_video(f"错误: 视频不足！需要 {total_videos_needed} 个, 但只有 {len(all_available_videos)} 个。")
                return
            random.shuffle(all_available_videos)
            videos_to_process = all_available_videos[:total_videos_needed]
            if os.path.exists(output_folder):
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
                video_chunk = videos_to_process[i:i + num_texts_per_group]
                group_folder = os.path.join(output_folder, f"group_{group_count}")
                os.makedirs(group_folder, exist_ok=True)
                self.log_video(f"\n---=== 开始处理第 {group_count} 组 ===---")

                for j, video_name in enumerate(video_chunk):
                    if self.video_stop_event.is_set():
                        self.log_video("🔴 任务在组内中止。")
                        break

                    input_video_path = os.path.join(video_folder, video_name)
                    output_video_path = os.path.join(group_folder, f"processed_{video_name}")
                    text_line = text_lines[j]

                    self.log_video(f"\n[{j + 1}/{len(video_chunk)}] 正在处理...")
                    self.log_video(f"  - 视频: {video_name}")

                    temp_file_to_delete = None

                    try:
                        # 调用预处理方法
                        corrected_video_path, temp_file_to_delete = self._preprocess_video_orientation(
                            input_video_path, group_folder, self.log_video
                        )

                        # 如果预处理失败，则跳过这个视频
                        if not corrected_video_path:
                            self.log_video(f"  -> 预处理失败，跳过视频: {video_name}")
                            continue

                        # MoviePy 加载的是已经100%正确的视频文件
                        video_clip = VideoFileClip(corrected_video_path)

                        text_parts = [part.strip() for part in text_line.split('&')]
                        self.log_video(f"  - 文案被分割为 {len(text_parts)} 部分: {text_parts}")

                        overlays = []
                        main_text_config = config['main_text']
                        main_overlay = video_create_text_overlay(text_parts[0], shared_style_config, main_text_config,
                                                                 video_clip.size)
                        pos_config = main_text_config['position']
                        x_pos, y_pos = pos_config.get('x', 'center'), pos_config.get('y', 'center')
                        main_overlay = main_overlay.set_position(
                            (x_pos, y_pos) if x_pos != 'center' else ('center', y_pos))
                        overlays.append(main_overlay)

                        main_y_position = main_overlay.pos(video_clip.size)[1]
                        last_clip_y, last_clip_height = main_y_position, main_overlay.size[1]

                        if len(text_parts) > 1:
                            sub_texts_configs = config.get('sub_texts', [])
                            for k, sub_text in enumerate(text_parts[1:]):
                                if k >= len(sub_texts_configs): break
                                sub_text_config = sub_texts_configs[k]
                                sub_overlay = video_create_text_overlay(sub_text, shared_style_config, sub_text_config,
                                                                        video_clip.size)
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
                                final_clip.write_videofile(output_video_path, codec=gpu_codec, audio_codec='aac',
                                                           threads=4, preset='fast', logger=None)
                            except Exception:
                                self.log_video(f"  -> 警告: GPU编码失败。正在回退到CPU编码。")
                                final_clip.write_videofile(output_video_path, codec=cpu_codec, audio_codec='aac',
                                                           threads=4, preset='medium', logger=None)
                        else:
                            self.log_video(f"  -> 使用CPU编码 ({cpu_codec})...")
                            final_clip.write_videofile(output_video_path, codec=cpu_codec, audio_codec='aac', threads=4,
                                                       preset='medium', logger=None)

                        video_clip.close()
                        final_clip.close()
                        self.log_video(f"  -> 成功! 输出文件: {os.path.basename(output_video_path)}")

                        gc.collect()
                        time.sleep(1)

                        try:
                            os.remove(input_video_path)
                            self.log_video(f"  -> ✅ 源视频已删除: {video_name}")
                        except Exception as e:
                            self.log_video(f"  -> ❌ 删除源视频时发生异常: {e}")

                    except Exception as e:
                        self.log_video(f"  -> 错误: 处理视频 {video_name} 时发生严重错误: {e}")
                        if os.path.exists(output_video_path):
                            try:
                                os.remove(output_video_path)
                            except OSError:
                                pass
                    finally:
                        # 无论处理成功或失败，都确保清理掉可能生成的临时文件
                        if temp_file_to_delete and os.path.exists(temp_file_to_delete):
                            try:
                                os.remove(temp_file_to_delete)
                                self.log_video(f"  - 已清理临时文件。")
                            except OSError as e:
                                self.log_video(f"  - 警告: 清理临时文件失败: {e}")

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

    # 请用这个版本完整替换你的 run_image_logic 函数
    # 请用这个版本完整替换你的 run_image_logic 函数
    def run_image_logic(self):
        # 首先获取通用配置
        output_folder = self.image_output_folder_entry.get()
        all_input_text = self.image_text_input_box.get("1.0", "end-1c")
        config = self.get_image_config_from_gui()
        captions = [line.strip() for line in all_input_text.splitlines() if line.strip()]

        # 检查通用配置是否有效
        if not all([output_folder, config, captions]):
            self.log_image("错误: 请确保已选择输出文件夹、完成参数配置并且文案不为空。")
            self.after(0, self._reset_image_buttons)
            return

        # 根据开关状态决定执行哪个逻辑
        if self.image_single_mode_switch.get() == 1:
            # --- 执行新的“单一模式”逻辑 ---
            try:
                single_base_folder = self.image_single_base_folder_entry.get()
                if not single_base_folder:
                    self.log_image("错误: 单一模式下，必须选择'单一底片文件夹'。")
                    return

                self.log_image("--- [单一模式] 开始处理 (顺序定位) ---")
                if os.path.exists(output_folder): shutil.rmtree(output_folder)
                os.makedirs(output_folder)

                subfolders = sorted(
                    [d for d in os.listdir(single_base_folder) if os.path.isdir(os.path.join(single_base_folder, d))])
                if not subfolders:
                    self.log_image(f"错误: 在'{single_base_folder}'中找不到任何子文件夹。")
                    return

                image_ext = ('.png', '.jpg', '.jpeg', '.webp')
                total_processed_count = 0

                # <--- 新增/修改逻辑开始 --->
                # 1. 在循环外先获取位置列表
                position_list = config.get("text_positions", [[0.5, 0.5]])
                num_positions = len(position_list)
                self.log_image(f"  -> 将按顺序循环使用 {num_positions} 个预设位置。")
                # <--- 新增/修改逻辑结束 --->

                for subfolder_name in subfolders:
                    if self.image_stop_event.is_set(): self.log_image("🔴 任务已中止."); break

                    self.log_image(f"\n--- 处理子文件夹: {subfolder_name} ---")
                    current_subfolder_path = os.path.join(single_base_folder, subfolder_name)

                    images_in_subfolder = [f for f in os.listdir(current_subfolder_path) if
                                           f.lower().endswith(image_ext)]
                    if not images_in_subfolder:
                        self.log_image(f"  -> 警告: 文件夹'{subfolder_name}'为空，已跳过。")
                        continue

                    base_image_path = os.path.join(current_subfolder_path, images_in_subfolder[0])
                    self.log_image(f"  -> 使用底片: {images_in_subfolder[0]}")

                    group_output_folder = os.path.join(output_folder, subfolder_name)
                    os.makedirs(group_output_folder, exist_ok=True)

                    for idx, caption in enumerate(captions):
                        if self.image_stop_event.is_set(): break

                        output_filename = f"{subfolder_name}_{idx + 1}.png"
                        output_path = os.path.join(group_output_folder, output_filename)

                        # <--- 新增/修改逻辑开始 --->
                        # 2. 按索引顺序循环获取位置
                        #    使用取模运算符(%)来实现循环
                        pos_config = position_list[idx % num_positions]
                        # <--- 新增/修改逻辑结束 --->

                        result = image_apply_text(base_image_path, caption, config, pos_config, output_path,
                                                  self.log_image, self.image_stop_event)

                        if result == 'STOPPED':
                            break
                        elif result is True:
                            total_processed_count += 1

                    if self.image_stop_event.is_set(): break

                if not self.image_stop_event.is_set():
                    self.log_image(f"\n---=== [单一模式] 处理完毕！总共生成 {total_processed_count} 张图片 ===---")

            except Exception as e:
                self.log_image(f"发生未预料的严重错误: {e}")
                traceback.print_exc()
            finally:
                self.after(0, self._reset_image_buttons)

        else:
            # --- 执行原有的“常规模式”逻辑 (此部分完全不变) ---
            try:
                image_folder = self.image_folder_entry.get()
                if not image_folder:
                    self.log_image("错误: 常规模式下，必须选择'图片文件夹'。")
                    return

                num_groups_str = self.image_num_groups_entry.get().strip()
                phone_serials_str = self.image_phone_serial_entry.get().strip()
                group_names, num_groups = [], 0

                if phone_serials_str:
                    group_names = [name.strip() for name in phone_serials_str.split('.') if name.strip()]
                    if not group_names: self.log_image("错误: 手机序号输入无效。"); return
                    num_groups = len(group_names)
                    self.log_image(f"手机序号模式激活，将创建 {num_groups} 个指定名称的文件夹。")
                elif num_groups_str:
                    try:
                        num_groups = int(num_groups_str)
                        if num_groups <= 0: raise ValueError
                        group_names = [f"group_{i + 1}" for i in range(num_groups)]
                        self.log_image(f"组数模式激活，将创建 {num_groups} 个文件夹。")
                    except (ValueError, TypeError):
                        self.log_image("错误: '生成组数' 必须是一个有效的正整数。");
                        return
                else:
                    self.log_image("错误: '生成组数' 或 '手机序号' 必须填写一个。");
                    return

                num_captions_per_set = len(captions)
                total_needed = num_groups * num_captions_per_set
                available_images = [f for f in os.listdir(image_folder) if
                                    f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
                if len(available_images) < total_needed:
                    self.log_image(f"错误: 图片不足！需要 {total_needed} 张, 但只有 {len(available_images)} 张。");
                    return
                if os.path.exists(output_folder): shutil.rmtree(output_folder)
                os.makedirs(output_folder)
                random.shuffle(available_images)
                images_to_process = available_images[:total_needed]

                self.log_image(f"准备就绪: 将处理 {total_needed} 张图片, 分成 {num_groups} 组。")
                self.log_image("!!! 警告：处理成功后，原始图片将被删除以防重复。请确保您有备份。 !!!")

                total_processed_count = 0
                for group_idx, group_name in enumerate(group_names):
                    if self.image_stop_event.is_set(): self.log_image("🔴 任务已中止."); break
                    start_index, end_index = group_idx * num_captions_per_set, (group_idx + 1) * num_captions_per_set
                    image_chunk = images_to_process[start_index:end_index]
                    group_folder = os.path.join(output_folder, group_name)
                    os.makedirs(group_folder, exist_ok=True)
                    self.log_image(f"\n---=== 开始处理组: {group_name} ===---")

                    for j, img_name in enumerate(image_chunk):
                        if self.image_stop_event.is_set(): self.log_image("🔴 任务在组内中止."); break

                        source_path = os.path.join(image_folder, img_name)
                        output_path = os.path.join(group_folder, img_name)
                        caption = captions[j]
                        # 常规模式依然使用随机定位
                        pos_config = random.choice(config.get("text_positions", [[0.5, 0.5]]))

                        result = image_apply_text(source_path, caption, config, pos_config, output_path, self.log_image,
                                                  self.image_stop_event)

                        if result == 'STOPPED':
                            break
                        elif result is True:
                            try:
                                os.remove(source_path)
                                self.log_image(f"  🗑️ 已删除源图片: {img_name}");
                                total_processed_count += 1
                            except OSError as e:
                                self.log_image(f"  ❌ 删除源图片失败: {img_name} - {e}")
                        else:
                            if os.path.exists(output_path):
                                try:
                                    os.remove(output_path)
                                except OSError:
                                    pass
                    if self.image_stop_event.is_set(): break

                if not self.image_stop_event.is_set():
                    self.log_image(f"\n---=== 图片处理完毕！总共处理并删除 {total_processed_count} 张图片 ===---")
                    if total_processed_count > 0:
                        tk_messagebox.showinfo("图片处理完成",
                                               f"总共处理并删除了 {total_processed_count} 张图片。\n输出文件夹: '{output_folder}'")
            except Exception as e:
                self.log_image(f"发生未预料的严重错误: {e}")
                traceback.print_exc()
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
            image_source_folder, greenscreen_parent_folder, output_folder = self.ab_image_source_folder_entry.get(), self.ab_greenscreen_folder_entry.get(), self.ab_output_folder_entry.get()
            if not all([image_source_folder, greenscreen_parent_folder, output_folder]): self.log_ab(
                "❌ 错误: 所有文件夹路径都必须填写。"); return

            num_groups_str = self.ab_num_groups_entry.get().strip()
            phone_serials_str = self.ab_phone_serial_entry.get().strip()
            group_names, num_groups = [], 0

            if phone_serials_str:
                group_names = [name.strip() for name in phone_serials_str.split('.') if name.strip()]
                if not group_names: self.log_ab("错误: 手机序号输入无效。"); self.after(0,
                                                                                       self._reset_ab_buttons); return
                num_groups = len(group_names)
                self.log_ab(f"手机序号模式激活，将创建 {num_groups} 个指定名称的文件夹。")
            elif num_groups_str:
                try:
                    num_groups = int(num_groups_str)
                    if num_groups <= 0: raise ValueError
                    group_names = [f"{i + 1}" for i in range(num_groups)]
                    self.log_ab(f"组数模式激活，将创建 {num_groups} 个文件夹。")
                except (ValueError, TypeError):
                    self.log_ab("错误: '生成组数' 必须是一个有效的正整数。"); self.after(0,
                                                                                        self._reset_ab_buttons); return
            else:
                self.log_ab("错误: '生成组数' 或 '手机序号' 必须填写一个。");
                self.after(0, self._reset_ab_buttons);
                return

            self.log_ab("正在扫描素材文件...")
            image_ext = ('.png', '.jpg', '.jpeg', '.webp')
            source_images = sorted([os.path.join(image_source_folder, f) for f in os.listdir(image_source_folder) if
                                    f.lower().endswith(image_ext)])
            greenscreen_subfolders = [os.path.join(greenscreen_parent_folder, sub) for sub in
                                      os.listdir(greenscreen_parent_folder) if
                                      os.path.isdir(os.path.join(greenscreen_parent_folder, sub)) and any(
                                          f.lower().endswith(image_ext) for f in
                                          os.listdir(os.path.join(greenscreen_parent_folder, sub)))]
            self.log_ab(f"🔍 扫描结果: 背景图 {len(source_images)} 张, 绿幕文件夹 {len(greenscreen_subfolders)} 个。")
            if not greenscreen_subfolders: self.log_ab(f"❌ 错误: 未找到任何合规的绿幕图片子文件夹。"); return
            images_needed_per_batch = sum(
                len([f for f in os.listdir(gs_folder) if f.lower().endswith(image_ext)]) for gs_folder in
                greenscreen_subfolders)
            if images_needed_per_batch == 0: self.log_ab("❌ 错误: 所有合规的绿幕文件夹都是空的。"); return
            total_images_needed = images_needed_per_batch * num_groups
            if len(source_images) < total_images_needed:
                self.log_ab(
                    f"❌ 错误: 背景图片素材不足！需要 {total_images_needed} 张, 但当前只有 {len(source_images)} 张。");
                return
            random.shuffle(source_images);
            greenscreen_subfolders.sort()
            if os.path.exists(output_folder): shutil.rmtree(output_folder)
            os.makedirs(output_folder)
            self.log_ab(f"▶️ 准备就绪: 将生成 {num_groups} 大组。")
            self.log_ab("⚠️ 警告: 处理成功后，原始背景图片将被删除！")

            for group_name in group_names:
                if self.ab_image_stop_event.is_set(): break
                self.log_ab(f"\n---=== 开始处理组: {group_name} ===---")
                group_output_folder = os.path.join(output_folder, group_name);
                os.makedirs(group_output_folder, exist_ok=True)
                for gs_folder in greenscreen_subfolders:
                    if self.ab_image_stop_event.is_set(): break
                    folder_tag = os.path.basename(gs_folder);
                    self.log_ab(f"  -- 开始处理子文件夹: {folder_tag} --")
                    current_gs_images = sorted([f for f in os.listdir(gs_folder) if f.lower().endswith(image_ext)])
                    for gs_image_name in current_gs_images:
                        if self.ab_image_stop_event.is_set() or not source_images:
                            if not source_images: self.log_ab("  ❌ 致命错误: 背景图片已用尽，任务提前中止。")
                            self.ab_image_stop_event.set();
                            break
                        bg_path, greenscreen_path = source_images.pop(0), os.path.join(gs_folder, gs_image_name)
                        image_tag = os.path.splitext(gs_image_name)[0];
                        output_filename = f"{folder_tag}-{image_tag}.png"
                        output_path = os.path.join(group_output_folder, output_filename)
                        self.log_ab(f"    - 合成: {os.path.basename(bg_path)} + {gs_image_name} -> {output_filename}")
                        if self._ab_worker(bg_path, greenscreen_path, output_path):
                            try:
                                os.remove(bg_path); self.log_ab(
                                    f"      ✅ 合成成功，已删除背景图: {os.path.basename(bg_path)}")
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
            traceback.print_exc()
        finally:
            self.after(0, self._reset_ab_buttons)
    # --- 长视频分割 (Video Splitting) ---
    def log_splitter(self, message, clear=False):
        """向长视频分割日志框记录信息"""
        self.after(0, self._update_log, self.splitter_log_textbox, message, clear)

    def start_video_split(self):
        """开始视频分割的线程，增加预裁剪的模板设置步骤"""
        self.splitter_stop_event.clear()

        input_folder = self.splitter_input_folder_entry.get()
        if not input_folder:
            tk_messagebox.showerror("错误", "请先选择长视频文件夹！")
            return

        video_files = [os.path.join(r, f) for r, d, fs in os.walk(input_folder) for f in fs if
                       f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
        if not video_files:
            tk_messagebox.showerror("错误", "在指定的文件夹中未找到任何视频文件！")
            return

        crop_roi = None
        if self.splitter_crop_switch.get() == 1:
            first_video_path = video_files[0]
            self.log_splitter(f"请为模板视频 '{os.path.basename(first_video_path)}' 框选要裁剪的区域...", clear=True)
            self.update_idletasks()

            crop_roi, msg = self._news_select_roi(first_video_path, "设置预裁剪区域")
            self.log_splitter(msg)

            if not crop_roi:
                self.log_splitter("操作已取消，任务中止。")
                return

        self.start_splitter_button.configure(state="disabled")
        self.stop_splitter_button.configure(state="normal")

        # 将视频列表和裁剪区域作为参数，传递给后台线程
        threading.Thread(target=self.run_video_split_logic, args=(video_files, crop_roi), daemon=True).start()
    def stop_video_split(self):
        """发送正确的停止信号"""
        self.log_splitter("🔴 发送停止信号...请等待当前文件处理完毕。")
        self.splitter_stop_event.set() # 确保设置的是 splitter_stop_event
        self.stop_splitter_button.configure(state="disabled")

    def _reset_splitter_buttons(self):
        """重置开始/停止按钮的状态"""
        self.start_splitter_button.configure(state="normal")
        self.stop_splitter_button.configure(state="disabled")

    def _reset_splitter_buttons(self):
        """重置“长视频分割”功能的开始/停止按钮状态"""
        self.start_splitter_button.configure(state="normal")
        self.stop_splitter_button.configure(state="disabled")

    # --- 视频截图片 (Frame Extraction) ---
    def log_extractor(self, message, clear=False):
        """向视频截图片日志框记录信息"""
        self.after(0, self._update_log, self.extractor_log_textbox, message, clear)

    def run_video_split_logic(self, video_files, crop_roi):
        """【最终修正版】视频分割的主逻辑 (可接收预裁剪参数)"""
        temp_files_to_clean = []
        try:
            output_folder = self.splitter_output_folder_entry.get()
            use_gpu = self.splitter_use_gpu_switch.get() == 1
            is_smart_resize = self.splitter_smart_resize_switch.get() == 1

            if not output_folder:
                self.log_splitter("❌ 错误: 输出文件夹必须选择。");
                return

            try:
                original_duration = float(self.splitter_duration_entry.get())
                if original_duration <= 0: raise ValueError
                split_duration = original_duration
                self.log_splitter(f"信息: 为确保时长精确，后台将使用 {split_duration:.2f}s 进行分割。")
            except (ValueError, TypeError):
                self.log_splitter("❌ 错误: 分割时长必须是一个有效的正数。");
                return

            self.log_splitter(f"\n★★★ 模板设置完成！将对所有 {len(video_files)} 个视频应用此设置。 ★★★")

            if not os.path.exists(output_folder): os.makedirs(output_folder)

            temp_resize_dir = os.path.join(output_folder, "temp_resize_area")
            if is_smart_resize:
                if os.path.exists(temp_resize_dir): shutil.rmtree(temp_resize_dir)
                os.makedirs(temp_resize_dir)

            total_clips_generated = 0
            for i, video_path in enumerate(video_files):
                if self.splitter_stop_event.is_set():
                    self.log_splitter("🔴 任务已中止。");
                    break

                self.log_splitter(
                    f"\n---=== 开始处理第 {i + 1}/{len(video_files)} 个视频: {os.path.basename(video_path)} ===---")

                path_to_split, temp_resized_file = video_path, None
                if is_smart_resize:
                    self.log_splitter(f"  -> [预处理] 正在对视频进行智能缩放...")
                    resized_path = os.path.join(temp_resize_dir, f"resized_{os.path.basename(video_path)}")

                    if self._smart_resize_worker(video_path, resized_path, (1080, 1920)):
                        self.log_splitter(f"  -> ✅ 智能缩放成功。")
                        path_to_split = resized_path
                        temp_files_to_clean.append(resized_path)
                    else:
                        self.log_splitter(f"  -> ❌ 智能缩放失败，将跳过此视频的分割。");
                        continue

                clips_count = self._video_split_worker(path_to_split, output_folder, split_duration, use_gpu, crop_roi)

                if clips_count > 0:
                    total_clips_generated += clips_count
                    self.log_splitter(f"  ✅ 成功分割出 {clips_count} 个片段。")

                if temp_resized_file and os.path.exists(temp_resized_file):
                    try:
                        os.remove(temp_resized_file)
                    except OSError:
                        pass

            if not self.splitter_stop_event.is_set():
                self.log_splitter(f"\n---=== 所有任务处理完毕！总共生成了 {total_clips_generated} 个短视频片段。 ===---")

        except Exception as e:
            self.log_splitter(f"发生未预料的严重错误: {e}")
            traceback.print_exc()
        finally:
            self.log_splitter("\n--- [任务结束] 正在清理所有临时文件... ---")
            for f in temp_files_to_clean:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            if 'temp_resize_dir' in locals() and os.path.exists(temp_resize_dir):
                try:
                    shutil.rmtree(temp_resize_dir)
                except OSError:
                    pass
            self.log_splitter("--- 清理完毕 ---")
            self.after(0, self._reset_splitter_buttons)
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

    def _video_split_worker(self, video_path, output_folder, duration, use_gpu, crop_roi=None):
        """【高速流复制版】如果未使用裁剪，则采用流复制模式进行高速分割。"""
        generated_count = 0
        try:
            ffmpeg_path = self._find_executable("ffmpeg")
            ffprobe_path = self._find_executable("ffprobe")
            if not ffmpeg_path or not ffprobe_path:
                self.log_splitter(f"  ❌ 错误: 找不到 ffmpeg 或 ffprobe。")
                return 0

            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = subprocess.CREATE_NO_WINDOW

            safe_ffprobe_path = f'"{os.path.normpath(ffprobe_path)}"'
            safe_input_path = f'"{os.path.normpath(video_path)}"'
            cmd_probe_str = f'{safe_ffprobe_path} -v error -select_streams v:0 -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {safe_input_path}'

            result = subprocess.run(cmd_probe_str, shell=True, check=True, capture_output=True, text=True,
                                    encoding='utf-8', creationflags=creation_flags)
            total_duration = float(result.stdout.strip())

            base_name = os.path.splitext(os.path.basename(video_path))[0]

            for i in range(int(total_duration // duration)):
                if self.splitter_stop_event.is_set(): break

                start_time = i * duration
                output_filename = f"{base_name}_part_{i + 1:03d}.mp4"
                output_path = os.path.join(output_folder, output_filename)

                self.log_splitter(f"  - 正在导出片段: {i + 1:03d} (从 {start_time:.2f}s 开始，时长 {duration:.2f}s)")

                safe_ffmpeg_path = f'"{os.path.normpath(ffmpeg_path)}"'
                safe_output_path = f'"{os.path.normpath(output_path)}"'

                command_parts = [safe_ffmpeg_path, '-y', '-ss', str(start_time), '-i', safe_input_path, '-t',
                                 str(duration)]

                if crop_roi:
                    # 如果启用了裁剪，必须重新编码，无法使用流复制
                    self.log_splitter("    -> 检测到预裁剪，将使用重新编码模式（速度较慢）。")
                    x, y, w, h = crop_roi
                    video_codec = 'h264_nvenc' if use_gpu and self.is_gpu_available else 'libx264'
                    preset = 'fast' if use_gpu else 'medium'
                    command_parts.extend(
                        [f'-vf "crop={w}:{h}:{x}:{y}"', '-c:v', video_codec, '-preset', preset, '-c:a', 'aac'])
                else:
                    # 如果没有裁剪，使用高速流复制模式

                    command_parts.extend(['-c', 'copy'])  # 复制视频和音频流

                command_parts.extend(['-map_metadata', '-1', safe_output_path])
                command_string = " ".join(command_parts)

                try:
                    subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True,
                                   encoding='utf-8', errors='ignore', creationflags=creation_flags)
                    generated_count += 1
                except subprocess.CalledProcessError as e_inner:
                    # 流复制模式失败的可能性很小，但为GPU编码失败提供回退
                    if crop_roi and use_gpu:
                        self.log_splitter("    -> 警告: GPU编码失败，自动尝试用CPU重试...")
                        command_string = command_string.replace('h264_nvenc', 'libx264').replace('fast', 'medium')
                        subprocess.run(command_string, shell=True, check=True, capture_output=True, text=True,
                                       encoding='utf-8', errors='ignore', creationflags=creation_flags)
                        generated_count += 1
                    else:
                        # 如果是流复制模式失败或CPU模式失败，则直接抛出
                        raise e_inner

        except subprocess.CalledProcessError as e:
            self.log_splitter(f"  ❌ FFmpeg 处理失败:\n{e.stderr.strip()}")
            return generated_count
        except Exception as e:
            self.log_splitter(f"  ❌ 处理视频 {os.path.basename(video_path)} 时发生错误: {e}")
            return generated_count

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

    def get_image_config_from_gui(self):
        try:
            pos_text = self.image_text_positions_textbox.get("1.0", "end-1c")
            pos_list = json.loads(pos_text.replace("'", "\""))
            zoom_text = self.image_zoom_crop_percentages_textbox.get("1.0", "end-1c")
            zoom_list = [float(x.strip()) for x in zoom_text.split(',') if x.strip()]
            spacing_text = self.image_line_spacing_options_textbox.get("1.0", "end-1c")
            spacing_list = [int(x.strip()) for x in spacing_text.split(',') if x.strip()]

            config = {
                # 共享样式和配置
                "text_positions": pos_list,
                "max_text_width_ratio": float(self.image_max_text_width_ratio_entry.get()),
                "line_spacing_options": spacing_list,
                "corner_radius": int(self.image_corner_radius_entry.get()),
                "text_padding": int(self.image_text_padding_entry.get()),
                "text_align_in_block": self.image_text_align_in_block_menu.get(),
                "zoom_crop_percentages": zoom_list,
                "allow_random_horizontal_flip": bool(self.image_flip_switch.get()),
                "no_background": self.image_no_bg_switch.get() == 1,
                # 主文案设置 (使用现有控件)
                "main_text": {
                    "font_path": self.image_font_path_entry.get(),
                    "font_size": int(self.image_font_size_entry.get()),
                    "font_color": list(ImageColor.getrgb(self.image_font_color_value)),
                    "font_background_color": list(ImageColor.getrgb(self.image_font_background_color_value)),
                },
                # 次文案设置 (从新增控件读取)
                "sub_text": {
                    "relative_y_offset": int(self.image_sub_offset_y_entry.get()),
                    "font_color": list(ImageColor.getrgb(self.image_sub_color_text_value)),
                    "font_background_color": list(ImageColor.getrgb(self.image_sub_color_bg_value)),
                }

            }
            return config
        except Exception as e:
            self.log_image(f"图片配置错误: {e}")
            return None

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
        """
        【v6.0 总调度函数】根据UI开关的状态，选择使用“逐行背景”或“整体背景”模式。
        """
        # 检查新添加的开关状态
        if self.video_line_by_line_bg_switch.get() == 1:
            # 开关打开，调用逐行处理函数
            return self._create_overlay_line_by_line(text, shared_style, specific_config, video_size)
        else:
            # 开关关闭，调用原始的整体处理函数
            return self._create_overlay_block_style(text, shared_style, specific_config, video_size)

    def _create_overlay_block_style(self, text, shared_style, specific_config, video_size):
        """
        【v6.0 新增】原始的“整体背景”渲染逻辑。为整个文本块创建一个背景。
        """
        video_width, _ = video_size
        colors = specific_config['颜色']
        text_color, stroke_color, bg_color_str = colors['文字颜色'], colors.get('描边颜色'), colors.get('背景颜色',
                                                                                                        'rgba(0,0,0,0)')
        padding_horizontal, padding_vertical = shared_style.get("左右内边距", 30), shared_style.get('垂直内边距', 25)
        font_file, font_size, stroke_width = shared_style['字体文件'], shared_style['字体大小'], shared_style.get(
            '描边粗细', 0)
        corner_radius, max_width_ratio, no_background = shared_style.get('背景圆角半径', 0), shared_style.get(
            '最大宽度比例', 0.9), shared_style.get('禁用背景', False)

        try:
            font = ImageFont.truetype(font_file, font_size)
        except IOError:
            font = ImageFont.load_default()

        max_pixel_width = int(video_width * max_width_ratio)
        dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

        manual_lines_raw = text.split('/')
        final_lines = []
        for raw_line in manual_lines_raw:
            wrapped_lines, _, _ = image_wrap_text(dummy_draw, raw_line.strip(), font, max_pixel_width)
            final_lines.extend(wrapped_lines)

        text_for_drawing = '\n'.join(final_lines)
        if not text_for_drawing: return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        text_bbox = dummy_draw.multiline_textbbox((0, 0), text_for_drawing, font=font, align='center',
                                                  stroke_width=stroke_width)
        text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]

        bg_w = int(text_w + 2 * padding_horizontal)
        bg_h = int(text_h + 2 * padding_vertical)

        overlay_image = Image.new("RGBA", (bg_w, bg_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_image)

        if not no_background:
            bg_rgb, bg_alpha = video_parse_rgba(bg_color_str)
            bg_fill_color = bg_rgb + (int(bg_alpha * 255),)
            if corner_radius > 0:
                draw.rounded_rectangle(((0, 0), (bg_w, bg_h)), int(corner_radius), fill=bg_fill_color)
            else:
                draw.rectangle(((0, 0), (bg_w, bg_h)), fill=bg_fill_color)

        text_x = (bg_w - text_w) / 2
        text_y = (bg_h - text_h) / 2 - text_bbox[1]
        draw.multiline_text((text_x, text_y), text_for_drawing, fill=text_color, font=font, align='center',
                            stroke_width=stroke_width, stroke_fill=stroke_color)

        return overlay_image

    def _create_overlay_line_by_line(self, text, shared_style, specific_config, video_size):
        """
        【v6.0 新增】无缝隙的“逐行背景”渲染逻辑。
        """
        video_width, _ = video_size
        colors = specific_config['颜色']
        text_color, stroke_color, bg_color_str = colors['文字颜色'], colors.get('描边颜色'), colors.get('背景颜色',
                                                                                                        'rgba(0,0,0,0)')
        padding_horizontal, padding_vertical = shared_style.get("左右内边距", 30), shared_style.get('垂直内边距', 25)
        font_file, font_size, stroke_width = shared_style['字体文件'], shared_style['字体大小'], shared_style.get(
            '描边粗细', 0)
        corner_radius, max_width_ratio, no_background = shared_style.get('背景圆角半径', 0), shared_style.get(
            '最大宽度比例', 0.9), shared_style.get('禁用背景', False)

        try:
            font = ImageFont.truetype(font_file, font_size)
        except IOError:
            font = ImageFont.load_default()

        max_pixel_width = int(video_width * max_width_ratio)
        dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

        manual_lines_raw = text.split('/')
        final_lines = []
        for raw_line in manual_lines_raw:
            wrapped_lines, _, _ = image_wrap_text(dummy_draw, raw_line.strip(), font, max_pixel_width)
            final_lines.extend(wrapped_lines)

        if not final_lines: return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        line_bboxes = [dummy_draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width) for line in final_lines]
        line_widths, line_heights = [b[2] - b[0] for b in line_bboxes], [b[3] - b[1] for b in line_bboxes]

        line_spacing = 0  # 确保背景框之间无缝隙

        canvas_width = int(max(line_widths) + (2 * padding_horizontal))
        canvas_height = int(
            sum(line_heights) + len(final_lines) * (2 * padding_vertical) + (len(final_lines) - 1) * line_spacing)

        overlay_image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_image)

        current_y = 0
        for i, line in enumerate(final_lines):
            line_w, line_h, line_bbox = line_widths[i], line_heights[i], line_bboxes[i]
            line_x_start = (canvas_width - line_w) / 2

            if not no_background:
                bg_rgb, bg_alpha = video_parse_rgba(bg_color_str)
                bg_fill_color = bg_rgb + (int(bg_alpha * 255),)
                bg_top, bg_bottom = current_y, current_y + padding_vertical + line_h + padding_vertical
                bg_coords = ((canvas_width - (line_w + 2 * padding_horizontal)) / 2, bg_top,
                             (canvas_width + (line_w + 2 * padding_horizontal)) / 2, bg_bottom)
                if corner_radius > 0:
                    draw.rounded_rectangle(bg_coords, radius=int(corner_radius), fill=bg_fill_color)
                else:
                    draw.rectangle(bg_coords, fill=bg_fill_color)

            text_y = current_y + padding_vertical
            text_pos = (line_x_start, text_y - line_bbox[1])
            draw.text(text_pos, line, font=font, fill=text_color, stroke_width=stroke_width, stroke_fill=stroke_color)
            current_y += (padding_vertical + line_h + padding_vertical) + line_spacing

        return overlay_image
    def save_settings(self):
        """【最终完整版】保存所有模块的所有UI配置信息。"""
        settings = {
            'video_settings': {
                'folder_path': self.video_folder_entry.get(),
                'output_path': self.video_output_folder_entry.get(),
                'text_input': self.video_text_input_box.get("1.0", "end-1c"),
                'num_groups': self.video_num_groups_entry.get(),
                'phone_serial': self.video_phone_serial_entry.get(),
                'durations': self.video_durations_entry.get(),
                'use_gpu': self.video_use_gpu_switch.get(),
                'random_remix': self.video_random_remix_switch.get(),
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
                'line_by_line_bg': self.video_line_by_line_bg_switch.get(),
                'sub1_offset_y': self.video_sub1_offset_y_entry.get(),
                'sub1_color_text': self.video_sub1_color_text_value,
                'sub1_color_stroke': self.video_sub1_color_stroke_value,
                'sub1_color_bg': self.video_sub1_color_bg_value,
                'sub2_offset_y': self.video_sub2_offset_y_entry.get(),
                'sub2_color_text': self.video_sub2_color_text_value,
                'sub2_color_stroke': self.video_sub2_color_stroke_value,
                'sub2_color_bg': self.video_sub2_color_bg_value,
            },
            'distribution_settings': {
                'image_folder': self.dist_image_folder_entry.get(),
                'output_folder': self.dist_output_folder_entry.get(),
                'phone_serial': self.dist_phone_serial_entry.get(),
            },
            'image_settings': {
                'folder_path': self.image_folder_entry.get(),
                'output_path': self.image_output_folder_entry.get(),
                'text_input': self.image_text_input_box.get("1.0", "end-1c"),
                'num_groups': self.image_num_groups_entry.get(),
                'phone_serial': self.image_phone_serial_entry.get(),
                'font_path': self.image_font_path_entry.get(),
                'font_size': self.image_font_size_entry.get(),
                'font_color': self.image_font_color_value,
                'font_background_color': self.image_font_background_color_value,
                'sub_offset_y': self.image_sub_offset_y_entry.get(),
                'sub_color_text': self.image_sub_color_text_value,
                'sub_color_bg': self.image_sub_color_bg_value,
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

            'ab_image_settings': {
                'source_folder': self.ab_image_source_folder_entry.get(),
                'greenscreen_folder': self.ab_greenscreen_folder_entry.get(),
                'output_folder': self.ab_output_folder_entry.get(),
                'num_groups': self.ab_num_groups_entry.get(),
                'phone_serial': self.ab_phone_serial_entry.get()
            },
            'video_splitter_settings': {
                'input_folder': self.splitter_input_folder_entry.get(),
                'output_folder': self.splitter_output_folder_entry.get(),
                'duration': self.splitter_duration_entry.get(),
                'use_gpu': self.splitter_use_gpu_switch.get(),
                'smart_resize': self.splitter_smart_resize_switch.get(),
            },
            'frame_extractor_settings': {
                'input_folder': self.extractor_input_folder_entry.get(),
                'output_folder': self.extractor_output_folder_entry.get(),
                'interval': self.extractor_interval_entry.get(),
                'resize': self.extractor_resize_switch.get()
            },
            'news_greenscreen_settings': {
                'content_folder': self.news_content_folder_entry.get(),
                'template_folder': self.news_template_folder_entry.get(),
                'output_folder': self.news_output_folder_entry.get(),
                'crop_duration': self.news_crop_duration_entry.get(),
                'mirror': self.news_mirror_switch.get(),
                'zoom': self.news_zoom_entry.get()
            },
            'news_blur_settings': {
                'input_folder': self.blur_input_folder_entry.get(),
                'output_folder': self.blur_output_folder_entry.get(),
                'crop_duration': self.blur_crop_duration_entry.get(),
                'mirror': self.blur_mirror_switch.get(),
                'zoom': self.blur_zoom_entry.get()
            },
            'greenscreen_composite_settings': {
                'source_folder': self.gs_composite_source_folder_entry.get(),
                'bg_folder': self.gs_composite_bg_folder_entry.get(),
                'output_folder': self.gs_composite_output_folder_entry.get(),
                'use_gs_audio': self.gs_composite_use_gs_audio_switch.get(),
                'num_groups': self.composite_num_groups_entry.get(),
                'phone_serial': self.composite_phone_serial_entry.get(),
                #'ghost_freeze': self.gs_composite_ghost_freeze_switch.get(),
                'freeze_duration': self.composite_freeze_duration_entry.get(),
                'similarity': self.gs_composite_similarity_slider.get(),
                'blend': self.gs_composite_blend_slider.get(),
                'despill': self.gs_composite_despill_slider.get(),
                'quality': self.gs_composite_quality_slider.get()
            },
            'video_clone_settings': {
                'input_folder': self.clone_input_folder_entry.get(),
                'output_folder': self.clone_output_folder_entry.get(),
                'duration': self.clone_total_duration_entry.get()
            },
            'cut_settings': {
                'input_folder': self.cut_input_folder_entry.get(),
                'output_folder': self.cut_output_folder_entry.get(),
                'play_until': self.cut_play_until_entry.get(),
                'resume_from': self.cut_resume_from_entry.get(),
            },
            'lut_settings': {
                'video_folder': self.lut_video_folder_entry.get(),
                'filter_folder': self.lut_filter_folder_entry.get(),
                'output_folder': self.lut_output_folder_entry.get(),
            },
            'audio_extractor_settings': {
                'input_folder': self.audio_input_folder_entry.get(),
                'output_folder': self.audio_output_folder_entry.get(),
                'duration': self.audio_duration_entry.get()
            },
            'dualscreen_settings': {
                'folder_a': self.dualscreen_folder_a_entry.get(),
                'folder_b': self.dualscreen_folder_b_entry.get(),
                'output_folder': self.dualscreen_output_folder_entry.get()
            },
            'ios_transfer_settings': {
                'source_folder': self.ios_source_folder_entry.get()
            },
            'uniform_resolution_settings': {
                'input_folder': self.uniform_res_input_folder_entry.get(),
                'output_folder': self.uniform_res_output_folder_entry.get()
            },
            'avatar_settings': {
                'input_folder': self.avatar_input_folder_entry.get(),
                'output_folder': self.avatar_output_folder_entry.get(),
                'zoom': self.avatar_zoom_entry.get(),
                'mirror': self.avatar_mirror_switch.get(),
                'contrast': self.avatar_contrast_entry.get(),
                'brightness': self.avatar_brightness_entry.get(),
                'saturation': self.avatar_saturation_entry.get()
            },
            'porter_settings': {
                'dir_a': self.porter_dir_a_entry.get(),
                'dir_b': self.porter_dir_b_entry.get(),
                'output_dir': self.porter_output_dir_entry.get(),
                'preprocess_trim': self.porter_preprocess_trim_entry.get(),
                'zoom': self.porter_zoom_entry.get(),
                'stretch_h': self.porter_stretch_h_entry.get(),
                'stretch_o': self.porter_stretch_o_entry.get(),
                'rotate_o': self.porter_rotate_o_entry.get(),
                'rotate_s': self.porter_rotate_s_entry.get(),
                'rotate_a_vol': self.porter_rotate_a_vol_entry.get(),
                'contrast': self.porter_contrast_entry.get(),
                'brightness': self.porter_brightness_entry.get(),
                'saturation': self.porter_saturation_entry.get()
            },
            'health_image_settings': {
                'folder_path': self.health_folder_entry.get(),
                'output_path': self.health_output_folder_entry.get(),
                'text_input': self.health_text_input_box.get("1.0", "end-1c"),
                'num_groups': self.health_num_groups_entry.get(),
                'phone_serial': self.health_phone_serial_entry.get(),
            },
        }
        try:
            with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        """【最终完整版】加载所有模块的所有UI配置信息，并修复重复加载和NameError的bug"""
        try:
            with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self.settings_loaded = True
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings_loaded = False
            return

        def _load_entry(entry_widget_name, config, key, default=''):
            if hasattr(self, entry_widget_name):
                widget = getattr(self, entry_widget_name)
                widget.delete(0, 'end')
                widget.insert(0, config.get(key, default))

        def _load_textbox(textbox_widget_name, config, key, default=''):
            if hasattr(self, textbox_widget_name):
                widget = getattr(self, textbox_widget_name)
                widget.delete("1.0", "end")
                widget.insert("1.0", config.get(key, default))

        def _load_switch(switch_widget_name, config, key, default=False):
            if hasattr(self, switch_widget_name):
                widget = getattr(self, switch_widget_name)
                if config.get(key, default):
                    widget.select()
                else:
                    widget.deselect()

        def _load_option_menu(menu_widget_name, config, key, default=''):
            if hasattr(self, menu_widget_name):
                widget = getattr(self, menu_widget_name)
                options = widget.cget("values")
                value_to_set = config.get(key, default)
                if value_to_set in options:
                    widget.set(value_to_set)
                elif default and default in options:
                    widget.set(default)

        def _load_slider(slider_widget_name, config, key, default=0):
            if hasattr(self, slider_widget_name):
                getattr(self, slider_widget_name).set(config.get(key, default))

        # --- 使用辅助函数统一加载所有配置 ---
        vs = settings.get('video_settings', {})
        _load_entry('video_folder_entry', vs, 'folder_path')
        _load_entry('video_output_folder_entry', vs, 'output_path')
        _load_textbox('video_text_input_box', vs, 'text_input')
        _load_entry('video_num_groups_entry', vs, 'num_groups', '1')
        _load_entry('video_phone_serial_entry', vs, 'phone_serial')
        _load_entry('video_durations_entry', vs, 'durations')
        _load_switch('video_use_gpu_switch', vs, 'use_gpu')
        _load_switch('video_random_remix_switch', vs, 'random_remix')
        _load_entry('video_shared_font_file_entry', vs, 'shared_font_file',
                    get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf')))
        _load_entry('video_shared_size_entry', vs, 'shared_size', '60')
        _load_entry('video_shared_max_width_ratio_entry', vs, 'shared_max_width_ratio', '0.9')
        _load_entry('video_shared_padding_horizontal_entry', vs, 'shared_padding_horizontal', '30')
        _load_entry('video_shared_padding_vertical_entry', vs, 'shared_padding_vertical', '25')
        _load_entry('video_shared_stroke_width_entry', vs, 'shared_stroke_width', '2')
        _load_entry('video_shared_corner_radius_entry', vs, 'shared_corner_radius', '20')
        _load_switch('video_no_bg_switch', vs, 'no_background')
        _load_switch('video_line_by_line_bg_switch', vs, 'line_by_line_bg', True)
        _load_entry('video_main_pos_x_entry', vs, 'main_pos_x', 'center')
        _load_entry('video_main_pos_y_entry', vs, 'main_pos_y', '150')
        self._update_color_widget('video_main_color_text', vs.get('main_color_text', 'white'))
        self._update_color_widget('video_main_color_stroke', vs.get('main_color_stroke', 'black'))
        self._update_color_widget('video_main_color_bg', vs.get('main_color_bg', 'rgba(0, 0, 0)'))
        _load_entry('video_sub1_offset_y_entry', vs, 'sub1_offset_y', '20')
        self._update_color_widget('video_sub1_color_text', vs.get('sub1_color_text', '#FFD700'))
        self._update_color_widget('video_sub1_color_stroke', vs.get('sub1_color_stroke', 'black'))
        self._update_color_widget('video_sub1_color_bg', vs.get('sub1_color_bg', 'rgba(200,50,50)'))
        _load_entry('video_sub2_offset_y_entry', vs, 'sub2_offset_y', '30')
        self._update_color_widget('video_sub2_color_text', vs.get('sub2_color_text', 'white'))
        self._update_color_widget('video_sub2_color_stroke', vs.get('sub2_color_stroke', 'black'))
        self._update_color_widget('video_sub2_color_bg', vs.get('sub2_color_bg', 'rgba(50,50,50)'))

        imgs = settings.get('image_settings', {})
        _load_entry('image_folder_entry', imgs, 'folder_path')
        _load_entry('image_output_folder_entry', imgs, 'output_path')
        _load_textbox('image_text_input_box', imgs, 'text_input')
        _load_entry('image_num_groups_entry', imgs, 'num_groups', '1')
        _load_entry('image_phone_serial_entry', imgs, 'phone_serial')
        _load_entry('image_font_path_entry', imgs, 'font_path',
                    get_resource_path(os.path.join('assets', 'WenYue_XinQingNianTi_J-W8.otf')))
        _load_entry('image_font_size_entry', imgs, 'font_size', '75')
        self._update_color_widget('image_font_color', imgs.get('font_color', '#FFFFFF'))
        self._update_color_widget('image_font_background_color', imgs.get('font_background_color', '#000000'))
        _load_entry('image_sub_offset_y_entry', imgs, 'sub_offset_y', '20')
        self._update_color_widget('image_sub_color_text', imgs.get('sub_color_text', '#FFD700'))
        self._update_color_widget('image_sub_color_bg', imgs.get('sub_color_bg', 'rgba(50,50,50)'))
        _load_entry('image_max_text_width_ratio_entry', imgs, 'max_text_width_ratio', '0.85')
        _load_entry('image_corner_radius_entry', imgs, 'corner_radius', '15')
        _load_entry('image_text_padding_entry', imgs, 'text_padding', '20')
        _load_option_menu('image_text_align_in_block_menu', imgs, 'text_align_in_block', 'center')
        _load_textbox('image_text_positions_textbox', imgs, 'text_positions', '[\n  [0.5, 0.5]\n]')
        _load_textbox('image_line_spacing_options_textbox', imgs, 'line_spacing_options', '25')
        _load_textbox('image_zoom_crop_percentages_textbox', imgs, 'zoom_crop_percentages', '0')
        _load_switch('image_flip_switch', imgs, 'allow_flip', True)
        _load_switch('image_no_bg_switch', imgs, 'no_background', False)


        ab_s = settings.get('ab_image_settings', {})
        _load_entry('ab_image_source_folder_entry', ab_s, 'source_folder')
        _load_entry('ab_greenscreen_folder_entry', ab_s, 'greenscreen_folder')
        _load_entry('ab_output_folder_entry', ab_s, 'output_folder')
        _load_entry('ab_num_groups_entry', ab_s, 'num_groups', '10')
        _load_entry('ab_phone_serial_entry', ab_s, 'phone_serial')

        splitter_s = settings.get('video_splitter_settings', {})
        _load_entry('splitter_input_folder_entry', splitter_s, 'input_folder')
        _load_entry('splitter_output_folder_entry', splitter_s, 'output_folder')
        _load_entry('splitter_duration_entry', splitter_s, 'duration', '3')
        _load_switch('splitter_use_gpu_switch', splitter_s, 'use_gpu')
        _load_switch('splitter_smart_resize_switch', splitter_s, 'smart_resize', True)

        extractor_s = settings.get('frame_extractor_settings', {})
        _load_entry('extractor_input_folder_entry', extractor_s, 'input_folder')
        _load_entry('extractor_output_folder_entry', extractor_s, 'output_folder')
        _load_entry('extractor_interval_entry', extractor_s, 'interval', '3')
        _load_switch('extractor_resize_switch', extractor_s, 'resize', True)

        dist_s = settings.get('distribution_settings', {})
        _load_entry('dist_image_folder_entry', dist_s, 'image_folder')
        _load_entry('dist_output_folder_entry', dist_s, 'output_folder')
        _load_entry('dist_phone_serial_entry', dist_s, 'phone_serial')

        news_gs = settings.get('news_greenscreen_settings', {})
        _load_entry('news_content_folder_entry', news_gs, 'content_folder')
        _load_entry('news_template_folder_entry', news_gs, 'template_folder')
        _load_entry('news_output_folder_entry', news_gs, 'output_folder')
        _load_entry('news_crop_duration_entry', news_gs, 'crop_duration', '4')
        _load_switch('news_mirror_switch', news_gs, 'mirror', False)
        _load_entry('news_zoom_entry', news_gs, 'zoom', '1.0')

        news_blur = settings.get('news_blur_settings', {})
        _load_entry('blur_input_folder_entry', news_blur, 'input_folder')
        _load_entry('blur_output_folder_entry', news_blur, 'output_folder')
        _load_entry('blur_crop_duration_entry', news_blur, 'crop_duration', '4')
        _load_switch('blur_mirror_switch', news_blur, 'mirror', False)
        _load_entry('blur_zoom_entry', news_blur, 'zoom', '1.0')

        gs_s = settings.get('greenscreen_composite_settings', {})
        _load_entry('gs_composite_source_folder_entry', gs_s, 'source_folder')
        _load_entry('gs_composite_bg_folder_entry', gs_s, 'bg_folder')
        _load_entry('gs_composite_output_folder_entry', gs_s, 'output_folder')
        _load_switch('gs_composite_use_gs_audio_switch', gs_s, 'use_gs_audio', False)
        #_load_switch('gs_composite_ghost_freeze_switch', gs_s, 'ghost_freeze', False)
        _load_entry('composite_num_groups_entry', gs_s, 'num_groups', '1')
        _load_switch('composite_remix_switch', gs_s, 'remix_mode', False)
        _load_entry('composite_freeze_duration_entry', gs_s, 'freeze_duration', '3')
        _load_slider('gs_composite_similarity_slider', gs_s, 'similarity', 0.2)
        _load_slider('gs_composite_blend_slider', gs_s, 'blend', 0.1)
        _load_slider('gs_composite_despill_slider', gs_s, 'despill', 0.5)
        _load_slider('gs_composite_quality_slider', gs_s, 'quality', 24)
        _load_entry('composite_phone_serial_entry', gs_s, 'phone_serial')
        _load_entry('ios_source_folder_entry', settings.get('ios_transfer_settings', {}), 'source_folder')
        _load_entry('clone_input_folder_entry', settings.get('video_clone_settings', {}), 'input_folder')
        _load_entry('clone_output_folder_entry', settings.get('video_clone_settings', {}), 'output_folder')
        _load_entry('clone_total_duration_entry', settings.get('video_clone_settings', {}), 'duration', '15')
        _load_entry('cut_input_folder_entry', settings.get('cut_settings', {}), 'input_folder')
        _load_entry('cut_output_folder_entry', settings.get('cut_settings', {}), 'output_folder')
        _load_entry('cut_play_until_entry', settings.get('cut_settings', {}), 'play_until', '2')
        _load_entry('cut_resume_from_entry', settings.get('cut_settings', {}), 'resume_from', '6')
        _load_entry('lut_video_folder_entry', settings.get('lut_settings', {}), 'video_folder')
        _load_entry('lut_filter_folder_entry', settings.get('lut_settings', {}), 'filter_folder')
        _load_entry('lut_output_folder_entry', settings.get('lut_settings', {}), 'output_folder')
        _load_entry('audio_input_folder_entry', settings.get('audio_extractor_settings', {}), 'input_folder')
        _load_entry('audio_output_folder_entry', settings.get('audio_extractor_settings', {}), 'output_folder')
        _load_entry('audio_duration_entry', settings.get('audio_extractor_settings', {}), 'duration')
        _load_entry('dualscreen_folder_a_entry', settings.get('dualscreen_settings', {}), 'folder_a')
        _load_entry('dualscreen_folder_b_entry', settings.get('dualscreen_settings', {}), 'folder_b')
        _load_entry('dualscreen_output_folder_entry', settings.get('dualscreen_settings', {}), 'output_folder')
        uni_res_s = settings.get('uniform_resolution_settings', {})
        _load_entry('uniform_res_input_folder_entry', uni_res_s, 'input_folder')
        _load_entry('uniform_res_output_folder_entry', uni_res_s, 'output_folder')
        avatar_s = settings.get('avatar_settings', {})
        _load_entry('avatar_input_folder_entry', avatar_s, 'input_folder')
        _load_entry('avatar_output_folder_entry', avatar_s, 'output_folder')
        _load_entry('avatar_zoom_entry', avatar_s, 'zoom', '2.0')
        _load_switch('avatar_mirror_switch', avatar_s, 'mirror', False)
        _load_entry('avatar_contrast_entry', avatar_s, 'contrast', '1.0')
        _load_entry('avatar_brightness_entry', avatar_s, 'brightness', '0.0')
        _load_entry('avatar_saturation_entry', avatar_s, 'saturation', '1.0')

        ps = settings.get('porter_settings', {})
        _load_entry('porter_dir_a_entry', ps, 'dir_a')
        _load_entry('porter_dir_b_entry', ps, 'dir_b')
        _load_entry('porter_output_dir_entry', ps, 'output_dir')
        _load_entry('porter_preprocess_trim_entry', ps, 'preprocess_trim', '0')
        _load_entry('porter_zoom_entry', ps, 'zoom', '1.5')
        _load_entry('porter_stretch_h_entry', ps, 'stretch_h', '1')
        _load_entry('porter_stretch_o_entry', ps, 'stretch_o', '50')
        _load_entry('porter_rotate_o_entry', ps, 'rotate_o', '20')
        _load_entry('porter_rotate_s_entry', ps, 'rotate_s', '20')
        _load_entry('porter_rotate_a_vol_entry', ps, 'rotate_a_vol', '50')
        _load_entry('porter_contrast_entry', ps, 'contrast', '1.1')
        _load_entry('porter_brightness_entry', ps, 'brightness', '0.03')
        _load_entry('porter_saturation_entry', ps, 'saturation', '1.2')

        health_s = settings.get('health_image_settings', {})
        _load_entry('health_folder_entry', health_s, 'folder_path')
        _load_entry('health_output_folder_entry', health_s, 'output_path')
        _load_textbox('health_text_input_box', health_s, 'text_input')
        _load_entry('health_num_groups_entry', health_s, 'num_groups', '1')
        _load_entry('health_phone_serial_entry', health_s, 'phone_serial')
        # --- 触发一次互斥状态更新 ---
        if hasattr(self, 'video_phone_serial_entry'): self._update_exclusive_entry_state(self.video_phone_serial_entry,
                                                                                         self.video_num_groups_entry)
        if hasattr(self, 'image_phone_serial_entry'): self._update_exclusive_entry_state(self.image_phone_serial_entry,
                                                                                         self.image_num_groups_entry)
        if hasattr(self, 'ab_phone_serial_entry'): self._update_exclusive_entry_state(self.ab_phone_serial_entry,
                                                                                      self.ab_num_groups_entry)
    def _update_color_widget(self, attr_name, color_value): setattr(self, attr_name + "_value", color_value); button = getattr(self, attr_name + "_button"); button.configure(text=str(color_value), fg_color="gray" if "rgba" in str(color_value) else color_value)

# ==============================================================================
# 应用程序启动入口
# ==============================================================================
# ==============================================================================
# 应用程序启动入口 (优化版)
# ==============================================================================
if __name__ == "__main__":
    # 1. 创建App实例，__init__会立刻执行完毕，速度很快
    app = App()
    app.withdraw()  # 先将空的主窗口隐藏起来

    # 2. 立刻创建并显示“启动中”窗口
    splash = ctk.CTkToplevel(app)
    splash.title("启动中...")
    splash_width, splash_height = 350, 150
    screen_width, screen_height = app.winfo_screenwidth(), app.winfo_screenheight()
    x = int((screen_width / 2) - (splash_width / 2))
    y = int((screen_height / 2) - (splash_height / 2))
    splash.geometry(f"{splash_width}x{splash_height}+{x}+{y}")
    splash.overrideredirect(True)  # 隐藏标题栏和边框
    ctk.CTkLabel(splash, text=" 程序正在启动，请稍候...", font=ctk.CTkFont(size=18)).pack(expand=True)
    splash.lift()  # 确保启动窗口在最顶层
    splash.update()  # 强制Tkinter立即绘制启动窗口


    def initialize_main_app():
        """在后台完成耗时的UI加载和设置"""
        app.setup_main_ui()  # 调用我们新的函数来创建所有UI组件
        splash.destroy()  # UI创建完成后，销毁启动窗口
        app.deiconify()  # 显示已经准备好的主窗口

        # 在主窗口显示后，再安全地启动硬件检测线程
        threading.Thread(target=app._detect_and_display_hardware, daemon=True).start()


    # 安排一个短暂的延迟后开始执行重量级初始化，确保启动窗口有时间被用户看到
    app.after(100, initialize_main_app)

    # 启动主事件循环
    app.mainloop()