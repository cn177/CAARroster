# CAAR —— 会员与队伍管理系统

一个**只给运营用**的内部后台，管三件事：

1. **录入** —— 把问卷星导出的 Excel 直接变成结构化会员档案（自动认字段、自动去重、自由文本归一化）。
2. **建队** —— 维护常设队伍（冲击队 / 摸鱼队 / 带新队），管人数上限、新手名额、队长。
3. **分配** —— 把还没队伍的新手分到合适的队伍，**每条推荐都给出理由**，还能一键生成分配草案。

技术栈是 **Flask + SQLite + Jinja2**：单机一个进程，零外部 CDN 依赖，数据全在你自己的服务器上，不需要任何第三方服务。

> 📷 **建议在这里补一张分配台的截图。** 开源项目里截图比文档的拉星效率高得多。

---

## 目录

- [这是什么 / 不是什么](#这是什么--不是什么)
- [一、快速开始（本地看效果）](#一快速开始本地看效果)
- [二、部署到自己的服务器](#二部署到自己的服务器)
- [三、日常怎么用](#三日常怎么用)
- [四、推荐是怎么算的](#四推荐是怎么算的)
- [五、数据、备份与安全](#五数据备份与安全)
- [六、代码结构（给想改代码的人）](#六代码结构给想改代码的人)
- [七、测试](#七测试)
- [八、遇到问题先看这里](#八遇到问题先看这里)
- [九、开源与二次开发](#九开源与二次开发)
- [十、还没做、以后可以加的](#十还没做以后可以加的)

---

## 这是什么 / 不是什么

**是什么**

- 给小团队（几十到几百人）用的**分组决策辅助工具**。核心不是"存数据"，是"把稀缺的老手合理地分给新手，并且让每个决定都有据可查"。
- 一个可以随时改的单体应用：4 个文件（`skills.py` / `importer.py` / `matching.py` / `views/forms.py`）就能改掉绝大部分业务逻辑。

**不是什么**（先说清楚，省得你翻半天代码）

- **没有会员端。** 会员不能自己注册、登录、申请入队。录入和分配都由运营完成 —— 200~300 人的规模，运营代录反而更快更可控。
- **没有公网 API。** 它是个网页后台，不是服务。
- **不做在线判题 / 计分板。** 那是赛事系统的事，这个只管人和队伍。
- **不是多租户 SaaS。** 一个部署服务一个协会。

---

## 一、快速开始（本地看效果）

**前置条件**：Python 3.10+（推荐 3.12）。其他什么都不用装。

### Windows

```powershell
# 1. 装好 Python（安装时务必勾 "Add python.exe to PATH"）
# 2. 直接双击 start-windows.bat，剩下的它全干：
#    建虚拟环境 → 装依赖 → 建数据库 → 让你设管理员密码 → 启动
```

### macOS / Linux

```bash
cd roster
python3 -m venv .venv
source .venv/bin/activate          # Windows 的 Git Bash 用 .venv/Scripts/activate

pip install -r requirements.txt

python app.py --seed-demo               # 可选：灌 50 人演示数据，正式用之前别跑
python app.py --create-admin admin 你的强密码
python app.py                            # 启动
```

打开 <http://127.0.0.1:8000>，用刚建的账号登录。

> 国内装依赖慢的话加镜像：
> `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

> 想清空演示数据重来：删掉 `data/roster.db`、`data/roster.db-wal`、`data/roster.db-shm` 三个文件，
> 再跑一次 `python app.py` 就会重新建库。

---

## 二、部署到自己的服务器

先看服务器是什么系统：

- **Windows Server** → 看「方式 A」，宝塔 / 远程桌面 / SSH 都能用
- **Linux** → 「方式 B」（Docker）或「方式 C」（systemd）

三种方式**默认都只监听 `127.0.0.1`，外网连不上**。这是故意的：内部系统不该裸奔在公网。

### 方式 A：Windows Server

Windows Server 上 gunicorn 跑不了，所以用 **waitress**（纯 Python，跨平台）。启动脚本已经写好了，你不用碰命令行。

**第 1 步：服务器上装 Python**

从 <https://www.python.org/downloads/windows/> 下载 **Windows installer (64-bit)**，安装时**最下面那个 "Add python.exe to PATH" 一定要勾上**。

> ⚠️ 如果你在命令行敲 `python` 会跳出「应用商店」，说明 Python 其实**没装** —— 那是微软放的占位符，不是真的 Python。启动脚本能识别这种假 Python 并明确告诉你。

**第 2 步：把代码传上去**

用部署包，别直接传整个 `roster` 目录 —— 里面那个 `.venv` 有 20 MB 且换了机器就没用，
而部署包只有 100 KB。

**方式一（最省事）**：用宝塔面板的「文件」功能，把 `ara-roster-部署包.zip` 上传到 `D:\`，
右键**在线解压**，得到 `D:\roster`。

**方式二**：有 SSH 的话在你自己的电脑上推（Windows 10/11 自带 ssh 和 scp）：

```powershell
scp D:\CAAR\ara-roster-部署包.zip 你的用户名@服务器IP:D:/
# 然后 SSH 上去解压：
ssh 你的用户名@服务器IP
powershell -Command "Expand-Archive -Path D:\ara-roster-部署包.zip -DestinationPath D:\ -Force"
```

**方式三**：非要传整个目录的话，先删掉本地的 `.venv`，否则会连它一起传：

```powershell
scp -r D:\CAAR\roster 你的用户名@服务器IP:D:/roster
```

**第 3 步：双击启动**

进 `D:\roster`，双击 **`start-windows.bat`**。它会自动完成：找 Python → 建独立环境 → 装依赖（走清华镜像）→ 建数据库 → 让你设管理员密码 → 启动服务。

第一次要等两三分钟，之后就几秒。看到这段话就成功了：

```
  服务已启动，正在监听 127.0.0.1:8000
      ssh -L 8000:127.0.0.1:8000 你的用户名@服务器IP
      http://127.0.0.1:8000
```

**第 4 步：从你自己的电脑访问**

服务器不对公网开放任何端口，你走 SSH 隧道。在**你自己电脑**的终端里执行：

```bash
ssh -L 8000:127.0.0.1:8000 你的用户名@服务器IP
```

保持这个窗口开着，浏览器打开 <http://127.0.0.1:8000> 就能用了。

> SSH 端口不是默认的 22 就加 `-p 端口号`。提示本地端口被占用，就把两边的 8000 一起换成 8001。

**第 5 步：让它开机自启、后台常驻**

上面那个黑窗口一关，服务就停了。用 Windows 自带的「任务计划程序」解决：

1. 开始菜单搜「任务计划程序」，打开
2. 右侧点「创建任务」（**不是**「创建基本任务」）
3. **常规**页：名称填 `ARA Roster`；勾「不管用户是否登录都要运行」；勾「使用最高权限运行」
4. **触发器**页：新建 → 开始任务选「启动时」→ 确定
5. **操作**页：新建 → 程序或脚本填 `powershell.exe`，添加参数填：
   ```
   -NoProfile -ExecutionPolicy Bypass -File D:\roster\start-windows.ps1
   ```
   「起始于」填 `D:\roster`
6. **设置**页：勾「如果任务失败，按以下频率重新启动」，间隔 1 分钟，尝试 3 次
7. 确定，会让你输一次服务器的登录密码

> 任务计划跑的时候没有交互界面，问密码那一步会卡住。所以**先手动双击一次 `start-windows.bat` 把账号建好**，再去配任务计划。

**第 6 步（别跳过）：顺手把宝塔面板自己加固**

宝塔面板被攻破 = 整个服务器没了，这个风险**比本系统大得多**：

- 面板端口**别用默认的 8888**，改成随机高位端口
- 开启面板的**二次验证**
- 面板设置里**限制访问 IP**（只有你们几个人用的话）
- 面板密码用强密码，别和别处重复

### 方式 B：Linux + Docker

```bash
cd roster
docker compose up -d --build
docker compose logs -f          # 第一次会提示你还没有管理账号

docker compose exec app python app.py --create-admin admin 你的强密码
```

> `docker-compose.yml` 里的 `ARA_ADMIN_PASSWORD` 默认是**注释掉的**，这是故意的：
> 宁可让你手动建一次账号，也不想给一个「照着文档复制就能直接上线」的默认弱口令。
> 嫌麻烦就把那两行 `#` 去掉填上密码，重启即可。

要绑域名对外访问，用 Nginx / Caddy 反代并配 HTTPS：

```nginx
server {
    listen 443 ssl http2;
    server_name roster.example.com;

    ssl_certificate     /etc/letsencrypt/live/roster.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/roster.example.com/privkey.pem;

    client_max_body_size 16m;      # 上传问卷星文件用

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

放在反代后面时，记得给容器加两个环境变量，否则登录限流会把所有访客当成同一个人：

```yaml
      ARA_TRUST_PROXY: "1"
      ARA_COOKIE_SECURE: "1"     # 只有真的上了 HTTPS 才开
```

### 方式 C：Linux + systemd

```bash
python3 -m venv /opt/ara/venv
/opt/ara/venv/bin/pip install -r requirements.txt
/opt/ara/venv/bin/python app.py --create-admin admin 你的强密码
```

`/etc/systemd/system/ara-roster.service`：

```ini
[Unit]
Description=ARA Roster
After=network.target

[Service]
WorkingDirectory=/opt/ara/roster
Environment=ARA_DATA_DIR=/var/lib/ara-roster
Environment=ARA_TZ_OFFSET=8
ExecStart=/opt/ara/venv/bin/gunicorn -w 1 -k gthread --threads 8 -b 127.0.0.1:8000 app:app
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/lib/ara-roster && sudo chown www-data /var/lib/ara-roster
sudo systemctl enable --now ara-roster
```

> 为什么是 `-w 1 -k gthread` 而不是多进程：SQLite 下单进程多线程最省心，没有跨进程写锁竞争。
> 300 人规模的手动录入，这个配置性能过剩。
> Windows 上装不到 gunicorn 是正常的 —— `requirements.txt` 用环境标记 `sys_platform` 把它排除了。

**最稳的访问方式**：不加公网域名，运营们走 SSH 隧道（同 Windows 的第 4 步）。攻击面几乎为零，代价是每次要先连隧道。

---

## 三、日常怎么用

### 1. 收人：问卷星 → 导入

- 问卷星免费版没有 API，走「分析 & 下载 → 下载答卷 → Excel」。
- 进 **导入** 页上传，系统会：
  - 自动识别「1、你的昵称/常用称呼是？」这样的题目列（关键词表在 `importer.py`）；
  - 把「我是萌新」「参加过几次」「大佬」这类自由文本归一成 新手 / 老手 / 大佬；
  - 把「摸鱼」「冲击」「带新」归一成意向；
  - 把「密码、数学」「编程5;搜索4」解析成技能标签（数字是自评 1–5）；
  - 把「2004」这样的出生年份换算成年龄；
  - 按 **手机 > QQ > Discord > 邮箱 > 昵称** 判断是否同一个人：已存在就更新，不存在才新建。
- 预览页可以逐字段改对应关系，**确认后才写库**。同一份文件重复上传只会更新，不会产生重复成员。

### 2. 建队：老手开队，运营登记

老手自己拉班底（这步别用系统替代，队伍是靠人的关系组的），运营在 **队伍** 页把队伍建进来：

- **人数上限**按赛事规则填，报名时系统靠它拦不合规的队伍。
- **新手名额**是这个队愿意带几个新手。**别贪多**：一个老手带超过 3 个新手，通常老手先崩溃。
- **队长**指定后会自动加进队伍并标记角色。
- 队伍状态设为「已锁定」后，分配台不再往它塞人。

### 3. 分配新手：分配台

进 **分配台**，左边是未分配的人，右边是队伍：

- 每个人下面列出最多 3 条系统推荐，**带评分和理由**（意向匹配 / 补上技能空缺 / 队里有老手 / 时长和作息接近）。
- 硬性冲突单独标红：新手名额已满、人数已满、意向不符、队伍要求开麦。
- 手动选队下拉框里，推荐队排在最上面。
- **生成新手分配草案**：一键对所有未分配新手跑一遍贪心分配，出一张表给你核对，确认后才真正执行。算法只考虑人数上限、新手名额、意向和技能，**不考虑任何私人关系**，所以执行前请扫一眼。
- 排不上的人会单独列出来 —— 这就是你要手工处理的补位池。**落单的人最容易流失，优先处理他们。**

### 4. 赛事：报名与合规校验

**赛事** 页把 CCBC、PKU、MITMH 以及自办赛事建好，各自填人数上下限。报名时：

- 人数不在区间内的队伍会被拦住并说明原因；
- 报名成功会**冻结一份当时的名单快照**（防止赛前有人退队导致对不上）；
- 可以一键导出该赛事的报名表 xlsx。

### 5. 导出

| 导出 | 内容 | 能不能外发 |
|---|---|---|
| 成员总表 | 全部档案（含内部备注） | ❌ 内部留档用 |
| 队伍名册 | 按队伍展开的成员清单 | ⚠️ 看情况，给队长核对可以 |
| 未分配名单 | 还没进队伍的人 | ⚠️ 内部用 |
| 赛事报名表 | 队伍 + 昵称 + 联系方式 | ✅ 给赛事方用这个 |

---

## 四、推荐是怎么算的

没有黑箱，规则全在 `matching.py` 一个文件里，你可以直接改。评分构成：

| 因素 | 权重 | 说明 |
|---|---|---|
| 意向匹配 | ±40 | 冲击 / 摸鱼 / 带新 与队伍类型是否一致 |
| 技能互补 | 最多 +30 | 本人的强项（自评 ≥4）正好是队伍没人能扛的方向 |
| 带新资源 | +15 / +8 | 队里有明确愿意带新的老手 / 只有老手 |
| 时间与作息 | ±12 | 可投入时长接近队伍均值、作息一致 |
| 语音 | ±20 | 队伍要求开麦但本人不方便，直接扣到不推荐 |
| 队伍结构 | +10 左右 | 空队、缺老手的队优先补 |
| 年龄段 | 参考 | 只做提示，不参与打分 |

硬性限制（人数上限、新手名额、队伍状态、意向严重冲突）直接进 blockers，**连推荐都不给**，只在界面上说明为什么不行。

**两个刻意的设计**：

1. **系统从不自动决定谁去哪队**，只排序 + 给理由。组队这件事，默契比算法重要。
2. **分数为负的人不进自动草案**。与其硬塞进去让两边都难受，不如丢进补位池让人工处理 —— 落单的人才是留存的胜负手。

---

## 五、数据、备份与安全

### 5.1 备份

所有数据都在 `ARA_DATA_DIR`（默认 `./data`）里，核心是 `roster.db`。备份就是拷这个目录：

```bash
# Linux：每天凌晨 3 点备份，保留 30 天
0 3 * * * cd /opt/ara/roster && tar czf /backup/ara-$(date +\%F).tar.gz data/ && find /backup -name 'ara-*.tar.gz' -mtime +30 -delete
```

Windows 上直接复制整个 `D:\roster\data` 目录即可（服务运行中也能拷，SQLite 开了 WAL）。

**务必演练一次恢复**：把备份解到另一个目录，用 `ARA_DATA_DIR=/tmp/restore python app.py --init-db` 打开看看数据在不在。**没恢复过的备份等于没有备份。**

### 5.2 已经内置的安全措施

| 措施 | 说明 |
|---|---|
| 无注册入口 | 账号只能在服务器上用命令行创建 |
| 密码哈希 | werkzeug 的 scrypt，不存明文 |
| 密码策略 | 至少 8 位，拒绝常见弱密码、纯数字、重复字符 |
| 登录限流 | 同一账号 5 分钟内失败 5 次 → 锁 15 分钟（可配） |
| 防用户名枚举 | 用户不存在时也做一次哈希运算，抹平响应时间差 |
| CSRF | 所有写操作校验令牌 |
| 会话 | HttpOnly + SameSite=Lax，登录时重建会话 |
| 安全响应头 | CSP（禁止内联脚本）、X-Frame-Options、nosniff、no-store |
| 路径校验 | 上传文件的读取被限制在临时目录内，防目录穿越 |
| 审计日志 | 谁在什么时候动了哪条数据，都在「日志」页 |
| 默认只听本机 | 不配就是 `127.0.0.1`，公网连不上 |

**已知的取舍**：CSP 里 `style-src` 放开了 `'unsafe-inline'`，因为模板里用了大量 `style="..."` 属性。`script-src` 是严格的 `'self'`，并且冒烟测试会扫描模板，一旦出现内联 `on*=` 事件处理器就报错 —— 保证这个前提不会悄悄失效。

### 5.3 个人信息与合规

**默认不收集真实姓名和手机号。** 这两项在表单、详情页、导出里**根本不会出现**，除非你显式设置 `ARA_COLLECT_IDENTITY=1`。少收集就是最有效的合规手段（最小必要原则）。

默认收集的是：昵称、QQ、Discord、邮箱、年龄、技能、参赛意向。

- **QQ 号 + 年龄仍然是个人信息**，只是泄漏后的伤害面比「真名 + 手机号」小得多（不容易被拿去办卡、注册、诈骗）。但 QQ 号是实名的，被拖库后可能被拿去社工和骚扰，所以：
  - 导出的「成员总表」不要发给外部赛事，赛事报名用「赛事报名表」；
  - 只给信任的运营开账号；离任的运营记得改密码；
  - 问卷里加一句用途说明（「仅用于协会内部组队，不会外传」），这就是最简版的告知同意。
- **未满 14 岁要单独注意。** 按《个人信息保护法》，不满 14 周岁的个人信息属于**敏感个人信息**，处理前需要取得监护人同意。系统会在仪表盘上提示有多少成员未满 `ARA_MINOR_AGE`（默认 14）岁。如果协会收中学生，问卷里请加上「未满 14 岁需家长同意」的说明。

### 5.4 换密码 / 加运营

```bash
python app.py --create-admin 新同事 强密码       # 加账号
python app.py --reset-password admin 新密码      # 忘密码

# Docker：
docker compose exec app python app.py --reset-password admin 新密码
```

> 所有账号权限相同（没有只读角色）。日志页能看到谁做了什么。

---

## 六、代码结构（给想改代码的人）

### 6.1 一次请求发生了什么

```
浏览器
  │  Cookie: session=...（签名，内含 uid 和 CSRF token）
  ▼
app.py            create_app()：注册蓝图、模板过滤器、安全响应头
  │
  ├─ auth.init_app 注册的 before_request 钩子（每个请求都跑）
  │    ① _load_user   从 session 里取出当前用户放进 g
  │    ② _csrf        POST/PUT/DELETE 必须带 _csrf，否则 400
  ▼
views/*.py        路由。读表单用 views/forms.py 解析，
  │               权限靠 @login_required 装饰器
  ▼
models.py         所有 SQL 都在这。每一层写操作都往 audit_logs 记一笔
  │
  ▼
db.py             SQLite 连接（WAL + busy_timeout），建表与列迁移
  ▼
templates/*.html  Jinja2。base.html 定骨架，_macros.html 放公共组件
```

### 6.2 目录

```
roster/
├── app.py                 入口 + CLI（--create-admin / --seed-demo / --init-db / --check-admin / --production）
├── config.py              所有可调项，都能用环境变量覆盖
├── db.py                  建表、列迁移、会员号生成、审计日志
├── models.py              数据访问层，所有 SQL 都在这里
├── matching.py            推荐与分配草案算法 ← 想让推荐更聪明就改这里
├── importer.py            问卷星文件解析与字段识别 ← 想让识别更准就改这里
├── skills.py              业务字典：经验、意向、队伍类型、技能分类、文本归一化
├── auth.py                登录、密码策略、会话、CSRF、限流辅助
├── throttle.py            登录限流（进程内滑动窗口）
├── seed_demo.py           演示数据
├── views/                 路由
│   ├── auth.py            登录 / 登出 / 改密码
│   ├── dashboard.py       仪表盘 / 日志
│   ├── members.py         成员增删改查
│   ├── teams.py           队伍管理 + 分配台（核心）
│   ├── events.py          赛事与报名
│   ├── data.py            导入 / 导出
│   └── forms.py           表单解析（含技能 0-5 的收集）
├── templates/             Jinja2 模板，中文界面，零外部 CDN 依赖
├── static/                样式与少量 JS
├── tests/smoke_test.py    端到端测试
├── start-windows.bat      Windows 一键启动（双击它）
├── start-windows.ps1      启动脚本本体（UTF-8 BOM，否则 PowerShell 读中文会乱码）
├── Dockerfile / docker-compose.yml / docker-entrypoint.sh   Linux 部署用
├── LICENSE                MIT
├── .gitattributes         强制 shell 脚本用 LF、PowerShell 用 CRLF
├── .github/workflows/     CI：跨系统跑冒烟测试 + 构建镜像
└── data/                  数据库与上传临时文件（不要提交到 git）
```

### 6.3 例子：给成员加一个「所在城市」字段

这是最常见的改动，走一遍就知道这套代码怎么摸了。**六个文件，顺序如下**：

1. **`db.py`** —— 在 `SCHEMA` 的 members 表里加一列 `city TEXT`，
   同时往 `COLUMN_MIGRATIONS` 里加 `("city", "TEXT")`。
   后者负责给**已经在跑的数据库**补列，不加的话老库会报错。
2. **`models.py`** —— `MEMBER_FIELDS` 里加上 `"city"`。
   文本字段不用进 `INT_FIELDS`（那是给整数型字段做类型转换的）。
3. **`views/forms.py`** —— 把 `"city"` 加进 `MEMBER_TEXT_FIELDS` 列表。
   `parse_member_form()` 会遍历这个列表，自动把它当文本字段收进来，不用另写代码。
4. **`templates/member_form.html`** —— 加一个 `<input name="city">`。
5. **`templates/member_detail.html`** —— 想在详情页显示就加一行 `<tr>`。
6. **`views/data.py`** —— 想导出就在 `export_members()` 的表头和数据行里各加一项。

最后跑 `python tests/smoke_test.py` 确认没坏。

### 6.4 想改的地方

- **加技能分类**：改 `skills.py` 的 `SKILLS`，再补 `_SKILL_KEYWORDS`，全站自动生效。
- **让问卷识别更准**：改 `importer.py` 的 `FIELD_RULES`，把问卷星里的实际题目关键词加进去。
- **调整推荐权重**：改 `matching.py` 的 `evaluate()`。
- **改文案/界面**：`templates/` 全是中文，直接改。
- **改配色**：`static/style.css` 顶部的 `:root` 变量。

### 6.5 环境变量总表

| 变量 | 默认 | 作用 |
|---|---|---|
| `ARA_DATA_DIR` | `./data` | 数据目录（数据库、密钥、上传临时文件） |
| `ARA_DB` | `$ARA_DATA_DIR/roster.db` | 数据库文件路径 |
| `ARA_SECRET_KEY` | 自动生成并存盘 | 会话签名密钥。多副本部署要显式指定 |
| `ARA_HOST` / `ARA_PORT` | `127.0.0.1` / `8000` | 监听地址 |
| `ARA_ORG_NAME` / `ARA_ORG_SHORT` | `CAAR` / `CAAR` | 页面显示名 |
| `ARA_CODE_PREFIX` | `CAAR` | 会员号前缀，如 `CAAR-0001` |
| `ARA_COLLECT_IDENTITY` | `0` | **是否收集真实姓名和手机号** |
| `ARA_MINOR_AGE` | `14` | 未成年人提醒的年龄线 |
| `ARA_TEAM_CAPACITY` | `6` | 新建队伍的默认人数上限 |
| `ARA_NEWBIE_QUOTA` | `2` | 新建队伍的默认新手名额 |
| `ARA_MENTOR_CAPACITY` | `3` | 老手带新人数建议值（表单提示用） |
| `ARA_LOGIN_MAX_ATTEMPTS` | `5` | 登录失败几次触发锁定 |
| `ARA_LOGIN_WINDOW` | `300` | 失败计数的窗口（秒） |
| `ARA_LOGIN_LOCKOUT` | `900` | 锁定时长（秒） |
| `ARA_COOKIE_SECURE` | `0` | 会话 Cookie 只走 HTTPS（有证书才开） |
| `ARA_TRUST_PROXY` | `0` | 信任 `X-Forwarded-For`（放在反代后面才开） |
| `ARA_SESSION_DAYS` | `14` | 会话有效期（天） |
| `ARA_MAX_UPLOAD` | `8388608` | 上传文件大小上限（字节） |
| `ARA_TZ_OFFSET` | `8` | 页面上显示时间用的时区偏移 |
| `ARA_ADMIN_USER` / `ARA_ADMIN_PASSWORD` | 空 | Docker 首次启动时自动建账号用 |
| `ARA_DEBUG` | `0` | 设成 `1` 打开模板热重载（只在开发时用） |

---

## 七、测试

```bash
python tests/smoke_test.py
```

不需要 pytest，也不碰你的正式数据 —— 它会自己开一个临时目录当数据目录。当前 **73 项全部通过**，覆盖：

- 鉴权：未登录跳转、错误密码、成功登录、401/429 状态码
- 问卷星文件：字段自动识别、自由文本归一化、出生年份换算、去重、重复导入
- 业务：建队 → 分配 → 推荐理由 → 自动草案生成与执行 → 赛事报名人数校验
- 导出：5 种 xlsx 都能生成，且默认不含真名/手机号列
- 页面：12 个页面全部 200
- 安全：CSRF 拦截、目录穿越拦截、安全响应头、模板无内联事件、登录限流、密码策略

CI（`.github/workflows/ci.yml`）会在 push / PR 时自动跑，矩阵是 Ubuntu 和 Windows × Python 3.11/3.12，另外还会构建一次 Docker 镜像确认部署路径没坏。

---

## 八、遇到问题先看这里

**`python` 打开的是应用商店，或者提示「不是内部或外部命令」**
Python 没装，或者装的时候没勾 "Add python.exe to PATH"。重装一遍并勾上那**最下面一个**复选框。装完关掉命令行窗口重新开一个。

**`pip install` 卡住或超时**
换国内镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

**启动时报 `Address already in use` / 端口被占用**
换端口：`python app.py --port 8001`（Windows 上启动脚本支持 `set ARA_PORT=8001` 后再双击）。

**登录时提示「用户名或密码不对」，但我确定没输错**
大概率是还没建账号。执行 `python app.py --check-admin`，退出码非 0 就说明没有账号，跑 `python app.py --create-admin admin 你的强密码`。忘了密码用 `--reset-password`。

**提示「尝试次数太多」，被锁了**
这是登录限流。等 15 分钟，或者重启一下服务（限流状态在内存里，重启即清空）。

**SSH 隧道连上了，但浏览器打不开**
确认隧道窗口还开着；确认地址是 `http://127.0.0.1:8000` 而不是服务器的 IP；确认服务那边窗口没关。

**上传 Excel 后一条记录都没解析出来**
检查预览页里「昵称」那一列有没有选对。至少要指定昵称列，否则没法建档案。

**改完代码没生效**
Flask 默认不热重载。重启服务。开发时可以设 `ARA_DEBUG=1`。

**数据想清空重来**
停掉服务，删掉 `data/roster.db` 及其 `-wal` / `-shm` 文件，重启。

---

## 九、开源与二次开发

**可以开源，代码里没有任何协会私有的东西**：组织名、会员号前缀、是否收集真名都是环境变量，别人拿去改个名字就能用。许可证是 MIT，想换 Apache-2.0 或 AGPL 改 `LICENSE` 一个文件就行。

依赖许可全部宽松（Flask / Werkzeug / Jinja2 是 BSD-3，openpyxl / waitress / gunicorn 是 MIT），和 MIT 不冲突。

### 发布前自查

- [ ] **`data/` 目录绝对不要提交。** 里面有 `roster.db`（全部真实成员信息）、`secret_key`（会话密钥）、以及上传过的问卷星原始文件。`.gitignore` 已经挡了，别用 `git add -f` 绕过。
- [ ] **`docker-compose.yml` 里不要留真密码。** 默认是注释状态，如果你本地填过，提交前改回去。
- [ ] 确认没有把真实名单放进 `seed_demo.py`（里面的名字全是编的）。
- [ ] 加一张截图（放在本文最上面）。
- [ ] 想清楚要不要挂协会的名字。挂着的好处是它本身就是协会的招牌和招人入口。

### ⚠️ 如果推上去了才发现推了真实数据

**删文件再提交是没用的，git 历史里永远还在。** 要么用 `git filter-repo` 重写历史（之后必须强推，并且所有克隆过的人都要重新克隆），要么删库重建、从干净的初始提交开始。**最省事的做法是：第一次 commit 之前就检查干净。**

### 仓库初始化

```bash
cd roster
git init -b main
git add .
git status              # 确认列表里没有 data/、没有 .venv/
git commit -m "feat: 协会会员与队伍管理系统"
git remote add origin git@github.com:你的用户名/ara-roster.git
git push -u origin main
```

### 顺手能变成「通用工具」的地方

这套代码不只能给推理协会用 —— 任何「收集意向 → 分队 / 分组 → 按名额校验」的场景都适配（社团招新分组、竞赛组队、活动分房）。真想让别人复用，改两处就够：

1. `skills.py` 的技能分类换成对应领域；
2. `importer.py` 的 `FIELD_RULES` 关键词换成对应问卷的问法。

这两处是刻意抽出来的，就是为了让别人不用读业务代码也能改。

---

## 十、还没做、以后可以加的

- 老手自己登录开队、新手自己申请（现在是运营代录，量不大时反而更快）
- 赛后反馈（「愿意再和这些人同队吗」）反哺下一轮推荐
- 与 Discord 机器人打通：分配入队后自动给角色、自动拉进频道
- 邮件 / 群通知：报名截止、队伍变动
- 内训赛：练习题、题解库、新人成长路径
- 只读角色（现在是所有账号权限相同）

---

## 常见设计问题

**Q：为什么不做成会员自助注册？**
A：协会只有 200–300 人，运营代录 + 问卷星收集反而更可控，也避免了一整套账号体系的维护成本。等真有需求再加。

**Q：能不能直接连问卷星自动同步？**
A：免费版没有 API。而且双向同步是痛苦的根源 —— 问卷星只当入口，进系统后一律以系统为准。

**Q：几百人 SQLite 撑得住吗？**
A：完全够。写入都是运营手动触发的低频操作，读写走 WAL 很轻松。真到几千人且高并发再换 Postgres，`models.py` 是唯一要改的地方。

**Q：删掉一个成员会怎样？**
A：会连带删除他的队伍履历和报名记录，队友不受影响。所以删除有二次确认。想保留历史可以把状态改成「退役」而不是删除。

**Q：为什么推荐算法是贪心，不是最优解？**
A：因为这里是"给人提建议"，不是"替人做决定"。贪心 + 可解释的理由，比一个说不出所以然的最优解更有用。
