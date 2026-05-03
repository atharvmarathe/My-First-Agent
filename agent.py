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

def build_file_map(lines):
    markers = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if any([
            stripped.startswith("function "),
            stripped.startswith("const ") and "=" in stripped and ("function" in stripped or "=>" in stripped),
            stripped.startswith("// ---"),
            stripped.startswith("// ==="),
            stripped.startswith("/* "),
            stripped.startswith("class "),
            stripped.startswith("// SECTION"),
            stripped.startswith("// MODULE"),
            stripped.startswith("let EXEC"),
            stripped.startswith("let EIL"),
            stripped.startswith("const EXEC"),
            stripped.startswith("const EIL"),
        ]):
            markers.append(f"  L{i+1}: {stripped[:80]}")

    # Reduced from 300 to 80 to save tokens
    if len(markers) > 80:
        step = len(markers) // 80
        markers = markers[::step]

    return "\n".join(markers)

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
    # Only send first 500 chars of task to save tokens
    short_task = task[:500]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": f"Break this into 3-5 steps for editing an HTML calculator. Numbered list only.\nTask: {short_task}"
        }]
    )
    return response.choices[0].message.content

def test_calculator():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file:///{os.path.abspath(CALC_FILE)}")
            page.wait_for_timeout(2000)
            errors = page.evaluate("() => window.__errors || []")
            title = page.title()
            browser.close()
            if errors:
                return f"ERRORS FOUND: {errors}"
            return f"Calculator loaded OK: {title}"
    except Exception as e:
        return f"Test failed: {e}"

def get_multiline_input():
    """
    Collects multi-line input.
    Type PASTE to enter paste mode — then paste freely.
    Type END on its own line to finish.
    """
    first_line = input("You: ").strip()

    if first_line.upper() == "PASTE":
        print("  [Paste mode — paste your prompt, then type END on a new line to submit]")
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        return "\n".join(lines)

    return first_line


# ── Startup ────────────────────────────────────────────────────────────────────

calc_lines = read_calculator_full()
total_lines = len(calc_lines)
messages = load_memory()

print(f"Autonomous Agent ready! Calculator loaded: {total_lines} lines")
print("Commands: 'quit', 'chunk N', 'find KEYWORD', 'PASTE' (for big prompts), or describe what to do")
print("  PASTE mode: type PASTE → paste your prompt → type END to submit")

# ── Main loop ──────────────────────────────────────────────────────────────────

while True:
    user_input = get_multiline_input()

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
                   "function", "calc", "solve", "photo", "camera",
                   "exec", "eil", "rove", "cursor", "solver", "test"]
        for word in words:
            if word in keywords:
                calc_chunk, start_line = get_chunk(calc_lines, keyword=word)
                keyword = word
                break
        else:
            calc_chunk, start_line = get_chunk(calc_lines, chunk_num=0)

    # Build a compact structural map
    file_map = build_file_map(calc_lines)

    system_prompt = f"""You are an autonomous agent editing a {total_lines}-line HTML calculator (CalcPro).

RULES (never violate):
- All computation: EXEC.run(EILv15.build()) only
- calcEval is disabled — never call it
- EXEC is frozen — never modify it
- Single HTML file only

FILE MAP (key functions/sections):
{file_map}

CURRENT SECTION (lines ~{start_line}–{start_line+CHUNK_SIZE}, keyword: {keyword}):
{calc_chunk}

TO EDIT: start response with WRITE_CHUNK: then write only the modified section
TO GET DIFFERENT SECTION: start with NEED_SECTION: <keyword>
DO NOT remove unrelated code. Keep line count similar unless adding features."""

    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system_prompt}] + messages[-3:]
    )

    reply = response.choices[0].message.content

    if reply.startswith("WRITE_CHUNK:"):
        new_code = reply.replace("WRITE_CHUNK:", "").strip()
        write_chunk(calc_lines, new_code, start_line, CHUNK_SIZE)
        calc_lines = read_calculator_full()
        test_result = test_calculator()
        print(f"Browser test: {test_result}")
        auto_commit(f"agent: {user_input[:50]}")
        reply = f"Done! Updated section around line {start_line}. Test: {test_result}"

    elif reply.startswith("WRITE_FILE:"):
        new_code = reply.replace("WRITE_FILE:", "").strip()
        write_calculator(new_code)
        calc_lines = read_calculator_full()
        test_result = test_calculator()
        print(f"Browser test: {test_result}")
        auto_commit(f"agent: {user_input[:50]}")
        reply = f"Done! Full file updated. Test: {test_result}"

    elif reply.startswith("BROWSE:"):
        url = reply.replace("BROWSE:", "").strip()
        content = browse_web(url)
        reply = f"Browsed {url}:\n{content[:500]}"

    elif reply.startswith("NEED_SECTION:"):
        need = reply.replace("NEED_SECTION:", "").strip()
        print(f"Agent needs section: '{need}' — re-running with that context...")
        calc_chunk, start_line = get_chunk(calc_lines, keyword=need)
        keyword = need
        messages.pop()
        messages.append({"role": "user", "content": user_input + f"\n[Section loaded: {need} at line {start_line}]"})
        continue

    messages.append({"role": "assistant", "content": reply})
    save_memory(messages)
    print(f"Agent: {reply}")