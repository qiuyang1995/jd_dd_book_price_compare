# 📚 图书价格抓取工具（京东 + 当当）

一个基于 Python 和 Selenium 的自动化图书价格抓取工具，支持从京东和当当网获取图书价格信息，并将结果保存到 Excel 文件中。

## ✨ 功能特点

- 🔍 **智能价格抓取**：自动从京东和当当网获取图书价格
- 🛒 **自营商品识别**：京东仅抓取自营商品价格，确保正品
- 🍪 **智能登录管理**：自动检测Cookie过期并重新登录
- 🌐 **反检测机制**：使用多重浏览器启动方案，绕过网站反爬机制
- 📊 **Excel集成**：直接读取Excel中的ISBN信息，并将结果写回Excel
- 🚀 **多重启动方案**：标准Selenium → undetected_chromedriver → webdriver-manager
- 🔒 **无痕模式**：默认使用浏览器无痕模式，保护隐私
- 📈 **实时进度显示**：GUI界面显示抓取进度和详细日志

## 🛠️ 技术架构

### 核心技术栈
- **GUI框架**：tkinter
- **网页自动化**：Selenium WebDriver + undetected_chromedriver
- **数据处理**：openpyxl (Excel操作)
- **网络请求**：requests (当当网API)
- **HTML解析**：BeautifulSoup4

### 浏览器驱动策略
1. **标准Selenium** (优先) - 配置无痕模式和反检测参数
2. **undetected_chromedriver** (备用) - 专业反检测浏览器
3. **webdriver-manager** (最终备用) - 自动下载驱动管理

## 📋 系统要求

### 必需环境
- Python 3.7+
- Google Chrome 浏览器
- Windows/macOS/Linux

### Python依赖包
```bash
pip install tkinter requests openpyxl selenium undetected-chromedriver beautifulsoup4 webdriver-manager
```

## 🚀 快速开始

### 1. 安装依赖
```bash
# 克隆项目（如适用）
git clone <repository-url>
cd jd_dd_book_price_compare

# 安装Python依赖
pip install -r requirements.txt
```

### 2. 准备Excel文件
创建一个Excel文件，包含以下列：
- **ISBN** 或 **ISBN号** 列：包含要查询的图书ISBN号

示例：
| ISBN | 书名 | 作者 |
|------|------|------|
| 9787513288675 | 中药代谢分析学 | XXX |
| 9787229202941 | 异重庆四重奏 | XXX |

### 3. 运行程序
```bash
python jd_dd_price_gui.py
```

### 4. 使用步骤
1. 点击 **"选择 Excel 文件"** 选择包含ISBN的Excel文件
2. 点击 **"测试京东访问"** 验证系统功能（可选）
3. 点击 **"开始执行"** 开始价格抓取
4. 首次使用需要在浏览器中手动登录京东账号
5. 程序会自动抓取价格并保存到Excel文件

## 🔧 核心功能详解

### 京东价格抓取
- **自营商品识别**：仅抓取带有"自营"标签的商品
- **价格精确提取**：支持小数点价格的完整提取
- **智能容器定位**：只处理真实搜索结果，忽略推荐商品
- **多重价格提取方案**：5种不同的价格提取策略确保成功率

### 当当价格抓取
- **价格和优惠信息**：同时获取商品价格和促销信息
- **API接口调用**：直接调用当当内部API获取数据
- **Cookie管理**：自动处理搜索页面Cookie

### 智能登录管理
```python
# 自动检测Cookie过期
def is_redirected_to_login(self, current_url):
    login_indicators = [
        'passport.jd.com', 'login.jd.com', '/login',
        'auth.jd.com', 'signin.jd.com'
    ]
    return any(indicator in current_url.lower() for indicator in login_indicators)

# 自动处理Cookie过期
def handle_cookie_expiration(self):
    # 删除过期Cookie文件和浏览器Cookie
    # 触发重新登录流程
```

## 📊 输出格式

程序会在原Excel文件中新增以下列：
- **京东价格**：自营商品价格（如：29.80）
- **当当价格**：商品价格（如：26.50）  
- **当当优惠**：促销信息（如：满减优惠，无）

## ⚙️ 配置选项

### 浏览器配置
```python
# 标准Selenium配置
chrome_options.add_argument("--incognito")  # 无痕模式
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
```

### 价格提取配置
```python
# 京东容器选择器
container_selector = "._wrapper_f6icl_11"

# 自营标签选择器  
self_support_selector = 'div._imgTag_1qbwk_1 img[alt="自营"]'

# 价格选择器
price_selector = "span._price_uqsva_14"
```

## 🔍 故障排除

### 常见问题

**1. 浏览器启动失败**
```
💡 可能的解决方案:
1. 检查网络连接是否正常
2. 关闭防火墙或杀毒软件
3. 运行: pip install webdriver-manager
4. 手动下载 ChromeDriver 并加入 PATH
```

**2. 登录状态失效**
- 程序会自动检测并处理Cookie过期
- 如遇问题，可手动删除 `jd_cookies.pkl` 文件

**3. 价格获取失败**
- 检查网络连接
- 确认京东账号已登录
- 验证ISBN格式正确

**4. Excel文件问题**
- 确保Excel文件中有 "ISBN" 或 "ISBN号" 列
- 文件不能为只读状态

## 📝 日志说明

程序提供详细的运行日志：
- 🚀 **启动阶段**：浏览器初始化状态
- 🔑 **登录阶段**：Cookie加载和登录状态
- 🔍 **抓取阶段**：每个ISBN的处理过程
- ✅ **成功标识**：价格获取成功
- ⚠️ **警告信息**：非关键错误
- ❌ **错误信息**：严重错误

## 🔐 隐私和安全

- **无痕模式**：默认使用浏览器无痕模式
- **本地存储**：Cookie仅保存在本地
- **安全登录**：使用官方登录页面，不存储密码
- **反检测**：多重反检测机制保护账号安全

## 📈 性能优化

- **智能延时**：请求间随机延时1-10秒
- **容错机制**：多种价格提取策略
- **资源管理**：自动关闭浏览器释放资源
- **并发控制**：单线程执行避免被封

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进这个项目！

### 开发环境搭建
```bash
# 克隆项目
git clone <repository-url>
cd jd_dd_book_price_compare

# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
python -m pytest tests/
```

### 打包exe
```bash
pip install pyinstaller
pyinstaller -F -w jd_dd_price_gui.py
```

## 📄 许可证

本项目仅供学习和研究使用。请遵守相关网站的使用条款和robots.txt规定。

## ⚠️ 免责声明

本工具仅用于个人学习和研究目的。使用本工具时请遵守相关网站的服务条款，不要进行大规模的数据抓取。作者不对使用本工具造成的任何后果承担责任。

## 📞 支持

如果您在使用过程中遇到问题，请：
1. 查看故障排除部分
2. 检查程序日志输出
3. 提交Issue（如适用）

---

**版本**: 1.0.0  
**最后更新**: 2024-10-09  
**作者**: [您的名字]