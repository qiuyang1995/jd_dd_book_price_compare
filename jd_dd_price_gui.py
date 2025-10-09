import tkinter as tk
import random
from tkinter import filedialog, messagebox, ttk, simpledialog
import requests
import openpyxl
import time
import threading
import os
import re
from bs4 import BeautifulSoup

COOKIE_FILE_JD = "jd_cookie.txt"
COOKIE_FILE_DD = "dd_cookie.txt"


class JDPriceFetcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📚 图书价格抓取工具（京东 + 当当）")
        self.root.geometry("650x430")
        self.root.resizable(False, False)

        self.cookie_jd = ""
        self.cookie_dd = ""
        self.file_path = ""
        self.running = False

        # 先创建 UI（确保 self.log_box / self.log 可用），再加载 cookie
        self.create_ui()
        self.load_cookies()

    # ---------------- UI 部分 ----------------
    def create_ui(self):
        tk.Label(self.root, text="📘 图书价格获取工具（京东 + 当当）", font=("微软雅黑", 16, "bold")).pack(pady=10)

        tk.Button(self.root, text="设置 京东 Cookie", command=lambda: self.set_cookie("jd"), width=20, bg="#4CAF50", fg="white").pack(pady=3)
        # tk.Button(self.root, text="设置 当当 Cookie", command=lambda: self.set_cookie("dd"), width=20, bg="#4CAF50", fg="white").pack(pady=3)

        tk.Button(self.root, text="选择 Excel 文件", command=self.select_file, width=20, bg="#2196F3", fg="white").pack(pady=5)
        self.start_btn = tk.Button(self.root, text="开始执行", command=self.start, width=20, bg="#FF9800", fg="white")
        self.start_btn.pack(pady=5)

        self.progress = ttk.Progressbar(self.root, length=400, mode='determinate')
        self.progress.pack(pady=10)
        self.log_box = tk.Text(self.root, height=10, width=75, wrap='word', state='disabled', bg="#f4f4f4")
        self.log_box.pack(pady=10)

    # ---------------- 日志输出 ----------------
    def log(self, msg):
        # 安全地向日志窗写入（UI 线程）
        try:
            self.log_box.config(state='normal')
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state='disabled')
        except Exception:
            # 如果日志区域不可用，退回到控制台输出，防止程序崩溃
            print(msg)

    # ---------------- Cookie 持久化 ----------------
    def load_cookies(self):
        try:
            if os.path.exists(COOKIE_FILE_JD):
                with open(COOKIE_FILE_JD, "r", encoding="utf-8") as f:
                    self.cookie_jd = f.read().strip()
                if self.cookie_jd:
                    self.log("✅ 已加载京东 Cookie。")

            # if os.path.exists(COOKIE_FILE_DD):
            #     with open(COOKIE_FILE_DD, "r", encoding="utf-8") as f:
            #         self.cookie_dd = f.read().strip()
            #     if self.cookie_dd:
            #         self.log("✅ 已加载当当 Cookie。")
        except Exception as e:
            # 任何读文件异常都记录，且不阻塞程序
            print("加载 Cookie 时出错：", e)

    def save_cookie(self, platform):
        try:
            if platform == "jd":
                with open(COOKIE_FILE_JD, "w", encoding="utf-8") as f:
                    f.write(self.cookie_jd or "")
            else:
                with open(COOKIE_FILE_DD, "w", encoding="utf-8") as f:
                    f.write(self.cookie_dd or "")
        except Exception as e:
            self.log(f"⚠️ 保存 Cookie 失败：{e}")

    def set_cookie(self, platform):
        name = "京东" if platform == "jd" else "当当"
        cookie_input = simpledialog.askstring(f"输入 {name} Cookie", f"请输入您的{name} Cookie：", parent=self.root)
        if cookie_input:
            if platform == "jd":
                self.cookie_jd = cookie_input.strip()
            else:
                self.cookie_dd = cookie_input.strip()
            self.save_cookie(platform)
            self.log(f"✅ {name} Cookie 已设置并保存。")
        else:
            self.log(f"⚠️ 未输入{name} Cookie。")

    # ---------------- Excel 文件选择 ----------------
    def select_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("Excel 文件", "*.xlsx")])
        if self.file_path:
            self.log(f"📂 已选择文件：{self.file_path}")

    # ---------------- 主流程 ----------------
    def start(self):
        if not self.cookie_jd:
            messagebox.showwarning("提示", "请先设置 京东 Cookie！")
            return
        if not self.file_path:
            messagebox.showwarning("提示", "请先选择 Excel 文件！")
            return

        self.start_btn.config(state='disabled')
        self.running = True
        threading.Thread(target=self.process_excel).start()

    def process_excel(self):
        try:
            wb = openpyxl.load_workbook(self.file_path)
            sheet = wb.active

            # 找出 ISBN 列
            isbn_col = None
            for col in range(1, sheet.max_column + 1):
                if str(sheet.cell(row=1, column=col).value).strip().lower() in ("isbn", "isbn号"):
                    isbn_col = col
                    break

            if not isbn_col:
                messagebox.showerror("错误", "未找到名为 ISBN 的列")
                self.start_btn.config(state='normal')
                return

            # 新增列：京东价格、当当价格
            jd_price_col = sheet.max_column + 1
            dd_price_col = jd_price_col + 1
            dd_discount_col = dd_price_col + 1
            sheet.cell(row=1, column=jd_price_col).value = "京东价格"
            sheet.cell(row=1, column=dd_price_col).value = "当当价格"
            sheet.cell(row=1, column=dd_discount_col).value = "当当优惠"

            total = sheet.max_row - 1
            self.progress["maximum"] = total

            for i in range(2, sheet.max_row + 1):
                try:
                    isbn = str(sheet.cell(row=i, column=isbn_col).value).strip()
                    if not isbn:
                        continue

                    jd_price = self.fetch_price_jd(isbn)
                    dd = self.fetch_price_dd(isbn)
                    dd_price = dd['price']
                    dd_discount = dd['discount']

                    sheet.cell(row=i, column=jd_price_col).value = jd_price
                    sheet.cell(row=i, column=dd_price_col).value = dd_price
                    sheet.cell(row=i, column=dd_discount_col).value = dd_discount

                    sleep_time = random.uniform(5, 30)
                    self.progress["value"] = i - 1
                    self.log(
                        f"{i - 1}/{total} ✅ {isbn} → 京东 ¥{jd_price or '未获取'} ｜ 当当 ¥{dd_price or '未获取'} {dd_discount} 下次请求：{sleep_time}秒后")

                    time.sleep(sleep_time)

                    # 在主线程安全更新UI
                    self.root.update_idletasks()
                except Exception:
                    pass

            wb.save(self.file_path)
            self.log("🎉 全部完成，结果已写入 Excel！")
            messagebox.showinfo("完成", "价格抓取完成！")

        except Exception as e:
            self.log(f"❌ 错误：{str(e)}")
        finally:
            self.start_btn.config(state='normal')

    # ---------------- 获取京东价格 ----------------
    def fetch_price_jd(self, isbn):
        try:
            url = "https://api.m.jd.com/api?appid=search-pc-java&t=1759932978170&client=pc&clientVersion=1.0.0&cthr=1&uuid=17595618277721101695858&loginType=3&keyword={isbn}&functionId=pc_search_searchWare&body={%22enc%22:%22utf-8%22,%22pvid%22:%22e521718745a94ccd88a05755ea2c33e8%22,%22area%22:%224_50953_50980_0%22,%22page%22:1,%22new_interval%22:true,%22s%22:1}&x-api-eid-token=jdd035SSIFU7UMZ4YJTQGMFEYJF3WOLE3WKM3ZYSLVHMK3H2JLGWH4OLOMNLWMN6CDIL2SARAF3UETUI4YNHYBOPCTLJEXIAAAAMZYQSZ3NIAAAAACJBO7TH2PYMGNUX&h5st=20251008221620178;6mzzwwam6hjw6t39;f06cc;tk03w9ea61c1418nGOXrO52RtWxfrPU87i2aknQeKLs3kJNk1Yk1eIAD8uj7KWgItdtUAayeg4KVAkHNat-K0V2pvizP;a44005325fc12d9f4247d5df1ef7c8f5;5.2;1759932978178;eVxhk4BZoVeErF6H5IOGAEqEn4KGrZfZnZfF7YfZB5hWvdeZnZ-G_U7ZBh-f1Z-VwFeVwV7JwReU_EOT9UrU9IrUvB_JtJbUrZOV-c7VvZfZnZfFbwrI-MrE-hfZXx-Z-c_IpdOU9YeU9QOVvV7U7crJ9A_J_YrJrR7JqJ7U7A_ZB5_Zuc7EzcrJ-hfZXx-ZxZfZnZfUsY7ZBh-f1ZfVzZ_WsJqK8wLH7kMU5YfZnZ-E-hfZXx-Z0NKOv5NGUkMI-h-T-trG9oLJvYfZB5hW-ZuVz8rM-h-T-JbF-hfZXxPCBh-f-J7Q-h-T-VOVsY7ZBhfZB5hWvh-T-dOVsY7ZBhfZB5hWtdeZnZfVwN6J-hfZBh-f1BOWB5_ZvdOE-YfZBhfZXx-ZI07M6MaItY_NsI6G-YfZnZPGyQ7GAY6ZBhfZB5hWxh-T-BOE-YfZBhfZXxfVB5_ZqN6J-hfZBh-f1R_VB5_ZrN6J-hfZBh-f1heZnZPUsY7ZBhfZB5hWxh-T-ROE-YfZBhfZXxPTth-T-VOE-YfZBhfZXx-ZrpPVzh_ZB5_ZwN6J-hfZBh-f1heZnZvHqYfZBhfZXxPUB5_Zuw7ZBhfZB5hWxh-T-x7ZBhfZB5hWxh-T-RrE-hfZBh-fmg-T-R7G8QaD8YfZB5hWkgfZXZPUqJ_IA8eV-Y7IAYrUCQ7H-h-T-ZeF-hfZBh-fmg-T-haF-hfZXx-ZtJeDB1eUrpLHKgvTxpfVwhfMTgvFqkbIz8rM-h-T-dLEuYfZB5xD;b657fb705dc3c39c1a7db5df5bb7dcc1;gRaW989Gy8bE_oLE7w-Gy8rFvM7MtoLI4wrJ1R6G88bG_wPD9k7J1RLHxgKJ&t=1759932978194"
            url = url.replace("{isbn}", isbn)

            headers = {
                "cookie": self.cookie_jd,
                "origin": "https://search.jd.com",
                "referer": "https://search.jd.com/",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            }

            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                self.log("⚠️ 京东请求失败，Cookie 可能过期。")
                return None

            data = resp.json()
            ware_list = data.get("data", {}).get("wareList", [])
            if not ware_list:
                return None
            for ware in ware_list:
                if ware.get("selfSupport") == 1 and ware.get("jdPrice"):
                    return ware["jdPrice"]
            return ware_list[0].get("jdPrice")
        except Exception as e:
            self.log(f"⚠️ 京东请求异常：{e}")
            return None

    # ---------------- 获取当当价格 ----------------
    def fetch_price_dd(self, isbn):
        # 第1步：请求搜索页
        search_url = f"https://search.dangdang.com/?key={isbn}&act=input&filter=0%7C0%7C0%7C0%7C0%7C1%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        }

        print(f"📡 请求当当搜索页：{search_url}")
        resp = requests.get(search_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            print("❌ 搜索页请求失败")
            return None

        html = resp.text
        cookies = resp.cookies.get_dict()
        # 提取 search_passback cookie（部分情况下不在 resp.cookies，需要从 Set-Cookie 头中匹配）
        cookie_header = resp.headers.get("Set-Cookie", "")
        match_passback = re.search(r"search_passback=([^;]+)", cookie_header)
        search_passback = match_passback.group(1) if match_passback else cookies.get("search_passback", "")

        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")

        # 提取价格
        price_tag = soup.select_one("span.search_now_price")
        price = price_tag.text.strip().replace("¥", "").replace("&yen;", "") if price_tag else ""

        # 提取商品ID
        # 常见形式：data-sku="29281138" 或 href="product.dangdang.com/29281138.html"
        product_id = None
        match_id = re.search(r'product\.dangdang\.com/(\d+)\.html', html)
        if match_id:
            product_id = match_id.group(1)
        else:
            match_id = re.search(r'data-sku=["\'](\d+)["\']', html)
            if match_id:
                product_id = match_id.group(1)

        if not product_id:
            print("⚠️ 未找到商品ID，无法继续获取优惠")
            return {"price": price, "discount": ""}

        print(f"✅ 当当价格：¥{price}，商品ID：{product_id}")

        # 第2步：请求优惠接口
        promo_url = (
            f"https://search.dangdang.com/Standard/Search/Extend/hosts/api/get_json.php"
            f"?type=promoIcon"
            f"&keys={product_id}"
            f"&url=0%2F%3Fkey%3D{isbn}%26act%3Dinput%26filter%3D0%7C0%7C0%7C0%7C0%7C1%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0%7C0"
            f"&c=false&l=7b2eea5e6454245e9e56ac31ae24f124"
        )

        cookie_str = (
            "ddscreen=2; "
            "__permanent_id=20251008120357543381482942643863985; "
            "dest_area=country_id%3D9000%26province_id%3D111%26city_id%3D0%26district_id%3D0%26town_id%3D0; "
            "__visit_id=20251008205927180350921430742688925; "
            "__out_refer=; "
            "__rpm=s_112100.5402553.8.1759928699406%7Cs_112100.5402553.8.1759928702841; "
            "__trace_id=20251008210502894333062959282935496; "
            f"search_passback={search_passback}"
        )

        promo_headers = {
            "Referer": search_url,
            "Cookie": cookie_str,
            "User-Agent": headers["User-Agent"]
        }

        print(f"📡 请求优惠接口：{promo_url}")
        promo_resp = requests.get(promo_url, headers=promo_headers, timeout=10)

        if promo_resp.status_code != 200:
            print("⚠️ 优惠接口请求失败")
            return {"price": price, "discount": ""}

        data = promo_resp.json()
        promo_list = data.get(product_id, [])
        discounts = [item["label_name"] for item in promo_list if item["label_name"] not in ("自营", "券")]
        discount_text = "，".join(discounts) if discounts else "无"

        print(f"✅ 优惠信息：{discount_text}")
        return {"price": price, "discount": discount_text}

if __name__ == "__main__":
    root = tk.Tk()
    app = JDPriceFetcherApp(root)
    root.mainloop()
