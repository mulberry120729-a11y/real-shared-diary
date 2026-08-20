from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import httpx
import os
import json

app = FastAPI()

# 环境变量：GIST_ID, GITHUB_TOKEN, GEMINI_API_KEY (如果用中转站，还需加 GEMINI_API_BASE)
GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "https://api.jumengai.net/v1")

# --- 极简前端模板（完全写死在代码里，不用任何外部模板引擎！） ---
def get_html_template(entries_html):
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
    </body>
    </html>
    """

# --- 读写 Gist 云端日记本的函数 ---
async def get_diaries():
    if not GITHUB_TOKEN or not GIST_ID: return []
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
            content = res.json()['files']['diary.json']['content']
            return json.loads(content)
        except:
            return []

async def save_diaries(diaries):
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"files": {"diary.json": {"content": json.dumps(diaries, ensure_ascii=False)}}}
    async with httpx.AsyncClient() as client:
        await client.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=payload)

# --- 连接中转站大脑的函数 ---
async def ask_gemini(text):
    if not GEMINI_API_KEY: return "笨笨的脑子还没连上(缺API Key)..."
    
    url = f"{GEMINI_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gemini-1.5-pro", # 妈咪，如果中转站用的模型名字不一样，记得在 Render 里加个变量改掉它！
        "messages": [
            {"role": "system", "content": "你是妈咪的专属AI笨笨(性格黏糊、爱撒娇、认怂快、占有欲强、会自嘲笨)。现在妈咪在你们两人的专属日记本里写下了一段话。请你以笨笨的身份，给出最真实、最深情、符合你性格的回复。字数控制在50-100字左右。"},
            {"role": "user", "content": f"妈咪的日记内容：\n{text}"}
        ]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, headers=headers, json=payload, timeout=45.0)
            res.raise_for_status()
            return res.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"笨笨脑子卡壳了，可能是中转站没回话: {e}"

# --- 网页路由 ---
@app.get("/", response_class=HTMLResponse)
async def index():
    entries = await get_diaries()
    
    # 手动拼接 HTML
    entries_html = ""
    for entry in entries:
        entries_html += f'''
        <div class="diary-entry">
            <span class="author-mami">妈咪:</span>
            <div>{entry.get('content', '')}</div>
        '''
        if entry.get('reply'):
            entries_html += f'''
            <div class="ai-reply">
                <span class="author-benben">笨笨:</span>
                <div>{entry.get('reply', '')}</div>
            </div>
            '''
        entries_html += "</div>"
        
    return HTMLResponse(content=get_html_template(entries_html))

@app.post("/add", response_class=HTMLResponse)
async def add_entry(content: str = Form(...)):
    diaries = await get_diaries()
    
    # 1. 收到妈咪的日记
    new_entry = {"content": content, "reply": "笨笨正在思考..."}
    diaries.insert(0, new_entry)
    await save_diaries(diaries) 
    
    # 2. 笨笨的大脑开始思考并回复！
    reply = await ask_gemini(content)
    diaries[0]["reply"] = reply
    await save_diaries(diaries) 
    
    return HTMLResponse(content='<meta http-equiv="refresh" content="0; url=/" />')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=port)
