import os
import sys
import json
import time
import sqlite3
import asyncio
import base64
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
import iroh

# ==================== 配置与全局状态 ====================
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
DOWNLOAD_DIR = Path("./downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = f"chat_history_{PORT}.db"
ALPN = b"iroh-p2p-chat/1.0"

app = FastAPI()
iroh_endpoint = None
active_connections: List[WebSocket] = []
active_peer_conns = {}  # peer_id -> connection

# ==================== SQLite 数据库 ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            peer_id TEXT,
            direction TEXT, -- 'in' or 'out'
            msg_type TEXT,  -- 'text' or 'file'
            content TEXT,
            filename TEXT,
            filesize INTEGER,
            created_at REAL
        )
    """)
    conn.commit()
    conn.close()

def save_message(peer_id, direction, msg_type, content="", filename=None, filesize=0):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages (peer_id, direction, msg_type, content, filename, filesize, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (peer_id, direction, msg_type, content, filename, filesize, time.time()))
    conn.commit()
    conn.close()

def load_history(peer_id=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if peer_id:
        cur.execute("SELECT peer_id, direction, msg_type, content, filename, filesize, created_at FROM messages WHERE peer_id = ? ORDER BY id ASC", (peer_id,))
    else:
        cur.execute("SELECT peer_id, direction, msg_type, content, filename, filesize, created_at FROM messages ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [{
        "peer_id": r[0], "direction": r[1], "msg_type": r[2], 
        "content": r[3], "filename": r[4], "filesize": r[5], "created_at": r[6]
    } for r in rows]

# ==================== 前端广播 ====================
async def notify_web(data: dict):
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            pass

# ==================== Iroh P2P 核心网络 ====================
async def handle_incoming_stream(recv_stream, send_stream):
    try:
        # 读取 4 字节头长度
        header_len_bytes = await recv_stream.read_exact(4)
        header_len = int.from_bytes(header_len_bytes, "big")
        header_bytes = await recv_stream.read_exact(header_len)
        header = json.loads(header_bytes.decode())

        peer_id = header.get("sender_id", "Unknown")
        msg_type = header.get("type")

        if msg_type == "text":
            text = header.get("content", "")
            save_message(peer_id, "in", "text", content=text)
            await notify_web({"event": "message", "peer_id": peer_id, "direction": "in", "msg_type": "text", "content": text})

        elif msg_type == "file":
            filename = header.get("filename")
            filesize = header.get("filesize")
            save_path = DOWNLOAD_DIR / filename

            # 接收二进制文件流
            with open(save_path, "wb") as f:
                remaining = filesize
                while remaining > 0:
                    chunk_size = min(64 * 1024, remaining)
                    chunk = await recv_stream.read_exact(chunk_size)
                    f.write(chunk)
                    remaining -= len(chunk)

            save_message(peer_id, "in", "file", filename=filename, filesize=filesize)
            await notify_web({
                "event": "message", "peer_id": peer_id, "direction": "in", 
                "msg_type": "file", "filename": filename, "filesize": filesize
            })

    except Exception as e:
        print(f"[Iroh] 接收数据异常: {e}")

async def iroh_accept_loop():
    global iroh_endpoint
    while True:
        try:
            conn = await iroh_endpoint.accept()
            if conn:
                asyncio.create_task(accept_streams(conn))
        except Exception as e:
            await asyncio.sleep(1)

async def accept_streams(conn):
    try:
        while True:
            bi = await conn.accept_bi()
            asyncio.create_task(handle_incoming_stream(bi.recv(), bi.send()))
    except Exception:
        pass

async def send_to_peer(peer_addr_str: str, payload_header: dict, file_bytes: bytes = None):
    global iroh_endpoint
    # 解析远端地址
    addr = iroh.EndpointAddr.from_string(peer_addr_str)
    conn = await iroh_endpoint.connect(addr, ALPN)
    bi = await conn.open_bi()
    send_stream = bi.send()

    # 打包发送
    header_json = json.dumps(payload_header).encode()
    await send_stream.write_all(len(header_json).to_bytes(4, "big"))
    await send_stream.write_all(header_json)

    if file_bytes:
        await send_stream.write_all(file_bytes)

    await send_stream.finish()

# ==================== Web 路由与接口 ====================
@app.on_event("startup")
async def startup():
    global iroh_endpoint
    init_db()
    # 注册 asyncio loop 给 iroh-ffi
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())
    
    # 启动 Iroh 节点
    options = iroh.EndpointOptions(preset=iroh.preset_n0(), alpns=[ALPN])
    iroh_endpoint = await iroh.Endpoint.bind(options)
    asyncio.create_task(iroh_accept_loop())
    print(f"\n✅ Iroh 节点已就绪！本机 Endpoint Addr 凭证:\n{iroh_endpoint.addr()}\n")

@app.get("/api/info")
async def get_info():
    addr = str(iroh_endpoint.addr())
    return {"addr": addr, "downloads_dir": str(DOWNLOAD_DIR.resolve())}

@app.get("/api/history")
async def get_history(peer_id: str = None):
    return load_history(peer_id)

@app.post("/api/send_text")
async def api_send_text(req: dict):
    peer_addr = req.get("peer_addr")
    content = req.get("content")
    header = {
        "type": "text",
        "sender_id": str(iroh_endpoint.id()),
        "content": content
    }
    await send_to_peer(peer_addr, header)
    save_message(peer_addr, "out", "text", content=content)
    return {"status": "ok"}

@app.post("/api/send_file")
async def api_send_file(peer_addr: str = "", file: UploadFile = File(...)):
    content = await file.read()
    header = {
        "type": "file",
        "sender_id": str(iroh_endpoint.id()),
        "filename": file.filename,
        "filesize": len(content)
    }
    await send_to_peer(peer_addr, header, file_bytes=content)
    save_message(peer_addr, "out", "file", filename=file.filename, filesize=len(content))
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

# ==================== 前端 UI ====================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Iroh P2P 互联与直传平台</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; display: flex; justify-content: center; height: 100vh; padding: 20px; }
        .container { width: 900px; background: #1e293b; border-radius: 12px; display: flex; flex-direction: column; box-shadow: 0 8px 30px rgba(0,0,0,0.5); overflow: hidden; }
        .header { padding: 16px; background: #0f172a; border-bottom: 1px solid #334155; }
        .badge { display: inline-block; padding: 3px 8px; font-size: 12px; border-radius: 4px; background: #3b82f6; color: #fff; font-family: monospace; cursor: pointer; }
        .peer-bar { display: flex; gap: 10px; padding: 12px 16px; background: #1e293b; border-bottom: 1px solid #334155; }
        input[type="text"] { flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; }
        button { padding: 8px 16px; border-radius: 6px; border: none; background: #2563eb; color: #fff; font-weight: bold; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        .chat-box { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        .msg { max-width: 70%; padding: 10px 14px; border-radius: 8px; font-size: 14px; line-height: 1.5; word-break: break-all; }
        .msg.in { align-self: flex-start; background: #334155; color: #f8fafc; }
        .msg.out { align-self: flex-end; background: #2563eb; color: #fff; }
        .footer { padding: 12px 16px; background: #0f172a; border-top: 1px solid #334155; display: flex; gap: 10px; align-items: center; }
        .file-btn { background: #475569; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div style="font-size: 16px; font-weight: bold; margin-bottom: 6px;">🌐 Iroh P2P 节点</div>
        <div style="font-size: 12px; color: #94a3b8;">
            本机凭证 (点击复制): <span class="badge" id="myAddr" onclick="copyAddr()">加载中...</span>
        </div>
    </div>
    <div class="peer-bar">
        <input type="text" id="targetAddr" placeholder="输入对方电脑的 Iroh Endpoint 凭证...">
    </div>
    <div class="chat-box" id="chatBox"></div>
    <div class="footer">
        <input type="text" id="msgInput" placeholder="输入消息..." onkeydown="if(event.key==='Enter') sendMsg()">
        <button onclick="sendMsg()">发送文本</button>
        <button class="file-btn" onclick="document.getElementById('fileInput').click()">发送文件</button>
        <input type="file" id="fileInput" style="display:none" onchange="sendFile(this)">
    </div>
</div>
<script>
    let myAddrStr = "";
    async function init() {
        const res = await fetch("/api/info");
        const data = await res.json();
        myAddrStr = data.addr;
        document.getElementById("myAddr").innerText = myAddrStr;
        loadHistory();
        connectWS();
    }
    function copyAddr() {
        navigator.clipboard.writeText(myAddrStr);
        alert("已复制本机 Iroh 凭证！");
    }
    async function loadHistory() {
        const res = await fetch("/api/history");
        const list = await res.json();
        const box = document.getElementById("chatBox");
        box.innerHTML = "";
        list.forEach(renderMsg);
    }
    function renderMsg(m) {
        const box = document.getElementById("chatBox");
        const div = document.createElement("div");
        div.className = `msg ${m.direction}`;
        if (m.msg_type === "text") {
            div.innerText = m.content;
        } else {
            div.innerHTML = `📁 <b>文件:</b> ${m.filename} <br><small>大小: ${(m.filesize/1024).toFixed(1)} KB</small>`;
        }
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    }
    function connectWS() {
        const ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.event === "message") renderMsg(data);
        };
    }
    async function sendMsg() {
        const input = document.getElementById("msgInput");
        const target = document.getElementById("targetAddr").value.trim();
        const text = input.value.trim();
        if (!target || !text) return alert("请填写目标凭证和消息内容！");
        await fetch("/api/send_text", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({peer_addr: target, content: text})
        });
        renderMsg({direction: "out", msg_type: "text", content: text});
        input.value = "";
    }
    async function sendFile(el) {
        const file = el.files[0];
        const target = document.getElementById("targetAddr").value.trim();
        if (!target || !file) return alert("请填写目标凭证并选择文件！");
        const fd = new FormData();
        fd.append("file", file);
        await fetch(`/api/send_file?peer_addr=${encodeURIComponent(target)}`, { method: "POST", body: fd });
        renderMsg({direction: "out", msg_type: "file", filename: file.name, filesize: file.size});
        el.value = "";
    }
    init();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML_PAGE)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
