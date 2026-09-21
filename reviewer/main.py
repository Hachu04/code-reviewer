import os

import requests
from google import genai

repo_full = os.environ.get("GITHUB_REPOSITORY", "hachu04/code-reviewer")
owner, repo = repo_full.split("/")
pr_number = os.environ.get("GITHUB_REF", "refs/pull/1/merge").split("/")[2]
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
    print(response.text)
    return response.text

def build_prompt(diff):
    prompt = f"You are a professional code reviewer, and your task is to look at pull request diff and check if there is any problem. Here is the diff: {diff}. I want you to return a structured list of problems: problem title, a brief description, where it occured, possible solution"
    return prompt

def call_llm(prompt):
    client = genai.Client()
    
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt
    )
    print(interaction.output_text)
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
    print(response)

if __name__ == "__main__":
    diff = get_pr_diff()
    prompt = build_prompt(diff)
    comment = call_llm(prompt)
    post_comment(comment)