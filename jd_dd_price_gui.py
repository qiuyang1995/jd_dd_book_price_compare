import tkinter as tk
import random
from tkinter import filedialog, messagebox, ttk, simpledialog
import requests
import openpyxl
import time
import threading
import os
import re
import pickle
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

COOKIE_FILE_JD = "jd_cookie.txt"
COOKIE_FILE_DD = "dd_cookie.txt"
JD_COOKIES_PKL = "jd_cookies.pkl"


class JDPriceFetcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📚 图书价格抓取工具（京东 + 当当）")
        self.root.geometry("650x430")
        self.root.resizable(False, False)

        self.file_path = ""
        self.running = False
        self.driver = None

        # 先创建 UI，再加载 cookie
        self.create_ui()

    # ---------------- UI 部分 ----------------
    def create_ui(self):
        tk.Label(self.root, text="📘 图书价格获取工具（京东 + 当当）", font=("微软雅黑", 16, "bold")).pack(pady=10)

        tk.Button(self.root, text="选择 Excel 文件", command=self.select_file, width=20, bg="#2196F3", fg="white").pack(pady=5)
        
        # 添加测试按钮
        tk.Button(self.root, text="测试京东访问", command=self.test_jd_access, width=20, bg="#9C27B0", fg="white").pack(pady=3)
        
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

    # ---------------- Excel 文件选择 ----------------
    def select_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("Excel 文件", "*.xlsx")])
        if self.file_path:
            self.log(f"📂 已选择文件：{self.file_path}")

    # ---------------- 主流程 ----------------
    def start(self):
        # 检查Cookie设置不再必须，因为我们使用Selenium登录
        if not self.file_path:
            messagebox.showwarning("提示", "请先选择 Excel 文件！")
            return

        self.start_btn.config(state='disabled')
        self.running = True
        threading.Thread(target=self.process_excel).start()

    def process_excel(self):
        try:
            # 初始化浏览器
            self.log("🚀 正在启动浏览器...")
            if not self.init_browser():
                self.log("❌ 浏览器启动失败")
                return
            
            # 登录京东
            self.log("🔑 正在登录京东...")
            if not self.login_or_load_jd_cookie():
                self.log("❌ 京东登录失败")
                return
            
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

                    sleep_time = random.uniform(1, 10)
                    sleep_time = int(sleep_time)
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
            # 确保关闭浏览器
            self.close_browser()
            self.start_btn.config(state='normal')

    # ---------------- 浏览器初始化和京东登录 ----------------
    def init_browser(self):
        """修复版本的浏览器初始化 - 多种后备方案"""
        self.log("🚀 正在初始化浏览器...")
        
        # 方案1: 先尝试标准 Selenium + 无痕模式
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            self.log("🔧 尝试使用标准 Selenium ...")
            
            # 使用标准 Selenium 配置无痕模式
            chrome_options = Options()
            # chrome_options.add_argument("--incognito")  # 无痕模式
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--disable-default-apps")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 初始化驱动
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # 添加反检测脚本
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.driver.maximize_window()
            self.driver.get("data:text/html,<html><body><h1>Standard Incognito Test OK</h1></body></html>")
            
            self.log("✅ 标准 Selenium 启动成功")
            return True
                    
        except Exception as e:
            self.log(f"⚠️ 标准 Selenium 失败: {e}")
            
            # 方案2: 尝试 undetected_chromedriver
            try:
                import undetected_chromedriver as uc
                self.log("🔄 尝试使用 undetected_chromedriver...")
                
                # 创建选项
                options = uc.ChromeOptions()
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--disable-extensions")
                options.add_argument("--no-first-run")
                options.add_argument("--disable-default-apps")
                options.add_argument("--remote-debugging-port=9222")

                # 初始化驱动
                self.driver = uc.Chrome(options=options, version_main=None)
                self.driver.maximize_window()
                
                # 测试访问
                self.driver.get("data:text/html,<html><body><h1>Undetected Test OK</h1></body></html>")
                
                self.log("✅ undetected_chromedriver 启动成功")
                return True

            except Exception as e2:
                self.log(f"⚠️ undetected_chromedriver 也失败: {e2}")
                
                # 方案3: 最后尝试 webdriver-manager
                try:
                    self.log("🔄 尝试安装并使用 webdriver-manager...")
                    import subprocess
                    import sys
                    
                    # 安装 webdriver-manager
                    result = subprocess.run([sys.executable, "-m", "pip", "install", "webdriver-manager"], 
                                          capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        from selenium import webdriver
                        from selenium.webdriver.chrome.service import Service
                        from selenium.webdriver.chrome.options import Options
                        from webdriver_manager.chrome import ChromeDriverManager
                        
                        chrome_options = Options()
                        # chrome_options.add_argument("--incognito")  # 无痕模式
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                        chrome_options.add_experimental_option('useAutomationExtension', False)
                        
                        service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=service, options=chrome_options)
                        
                        # 添加反检测脚本
                        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                        
                        self.driver.maximize_window()
                        self.driver.get("data:text/html,<html><body><h1>WebDriver Manager Test OK</h1></body></html>")
                        
                        self.log("✅ webdriver-manager 启动成功")
                        return True
                    else:
                        self.log("❌ webdriver-manager 安装失败")
                        
                except Exception as e3:
                    self.log(f"❌ webdriver-manager 也失败: {e3}")
                    
            # 所有方案都失败
            self.log("❌ 所有浏览器启动方案都失败")
            
            # 详细错误信息
            import traceback
            self.log(f"详细错误：{traceback.format_exc()}")
            
            # 提供解决方案
            self.log("💡 可能的解决方案:")
            self.log("   1. 检查网络连接是否正常")
            self.log("   2. 关闭防火墙或杀毒软件")
            self.log("   3. 运行: pip install webdriver-manager")
            self.log("   4. 手动下载 ChromeDriver 并加入 PATH")
            
            return False

    def login_or_load_jd_cookie(self):
        """登录京东或加载已保存的Cookie"""
        if not self.driver:
            return False
            
        try:
            self.driver.get("https://www.jd.com/")
            
            # 尝试加载已保存的Cookie
            if os.path.exists(JD_COOKIES_PKL):
                try:
                    with open(JD_COOKIES_PKL, "rb") as f:
                        cookies = pickle.load(f)
                    for cookie in cookies:
                        self.driver.add_cookie(cookie)
                    self.driver.refresh()
                    self.log("✅ 已加载上次登录状态。")
                    # 在主线程中更新UI
                    self.root.update_idletasks()
                    return True
                except Exception as e:
                    self.log(f"加载 cookie 失败：{e}")
            
            # 需要手动登录
            messagebox.showinfo("登录提示", "请在打开的浏览器中扫码登录京东，然后点击确定继续。")
            self.driver.get("https://passport.jd.com/new/login.aspx")
            messagebox.showinfo("继续", "扫码登录完成后点击确定继续。")
            
            # 登录完成后保存 cookie
            cookies = self.driver.get_cookies()
            with open(JD_COOKIES_PKL, "wb") as f:
                pickle.dump(cookies, f)
            self.log("✅ 登录信息已保存，可下次免登录。")
            # 在主线程中更新UI
            self.root.update_idletasks()
            return True
                
        except Exception as e:
            self.log(f"❌ 京东登录过程出错：{e}")
            return False
    def close_browser(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                self.log("✅ 浏览器已关闭")
            except Exception as e:
                self.log(f"⚠️ 关闭浏览器时出错：{e}")

    # ---------------- 获取京东价格（使用Selenium） ----------------
    def fetch_price_jd(self, isbn):
        """使用Selenium获取京东价格（仅限自营商品）"""
        if not self.driver:
            self.log("⚠️ 浏览器未初始化")
            return None
            
        try:
            # 访问京东搜索页
            url = f"https://search.jd.com/Search?keyword={isbn}"
            self.log(f"🔍 访问搜索页: {url}")
            self.driver.get(url)
            
            # 检测是否被跳转到登录页（cookie过期）
            current_url = self.driver.current_url
            if self.is_redirected_to_login(current_url):
                self.log("⚠️ 检测到被跳转到登录页，cookie可能已过期")
                if self.handle_cookie_expiration():
                    # 重新访问搜索页
                    self.log(f"🔄 重新访问搜索页: {url}")
                    self.driver.get(url)
                else:
                    return "登录失败"
            
            # 等待页面基本加载
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                )
                time.sleep(3)  # 额外等待动态内容加载
                
                price = self.extract_self_sold_price()
                return price
            except TimeoutException:
                self.log("⚠️ 页面加载超时")
                return "超时"
                
        except Exception as e:
            self.log(f"⚠️ 京东请求异常：{e}")
            return None
    
    def is_redirected_to_login(self, current_url):
        """检测是否被跳转到登录页"""
        login_indicators = [
            'passport.jd.com',
            'login.jd.com', 
            '/login',
            'auth.jd.com',
            'signin.jd.com'
        ]
        
        for indicator in login_indicators:
            if indicator in current_url.lower():
                self.log(f"🔍 检测到登录页指示器: {indicator}")
                return True
        
        return False
    
    def handle_cookie_expiration(self):
        """处理cookie过期问题"""
        try:
            # 删除过期cookie文件
            if os.path.exists(JD_COOKIES_PKL):
                os.remove(JD_COOKIES_PKL)
                self.log("✅ 已删除过期cookie文件")
            
            # 清理浏览器中cookie
            self.driver.delete_all_cookies()
            self.log("✅ 已清理浏览器cookie")
            
            # 重新登录
            self.log("🔄 尝试重新登录...")
            return self.login_or_load_jd_cookie()
            
        except Exception as e:
            self.log(f"⚠️ 处理cookie过期失败: {e}")
            return False
    
    def extract_self_sold_price(self):
        """提取京东自营商品价格 - 根据实际页面结构修复"""
        driver = self.driver
        
        try:
            # 等待商品列表加载 - 使用您提供的实际选择器
            self.log("⏳ 等待商品列表加载...")
             
            # 使用您提供的实际商品容器选择器
            container_selector = "._wrapper_f6icl_11"
            
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, container_selector))
                )
                containers = driver.find_elements(By.CSS_SELECTOR, container_selector)
                self.log(f"✅ 找到 {len(containers)} 个商品容器")
            except TimeoutException:
                self.log("⚠️ 等待商品容器超时")
                return "超时"
            
            if not containers:
                self.log("⚠️ 未找到商品容器")
                return "超时"
            
            # 只处理第一个容器（真正的搜索结果），但要遍历其中所有商品
            main_container = containers[0]
            
            # 在主容器中查找所有商品项
            # 尝试多种选择器来查找商品项
            item_selectors = [
                "li[data-sku]",  # 原始选择器
                "li",            # 通用li元素
                "div[data-sku]", # div类型的商品
                ".gl-item",      # 商品项class
                "[class*='item']", # 包含item的class
            ]
            
            items = []
            for selector in item_selectors:
                try:
                    items = main_container.find_elements(By.CSS_SELECTOR, selector)
                    if items:
                        self.log(f"✅ 使用选择器 '{selector}' 在主容器中找到 {len(items)} 个商品项")
                        break
                    else:
                        self.log(f"⚠️ 选择器 '{selector}' 未找到商品")
                except Exception as e:
                    self.log(f"⚠️ 选择器 '{selector}' 查找失败: {e}")
                    continue
            
            if not items:
                self.log("⚠️ 所有选择器都未找到商品项，尝试直接从容器中获取所有子元素")
                try:
                    # 最后的后备方案：获取所有直接子元素
                    items = main_container.find_elements(By.XPATH, "./*")
                    self.log(f"✅ 后备方案找到 {len(items)} 个子元素")
                except Exception as e:
                    self.log(f"⚠️ 后备方案也失败: {e}")
                    return "超时"


            # 遍历商品，查找自营商品
            for i, item in enumerate(items):
                try:
                    # 检查是否为自营商品 - 使用您提供的实际结构
                    self.log(f"🔍 检查商品 #{i+1} 是否为自营...")
                    
                    # 使用您提供的自营标签结构
                    self_support_selector = 'div._imgTag_1qbwk_1 img[alt="自营"]'
                    
                    try:
                        tag = item.find_element(By.CSS_SELECTOR, self_support_selector)
                        if tag:
                            self.log(f"✅ 找到自营商品 #{i+1}")
                            
                            # 提取价格 - 使用您提供的实际价格结构
                            price = self.extract_price_from_item(item, i+1)
                            if price:
                                return price
                    except NoSuchElementException:
                        self.log(f"⚠️ 商品 #{i+1} 不是自营")
                        continue
                                
                except Exception as e:
                    self.log(f"⚠️ 处理商品 #{i+1} 时出错: {e}")
                    continue

            self.log("⚠️ 未找到自营商品或价格")
            return "无自营"
            
        except Exception as e:
            self.log(f"⚠️ 价格提取异常: {e}")
            return "超时"
    
    def extract_price_from_item(self, item, item_num):
        """从单个商品容器中提取价格 - 修复小数部分提取"""
        try:
            self.log(f"📍 开始提取商品 #{item_num} 的价格...")
            
            # 方法1: 使用您提供的完整价格结构 - 修复版本
            # <span class="_price_uqsva_14"><i class="_yen_uqsva_20">¥</i>65<span>.</span><span class="_decimal_uqsva_28">99</span></span>
            try:
                price_container = item.find_element(By.CSS_SELECTOR, "span._price_uqsva_14")
                if price_container:
                    # 获取整个价格容器的文本
                    full_price_text = price_container.text.strip()
                    self.log(f"🔍 方法1 - 找到价格容器，原始文本: {repr(full_price_text)}")
                    if full_price_text:
                        # 清理价格数据，处理换行和空格
                        clean_price = full_price_text.replace("¥", "").replace("￥", "").replace("\n", "").replace(" ", "").strip()
                        # 重新组合价格：处理被分隔的数字和小数点
                        import re
                        # 提取所有数字和小数点，然后重新组合
                        numbers_and_dots = re.findall(r'[\d\.]+', clean_price)
                        self.log(f"🔍 方法1 - 清理后: '{clean_price}', 提取的数字: {numbers_and_dots}")
                        if numbers_and_dots:
                            # 将提取的数字部分连接起来
                            reconstructed_price = ''.join(numbers_and_dots)
                            # 验证是否为有效价格格式
                            if re.match(r'^\d+\.\d+$|^\d+$', reconstructed_price):
                                self.log(f"✅ 方法1成功：商品 #{item_num} 价格: {reconstructed_price}")
                                return reconstructed_price
                        else:
                            self.log(f"⚠️ 方法1 - 未找到数字")
                    else:
                        self.log(f"⚠️ 方法1 - 价格文本为空")
                else:
                    self.log(f"⚠️ 方法1 - 未找到价格容器")
            except NoSuchElementException:
                self.log(f"⚠️ 方法1 - NoSuchElementException: span._price_uqsva_14")
            except Exception as e:
                self.log(f"⚠️ 方法1异常: {e}")
            
            # 方法2: 手动组合价格元素 - 完整版本
            try:
                # 获取价格容器
                price_container = item.find_element(By.CSS_SELECTOR, "span._price_uqsva_14")
                
                # 获取容器内的HTML内容
                container_html = price_container.get_attribute('innerHTML')
                
                # 使用正则提取整数部分（在</i>之后，<span>之前）
                import re
                integer_match = re.search(r'</i>(\d+)<span>', container_html)
                
                # 直接查找小数部分元素
                decimal_elements = price_container.find_elements(By.CSS_SELECTOR, "span._decimal_uqsva_28")
                
                if integer_match and decimal_elements:
                    integer_part = integer_match.group(1)
                    decimal_part = decimal_elements[0].text.strip()
                    full_price = f"{integer_part}.{decimal_part}"
                    self.log(f"✅ 方法2成功：商品 #{item_num} 价格: {full_price} (整数: {integer_part}, 小数: {decimal_part})")
                    return full_price
                elif integer_match:
                    # 如果没有小数部分，只返回整数
                    integer_part = integer_match.group(1)
                    self.log(f"✅ 方法2成功：商品 #{item_num} 价格: {integer_part} (仅整数部分)")
                    return integer_part
                else:
                    # 备用方案：从整个HTML中提取数字
                    all_numbers = re.findall(r'\d+', container_html)
                    if len(all_numbers) >= 2:
                        # 假设第一个数字是整数，第二个是小数
                        integer_part = all_numbers[0]
                        decimal_part = all_numbers[1]
                        full_price = f"{integer_part}.{decimal_part}"
                        self.log(f"✅ 方法2备用成功：商品 #{item_num} 价格: {full_price}")
                        return full_price
                    elif len(all_numbers) == 1:
                        price = all_numbers[0]
                        self.log(f"✅ 方法2备用成功：商品 #{item_num} 价格: {price} (仅整数)")
                        return price
                    
            except NoSuchElementException:
                pass
                
            # 方法3: 更精确的正则提取
            try:
                price_container = item.find_element(By.CSS_SELECTOR, "span._price_uqsva_14")
                container_text = price_container.text.strip()
                
                if container_text:
                    # 使用更精确的正则表达式匹配价格
                    import re
                    # 匹配各种价格格式：65.99, 65, ¥65.99, ¥65 等
                    price_patterns = [
                        r'(\d+\.\d+)',          # 65.99
                        r'¥(\d+\.\d+)',        # ¥65.99
                        r'￥(\d+\.\d+)',        # ￥65.99
                        r'(\d+)',               # 65 (作为后备)
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, container_text)
                        if matches:
                            price = matches[0]
                            self.log(f"✅ 方法3成功：商品 #{item_num} 正则提取价格: {price} (模式: {pattern})")
                            return price
                            
            except Exception:
                pass
            
            # 方法4: 使用更通用的价格选择器
            price_selectors = [
                "span._price_uqsva_14",
                "i.price_n",
                "span.p-price i",
                "em.J_price",
                ".price strong i",
                "[class*='price'] i",
                "[class*='price'] em",
                ".J_price"
            ]
            
            for price_sel in price_selectors:
                try:
                    price_el = item.find_element(By.CSS_SELECTOR, price_sel)
                    price_text = price_el.text.strip()
                    if price_text:
                        # 使用正则提取数字部分
                        import re
                        price_match = re.search(r'\d+\.\d+|\d+', price_text)
                        if price_match:
                            price = price_match.group()
                            self.log(f"✅ 方法4成功：商品 #{item_num} 价格: {price}（选择器: {price_sel}）")
                            return price
                except NoSuchElementException:
                    continue
            
            # 方法5: 最后的后备方案 - 正则搜索整个元素文本
            try:
                all_text = item.text
                if all_text:
                    import re
                    # 查找价格模式，优先匹配带小数的价格
                    price_patterns = [
                        r'(\d+\.\d{1,2})',      # 65.99, 65.9
                        r'¥(\d+\.\d{1,2})',    # ¥65.99
                        r'￥(\d+\.\d{1,2})',    # ￥65.99  
                        r'(\d{2,})'             # 至少两位数字(作为后备)
                    ]
                    
                    for pattern in price_patterns:
                        matches = re.findall(pattern, all_text)
                        if matches:
                            price = matches[0]
                            self.log(f"✅ 方法5成功：商品 #{item_num} 正则提取价格: {price}")
                            return price
                            
            except Exception:
                pass
                
            self.log(f"⚠️ 商品 #{item_num} 未能提取到价格")
            return None
            
        except Exception as e:
            self.log(f"⚠️ 商品 #{item_num} 价格提取异常: {e}")
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

    # ---------------- 测试方法 ----------------
    def test_jd_access(self):
        """测试京东访问功能"""
        def run_test():
            try:
                self.log("🧪 开始测试京东访问...")
                
                # 初始化浏览器
                if not self.init_browser():
                    self.log("❌ 测试失败：浏览器启动失败")
                    return
                
                # 登录京东
                if not self.login_or_load_jd_cookie():
                    self.log("❌ 测试失败：京东登录失败")
                    self.close_browser()
                    return
                
                # 测试ISBN列表
                test_isbns = [
                    "9787513288675",  # 中药代谢分析学
                    "9787229202941"   # 《异重庆四重奏》
                ]
                
                success_count = 0
                for i, isbn in enumerate(test_isbns, 1):
                    self.log(f"🔍 {i}/{len(test_isbns)} 正在测试 ISBN: {isbn}")
                    price = self.fetch_price_jd(isbn)
                    
                    if price and price not in ["无自营", "超时"]:
                        self.log(f"✅ 成功获取价格: ¥{price}")
                        success_count += 1
                    else:
                        self.log(f"⚠️ 未获取到价格: {price or '空'}")
                    
                    # 防止请求过频
                    if i < len(test_isbns):
                        self.log("⏳ 等待5秒...")
                        time.sleep(5)
                
                # 测试结果
                if success_count > 0:
                    self.log(f"✅ 测试完成！成功获取 {success_count}/{len(test_isbns)} 个价格")
                    messagebox.showinfo("测试结果", f"测试成功！\n成功获取 {success_count}/{len(test_isbns)} 个价格")
                else:
                    self.log("❌ 测试失败：未能获取任何价格")
                    messagebox.showwarning("测试结果", "测试失败！\n未能获取任何价格，请检查网络和登录状态")
                
            except Exception as e:
                self.log(f"❌ 测试过程中发生错误：{e}")
                messagebox.showerror("测试错误", f"测试过程中发生错误：\n{e}")
            finally:
                # 确保关闭浏览器
                self.close_browser()
        
        # 在新线程中运行测试，防止阻塞UI
        threading.Thread(target=run_test, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = JDPriceFetcherApp(root)
    root.mainloop()
