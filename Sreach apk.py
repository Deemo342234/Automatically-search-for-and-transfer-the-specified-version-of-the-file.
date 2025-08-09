import os
import shutil
import re
import time
import tkinter as tk
from tkinter import filedialog, Listbox, Scrollbar, Button, Label, Entry, messagebox, Checkbutton, IntVar
import threading
from datetime import datetime
import schedule


class QCFileUpdater:
    def __init__(self, root):
        self.root = root
        self.root.title("QC APK文件版本管理工具（按数字大小排序）")
        self.root.geometry("900x700")

        # 配置参数（强调版本号为数字递增）
        self.config = {
            "search_path": "",  # 根搜索目录
            "target_path": "",  # 目标保存路径
            "check_interval": 5,  # 检测间隔(分钟)
            # 版本号正则：匹配qc后跟随的数字版本（支持x.x.x或纯数字序列）
            "version_pattern": r"qc.*?(\d+(?:\.\d+)*)",  # 兼容纯数字（如123）或分段数字（如1.2.3）
            "last_max_version": None,  # 记录上次检测到的最大版本号
            "auto_copy": True  # 是否自动复制最新版本
        }

        # 状态变量
        self.running = False
        self.checking = False
        self.results = []

        # 创建UI
        self.create_widgets()

        # 启动定时任务线程
        self.schedule_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.schedule_thread.start()

    def create_widgets(self):
        # 路径配置区域
        path_frame = tk.LabelFrame(self.root, text="路径配置")
        path_frame.pack(pady=5, fill=tk.X, padx=10)

        # 搜索路径
        tk.Frame(path_frame).pack(fill=tk.X, pady=2)
        Label(path_frame, text="搜索根目录:").pack(side=tk.LEFT, padx=5)
        self.path_entry = Entry(path_frame)
        self.path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        browse_btn = Button(path_frame, text="浏览", command=self.browse_search_path)
        browse_btn.pack(side=tk.LEFT, padx=5)

        # 目标路径
        tk.Frame(path_frame).pack(fill=tk.X, pady=2)
        Label(path_frame, text="目标保存路径:").pack(side=tk.LEFT, padx=5)
        self.target_entry = Entry(path_frame)
        self.target_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        target_btn = Button(path_frame, text="选择目标", command=self.browse_target_path)
        target_btn.pack(side=tk.LEFT, padx=5)

        # 配置区域
        config_frame = tk.LabelFrame(self.root, text="版本检测配置")
        config_frame.pack(pady=5, fill=tk.X, padx=10)

        # 检测间隔
        tk.Frame(config_frame).pack(fill=tk.X, pady=2)
        Label(config_frame, text="检测间隔(分钟):").pack(side=tk.LEFT, padx=5)
        self.interval_entry = Entry(config_frame, width=10)
        self.interval_entry.insert(0, str(self.config["check_interval"]))
        self.interval_entry.pack(side=tk.LEFT, padx=5)

        # 版本号正则（强调数字特征）
        tk.Frame(config_frame).pack(fill=tk.X, pady=2)
        Label(config_frame, text="版本匹配正则:").pack(side=tk.LEFT, padx=5)
        self.pattern_entry = Entry(config_frame)
        self.pattern_entry.insert(0, self.config["version_pattern"])
        self.pattern_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        Label(config_frame, text="(匹配qc后的数字，如: qc(\\d+\\.\\d+)|qc(\\d+))").pack(side=tk.LEFT, padx=5)

        # 自动复制选项
        self.auto_copy_var = IntVar(value=1 if self.config["auto_copy"] else 0)
        auto_copy_check = Checkbutton(
            config_frame,
            text="自动复制最大版本到目标路径",
            variable=self.auto_copy_var
        )
        auto_copy_check.pack(side=tk.LEFT, padx=20)

        # 控制按钮
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)

        self.start_btn = Button(btn_frame, text="开始监控", command=self.start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=10)

        self.stop_btn = Button(btn_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        self.check_btn = Button(btn_frame, text="立即检测最大版本", command=self.check_updates)
        self.check_btn.pack(side=tk.LEFT, padx=10)

        # 结果列表（突出显示最大最大版本）
        result_frame = tk.LabelFrame(self.root, text="QC APK文件列表（最大版本已标红）")
        result_frame.pack(pady=5, fill=tk.BOTH, expand=True, padx=10)

        scrollbar = Scrollbar(result_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.result_list = Listbox(result_frame, yscrollcommand=scrollbar.set, selectmode=tk.SINGLE)
        self.result_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.result_list.yview)

        # 手动操作按钮
        action_frame = tk.Frame(self.root)
        action_frame.pack(pady=5)

        copy_btn = Button(action_frame, text="复制最大版本到目标", command=self.copy_latest)
        copy_btn.pack(side=tk.LEFT, padx=10)

        # 状态区域
        self.status_label = Label(self.root, text="就绪", fg="gray")
        self.status_label.pack(side=tk.BOTTOM, pady=5)

        # 日志区域
        log_frame = tk.LabelFrame(self.root, text="操作日志（记录版本比较结果）")
        log_frame.pack(pady=5, fill=tk.X, padx=10)

        self.log_text = tk.Text(log_frame, height=5, state=tk.DISABLED)
        self.log_text.pack(fill=tk.X, padx=5, pady=5)

    def log(self, message):
        """记录日志，包含时间戳"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        self.status_label.config(text=message)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        print(log_entry.strip())

    def browse_search_path(self):
        path = filedialog.askdirectory(title="选择根搜索目录（含子目录）")
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)
            self.config["search_path"] = path

    def browse_target_path(self):
        path = filedialog.askdirectory(title="选择目标保存目录")
        if path:
            self.target_entry.delete(0, tk.END)
            self.target_entry.insert(0, path)
            self.config["target_path"] = path

    def start_monitoring(self):
        """启动监控，初始化配置"""
        self.config["search_path"] = self.path_entry.get()
        self.config["target_path"] = self.target_entry.get()
        self.config["auto_copy"] = self.auto_copy_var.get() == 1

        if not self.config["search_path"]:
            messagebox.showwarning("警告", "请选择搜索根目录")
            return

        if not self.config["target_path"]:
            messagebox.showwarning("警告", "请选择目标保存路径")
            return

        try:
            self.config["check_interval"] = int(self.interval_entry.get())
            self.config["version_pattern"] = self.pattern_entry.get()
        except ValueError:
            messagebox.showwarning("警告", "检测间隔必须是数字")
            return

        self.running = True
        self.start_btn.config(state=tk.DISABLED)  # 修正了此处的笔误
        self.stop_btn.config(state=tk.NORMAL)
        self.log(f"开始监控QC APK文件（优先选择最大版本），间隔{self.config['check_interval']}分钟")
        threading.Thread(target=self.check_updates, daemon=True).start()

    def stop_monitoring(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("已停止监控QC APK文件")

    def run_scheduler(self):
        """定时时任务调度器"""
        while True:
            if self.running:
                schedule.every(self.config["check_interval"]).minutes.do(
                    lambda: threading.Thread(target=self.check_updates, daemon=True).start()
                )
            schedule.run_pending()
            time.sleep(10)

    def parse_version(self, filename):
        """解析版本号为可比较的数字元组（核心优化点）"""
        match = re.search(self.config["version_pattern"], filename, re.IGNORECASE)
        if match and match.group(1):
            version_str = match.group(1)
            # 将版本号拆分为数字列表（如"1.2.3"→(1,2,3)，"456"→(456,)）
            try:
                return tuple(map(int, version_str.split('.')))
            except ValueError:
                # 若包含非数字字符，视为无效版本
                return None
        return None

    def get_version_files(self):
        """搜索所有QC APK文件并按版本号排序（从大到小）"""
        if not self.config["search_path"] or not os.path.exists(self.config["search_path"]):
            return []

        files = []
        for root_dir, _, file_list in os.walk(self.config["search_path"]):
            for file in file_list:
                # 筛选包含QC的APK文件（已修改为只检测APK）
                if "qc" in file.lower() and file.lower().endswith(".apk"):
                    file_path = os.path.join(root_dir, file)
                    version = self.parse_version(file)
                    if version:  # 只保留能解析出有效数字版本的文件
                        files.append({
                            "path": file_path,
                            "name": file,
                            "version": version,  # 数字元组，用于比较
                            "version_str": ".".join(map(str, version)),  # 字符串形式，用于显示
                            "relative_path": os.path.relpath(root_dir, self.config["search_path"])
                        })

        # 按版本号降序排序（核心：数字元组可直接比较大小）
        return sorted(files, key=lambda x: x["version"], reverse=True)

    def check_updates(self):
        """检测并选择最大版本号的APK文件"""
        if self.checking or not self.running:
            return

        self.checking = True
        try:
            self.log("开始检测QC APK文件，寻找最大版本号...")
            qc_files = self.get_version_files()
            if not qc_files:
                self.log("未找到有效的QC APK文件（需包含数字版本号）")
                return

            # 更新列表显示（最大版本标红）
            self.root.after(0, self.update_file_list, qc_files)

            # 最大版本是列表第一个元素（已按降序排序）
            max_version_file = qc_files[0]
            max_version = max_version_file["version"]
            max_version_str = max_version_file["version_str"]

            # 比较是否为新的最大版本
            if (self.config["last_max_version"] is None
                    or max_version > self.config["last_max_version"]):
                self.log(f"发现新的最大版本: {max_version_file['name']}（版本: {max_version_str}）")
                self.config["last_max_version"] = max_version

                if self.config["auto_copy"]:
                    self.copy_to_target(max_version_file["path"])
            else:
                self.log(f"当前最大版本保持不变: {max_version_str}（{max_version_file['name']}）")

        except Exception as e:
            self.log(f"检测出错: {str(e)}")
        finally:
            self.checking = False

    def update_file_list(self, qc_files):
        """更新文件列表，最大版本标红显示"""
        self.result_list.delete(0, tk.END)
        self.results = qc_files  # 保存完整信息，方便后续操作

        for i, file in enumerate(qc_files):
            # 最大版本（第一个元素）标红
            if i == 0:
                self.result_list.insert(tk.END,
                                        f"[最大版本 {file['version_str']}] {file['name']} (位于: {file['relative_path']})")
                self.result_list.itemconfig(i, fg="red")
            else:
                self.result_list.insert(tk.END,
                                        f"[版本 {file['version_str']}] {file['name']} (位于: {file['relative_path']})")

        # 自动选中最大版本
        self.result_list.selection_set(0)

    def delete_old_versions(self, target_path, current_filename):
        """删除目标目录中同系列的旧版本APK（保留最大版本）"""
        if not os.path.exists(target_path):
            return

        # 提取QC文件的基础标识（如从"qc_app_1.2.3.apk"提取"qc_app"）
        base_pattern = re.sub(self.config["version_pattern"], "qc", current_filename, flags=re.IGNORECASE)
        base_name = os.path.splitext(base_pattern)[0].lower()

        deleted_count = 0
        for file in os.listdir(target_path):
            # 只删除同系列的旧版本QC APK文件
            if ("qc" in file.lower()
                    and base_name in file.lower()
                    and file.lower() != current_filename.lower()
                    and file.lower().endswith(".apk")):  # 确保只删除APK文件

                file_path = os.path.join(target_path, file)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    self.log(f"已删除旧版本APK: {file}")
                except Exception as e:
                    self.log(f"删除旧版本APK {file} 失败: {str(e)}")

        if deleted_count == 0:
            self.log("目标目录中无旧版本APK文件可删除")
        else:
            self.log(f"共删除 {deleted_count} 个旧版本APK文件")

    def copy_to_target(self, file_path):
        """复制最大版本APK到目标路径（先删旧版本）"""
        if not self.config["target_path"] or not os.path.exists(self.config["target_path"]):
            self.log("目标路径不存在，无法复制APK")
            return False

        try:
            file_name = os.path.basename(file_path)

            # 复制前先删除旧版本APK
            self.delete_old_versions(self.config["target_path"], file_name)

            # 复制最大版本APK文件
            dest_path = os.path.join(self.config["target_path"], file_name)
            shutil.copy2(file_path, dest_path)
            self.log(f"已复制最大版本APK到目标路径: {file_name}")
            return True
        except Exception as e:
            self.log(f"APK复制失败: {str(e)}")
            return False

    def copy_latest(self):
        """手动复制当前最大版本APK"""
        if not self.results:
            messagebox.showwarning("警告", "未找到QC APK文件")
            return

        # 最大版本是列表第一个元素
        latest_path = self.results[0]["path"]
        self.copy_to_target(latest_path)


if __name__ == "__main__":
    root = tk.Tk()
    app = QCFileUpdater(root)
    root.mainloop()
