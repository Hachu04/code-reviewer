import json
import os
import re

import requests
from openai import OpenAI

DEPENDENCY_FILES = [
    "requirements.txt",
    "pyproject.toml", 
    "Pipfile",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
]

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
            match = re.search(r'^[+-]\s*(?:async\s+)?def\s+([a-zA-Z_]\w*)\s*\(', line)
            if match:
                function = match.group(1)
                changed_functions.append(function)
                
    with open("repo_context.json", "r") as f:
        context = json.load(f)
        
    reverse_context = build_reverse_context(context)
    reverse_context_plain = {}
    for called_qual, callers in reverse_context.items():
        called_plain = called_qual.split(':')[0]
        reverse_context_plain.setdefault(called_plain, []).extend(callers)
    
    reverse_index = build_reverse_index(context)
            
    function_sources = {}
    file_contents = {}
    
    for function in changed_functions:
        if function not in reverse_index:
            continue
        for filepath in reverse_index[function]:
            data = fetch_function_source(function, filepath, context, file_contents)
            if data is None:
                continue
            
            data["file"] = filepath
            data["called_by"] = reverse_context_plain.get(function, [])
            
            seen = set()
            related = {}
            for related_name in data["calls"] + data["called_by"]:
                if ':' in related_name:
                    plain_name = related_name.split(':')[0]
                elif '.' in related_name:
                    plain_name = related_name.split('.')[0]
                else:
                    plain_name = related_name
                    
                if plain_name not in reverse_index:
                    continue
                    
                for related_filepath in reverse_index[plain_name]:
                    pair = (plain_name, related_filepath)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    
                    related_data = fetch_function_source(plain_name, related_filepath, context, file_contents)
                    if related_data is not None:
                        related[f"{plain_name}:{related_filepath}"] = related_data

            data["related"] = related
            key = f"{function}:{filepath}"
            function_sources[key] = data
        
    return function_sources, context

def build_reverse_index(repo_context):
    reverse_index = {}
        
    for filepath, functions in repo_context.items():
        if functions is None:
            continue
        for qualified_name in functions:
            plain_name = qualified_name.split(':')[0]
            if plain_name not in reverse_index:
                reverse_index[plain_name] = []
            reverse_index[plain_name].append(filepath)
            
    return reverse_index

def build_reverse_context(repo_context):
    reverse = {}
    for functions in repo_context.values():
        if functions is None:
            continue
        for qualified_name, data in functions.items():
            for called in data["calls"]:
                if called not in reverse:
                    reverse[called] = []
                reverse[called].append(qualified_name)
    return reverse

def fetch_function_source(function, filepath, context, file_contents=None):
    if file_contents is None:
        file_contents = {}
        
    qualified_key = next(
        (k for k in context[filepath] if k.split(':')[0] == function),
        None
    )
    if qualified_key is None:
        return None
    
    start_line = context[filepath][qualified_key]['start_point']
    end_line = context[filepath][qualified_key]['end_point']

    if not os.path.exists(filepath):
        return None
    
    if filepath not in file_contents:
        with open(filepath, "r", encoding="utf-8") as f:
            file_contents[filepath] = f.readlines()
    
    source = "".join(file_contents[filepath][start_line:end_line + 1])
    
    return {
        "calls": context[filepath][qualified_key]["calls"],
        "start_point": start_line,
        "end_point": end_line,
        "source": source
    }
    
def get_dependencies():
    result = ""
    for dep_file in DEPENDENCY_FILES:
        if os.path.exists(dep_file):
            with open(dep_file, "r") as f:
                result += f"\n{dep_file}:\n{f.read().strip()}\n"
    return result
    
def format_structural_context(repo_context):
    result = ""
    
    deps = get_dependencies()
    if deps:
        result += f"Dependencies:{deps}\n\n"
    
    for filepath, functions in repo_context.items():
        if functions is None:
            continue
        result += f"\nFile: {filepath} ({len(functions)} functions)\n"
        
        for qualified_name, data in functions.items():
            plain_name = qualified_name.split(':')[0]
            calls = ', '.join(data['calls']) if data['calls'] else 'nothing'
            result += f"  {plain_name} → calls: {calls}\n"
    
    return result

def build_prompt(diff, context, structural_context):
    TOTAL_BUDGET = 16000
    STRUCTURAL_BUDGET = 2000
    CHANGED_BUDGET = 6000
    RELATED_BUDGET = TOTAL_BUDGET - STRUCTURAL_BUDGET - CHANGED_BUDGET - len(diff)

    # section 1: structural overview (always include, truncate if needed)
    structural_str = structural_context[:STRUCTURAL_BUDGET]
    if len(structural_context) > STRUCTURAL_BUDGET:
        structural_str += "\n[Structural overview truncated]"

    # section 2: changed functions source (high priority)
    changed_str = ""
    for key, data in context.items():
        entry = f"\nFile: {data['file']}\n"
        entry += f"Function: {key.split(':')[0]}\n"
        entry += f"Calls: {', '.join(data['calls'])}\n"
        entry += f"Called by: {', '.join(data['called_by'])}\n"
        entry += f"Source:\n{data['source']}\n---\n"
        
        if len(changed_str) + len(entry) > CHANGED_BUDGET:
            changed_str += "\n[Changed functions truncated]"
            break
        changed_str += entry

    # section 3: related functions (lower priority, remaining budget)
    related_str = ""
    for key, data in context.items():
        if not data['related']:
            continue
        for related_key, related_data in data['related'].items():
            entry = f"{related_key.split(':')[0]}:\n{related_data['source']}\n"
            if len(related_str) + len(entry) > RELATED_BUDGET:
                related_str += "\n[Related functions truncated]"
                break
        related_str += entry

    prompt = f"""You are a professional code reviewer reviewing a pull request.

Here is the overall repository structure:
{structural_str}

Here is the diff:
{diff}

Here is the structural context of functions changed in this PR:
{changed_str}

Here are related functions for additional context:
{related_str}

Return a structured list of problems using this exact markdown format for each problem:

---

### 1. Quick problem name
* **Problem Title:** title here
* **Where it Occurred:** file and line if known
* **Brief Description:** description here
* **Possible Solution:** solution here

---

Separate each problem with a blank line and '---'. Use markdown so it renders properly as a GitHub comment."""
    print(prompt)
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
    function_sources, repo_context = get_context(diff)
    structural = format_structural_context(repo_context)
    prompt = build_prompt(diff, function_sources, structural)
    comment = call_llm(prompt)
    post_comment(comment)