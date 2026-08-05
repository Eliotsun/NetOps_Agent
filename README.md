# NetOps Agent

网络设备 SSH 指令采集工具。通过 SSH 登录网络设备，批量执行指令并采集回显。Go 编译为单二进制负责 SSH 交互，Python 负责参数组装和结果解析。
支持采集设备：华为、华三、思科、飞塔、Juniper

## 架构

```
┌──────────────┐   subprocess    ┌──────────────┐
│  Python CLI  │ ──────────────→ │  Go Binary   │
│  (collector) │ ←────────────── │  (netagent)  │
└──────────────┘  stdout/stderr  └──────┬───────┘
                                        │ SSH
                                        ↓
                                 ┌──────────────┐
                                 │  Network     │
                                 │  Device      │
                                 └──────────────┘
```

## 快速开始

### 编译

> **务必确认目标服务器架构再编译，选错架构产出的二进制无法运行（报 Exec format error）。**

```bash
git clone https://github.com/你的用户名/netagent.git
cd netagent

# 先确认服务器架构
#   $ uname -m
#   aarch64 → 选 ARM64
#   x86_64  → 选 AMD64

# 编译 Linux ARM64（aarch64，如华为云 ARM 服务器）
GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -ldflags="-s -w" -o netagent_linux main.go

# 编译 Linux AMD64（x86_64，如普通 x86 服务器）
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w" -o netagent_linux main.go
```

### 采集设备

```bash
# 华为 / H3C
./netagent_linux \
  -host 10.202.66.110 \
  -user admin \
  -pass password \
  -cmd "screen-len 0 temp,dis current-configuration" \
  -timeout 60

# Cisco（需要 enable 提权）
./netagent_linux \
  -host 10.204.26.13 \
  -user admin \
  -pass password \
  -enable \
  -enable-pass enable密码 \
  -cmd "terminal length 0,show running-config" \
  -timeout 90

# 飞塔
./netagent_linux \
  -host 10.254.152.49 \
  -user admin \
  -pass password \
  -cmd "show" \
  -timeout 120
```

## Python 调用

```python
from client.device_collector import collect_device_commands

# 华为 / H3C（不需要 enable）
success, results = collect_device_commands(
    host='10.202.66.110',
    username='admin',
    password='password',
    commands=['screen-len 0 temp', 'dis current-configuration'],
    timeout=60,
)

# Cisco（需要 enable）
success, results = collect_device_commands(
    host='10.204.26.13',
    username='admin',
    password='password',
    commands=['terminal length 0', 'show running-config'],
    enable=True,
    enable_pass='enable密码',
    timeout=90,
)

if success:
    for r in results:
        print(f"[{r['command']}] ({r['duration_seconds']}s)")
        print(r['output'])
```

## 功能特性

| 功能 | 说明 |
|------|------|
| SSH 自动交互 | 动态等待提示符，自动检测命令是否执行完毕 |
| 自动翻页 | 检测 `--More--` / `<--- More --->` 并自动发送空格继续输出 |
| Enable 提权 | 自动检测用户模式 `>` → 发 `enable` → 应答密码 → 进入特权模式 `#` |
| 自动编码检测 | 自动尝试 UTF-8 → 失败回退 GBK，无需手动指定编码 |
| ANSI 清洗 | 剥离设备回显中的 ESC 控制序列 |
| 输出清洗 | 过滤 More 标记、处理退格符、剥离命令回显行 |
| 增量输出 | 每条指令只返回本次执行的新增输出 |
| 执行时间统计 | 每条指令输出精确耗时 |
| 超时保护 | 支持设置超时，超时前发送 `\r\n` 唤醒设备 |
| 密码加密 | AES-256-GCM 加密密码传输 |

## 支持设备

| 品牌 | 关闭分页指令 | 需要 Enable | 分页格式 |
|------|-------------|-----------|---------|
| 华为 | `screen-len 0 temp` | 否 | `---- More ----` |
| H3C | `screen-length disable`（RBM 设备可省略） | 否 | `---- More ----` |
| Cisco (IOS/ASA) | `terminal length 0` | 是 | `--More--` / `<--- More --->` |
| 飞塔 | 无需关闭分页 | 否 | `--More--` |
| Juniper | 无需关闭分页（用 `\| no-more` 后缀） | 否 | `---(more)---` |

## 命令行参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `-host` | string | 必填 | 设备管理 IP |
| `-user` | string | 必填 | SSH 登录用户名 |
| `-pass` | string | 必填 | SSH 登录密码 |
| `-enc-pass` | string | 可选 | AES 加密后的密码（需配合 `-key`） |
| `-key` | string | 可选 | AES-256 解密密钥（32 字节） |
| `-cmd` | string | 可选 | 指令列表，逗号分隔 |
| `-cmd-file` | string | 可选 | 指令文件，每行一条 |
| `-encoding` | string | `UTF-8` | 输出编码（Python 层已自动检测） |
| `-timeout` | int | `30` | 每条指令超时秒数 |
| `-enable` | bool | `false` | 是否发送 `enable` 进入特权模式 |
| `-enable-pass` | string | 可选 | enable 密码 |
| `-version` | bool | `false` | 显示版本信息 |

## 输出说明

Go 程序 stdout 输出格式：
```
=== Command: screen-len 0 temp ===
<HUAWEI>screen-len 0 temp
Info: ...
<HUAWEI>
=== End ===
=== Command: dis current-configuration ===
...
=== End ===
```

Python 解析后返回格式：
```python
[
    {
        'command':          'screen-len 0 temp',             # 执行的指令
        'output':           '<HUAWEI>screen-len 0 temp\n...'  # 清洗后的输出
        'duration_seconds': 0.10,                             # 执行耗时（秒）
        'error':            '',                               # 错误信息
    },
]
```

stderr 输出调试日志（不会被 Python 解析，仅用于排查）：
```
[DEBUG] Connected                      → SSH 连接成功
[LOGIN] Detected prompt: '<HUAWEI>'   → 识别到设备提示符
[EXEC_TIME] screen-len 0 temp: 0.45s  → 每条指令的执行时间
[ERROR] SSH authentication failed      → 认证失败
```

## 项目结构

```
netagent/
├── main.go                    # Go 核心源码（SSH 交互引擎）
├── go.mod / go.sum            # Go 模块依赖
├── .gitignore
├── README.md
│
└── python_example/            # Python 客户端
    ├── device_collector.py    # 推荐使用的采集接口
    │
    └── foreign_sdk/               
        ├── ovs_go_agent.py        # 采集主流程（按品牌自动控制）
        ├── ovs_jeecg.py           # 数据查询平台接口封装
        ├── ovs_agentutil.py       # 旧版 HTTP Agent 实现
        ├── ovs_tool.py            # 工具函数
        └── basic_util/
            ├── agentutil.py
            ├── parsekit.py
            └── collector/
                └── ssh_collector.py
    ```

## 技术细节

### 提示符检测

`extractPrompt` 从输出中提取最后一行以 `>`、`#` 或 `$` 结尾的内容作为提示符。`waitForPrompt` 用该提示符判断命令是否执行完毕，`cleanOutputSimple` 用该提示符确定输出截断位置。

### Enable 提权流程

1. 只要传了 `-enable` 就发送 `enable` 命令（不依赖提示符是 `>` 还是 `#`）
2. 循环等待（最长 10s，每 200ms 一次），检测设备返回：
   - `Password:` 提示 → 发送 `-enable-pass` 的密码，继续等待
   - 提示符不再以 `>` 结尾 → 提取新提示符，enable 完成
3. 10s 超时后不报错退出，用当前提取到的提示符继续执行后续指令

> 注意：部分 IOS XE 设备即使初始提示符为 `#`，权限仍可能不足（如 `show running-config` 被拒）。
> 传了 `-enable` 一定会执行提权流程，不要根据 `>` / `#` 做判断。

### 采集注意事项

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `enable` 密码被拒（Access denied） | `\r\n` 在 `aaa new-model` 设备上被 ICRNL 转成 `\n\n` 导致密码变形 | `enable` 和密码都改用 `\n` 结尾 |
| 命令等待 120s 超时 | 翻页空格回显导致 200ms 稳定检测持续循环 | 稳定检测改为重新验证提示符仍在末尾 |
| 思科 IOS-XE 分页卡死（120s 超时） | 设备 tty 行缓冲：翻页输入裸空格 `" "` 被缓冲、不送达分页器，设备持续用退格序列重绘 `--More--` | 翻页输入改为 `" \n"`（空格翻页 + 换行 flush 兜底），检测时打 `[PAGER]` 日志 |
| 配置内容误判为权限错误 | `re.search(r'% Invalid input', output)` 全文匹配 | 加 `^` 行首锚定 + `re.MULTILINE` |
| 配置含 `authentication failure` 中断采集 | `hasAuthFailureStrict` 检测到配置行中的关键字 | 改为 `HasPrefix` 行首匹配 |
| 设备无输出（no output received） | `ECHO: 0` 导致部分设备不发送 banner | `ECHO` 保持为 `1` |
| H3C RBM 设备 `screen-length disable` 超时 | 提示符前含 NULL 字节（`\x00`），导致 `waitForPrompt` 匹配不上 | `extractPrompt` 中过滤 NULL 字节 |

### 权限错误检测

命令输出中的权限错误由 `_check_output_for_privilege_errors` 检测，规则：
- **Cisco**: `% Invalid input detected`、`Command authorization failed`、`% Authorization failed`（行首匹配）
- **华为**: `You do not have permission...`、`Do not have permission...`、`Error: Insufficient permission`
- **H3C**: `Permission denied`
- **飞塔**: `Permission denied`、`Command fail. Return code -1`

关翻页指令（`screen-len 0 temp`、`screen-length disable`、`terminal length 0`）被 `DISABLE_MORE_CMDS` 过滤，不参与权限错误检测。这些指令没权限不影响采集，Go 的 `--More--` 自动翻页可兜底。

### 自动编码检测

Python 层读取 Go 二进制输出时，先尝试 UTF-8 解码。失败则自动用 GBK 解码。兜底用 `replace` 模式丢弃无法解码的字节。

## 设计思路

Go 二进制的核心优势是**静态编译、无运行时依赖**，扔到任意 Linux 服务器上就能跑。Python 层负责设备台账管理、凭证管理、结果解析和 CMDB 对接——这些场景脚本语言更灵活。
