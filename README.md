# HoloChat

**HoloChat** 是一款开源的点对点（P2P）聊天与文件传输应用，基于 [iroh](https://github.com/n0-computer/iroh) 构建：消息与文件在设备之间端到端加密直传，无需中心服务器，也无需公网 IP。

跨局域网可通过 UDP 打洞直连；直连失败时自动降级到 DERP 中继转发。

---

## 特性

- **P2P 直连**：节点间加密通信，无账号体系、无消息云备份
- **私聊 + 频道**：邀请制群组、成员同步、房主管理
- **文件传输**：实时进度与速度，支持图片 / 视频 / 音频预览
- **富文本消息**：Markdown、代码高亮、引用回复、拖拽发送
- **在线状态**：心跳探活、直连 / 中继链路指示、RTT 显示
- **消息通知**：系统通知 + 提示音；支持对联系人 / 频道设置**消息免打扰**
- **便携运行**：数据与配置都在项目目录内，可整目录拷贝使用
- **原生窗口**：Windows 下可打包为单文件 exe（WebView2 窗口）

---

## 凭证说明

添加好友时会用到「凭证」。三种常见形式：

| 类型 | 形态 | 用途 |
|------|------|------|
| **Node ID** | 64 位十六进制 | 节点身份（类似账号），**不能单独用来拨号** |
| **完整凭证** | `<node_id> relay=… addrs=[…]` | 含中继与直连地址，**最可靠** |
| **短码** | `iroh1:…` | 紧凑格式（Node ID + 中继），便于分享；中继未就绪时不可用 |

在界面左下角本机卡片中可复制完整凭证或短码，发给对方即可互加。

> 建议：同一局域网或网络环境较好时优先用完整凭证；跨网分享可用短码。

---

## 快速开始

### Windows（推荐）

双击 `run.bat`，或在终端执行：

```bat
run.bat
```

脚本会使用项目内嵌 Python 安装依赖、启动后端与前端开发服务，然后打开浏览器访问应用。

### macOS / Linux / WSL

```bash
chmod +x run.sh
./run.sh
```

### 使用打包版（Windows）

若你从 Release 获取了 `IrohChat.exe`，直接双击运行即可（无需安装 Python）。

启动后：

1. 首次使用可「生成新身份」或「导入已有私钥」（身份决定 Node ID）
2. 复制自己的完整凭证或短码，发给对方
3. 粘贴对方凭证，添加联系人后开始聊天 / 传文件

---

## 从源码运行（开发）

### 环境要求

- Python 3.12+
- Node.js 18+
- 依赖 `iroh`（Python 绑定）

### 后端

```bash
cd backend
pip install -r requirements.txt
python run.py 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

开发模式下前端默认在 `http://localhost:5173`，通过代理访问后端 API。

### 打包 exe（Windows）

```bash
cd frontend && npm run build
# 停止正在运行的 IrohChat.exe，释放端口后：
python -m PyInstaller --noconfirm iroh.spec
```

产物位于 `dist/IrohChat.exe`。

---

## 架构

```
浏览器 / WebView2 窗口 (Vue 3 SPA)
        │  REST /api/*     WebSocket /ws
        ▼
   FastAPI 后端 (uvicorn)
        │
        ├─ SQLite（本地消息、联系人、频道）
        └─ iroh Endpoint ──UDP 打洞 / DERP 中继──► 对端节点
```

应用层协议为自定义轻量格式：`4 字节长度前缀 + JSON 头 [+ 文件二进制]`。

---

## 项目结构

```
HoloChat/
├─ backend/              FastAPI + iroh 后端
│  └─ app/
│     ├─ main.py         REST / WebSocket 路由
│     ├─ iroh_net.py     P2P 节点、收发、探活
│     ├─ store.py        SQLite 持久化
│     └─ paths.py        便携路径（全部相对项目根）
├─ frontend/             Vue 3 + Vite + Tailwind SPA
├─ data/                 运行时数据（不入库）
├─ downloads/            接收文件目录（不入库）
├─ python/               可选：内嵌运行时（不入库）
├─ run.bat / run.sh      一键启动
├─ iroh.spec             PyInstaller 打包配置
└─ main.py               历史单文件版本（仅作参考）
```

---

## 便携与隐私

- 数据库、下载文件、缓存、临时目录均写在项目内，不写入系统盘用户目录
- 身份私钥保存在本地 `data/secret.key`（已被 `.gitignore` 排除，请勿上传）
- 消息与文件不经第三方服务器中转存储（中继仅在打洞失败时做加密转发）
- **请勿**将 `data/`、`downloads/`、`*.key`、聊天数据库提交到公开仓库

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python · FastAPI · uvicorn · iroh · SQLite |
| 前端 | Vue 3 · Vite · Tailwind CSS · Pinia · marked · highlight.js |
| 桌面 | PyInstaller · WebView2（pywebview） |

---

## 常见问题

**两端连不上？**  
确认双方应用已启动，且凭证完整。企业网 / 严格 NAT 下可能依赖中继；界面信号徽章显示 `Relay` 表示正在中继，`Direct` 表示已直连。

**短码复制不了？**  
短码依赖本机中继就绪。稍等片刻，或改用完整凭证。

**换了电脑身份会变吗？**  
会。Node ID 由本地私钥决定；可通过身份导入 / 导出迁移。私钥泄露等同账号泄露，请妥善备份。

---

## 许可

请以仓库中的 LICENSE 文件为准。若尚未添加，使用前请联系作者确认授权方式。

---

## 致谢

- [iroh](https://github.com/n0-computer/iroh) — 高性能 P2P 网络库
- n0 computer 及相关 DERP 中继基础设施
