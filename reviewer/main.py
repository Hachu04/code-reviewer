import json
import os
import re

import requests
from openai import OpenAI

repo_full = os.environ.get("GITHUB_REPOSITORY", "hachu04/code-reviewer")
owner, repo = repo_full.split("/")
pr_number = os.environ["PR_NUMBER"]
token = os.environ["GITHUB_TOKEN"]

def get_pr_diff():
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3.diff",
            "X-GitHub-Api-Version" : "2026-03-10"
        }
    )
    response.raise_for_status()
    return response.text

def get_context(diff):
    changed_functions = []
    lines = diff.split('\n')
    
    for line in lines:
        if (line.startswith('+') and not line.startswith('+++')) or \
        (line.startswith('-') and not line.startswith('---')):
            match = re.search(r'^[+-]\s*def\s+([a-zA-Z_]\w*)\s*\(', line)
            if match:
                function = match.group(1)
                changed_functions.append(function)
                
    with open("repo_context.json", "r") as f:
        context = json.load(f)
    
    reverse_index = {}
    
    for filepath, functions in context.items():
        for qualified_name in functions:
            plain_name = qualified_name.split(':')[0]
            if plain_name not in reverse_index:
                reverse_index[plain_name] = []
            reverse_index[plain_name].append(filepath)
            
    function_sources = {}
    
    for function in changed_functions:
        if function not in reverse_index:
            continue
        for filepath in reverse_index[function]:
            # find the qualified key that matches this plain name
            qualified_key = next(
                (k for k in context[filepath] if k.split(':')[0] == function),
                None
            )
            if qualified_key is None:
                continue
            start_line = context[filepath][qualified_key]['start_point']
            end_line = context[filepath][qualified_key]['end_point']
        
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                file_lines = f.readlines()
            
            source = "".join(file_lines[start_line:end_line + 1])
            key = f"{function}:{filepath}"
            function_sources[key] = {
                "file": filepath,
                "calls": context[filepath][qualified_key]["calls"],
                "start_point": start_line,
                "end_point": end_line,
                "source": source
            }
        
    return function_sources

def build_prompt(diff, context):
    context_str = ""
    for key, data in context.items():
        context_str += f"\nFile: {data['file']}\n"
        context_str += f"Function: {key.split(':')[0]}\n"
        context_str += f"Calls: {', '.join(data['calls'])}\n"
        context_str += f"Source:\n{data['source']}\n"
        context_str += "---\n"
    
    prompt = f"""You are a professional code reviewer reviewing a pull request.

Here is the diff:
{diff}

Here is the structural context of functions changed in this PR:
{context_str}

Return a structured list of problems using this exact markdown format for each problem:


---

### 1. Quick problem name
* **Problem Title:** title here
* **Where it Occurred:** file and line if known
* **Brief Description:** description here
* **Possible Solution:** solution here

---

Separate each problem with a blank line and '---'. Use markdown so it renders properly as a GitHub comment."""
    
    return prompt

def call_llm(prompt):
    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    )
    
    response = client.chat.completions.create(
        model=os.environ.get("LLM_MODEL", "gemini-3.6-flash"),
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def post_comment(comment):
    response = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version" : "2026-03-10"
            },
        json={"body": comment}
    )
    response.raise_for_status()

if __name__ == "__main__":
    diff = get_pr_diff()
    context = get_context(diff)
    prompt = build_prompt(diff, context)
    comment = call_llm(prompt)
    post_comment(comment)