import json
import os

import requests
from google import genai

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
            line = line.lstrip('+-')
            if line.startswith('def'):
                function = line.split('def ')[1].split('(')[0]
                changed_functions.append(function)
                
    with open("repo_context.json", "r") as f:
        context = json.load(f)
    
    reverse_index = {}
    
    for filepath, functions in context.items():
        for function_name in functions:
            reverse_index[function_name] = filepath
    
    function_sources = {}
    
    for function in changed_functions:
        if function not in reverse_index:
            continue
        filepath = reverse_index[function]
        start_line = context[filepath][function]['start_point']
        end_line = context[filepath][function]['end_point']
        
        with open(filepath, "r") as f:
            lines = f.readlines()
        
        source = "".join(lines[start_line:end_line])
        function_sources[function] = {
                "file": filepath,
                "calls": context[filepath][function]["calls"],
                "start_point": start_line,
                "end_point": end_line,
                "source": source
            }
        
    return function_sources

def build_prompt(diff, context):
    prompt = f"You are a professional code reviewer, and your task is to look at pull request diff and check if there is any problem. Here is the diff: {diff}. Here is the context: {context} I want you to return a structured list of problems: problem title, a brief description, where it occured, possible solution"
    return prompt

def call_llm(prompt):
    client = genai.Client()
    
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt
    )
    return interaction.output_text

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