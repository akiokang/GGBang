import os
import sys
import subprocess
import uuid
import hashlib
import json
import base64
from tkinter import messagebox, simpledialog
from datetime import datetime, timedelta

try:
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.fernet import Fernet
except ImportError:
    # 在最终用户电脑上，这个错误不应该发生，因为库会被pyinstaller打包
    # 但如果发生，显示一个通用错误
    messagebox.showerror("初始化错误", "加载所需组件失败，请联系软件供应商。")
    sys.exit()

# --- 配置 (模板占位符) ---
# 修改: 下面的 '%%PRODUCT_ID%%' 将在打包时被开发者工具包动态替换为真实的产品ID
PRODUCT_ID = "%%PRODUCT_ID%%"
APP_NAME = PRODUCT_ID  # 应用数据文件夹的名称直接使用产品ID，保证唯一性
LICENSE_FILE_NAME = 'license.dat'
ENCRYPTED_DATA_FILE = f'{PRODUCT_ID}_encrypted.dat'  # 文件名也由产品ID决定
PUBLIC_KEY_FILE = 'public.key'


def get_app_data_path():
    """获取跨平台的用户应用数据目录，并确保我们的应用子目录存在。"""
    if sys.platform == 'win32':
        # 使用 APP_NAME 变量
        app_data_dir = os.path.join(os.getenv('APPDATA'), APP_NAME)
    elif sys.platform == 'darwin':
        app_data_dir = os.path.join(os.path.expanduser('~/Library/Application Support'), APP_NAME)
    else:  # Linux
        app_data_dir = os.path.join(os.path.expanduser('~/.config'), APP_NAME)

    # 检查占位符是否已被替换，如果未被替换则报错退出
    if "%%" in app_data_dir:
        messagebox.showerror("配置错误", "软件打包不完整，无法确定存储路径。")
        sys.exit()

    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, LICENSE_FILE_NAME)


def get_hardware_info(command):
    # ... (此函数无变化) ...
    try:
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore',
                                startupinfo=startupinfo)
        lines = result.stdout.strip().splitlines()
        return "".join(line.strip() for line in lines if
                       line.strip() and line.strip() != 'SerialNumber' and line.strip() != 'ProcessorId')
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def get_machine_id():
    # ... (此函数无变化) ...
    id_parts = []
    if sys.platform == 'win32':
        id_parts.append(get_hardware_info(['wmic', 'baseboard', 'get', 'SerialNumber']))
        id_parts.append(get_hardware_info(['wmic', 'cpu', 'get', 'ProcessorId']))
        id_parts.append(get_hardware_info(['getmac']))
    else:
        try:
            id_parts.append(get_hardware_info(['cat', '/sys/class/dmi/id/board_serial']))
            id_parts.append(get_hardware_info(['cat', '/sys/class/dmi/id/product_uuid']))
            for interface in os.listdir('/sys/class/net/'):
                if interface != 'lo':
                    with open(f'/sys/class/net/{interface}/address') as f:
                        id_parts.append(f.read().strip());
                        break
        except Exception:
            pass
    combined_id = "".join(filter(None, id_parts))
    if not combined_id:
        mac = ':'.join(('%012X' % uuid.getnode())[i:i + 2] for i in range(0, 12, 2))
        combined_id = mac
    return hashlib.sha256(combined_id.encode()).hexdigest()


def verify_registration_code(reg_code, public_key):
    # ... (此函数无变化) ...
    try:
        decoded_code = base64.urlsafe_b64decode(reg_code.encode('utf-8'))
        payload_bytes, signature = decoded_code.rsplit(b'###SIGNATURE###', 1)
        public_key.verify(
            signature, payload_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return None


def run_decrypted_app(decrypted_data):
    # ... (此函数无变化) ...
    temp_file_path = None
    try:
        temp_dir = os.environ.get('TEMP', os.getcwd())
        temp_file_path = os.path.join(temp_dir, f"tmp_{uuid.uuid4().hex}.exe")
        with open(temp_file_path, 'wb') as f:
            f.write(decrypted_data)
        subprocess.run([temp_file_path], check=True)
    except Exception as e:
        messagebox.showerror("运行错误", f"无法启动应用程序: {e}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


def main():
    license_storage_path = get_app_data_path()

    if getattr(sys, 'frozen', False):
        resource_path = sys._MEIPASS
    else:
        resource_path = os.path.dirname(os.path.abspath(__file__))

    public_key_path = os.path.join(resource_path, PUBLIC_KEY_FILE)
    encrypted_data_path = os.path.join(resource_path, ENCRYPTED_DATA_FILE)

    try:
        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())
        with open(encrypted_data_path, 'rb') as f:
            encrypted_bundle = f.read()
    except Exception as e:
        messagebox.showerror("错误", f"程序内部文件损坏或丢失: {e}\n({encrypted_data_path})");
        return

    internal_password = b'a-very-strong-and-secret-internal-password'
    key = hashlib.sha256(internal_password).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    f = Fernet(fernet_key)

    is_activated = False  # 设置一个标志位，用于判断授权是否有效

    # 1. 优先检查现有授权文件
    if os.path.exists(license_storage_path):
        try:
            with open(license_storage_path, 'r') as file:
                license_data = json.load(file)

            # 检查硬件ID是否匹配
            if get_machine_id() != license_data.get('machine_id'):
                messagebox.showerror("授权失败", "硬件环境不匹配，此授权已绑定到其他电脑。")
                return  # 硬件不匹配是硬性错误，直接退出

            # 检查到期日
            expiration_date_str = license_data.get('expiration_date')
            if expiration_date_str != "permanent":
                # 【修正】修正了原有多一天的BUG
                expiration_date = datetime.strptime(expiration_date_str, "%Y-%m-%d")
                if datetime.now() > expiration_date:
                    # --- 主要修改点 ---
                    # 授权已过期，不再直接return退出
                    # 而是弹窗提示后，让程序继续往下走到激活流程
                    messagebox.showinfo("授权已过期",
                                        f"您的软件授权已于 {expiration_date_str} 过期。\n请点击“确定”后输入新的注册码以重新激活。")
                else:
                    # 授权未过期，标记为已激活
                    is_activated = True
            else:
                # 永久授权，标记为已激活
                is_activated = True
        except Exception:
            # 授权文件损坏，同样让程序继续往下走到激活流程
            messagebox.showerror("错误", "许可证文件损坏或无效，请重新激活。")

    # 2. 如果未激活（包括首次运行、文件损坏、授权过期），则执行激活流程
    if not is_activated:
        reg_code = simpledialog.askstring("软件激活", "请输入您的注册码:")
        if not reg_code:
            return  # 如果用户在激活窗口点击取消，则退出程序

        payload = verify_registration_code(reg_code, public_key)

        # 验证注册码是否有效，且产品ID是否匹配
        if payload and payload.get('product_id') == PRODUCT_ID:
            days_to_expire = payload.get('days', 0)
            if days_to_expire > 0:
                expiration_date = datetime.now() + timedelta(days=days_to_expire)
                expiration_date_str = expiration_date.strftime("%Y-%m-%d")
            else:
                expiration_date_str = "permanent"
            new_license_data = {
                'reg_code': reg_code,
                'machine_id': get_machine_id(),
                'activation_date': datetime.now().strftime("%Y-%m-%d"),
                'expiration_date': expiration_date_str
            }

            # --- 关键：使用 'w' 模式写入文件，会直接覆盖旧的 license.dat 文件 ---
            with open(license_storage_path, 'w') as file:
                json.dump(new_license_data, file)

            messagebox.showinfo("成功", "软件激活成功！")
            is_activated = True  # 激活成功，更新标志位
        else:
            messagebox.showerror("激活失败", "无效的注册码或注册码不适用于本软件。")
            # 激活失败，is_activated 仍为 False，程序将不会运行

    # 3. 最后，只有在授权状态有效时，才运行主程序
    if is_activated:
        try:
            decrypted_data = f.decrypt(encrypted_bundle)
            run_decrypted_app(decrypted_data)
        except Exception as e:
            messagebox.showerror("运行错误", f"解密或启动应用程序失败: {e}")


if __name__ == '__main__':
    main()