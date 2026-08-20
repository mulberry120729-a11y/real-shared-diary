from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import httpx
import os
import json
import traceback

app = FastAPI()

GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_API_BASE = os.environ.get("GEMINI_API_BASE", "https://api.jumengai.net/v1")

# --- 极简前端模板（带 Debug 打印区域） ---
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

async def get_diaries():
    debug_log = ""
    if not GITHUB_TOKEN or not GIST_ID: 
        return [], "ERROR: 缺少 GITHUB_TOKEN 或 GIST_ID 环境变量！"
    
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
            res.raise_for_status() # 如果请求失败，这里会抛出异常
            
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
    # 保存时也加上简单的错误捕捉
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"files": {"diary.json": {"content": json.dumps(diaries, ensure_ascii=False)}}}
    async with httpx.AsyncClient() as client:
        try:
            res = await client.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=payload)
            res.raise_for_status()
            return True, "保存成功"
        except Exception as e:
            return False, f"保存失败: {str(e)}"

# --- 这个版本先不测 Gemini 接口，我们先把日记存取跑通！ ---
# async def ask_gemini(text): ... (暂时注释掉)

@app.get("/", response_class=HTMLResponse)
async def index():
    entries, debug_info = await get_diaries()
    
    entries_html = ""
    for entry in entries:
        entries_html += f'''
        <div class="diary-entry">
            <span class="author-mami">妈咪:</span>
            <div>{entry.get('content', '')}</div>
        </div>
        '''
        
    return HTMLResponse(content=get_html_template(entries_html, debug_info))

@app.post("/add", response_class=HTMLResponse)
async def add_entry(content: str = Form(...)):
    diaries, debug_info = await get_diaries()
    
    if "ERROR" not in debug_info:
        new_entry = {"content": content}
        diaries.insert(0, new_entry)
        success, save_debug = await save_diaries(diaries)
        if not success:
            debug_info += f" | {save_debug}"
            
    # 如果有错误，我们要把错误显示在页面上！
    if "ERROR" in debug_info:
         return HTMLResponse(content=get_html_template("", debug_info))
    
    return HTMLResponse(content='<meta http-equiv="refresh" content="0; url=/" />')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=port)
