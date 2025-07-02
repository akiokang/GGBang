@echo off

:: 将当前命令提示符的字符编码切换到UTF-8 (代码页65001)，以正确处理中文路径和字符
:: > nul 是为了不显示“Active code page: 65001”这句提示，让界面更干净
chcp 65001 > nul

:: 现在可以安全地运行Python脚本了
echo 正在启动应用程序，请稍候...
python developer_toolkit_final_ui.py

:: 脚本执行完毕后暂停，等待用户按键，以便查看日志
echo.
echo 应用程序已关闭。
pause