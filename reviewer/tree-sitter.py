import builtins
import glob
import json
import os

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

BUILTINS = set(dir(builtins))

PY_LANGUAGE = Language(tspython.language())

parser = Parser(PY_LANGUAGE)

def find_functions(node, functions=None):
    if functions is None:
        functions = {}
    if node.type == 'function_definition':
        name_node = node.child_by_field_name('name')
        if name_node is not None:
            name = name_node.text.decode('utf8')
            qualified_name = f"{name}:{node.start_point[0]}"
            functions[qualified_name] = {
                "calls": find_calls_in_function(node),
                "start_point": node.start_point[0],
                "end_point": node.end_point[0]
            }
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
            if "'" not in name and '[' not in name and name not in BUILTINS:
                calls.append(name)
    for child in node.children:
        find_calls_in_function(child, calls)
    return calls

def build_file_context(filepath):
    with open(filepath, "rb") as f:
        source = f.read()
        
    tree = parser.parse(source)

    if tree.root_node.has_error:
        print(f"Warning: syntax errors found in {filepath}, skipping")
        return {}
    
    return find_functions(tree.root_node)

def build_repo_context(root_path=""):
    files = glob.glob(os.path.join(root_path, "**/*.py"), recursive=True)
    
    repo_context = {}
    
    for file in files:
        repo_context[file] = build_file_context(file)
    
    # build set of all known function names
    all_function_names = set()
    for functions in repo_context.values():
        if functions is None:
            continue
        for qualified_name in functions:
            all_function_names.add(qualified_name.split(':')[0])
    
    # filter calls to only keep user-defined functions
    for functions in repo_context.values():
        if functions is None:
            continue
        for data in functions.values():
            data['calls'] = [c for c in data['calls'] if c in all_function_names]
    
    return repo_context

context = build_repo_context()
with open("repo_context.json", "w") as f:
    json.dump(context, f, indent=2)