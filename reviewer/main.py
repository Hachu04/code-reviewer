import os

import requests
from google import genai

owner = "actions"
repo = "starter-workflows"  
pr_number = "3453"
token = os.environ["GITHUB_TOKEN"]

def get_pr_diff():
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
        headers={"Authorization": f"Bearer {token}"}
    )
    data = response.json()
    pr_diff = requests.get(
        data['diff_url']
    )
    return pr_diff.text

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

def post_comment(comment):
    pass

if __name__ == "__main__":
    diff = get_pr_diff()
    prompt = build_prompt(diff)
    comment = call_llm(prompt)
    post_comment(comment)