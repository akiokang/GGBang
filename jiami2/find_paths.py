import sys
import os
import glob

print(f"Python 安装根目录 (sys.prefix): {sys.prefix}\n")

# Tcl/Tk 库通常位于 Python 安装目录下的 'tcl' 文件夹中
tcl_root = os.path.join(sys.prefix, 'tcl')
print(f"正在搜索 Tcl/Tk 根目录: {tcl_root}\n")

if not os.path.isdir(tcl_root):
    print("错误: 未找到 Tcl/Tk 根目录。您的 Python/Tkinter 安装可能不完整。")
else:
    # 使用通配符查找 tcl 和 tk 文件夹
    tcl_folders = glob.glob(os.path.join(tcl_root, 'tcl*'))
    tk_folders = glob.glob(os.path.join(tcl_root, 'tk*'))

    tcl_path = None
    tk_path = None

    if tcl_folders:
        tcl_path = tcl_folders[0]
        print(f"找到 TCL_LIBRARY 路径: {tcl_path}")
    else:
        print("错误: 在 Tcl/Tk 根目录中未找到 tcl 文件夹 (例如 tcl8.6)。")

    if tk_folders:
        tk_path = tk_folders[0]
        print(f"找到 TK_LIBRARY 路径: {tk_path}")
    else:
        print("错误: 在 Tcl/Tk 根目录中未找到 tk 文件夹 (例如 tk8.6)。")

    if not tcl_path or not tk_path:
        print("\n警告: 自动查找失败。请您手动进入上面的 'Tcl/Tk 根目录'，找到名字类似于 'tcl8.6' 和 'tk8.6' 的文件夹，并使用它们的完整路径。")