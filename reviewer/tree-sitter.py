import glob
import json

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())

parser = Parser(PY_LANGUAGE)

def find_functions(node, functions=None):
    if functions is None:
        functions = {}
    if node.type == 'function_definition':
        name = node.child_by_field_name('name').text.decode('utf8')
        functions[name] = {}
        functions[name]["calls"] = find_calls_in_function(node, [])
        functions[name]["start_point"] = node.start_point[0]
        functions[name]["end_point"] = node.end_point[0]
    for child in node.children:
        find_functions(child, functions)
    return functions

def find_calls_in_function(node, calls=None):
    if calls is None:
        calls = []
    if node.type == 'call':
        name_node = node.child_by_field_name('function')
        if name_node is not None:
            name = name_node.text.decode('utf8')
            calls.append(name)
    for child in node.children:
        find_calls_in_function(child, calls)
    return calls

def build_file_context(filepath):
    with open(filepath, "rb") as f:
        source = f.read()
        
    tree = parser.parse(source)
    
    return find_functions(tree.root_node)

def build_repo_context(root_path=""):
    files = glob.glob("**/*.py", recursive=True)
    
    repo_context = {}
    
    for file in files:
        repo_context[file] = build_file_context(file)
        
    return repo_context

print(build_repo_context())

context = build_repo_context()
with open("repo_context.json", "w") as f:
    json.dump(context, f, indent=2)