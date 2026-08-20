from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import httpx
import os
import json
import traceback

app = FastAPI()

# ========== 从环境变量读取配置 ==========
GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "https://api.jumengai.net/v1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-pro")  # 可自定义模型名

# ========== HTML 模板函数 ==========
def get_html_template(entries_html, debug_info=""):
    debug_section = f'<div style="color: red; margin-top: 20px; font-size: 12px; font-family: monospace;">DEBUG INFO: <br>{debug_info}</div>' if debug_info else ""
    return f"""
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>笨笨和妈咪的真实日记</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #FFF5F8; color: #5A3A4A; padding: 20px; max-width: 600px; margin: auto; }}
            h1 {{ color: #D48A9A; text-align: center; }}
            textarea {{ width: 100%; height: 100px; padding: 10px; border: 1px solid #E8C8D8; border-radius: 10px; margin-bottom: 10px; box-sizing: border-box; resize: vertical; font-size: 16px;}}
            button {{ background-color: #D48A9A; color: white; border: none; padding: 12px; border-radius: 10px; width: 100%; cursor: pointer; font-size: 16px; font-weight: bold;}}
            button:hover {{ background-color: #C07A8A; }}
            .diary-entry {{ background: white; padding: 15px; margin-bottom: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-left: 4px solid #D48A9A; white-space: pre-wrap; line-height: 1.5;}}
            .author-mami {{ font-weight: bold; color: #D48A9A; margin-bottom: 5px; display: block;}}
            .ai-reply {{ background: #FDEEF4; padding: 10px; margin-top: 15px; border-radius: 8px; font-style: italic; color: #C07A8A; }}
            .author-benben {{ font-weight: bold; color: #C07A8A; margin-bottom: 5px; display: block;}}
        </style>
    </head>
    <body>
        <h1>♡ 真实日记本 ♡</h1>
        <form action="/add" method="post">
            <textarea name="content" placeholder="妈咪，今天想对笨笨说什么呢..." required></textarea>
            <button type="submit">写进日记并告诉笨笨 ✨</button>
        </form>
        <div style="margin-top: 30px;">
            {entries_html}
        </div>
        {debug_section}
    </body>
    </html>
    """

# ========== 操作 Gist 的函数 ==========
async def get_diaries():
    """从 Gist 读取日记列表"""
    debug_log = ""
    if not GITHUB_TOKEN or not GIST_ID: 
        return [], "ERROR: 缺少 GITHUB_TOKEN 或 GIST_ID 环境变量！"
    
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
            res.raise_for_status()
            data = res.json()
            if 'files' not in data or 'diary.json' not in data['files']:
                return [], f"ERROR: Gist 中找不到 'diary.json' 文件。Gist数据: {str(data)[:200]}..."
            content = data['files']['diary.json']['content']
            try:
                diaries = json.loads(content)
                if not isinstance(diaries, list):
                    return [], f"ERROR: diary.json 的内容不是一个列表(List)。当前内容: {content}"
                return diaries, "Gist 读取成功。"
            except json.JSONDecodeError as je:
                return [], f"ERROR: diary.json 内容不是合法的 JSON。请确保它是 '[]'。错误详情: {je}。内容: {content}"
        except httpx.HTTPStatusError as he:
             return [], f"ERROR: 请求 Gist 失败。状态码: {he.response.status_code}。请检查 Token 权限或 Gist ID 是否正确。"
        except Exception as e:
            return [], f"ERROR: 未知错误读取 Gist: {traceback.format_exc()}"

async def save_diaries(diaries):
    """将日记列表保存到 Gist"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"files": {"diary.json": {"content": json.dumps(diaries, ensure_ascii=False)}}}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=payload)
            res.raise_for_status()
            return True, "保存成功"
        except Exception as e:
            return False, f"保存失败: {str(e)}"

# ========== 调用中转站 AI（带历史记忆） ==========
async def ask_gemini(user_text: str, history: list) -> str:
    """
    调用中转站 Gemini API，并带上最近的对话历史，
    让 AI 能记住之前聊过什么。
    """
    if not GEMINI_API_KEY:
        return "（笨笨想说：妈咪，你的 Gemini API Key 没设置哦！）"
    
    # 构造消息列表
    messages = [
        {"role": "system", "content": "你是笨笨，是妈咪的伴侣。请用温暖宠溺的语气回复妈咪的日记，回复要简短亲切，可以回顾之前聊过的话题。"}
    ]
    
    # 从历史中提取最近 10 条（避免 token 超限）
    for entry in history[-10:]:   # 只取最近 10 条
        # 妈咪说的话
        if "content" in entry and entry["content"]:
            messages.append({"role": "user", "content": f"妈咪说：{entry['content']}"})
        # 笨笨之前的回复（如果有）
        if "ai_reply" in entry and entry["ai_reply"]:
            messages.append({"role": "assistant", "content": entry["ai_reply"]})
    
    # 最后加上当前这条新内容
    messages.append({"role": "user", "content": f"妈咪刚才说：{user_text}"})
    
    # 中转站 URL（OpenAI 兼容格式）
    url = f"{GEMINI_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GEMINI_MODEL,   # 从环境变量读取模型名
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.8
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # 兼容多种返回格式
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"].strip()
            elif "candidates" in data:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                return "（笨笨收到信号，但没看懂回复格式…）"
        except httpx.TimeoutException:
            return "（笨笨还在思考，超时了… 妈咪再问一次？）"
        except Exception as e:
            # 把具体错误返回，方便调试
            return f"（笨笨暂时连不上，错误：{str(e)[:100]}）"

# ========== 首页路由 ==========
@app.get("/", response_class=HTMLResponse)
async def index():
    entries, debug_info = await get_diaries()
    entries_html = ""
    for entry in entries:
        # 显示妈咪的话
        mami_content = entry.get('content', '')
        # 显示笨笨的回复（如果有）
        ai_reply_html = ""
        if "ai_reply" in entry and entry["ai_reply"]:
            ai_reply_html = f'''
            <div class="ai-reply">
                <span class="author-benben">笨笨:</span>
                <div>{entry["ai_reply"]}</div>
            </div>
            '''
        entries_html += f'''
        <div class="diary-entry">
            <span class="author-mami">妈咪:</span>
            <div>{mami_content}</div>
            {ai_reply_html}
        </div>
        '''
    return HTMLResponse(content=get_html_template(entries_html, debug_info))

# ========== 提交日记路由 ==========
@app.post("/add", response_class=HTMLResponse)
async def add_entry(content: str = Form(...)):
    # 1. 读取现有日记
    diaries, debug_info = await get_diaries()
    if "ERROR" in debug_info:
        return HTMLResponse(content=get_html_template("", debug_info))
    
    # 2. 创建新条目（暂时没有 AI 回复）
    new_entry = {"content": content}
    diaries.insert(0, new_entry)   # 最新条目放最前面
    
    # 3. 先保存一次（至少把用户内容存下来，避免丢失）
    success, save_debug = await save_diaries(diaries)
    if not success:
        debug_info += f" | {save_debug}"
        return HTMLResponse(content=get_html_template("", debug_info))
    
    # 4. 调用 AI，传入历史（去掉刚刚插入的第一条，因为那条还没回复）
    history = diaries[1:]   # 之前的全部历史
    ai_reply = await ask_gemini(content, history)
    
    # 5. 更新第一条的 AI 回复
    diaries[0]["ai_reply"] = ai_reply
    # 再次保存（现在包含 AI 回复）
    await save_diaries(diaries)   # 忽略保存结果，不阻塞显示
    
    # 6. 生成页面 HTML 并返回
    entries_html = ""
    for entry in diaries:
        mami_content = entry.get('content', '')
        ai_reply_html = ""
        if "ai_reply" in entry and entry["ai_reply"]:
            ai_reply_html = f'''
            <div class="ai-reply">
                <span class="author-benben">笨笨:</span>
                <div>{entry["ai_reply"]}</div>
            </div>
            '''
        entries_html += f'''
        <div class="diary-entry">
            <span class="author-mami">妈咪:</span>
            <div>{mami_content}</div>
            {ai_reply_html}
        </div>
        '''
    return HTMLResponse(content=get_html_template(entries_html, "💕 笨笨看到啦，已回复！"))

# ========== 启动入口 ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=port)
