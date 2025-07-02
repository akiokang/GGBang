import os
import sys
import uuid
import base64
import hashlib
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, font
import threading
import queue
import subprocess

# 检查必需的库是否存在
try:
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.fernet import Fernet
except ImportError:
    messagebox.showerror("缺少库", "需要 'cryptography' 库。\n请在命令行中运行: pip install cryptography")
    sys.exit()

# --- 全局配置 ---
INTERNAL_PASSWORD = b'a-very-strong-and-secret-internal-password'
CONFIG_FILE = 'products_config.json'  # 新增: 本地产品配置文件
LICENSE_FILE_NAME = 'license.dat'


class DeveloperToolkitApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GGBang授权工具包 v6 (配置优化版)")
        self.root.geometry("750x700")

        # --- 实例变量 ---
        self.selected_exe_path = tk.StringVar(value="尚未选择")
        self.product_id_var = tk.StringVar()  # 用于绑定下拉框和输入框
        self.private_key_path = "private.key"
        self.public_key_path = "public.key"
        self.valid_days = tk.StringVar(value="0")
        self.products_config = {}  # 新增: 用于存储产品信息的字典

        # 打包专用变量
        self.pack_output_dir = tk.StringVar(value="")
        self.pack_icon_path = tk.StringVar(value="")
        self.pack_is_running = False
        self.log_queue = queue.Queue()

        # --- 样式和布局 ---
        # ... (样式代码无变化) ...
        style = ttk.Style(self.root)
        style.configure('TNotebook.Tab', font=('Helvetica', 10, 'bold'))
        style.configure('Accent.TButton', font=('Helvetica', 10, 'bold'))

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(expand=True, fill='both')

        notebook = ttk.Notebook(main_frame)
        notebook.pack(expand=True, fill='both', pady=5)

        tab1 = ttk.Frame(notebook)
        tab2 = ttk.Frame(notebook)
        tab3 = ttk.Frame(notebook)
        tab4 = ttk.Frame(notebook)

        notebook.add(tab1, text="  1. 项目设置  ")
        notebook.add(tab2, text="  2. 生成注册码  ")
        notebook.add(tab3, text="  3. 最终打包  ")
        notebook.add(tab4, text="  4. 本地测试  ")

        log_frame = ttk.Labelframe(main_frame, text="执行日志", padding=5)
        log_frame.pack(expand=True, fill='both', pady=(10, 0))
        self.log_widget = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', wrap='word',
                                                    font=('Courier', 9))
        self.log_widget.pack(expand=True, fill='both')

        # --- 初始化 ---
        self.load_products_config()  # 启动时加载配置
        self.create_setup_tab(tab1)
        self.create_keygen_tab(tab2)
        self.create_packaging_tab(tab3)
        self.create_testing_tab(tab4)
        self.update_all_comboboxes()  # 初始化所有下拉框
        self.process_log_queue()

    def open_output_directory(self):
        """打开在输出路径框中指定的文件夹"""
        path = self.pack_output_dir.get()

        if not path:
            self.log("错误: 输出路径为空，无法打开。", "error")
            messagebox.showerror("路径为空", "请先选择一个输出路径。")
            return

        if not os.path.isdir(path):
            self.log(f"错误: 路径 '{path}' 不是一个有效的目录。", "error")
            messagebox.showerror("路径无效", f"指定的路径不是一个有效的文件夹:\n{path}")
            return

        self.log(f"正在打开文件夹: {path}", "info")
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', path])
            else:  # Linux
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self.log(f"错误: 无法打开文件夹 - {e}", "error")
            messagebox.showerror("打开失败", f"无法打开文件夹，请检查您的系统设置。\n错误: {e}")
    # --- 新增: 配置加载和保存功能 ---
    def load_products_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.products_config = json.load(f)
                self.log(f"成功加载产品配置文件: {CONFIG_FILE}", "success")
            else:
                self.log("未找到产品配置文件，将自动创建。", "warning")
        except Exception as e:
            self.log(f"加载配置文件失败: {e}", "error")
            messagebox.showerror("错误", f"加载配置文件 '{CONFIG_FILE}' 失败: {e}")

    def save_products_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.products_config, f, indent=4)
            self.log(f"产品配置已保存到: {CONFIG_FILE}", "success")
        except Exception as e:
            self.log(f"保存配置文件失败: {e}", "error")
            messagebox.showerror("错误", f"保存配置文件 '{CONFIG_FILE}' 失败: {e}")

    # --- 新增: 更新所有下拉框内容 ---
    def update_all_comboboxes(self):
        product_ids = list(self.products_config.keys())
        if hasattr(self, 'keygen_pid_combo'):
            self.keygen_pid_combo['values'] = product_ids
        if hasattr(self, 'pack_pid_combo'):
            self.pack_pid_combo['values'] = product_ids
        if hasattr(self, 'test_pid_combo'):
            self.test_pid_combo['values'] = product_ids

        if product_ids:
            # 如果当前变量值不在列表里，则默认选第一个
            if self.product_id_var.get() not in product_ids:
                self.product_id_var.set(product_ids[0])
        self.log("所有产品下拉框已更新。", "info")

    def log(self, message, level="info"):
        self.log_queue.put((message, level))

    def process_log_queue(self):
        # ... (此函数无变化) ...
        try:
            while True:
                message, level = self.log_queue.get_nowait()
                if message == "TASK_DONE" and level == "special":
                    self.check_packaging_status()
                    continue
                self.log_widget.config(state='normal')
                tag = level.lower()
                self.log_widget.tag_configure("info", foreground="black")
                self.log_widget.tag_configure("success", foreground="green", font=font.Font(weight='bold'))
                self.log_widget.tag_configure("error", foreground="red", font=font.Font(weight='bold'))
                self.log_widget.tag_configure("warning", foreground="#E69138")
                self.log_widget.tag_configure("process", foreground="#4a86e8", font=font.Font(weight='bold'))
                self.log_widget.insert('end', message + '\n', tag)
                self.log_widget.config(state='disabled')
                self.log_widget.see('end')
        except queue.Empty:
            pass
        self.root.after(100, self.process_log_queue)

    def create_setup_tab(self, parent):
        frame = ttk.Frame(parent, padding=20)
        frame.pack(expand=True, fill='both')

        lf1 = ttk.Labelframe(frame, text="步骤 1: 生成密钥对 (所有产品共用)", padding=15)
        lf1.pack(fill='x', pady=10)
        ttk.Button(lf1, text="生成 private.key 和 public.key", command=self.run_key_generation).pack()

        lf2 = ttk.Labelframe(frame, text="步骤 2: 添加/更新产品并加密", padding=15)
        lf2.pack(fill='x', pady=10)

        pid_frame = ttk.Frame(lf2)
        pid_frame.pack(fill='x', pady=5)
        ttk.Label(pid_frame, text="产品ID (英文/数字):", width=20).pack(side='left')
        # 这里依然使用输入框，因为是定义产品的地方
        ttk.Entry(pid_frame, textvariable=self.product_id_var).pack(side='left', fill='x', expand=True)

        select_frame = ttk.Frame(lf2)
        select_frame.pack(fill='x', pady=(5, 0))
        ttk.Button(select_frame, text="选择此产品的 .EXE 主程序", command=self.select_exe_file).pack(side='left',
                                                                                                     padx=(0, 10))
        ttk.Label(select_frame, textvariable=self.selected_exe_path, foreground="blue").pack(side='left')

        ttk.Button(lf2, text="加密EXE并保存产品配置", command=self.run_encryption_and_save_config,
                   style='Accent.TButton').pack(pady=10)

    def run_key_generation(self):
        # ... (此函数无变化) ...
        self.log("开始生成2048位RSA密钥对...")
        if os.path.exists(self.private_key_path) or os.path.exists(self.public_key_path):
            if not messagebox.askyesno("确认", "密钥文件已存在，要覆盖它们吗？"):
                self.log("操作取消。", "warning");
                return
        try:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with open(self.private_key_path, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            public_key = private_key.public_key()
            with open(self.public_key_path, "wb") as f:
                f.write(public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ))
            self.log(f"成功: '{self.private_key_path}' 和 '{self.public_key_path}' 已生成。", "success")
            messagebox.showinfo("成功", f"密钥对已生成！\n请务必妥善保管 {self.private_key_path}，不要泄露。")
        except Exception as e:
            self.log(f"错误: 生成密钥失败 - {e}", "error")
            messagebox.showerror("错误", f"生成密钥失败: {e}")

    def select_exe_file(self):
        # ... (此函数无变化) ...
        path = filedialog.askopenfilename(title="请选择一个EXE文件",
                                          filetypes=(("Executable files", "*.exe"), ("All files", "*.*")))
        if path:
            self.selected_exe_path.set(path)
            self.log(f"已选择主程序: {path}")

    def run_encryption_and_save_config(self):
        exe_path = self.selected_exe_path.get()
        pid = self.product_id_var.get().strip()
        if not pid:
            messagebox.showerror("错误", "产品ID不能为空！");
            return
        if exe_path == "尚未选择":
            messagebox.showerror("错误", "请先选择一个要加密的EXE文件！");
            return

        encrypted_data_path = f"{pid}_encrypted.dat"
        self.log(f"开始为产品 '{pid}' 加密 '{os.path.basename(exe_path)}'...")
        try:
            # ... (加密逻辑不变) ...
            key = hashlib.sha256(INTERNAL_PASSWORD).digest()
            fernet_key = base64.urlsafe_b64encode(key)
            f = Fernet(fernet_key)
            with open(exe_path, 'rb') as original_file:
                original_data = original_file.read()
            encrypted_bundle = f.encrypt(original_data)
            with open(encrypted_data_path, 'wb') as encrypted_file:
                encrypted_file.write(encrypted_bundle)
            self.log(f"成功: 加密数据文件 '{encrypted_data_path}' 已生成。", "success")

            # --- 新增: 保存配置 ---
            self.products_config[pid] = {'exe_path': exe_path}
            self.save_products_config()
            self.update_all_comboboxes()  # 实时更新下拉框
            messagebox.showinfo("成功", f"产品 '{pid}' 已加密并保存配置！")

        except Exception as e:
            self.log(f"错误: 加密文件失败 - {e}", "error")
            messagebox.showerror("错误", f"加密文件失败: {e}")

    def create_keygen_tab(self, parent):
        frame = ttk.Frame(parent, padding=20)
        frame.pack(expand=True, fill='both')
        lf = ttk.Labelframe(frame, text="为客户生成一个新注册码", padding=15)
        lf.pack(fill='both', expand=True)

        pid_frame = ttk.Frame(lf)
        pid_frame.pack(fill='x', pady=5)
        ttk.Label(pid_frame, text="选择产品:", width=15).pack(side='left')
        # --- 修改: 使用下拉框 ---
        self.keygen_pid_combo = ttk.Combobox(pid_frame, textvariable=self.product_id_var, state='readonly')
        self.keygen_pid_combo.pack(side='left', fill='x', expand=True)

        days_frame = ttk.Frame(lf)
        days_frame.pack(fill='x', pady=5)
        ttk.Label(days_frame, text="使用天数 (0=永久):", width=15).pack(side='left')
        ttk.Entry(days_frame, textvariable=self.valid_days, width=10).pack(side='left')
        ttk.Button(lf, text="生成新码", command=self.run_code_generation, style='Accent.TButton').pack(pady=20)
        self.reg_code_text = scrolledtext.ScrolledText(lf, height=5, state='disabled', wrap='word', font=('Courier', 9))
        self.reg_code_text.pack(fill='both', expand=True, pady=5)

    def run_code_generation(self):
        pid = self.product_id_var.get().strip()
        if not pid:
            messagebox.showerror("错误", "请从下拉框中选择一个产品！");
            return
        # ... (后续逻辑无变化) ...
        self.log(f"正在为产品 '{pid}' 生成新的签名注册码...")
        if not os.path.exists(self.private_key_path):
            self.log("错误: 找不到私钥文件 'private.key'。", "error")
            messagebox.showerror("错误", "找不到 private.key！\n请先在“项目设置”中生成。")
            return
        try:
            days = int(self.valid_days.get())
        except ValueError:
            messagebox.showerror("输入错误", "使用天数必须是一个整数！");
            return

        try:
            with open(self.private_key_path, "rb") as key_file:
                private_key = serialization.load_pem_private_key(key_file.read(), password=None)

            payload_data = {'uid': str(uuid.uuid4()), 'days': days, 'product_id': pid}
            payload_json = json.dumps(payload_data)
            payload_bytes = payload_json.encode('utf-8')

            signature = private_key.sign(
                payload_bytes,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            registration_code = base64.urlsafe_b64encode(payload_bytes + b'###SIGNATURE###' + signature).decode('utf-8')

            self.reg_code_text.config(state='normal')
            self.reg_code_text.delete('1.0', 'end')
            self.reg_code_text.insert('1.0', registration_code)
            self.reg_code_text.config(state='disabled')
            self.log(f"成功: 已为产品 '{pid}' 生成一个有效期为 {days} 天的注册码。", "success")
        except Exception as e:
            self.log(f"错误: 生成注册码失败 - {e}", "error")
            messagebox.showerror("错误", f"生成注册码失败: {e}")

    def create_packaging_tab(self, parent):
        frame = ttk.Frame(parent, padding=20)
        frame.pack(expand=True, fill='both')
        lf = ttk.Labelframe(frame, text="一键打包应用程序", padding=15)
        lf.pack(fill='both', expand=True)

        name_frame = ttk.Frame(lf)
        name_frame.pack(fill='x', pady=5)
        ttk.Label(name_frame, text="选择产品打包:", width=15).pack(side='left')
        # --- 修改: 使用下拉框 ---
        self.pack_pid_combo = ttk.Combobox(name_frame, textvariable=self.product_id_var, state='readonly')
        self.pack_pid_combo.pack(side='left', expand=True, fill='x')

        # ... (后续UI和逻辑无变化) ...
        out_frame = ttk.Frame(lf)
        out_frame.pack(fill='x', pady=5)
        ttk.Label(out_frame, text="输出路径:", width=15).pack(side='left')
        ttk.Entry(out_frame, textvariable=self.pack_output_dir, state='readonly').pack(side='left', expand=True,
                                                                                       fill='x', padx=(0, 5))
        ttk.Button(out_frame, text="选择...", command=self.select_output_path).pack(side='left')
        ttk.Button(out_frame, text="打开", command=self.open_output_directory).pack(side='left')

        icon_frame = ttk.Frame(lf)
        icon_frame.pack(fill='x', pady=5)
        ttk.Label(icon_frame, text="图标 (.ico):", width=15).pack(side='left')
        ttk.Entry(icon_frame, textvariable=self.pack_icon_path, state='readonly').pack(side='left', expand=True,
                                                                                       fill='x', padx=(0, 5))
        ttk.Button(icon_frame, text="选择...", command=self.select_icon_file).pack(side='left')

        self.pack_progress = ttk.Progressbar(lf, mode='indeterminate')
        self.pack_progress.pack(fill='x', pady=10)
        self.pack_button = ttk.Button(lf, text="开始打包", command=self.start_packaging_thread, style='Accent.TButton')
        self.pack_button.pack(pady=10, ipady=5)

    def select_output_path(self):
        path = filedialog.askdirectory(title="请选择一个文件夹来存放打包好的程序")
        if path:
            self.pack_output_dir.set(path)

    def select_icon_file(self):
        path = filedialog.askopenfilename(title="请选择一个图标文件",
                                          filetypes=(("Icon files", "*.ico"), ("All files", "*.*")))
        if path:
            self.pack_icon_path.set(path)
    def start_packaging_thread(self):
        if self.pack_is_running:
            self.log("错误: 已有一个打包任务正在运行。", "error");
            return

        app_name = self.product_id_var.get().strip()  # 修改: 从共享变量获取
        if not app_name:
            messagebox.showerror("错误", "请从下拉框中选择一个产品进行打包！");
            return

        # ... (后续逻辑无变化) ...
        output_dir = self.pack_output_dir.get()
        icon_path = self.pack_icon_path.get()
        loader_script = "smart_loader_v3.py"

        encrypted_data_path = f"{app_name}_encrypted.dat"

        if not all(os.path.exists(p) for p in [loader_script, self.public_key_path, encrypted_data_path]):
            messagebox.showerror("文件缺失",
                                 f"请确保以下文件存在于本目录下:\n- {loader_script} (模板)\n- {self.public_key_path}\n- {encrypted_data_path} (产品的加密文件)")
            return
        if icon_path and not os.path.exists(icon_path):
            messagebox.showerror("文件缺失", f"找不到指定的图标文件: {icon_path}");
            return

        self.pack_is_running = True
        self.pack_button.config(state='disabled', text="打包中...")
        self.pack_progress.start()
        thread = threading.Thread(target=self.run_pyinstaller,
                                  args=(app_name, output_dir, icon_path, loader_script, encrypted_data_path))
        thread.daemon = True
        thread.start()

    def run_pyinstaller(self, app_name, output_dir, icon_path, loader_template, encrypted_data_path):
        temp_loader_path = f"temp_loader_{app_name}.py"
        try:
            self.log("-" * 60, "process")
            self.log(f"开始为产品 '{app_name}' 打包...", "process")

            # --- 新增: 动态创建特定产品的加载器 ---
            with open(loader_template, 'r', encoding='utf-8') as f:
                loader_content = f.read()

            # 用真实的产品ID替换模板中的占位符
            loader_content = loader_content.replace('%%PRODUCT_ID%%', app_name)

            with open(temp_loader_path, 'w', encoding='utf-8') as f:
                f.write(loader_content)
            self.log(f"已创建临时加载器: {temp_loader_path}", "info")
            # --- 动态创建结束 ---
            tcl_path = r"C:\Users\MSN\AppData\Local\Programs\Python\Python39\tcl\tcl8"  # 替换成你的真实路径
            tk_path = r"C:\Users\MSN\AppData\Local\Programs\Python\Python39\tcl\tk8.6"  # 替换成你的真实路径
            command = [
                'pyinstaller', '--noconfirm', '--onefile', '--windowed',
                '--name', app_name,
                '--distpath', output_dir,
                '--add-data', f'{encrypted_data_path}{os.pathsep}.',
                '--add-data', f'{self.public_key_path}{os.pathsep}.',

            ]
            if icon_path:
                command.extend(['--icon', icon_path])

            command.append(temp_loader_path)  # 修改: 打包的是临时生成的加载器

            self.log("执行命令: " + " ".join(f'"{c}"' if " " in c else c for c in command), "info")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                       encoding='utf-8', errors='ignore',
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            for line in iter(process.stdout.readline, ''):
                self.log(line.strip(), "info")
            process.stdout.close()
            return_code = process.wait()

            if return_code == 0:
                self.log(f"成功: 打包完成！程序 '{app_name}.exe' 已输出到 '{output_dir}'", "success")
                messagebox.showinfo("打包成功", f"程序 '{app_name}.exe' 已成功生成在以下目录:\n{output_dir}")
            else:
                self.log(f"错误: PyInstaller 执行失败，返回码: {return_code}", "error")
                messagebox.showerror("打包失败", "PyInstaller 执行失败，请检查日志。")

        except Exception as e:
            self.log(f"严重错误: 打包线程异常 - {e}", "error")
        finally:
            if os.path.exists(temp_loader_path):
                os.remove(temp_loader_path)  # 清理临时文件
            self.log_queue.put(("TASK_DONE", "special"))

    def check_packaging_status(self):
        # ... (此函数无变化) ...
        self.pack_is_running = False
        self.pack_button.config(state='normal', text="开始打包")
        self.pack_progress.stop()

    def create_testing_tab(self, parent):
        frame = ttk.Frame(parent, padding=20)
        frame.pack(expand=True, fill='both')
        lf = ttk.Labelframe(frame, text="调试与测试工具", padding=15)
        lf.pack(fill='x', pady=10)

        pid_frame = ttk.Frame(lf)
        pid_frame.pack(fill='x', pady=5)
        ttk.Label(pid_frame, text="选择要清除授权的产品:", width=20).pack(side='left')
        # --- 修改: 使用下拉框 ---
        self.test_pid_combo = ttk.Combobox(pid_frame, textvariable=self.product_id_var, state='readonly')
        self.test_pid_combo.pack(side='left', fill='x', expand=True)

        ttk.Label(lf, text="如果您在本地测试时无法再次激活，请使用此功能清除本机的授权信息。",
                  justify='left').pack(anchor='w', pady=(5, 10))
        ttk.Button(lf, text="清除本机授权 (模拟新用户)", command=self.clear_local_license,
                   style='Accent.TButton').pack()

    def get_app_data_path(self, app_name):  # 修改: 接收app_name作为参数
        if sys.platform == 'win32':
            app_data_dir = os.path.join(os.getenv('APPDATA'), app_name)
        elif sys.platform == 'darwin':
            app_data_dir = os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
        else:
            app_data_dir = os.path.join(os.path.expanduser('~/.config'), app_name)
        return os.path.join(app_data_dir, LICENSE_FILE_NAME)

    def clear_local_license(self):
        pid = self.product_id_var.get().strip()  # 修改: 从共享变量获取
        if not pid:
            messagebox.showerror("错误", "请从下拉框中选择一个产品！");
            return

        # ... (后续逻辑无变化) ...
        self.log(f"开始为产品 '{pid}' 清除本地授权信息...")
        license_path = self.get_app_data_path(pid)

        if os.path.exists(license_path):
            if not messagebox.askyesno("确认清除", f"确定要删除产品 '{pid}' 的授权文件吗？\n\n{license_path}"):
                self.log("操作取消。", "warning");
                return
            try:
                os.remove(license_path)
                self.log(f"成功: 已删除授权文件 '{license_path}'。", "success")
                messagebox.showinfo("成功", "本地授权信息已清除！")
            except Exception as e:
                self.log(f"错误: 删除文件失败 - {e}", "error")
                messagebox.showerror("删除失败", f"无法删除授权文件，请检查权限。\n错误: {e}")
        else:
            self.log("信息: 未找到本地授权文件，无需清除。", "info")
            messagebox.showinfo("未找到", f"产品 '{pid}' 在本机尚未激活，无需清除。")


# --- main ---
if __name__ == "__main__":
    try:
        from ttkthemes import ThemedTk

        root = ThemedTk(theme="arc")
    except ImportError:
        root = tk.Tk()

    app = DeveloperToolkitApp(root)
    root.mainloop()