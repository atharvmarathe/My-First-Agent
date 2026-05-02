import os
import json
import subprocess
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MEMORY_FILE = "memory.json"
CALC_FILE = "calcpro-v34.html"
CHUNK_SIZE = 200

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_memory(messages):
    with open(MEMORY_FILE, "w") as f:
        json.dump(messages, f, indent=2)

def read_calculator_full():
    if os.path.exists(CALC_FILE):
        with open(CALC_FILE, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()
    return []

def get_chunk(lines, keyword=None, chunk_num=0):
    if keyword:
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                start = max(0, i - 20)
                end = min(len(lines), i + 180)
                return "".join(lines[start:end]), i
    start = chunk_num * CHUNK_SIZE
    end = min(len(lines), start + CHUNK_SIZE)
    return "".join(lines[start:end]), start

def write_calculator(content):
    with open(CALC_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print("Calculator file updated!")

def write_chunk(lines, new_chunk, start_line, chunk_line_count):
    end_line = min(len(lines), start_line + chunk_line_count)
    new_lines = new_chunk.splitlines(keepends=True)
    lines[start_line:end_line] = new_lines
    with open(CALC_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Updated lines {start_line}-{end_line}!")

def auto_commit(message="agent update"):
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Auto-committed to GitHub!")
    except Exception as e:
        print(f"Commit failed: {e}")

def browse_web(url):
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        return soup.get_text()[:2000]
    except:
        return "Could not fetch URL"

def break_into_steps(task):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"""Break this task into 3-5 small steps for editing an 18000 line HTML calculator file.
Return ONLY a numbered list, nothing else.
Task: {task}"""
        }]
    )
    return response.choices[0].message.content

calc_lines = read_calculator_full()
total_lines = len(calc_lines)
messages = load_memory()

print(f"Autonomous Agent ready! Calculator loaded: {total_lines} lines")
print("Commands: 'quit', 'chunk N', 'find KEYWORD', or just describe what to do")

while True:
    user_input = input("You: ")
    if user_input.lower() == "quit":
        break

    if len(user_input) > 50:
        print("Breaking into steps...")
        steps = break_into_steps(user_input)
        print(f"Plan:\n{steps}\n")
        confirm = input("Proceed? (y/n): ")
        if confirm.lower() != 'y':
            continue

    keyword = None
    chunk_num = 0

    if user_input.lower().startswith("chunk "):
        chunk_num = int(user_input.split()[1])
        calc_chunk, start_line = get_chunk(calc_lines, chunk_num=chunk_num)
    elif user_input.lower().startswith("find "):
        keyword = user_input.split(" ", 1)[1]
        calc_chunk, start_line = get_chunk(calc_lines, keyword=keyword)
    else:
        words = user_input.lower().split()
        keywords = ["copy", "graph", "formula", "step", "api", "button",
                   "modal", "share", "history", "theme", "css", "style",
                   "function", "calc", "solve", "photo", "camera"]
        for word in words:
            if word in keywords:
                calc_chunk, start_line = get_chunk(calc_lines, keyword=word)
                keyword = word
                break
        else:
            calc_chunk, start_line = get_chunk(calc_lines, chunk_num=0)

    system_prompt = f"""You are an autonomous agent editing a {total_lines}-line calculator HTML file.

Current section (lines ~{start_line}-{start_line+CHUNK_SIZE}, keyword: {keyword}):
{calc_chunk}

When modifying code:
- Start response with WRITE_CHUNK: then write the modified section only
- Keep the same number of lines roughly
- Do not rewrite the whole file unless asked

When browsing: start with BROWSE:url
Otherwise respond normally."""

    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system_prompt}] + messages[-10:]
    )

    reply = response.choices[0].message.content

    if reply.startswith("WRITE_CHUNK:"):
        new_code = reply.replace("WRITE_CHUNK:", "").strip()
        write_chunk(calc_lines, new_code, start_line, CHUNK_SIZE)
        calc_lines = read_calculator_full()
        auto_commit(f"agent: {user_input[:50]}")
        reply = f"Done! Updated section around line {start_line} and pushed to GitHub!"

    elif reply.startswith("WRITE_FILE:"):
        new_code = reply.replace("WRITE_FILE:", "").strip()
        write_calculator(new_code)
        calc_lines = read_calculator_full()
        auto_commit(f"agent: {user_input[:50]}")
        reply = "Done! Full file updated and pushed to GitHub!"

    elif reply.startswith("BROWSE:"):
        url = reply.replace("BROWSE:", "").strip()
        content = browse_web(url)
        reply = f"Browsed {url}:\n{content[:500]}"

    messages.append({"role": "assistant", "content": reply})
    save_memory(messages)
    print(f"Agent: {reply}")