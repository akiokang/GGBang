import os
import sys
import shutil
import subprocess


def find_executable(name):
    """
    一个简化的、用于定位可执行文件的函数。
    它会先检查当前目录下的 'ffmpeg' 子文件夹，然后检查系统的PATH。
    """
    executable_name = f"{name}.exe" if sys.platform.startswith("win") else name

    # 检查脚本所在目录下的 'ffmpeg' 子文件夹
    # 这模拟了 GGBang.py 的行为
    current_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(current_dir, "ffmpeg", executable_name)
    if os.path.isfile(local_path):
        print(f"[诊断信息] 在本地 'ffmpeg' 文件夹中找到: {local_path}")
        return local_path

    # 如果本地找不到，则检查整个系统的环境变量 PATH
    system_path = shutil.which(executable_name)
    if system_path:
        print(f"[诊断信息] 在系统 PATH 中找到: {system_path}")
        return system_path

    return None


def run_diagnostic():
    """
    执行诊断流程
    """
    print("--- FFmpeg 最终诊断脚本 ---")

    # --- 步骤 1: 找出Python脚本实际将要使用的ffmpeg.exe ---
    print("\n[步骤 1] 正在查找Python脚本会使用的 ffmpeg.exe...")
    ffmpeg_path = find_executable("ffmpeg")

    if not ffmpeg_path:
        print("\n[致命错误] 查找失败！")
        print("请确认您的 'ffmpeg' 文件夹和里面的 ffmpeg.exe 是否与 check_ffmpeg.py 在同一级目录下。")
        return

    print(f"\n[诊断结果] Python脚本实际调用的FFmpeg路径是: \n{ffmpeg_path}")

    # --- 步骤 2: 检查这个找到的ffmpeg.exe的版本 ---
    print("\n[步骤 2] 正在检查这个FFmpeg的版本信息...")
    try:
        version_result = subprocess.run([ffmpeg_path, "-version"], capture_output=True, text=True, check=True,
                                        encoding='utf-8', errors='ignore')
        version_first_line = version_result.stdout.strip().splitlines()[0]
        print(f"\n[诊断结果] 该程序的版本是: \n{version_first_line}")

        if "gyan.dev" not in version_first_line and "7." not in version_first_line:
            print("\n[重要警告] 这个版本看起来不是您新下载的7.1.1版本！这很可能就是问题所在！")

    except Exception as e:
        print(f"\n[致命错误] 无法获取该FFmpeg的版本信息。错误: {e}")
        return

    # --- 步骤 3: 使用这个找到的ffmpeg.exe执行您验证过成功的命令 ---
    print("\n[步骤 3] 准备使用此FFmpeg进行视频转换...")
    input_video = input("\n> 请将您有问题的.mov视频文件的完整路径粘贴到这里，然后按回车:\n")

    if not os.path.exists(input_video.strip().strip('"')):
        print(f"\n[致命错误] 文件不存在: {input_video}")
        return

    output_video = "python_test_output.mp4"
    print(f"\n[操作] 正在尝试将视频转换为 '{output_video}'...")

    command = [
        ffmpeg_path,
        "-y",
        "-i", input_video,
        "-metadata:s:v:0", "rotate=0",
        "-c:v", "libx264",
        "-preset", "medium",
        "-c:a", "copy",
        output_video
    ]

    print(f"\n[执行命令] {' '.join(command)}\n")

    try:
        # 执行命令并捕获所有输出
        process_result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8',
                                        errors='ignore')
        print("--- [成功] 命令已通过Python脚本执行完毕！---")

        # 打印ffmpeg在运行时可能输出的详细信息
        if process_result.stderr:
            print("\n--- 来自FFmpeg的详细处理日志 ---\n")
            print(process_result.stderr)

        print(f"\n[最终检查] 请在文件夹中找到新生成的 '{output_video}' 文件，检查它是否完全正确。")

    except subprocess.CalledProcessError as e:
        print("\n--- [致命错误] 命令在Python脚本中执行失败！---")
        print("\n--- FFmpeg的错误输出 (请仔细阅读下面的错误信息) ---\n")
        print(e.stderr)

    except Exception as e:
        print(f"\n[致命错误] 发生了意料之外的Python错误: {e}")


if __name__ == "__main__":
    run_diagnostic()
    input("\n诊断结束。按回车键退出。")