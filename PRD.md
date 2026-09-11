# 角色与目标
你是一个资深的分布式系统与全栈架构师。请帮我设计并实现一个基于 Python 与 Iroh（P2P 协议库）的多人群组通信与文件互传系统，前端要求具备现代化的 Discord 风格多栏交互界面。

---

## 核心业务与技术架构要求

### 1. 网络与通信层 (P2P Mesh)
- **底层通信**：使用 Python 官方绑定的 `iroh` 库 (`pip install iroh`)。
- **连接与穿透**：利用 Iroh 的 Endpoint 与公钥机制，支持跨局域网（NAT 打洞直连）和中继降级（DERP），两台及以上处于不同网络的电脑无需公网 IP 即可互通。
- **多人通信模式**：
  - 支持多人群组广播（基于 `iroh-gossip` 话题订阅或点对点网状转发）。
  - 支持 1 对 1 点对点直接流式传输。
- **协议格式**：自定义轻量应用层协议——4 字节大端长度前缀 + JSON 头，文件内容在头之后以二进制流式传输。当前实现的报文 `type` 区分：
  - `text`（文本/Markdown 消息，含 `content` / 可选 `reply_to`）
  - `file`（二进制文件流式传输，头含 `filename`、`filesize`）
  - 节点存活与链路探测由心跳 `presence` 事件承载（路由/拓扑层）

### 2. 身份与数据持久化 (去中心化 Local-First)
- **去中心化身份 (DID)**：每个节点启动时根据自身 Iroh 公钥生成全局唯一 Node ID；该私钥持久化到项目内 `data/secret.key`，使 Node ID 在每次重启后保持稳定（本地优先身份）。
- **自定义配置**：用户可在前端设置自己的“昵称（Nickname）”和“头像（Avatar）”，并向所在群组/好友广播更新。
- **本地存储 (SQLite)**：
  - `peers` 表：记录已发现/已连接的节点公钥、别名/昵称、头像缓存路径、最后活跃时间。
  - `groups` 表：记录加入的群组 Topic 凭证、群名称、群成员列表。
  - `messages` 表：按群组或私聊归档所有消息记录（发送方 Node ID、内容、类型、时间戳、文件元信息）。
  - `files` 表：记录收发文件的本地存储路径、校验值及下载进度。

### 3. 后端服务 (Python / FastAPI)
- 提供本地 REST API 及 WebSocket 供前端调用。
- 处理前端操作到 Iroh 异步网络事件的桥接（iroh Python 官方绑定通过 `asyncio` 可等待的 FFI 方法如 `Endpoint.bind` / `accept_next` / `connect` 与事件循环协作）。
- 接收到对端发送的文件后，自动流式保存至本地 `downloads/` 目录，并按块向前端推送 `file_progress` 进度事件（收/发双向），完成后再广播 `message` 通知。
- 注：iroh v1.1.0 绑定的 `watch_home_relay` 回调在注册时会触发 Rust 端“no reactor running”断言导致进程崩溃，故不启用该推送；home relay 信息改为从 `Endpoint.addr().relay_url()` 主动轮询获取。

### 4. 前端交互与 UI (Discord 风格)
- **视觉风格**：Discord 经典深色主题（Dark Theme: `#313338`, `#2b2d31`, `#1e1f22`），采用 Tailwind CSS 构建现代化毛玻璃/圆角卡片质感。
- **四栏式经典布局**：
  1. **服务器/群组栏 (Server Bar)**：快速切换个人私聊、多人房间/话题，以及添加/加入新房间弹窗。
  2. **频道与联系人栏 (Channel/DM Bar)**：显示当前房间下的文字频道、私聊列表，底部展示本机节点卡片（头像、昵称、Node ID 简码、一键复制凭证）。
  3. **中央聊天与文件流 (Chat View)**：
     - 支持 Markdown、代码高亮。
     - 独立消息卡片：展示每位群成员各自的头像、自定义昵称及发送时间。
     - 文件传输卡片：显示文件图标、大小、下载按钮及图片缩略图实时预览。
     - 全局拖拽（Drag & Drop）文件直接上传发送。
  4. **右侧成员列表 (Member List)**：实时展示当前房间内的在线/离线成员（头像、昵称、P2P 链路状态指示）。

### 5. 便携化部署与系统盘保护规范（重要）
- **项目目录完全自包含（Portable）**：
  - 使用项目内嵌的 Python 运行时（项目根 `python/`，非系统 Python），所有依赖隔离安装在 `python/Lib/site-packages` 内。
  - 运行时产生的数据库（`chat.db`）、文件缓存（`./cache`）、头像、接收下载目录（`./downloads`）均强制使用项目相对路径，严禁往用户主目录（`~`）、系统 `AppData`、`Temp` 或系统盘写入垃圾文件。
  - 提供一键便携启动与初始化脚本（如 `run.bat` / `run.sh`），运行时自动将 `TEMP` / `TMP` 临时目录重定向至项目本地的 `.tmp/`。
- **国内镜像与极速安装**：
  - 依赖安装命令必须默认配置国内高速镜像源（如清华源、阿里源）：
    - Python/Pip 镜像源：`https://pypi.tuna.tsinghua.edu.cn/simple`
    - npm/pnpm 镜像源（如涉及前端独立构建）：`https://registry.npmmirror.com`
  - pip 安装时增加 `--no-cache-dir` 或指定本地项目缓存路径，防止在系统盘 `~/.cache` 堆积无用 Wheel 缓存。

---

## 交付产物要求
1. **项目工程结构**：清晰的便携式目录结构。
2. **便携式一键启动脚本**：
   - 提供 `run.bat` (Windows) 和 `run.sh` (Linux/macOS)，使用项目内嵌运行时 `python/`，配置镜像源安装依赖、临时文件本地化并启动服务。
3. **完整可运行的代码**：包含后端 FastAPI + Iroh 核心通信，以及 Discord 风格的前端界面。
4. **依赖清单 (requirements.txt)** 与轻量测试验证指南。