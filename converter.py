#!/usr/bin/env python3

import os
import re
import json
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

def extract_balanced(text, start):
    level = 0
    for i, char in enumerate(text[start:], start):
        if char == '{':
            level += 1
        elif char == '}':
            level -= 1
            if level == 0:
                return text[start:i+1]
    return ""

def parse_kotlin_dsl(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Extract version
    version_match = re.search(r'version\s*=\s*"([^"]+)"', content)
    version = version_match.group(1) if version_match else "2.1"

    # Extract project block
    project_match = re.search(r'project\s*\{', content)
    if not project_match:
        return None

    start = project_match.end() - 1
    project_block = extract_balanced(content, start)
    if not project_block:
        return None
    project_content = project_block[1:-1]  # remove {}

    # Parse project details
    project = {
        'version': version,
        'project': {}
    }

    # Description
    desc_match = re.search(r'description\s*=\s*"([^"]+)"', project_content)
    if desc_match:
        project['project']['description'] = desc_match.group(1)

    # Build types
    build_types = re.findall(r'buildType\(([^)]+)\)', project_content)
    if build_types:
        project['project']['buildTypes'] = [{'id': bt.strip()} for bt in build_types]

    # Subprojects
    subprojects = re.findall(r'subProject\(([^)]+)\)', project_content)
    if subprojects:
        project['project']['subProjects'] = [{'id': sp.strip()} for sp in subprojects]

    # VCS roots
    vcs_roots = re.findall(r'vcsRoot\(([^)]+)\)', project_content)
    if vcs_roots:
        project['project']['vcsRoots'] = [{'id': vr.strip()} for vr in vcs_roots]

    # Features
    features_match = re.search(r'features\s*\{([^}]+)\}', project_content, re.DOTALL)
    if features_match:
        features_content = features_match.group(1)
        # Simple parsing for githubConnection
        github_match = re.search(r'githubConnection\s*\{([^}]+)\}', features_content, re.DOTALL)
        if github_match:
            project['project']['features'] = [{'type': 'githubConnection'}]

    # Now parse individual objects
    objects = {}
    for match in re.finditer(r'object\s+(\w+)\s*:\s*(\w+)\(\{', content):
        obj_name = match.group(1)
        obj_type = match.group(2)
        start = match.end() - 1
        obj_content = extract_balanced(content, start)
        if obj_content:
            obj_content = obj_content[1:-1]  # remove outer {}
            if obj_type == 'BuildType':
                objects[obj_name] = parse_build_type(obj_content)
            elif obj_type == 'Project':
                objects[obj_name] = parse_project(obj_content)
            elif obj_type == 'GitVcsRoot':
                objects[obj_name] = parse_vcs_root(obj_content)
            elif obj_type == 'Template':
                objects[obj_name] = parse_build_type(obj_content)  # Treat as BuildType

    def map_project(proj):
        if 'buildTypes' in proj:
            for bt in proj['buildTypes']:
                if bt['id'] in objects:
                    obj = objects[bt['id']]
                    if obj is not None:
                        bt.update(obj)
        if 'subProjects' in proj:
            for sp in proj['subProjects']:
                if sp['id'] in objects:
                    obj = objects[sp['id']]
                    if obj is not None:
                        sp.update(obj)
                        map_project(sp)  # recursive for nested
        if 'vcsRoots' in proj:
            for vr in proj['vcsRoots']:
                if vr['id'] in objects:
                    obj = objects[vr['id']]
                    if obj is not None:
                        vr.update(obj)

    map_project(project['project'])
    return project

def parse_build_type(content):
    bt = {}

    # Name
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        bt['name'] = name_match.group(1)

    # Steps
    steps_match = re.search(r'steps\s*\{', content)
    if steps_match:
        start = steps_match.end() - 1
        steps_block = extract_balanced(content, start)
        if steps_block:
            steps_content = steps_block[1:-1]
            bt['steps'] = parse_steps(steps_content)

    # Triggers
    triggers_match = re.search(r'triggers\s*\{([^}]+)\}', content, re.DOTALL)
    if triggers_match:
        triggers_content = triggers_match.group(1)
        bt['triggers'] = parse_triggers(triggers_content)

    # Features
    features_match = re.search(r'features\s*\{([^}]+)\}', content, re.DOTALL)
    if features_match:
        features_content = features_match.group(1)
        bt['features'] = parse_features(features_content)

    # Params
    params_match = re.search(r'params\s*\{([^}]+)\}', content, re.DOTALL)
    if params_match:
        params_content = params_match.group(1)
        bt['params'] = parse_params(params_content)

    # VCS
    vcs_match = re.search(r'vcs\s*\{([^}]+)\}', content, re.DOTALL)
    if vcs_match:
        vcs_content = vcs_match.group(1)
        bt['vcs'] = parse_vcs(vcs_content)

    # Artifact rules
    artifact_match = re.search(r'artifactRules\s*=\s*"""([^"]+)"""', content, re.DOTALL)
    if artifact_match:
        bt['artifactRules'] = artifact_match.group(1).strip()

    return bt

def parse_steps(content):
    steps = []
    # Parse script steps
    for match in re.finditer(r'script\s*\{', content):
        start = match.end() - 1
        script_block = extract_balanced(content, start)
        if script_block:
            script_content = script_block[1:-1]
            step = parse_script_step(script_content)
            steps.append(step)
    # Parse python steps
    for match in re.finditer(r'python\s*\{', content):
        start = match.end() - 1
        python_block = extract_balanced(content, start)
        if python_block:
            python_content = python_block[1:-1]
            step = parse_python_step(python_content)
            steps.append(step)
    # Parse kotlinScript steps
    for match in re.finditer(r'kotlinScript\s*\{', content):
        start = match.end() - 1
        kotlin_block = extract_balanced(content, start)
        if kotlin_block:
            kotlin_content = kotlin_block[1:-1]
            step = parse_kotlin_step(kotlin_content)
            steps.append(step)
    # Parse powerShell steps
    for match in re.finditer(r'powerShell\s*\{', content):
        start = match.end() - 1
        powershell_block = extract_balanced(content, start)
        if powershell_block:
            powershell_content = powershell_block[1:-1]
            step = parse_powershell_step(powershell_content)
            steps.append(step)
    # Parse general step blocks
    for match in re.finditer(r'step\s*\{', content):
        start = match.end() - 1
        step_block = extract_balanced(content, start)
        if step_block:
            step_content = step_block[1:-1]
            step = parse_general_step(step_content)
            steps.append(step)
    return steps

def parse_script_step(content):
    step = {'type': 'script'}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        step['name'] = name_match.group(1)
    id_match = re.search(r'id\s*=\s*"([^"]+)"', content)
    if id_match:
        step['id'] = id_match.group(1)
    enabled_match = re.search(r'enabled\s*=\s*(true|false)', content)
    if enabled_match:
        step['enabled'] = enabled_match.group(1) == 'true'
    working_dir_match = re.search(r'workingDir\s*=\s*"([^"]+)"', content)
    if working_dir_match:
        step['workingDir'] = working_dir_match.group(1)
    script_match = re.search(r'scriptContent\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if script_match:
        step['scriptContent'] = script_match.group(1).strip()
    # Parse conditions
    conditions_match = re.search(r'conditions\s*\{([^}]*)\}', content, re.DOTALL)
    if conditions_match:
        conditions_content = conditions_match.group(1)
        conditions = []
        # Parse equals
        equals_matches = re.findall(r'equals\("([^"]+)"\s*,\s*"([^"]+)"\)', conditions_content)
        for prop, val in equals_matches:
            conditions.append({"type": "equals", "property": prop, "value": val})
        # Parse contains
        contains_matches = re.findall(r'contains\("([^"]+)"\s*,\s*"([^"]+)"\)', conditions_content)
        for prop, val in contains_matches:
            conditions.append({"type": "contains", "property": prop, "value": val})
        if conditions:
            step['conditions'] = conditions
    return step

def parse_python_step(content):
    step = {'type': 'python'}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        step['name'] = name_match.group(1)
    id_match = re.search(r'id\s*=\s*"([^"]+)"', content)
    if id_match:
        step['id'] = id_match.group(1)
    command_match = re.search(r'command\s*=\s*script\s*\{([^}]+)\}', content, re.DOTALL)
    if command_match:
        command_content = command_match.group(1)
        content_match = re.search(r'content\s*=\s*"""([^"]*)"""', command_content, re.DOTALL)
        if content_match:
            step['scriptContent'] = content_match.group(1).strip()
    return step

def parse_powershell_step(content):
    step = {'type': 'powershell'}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        step['name'] = name_match.group(1)
    id_match = re.search(r'id\s*=\s*"([^"]+)"', content)
    if id_match:
        step['id'] = id_match.group(1)
    script_mode_match = re.search(r'scriptMode\s*=\s*script\s*\{', content)
    if script_mode_match:
        start = script_mode_match.end() - 1
        script_block = extract_balanced(content, start)
        if script_block:
            script_content = script_block[1:-1]
            content_match = re.search(r'content\s*=\s*"""(.*?)"""', script_content, re.DOTALL)
            if content_match:
                step['scriptContent'] = content_match.group(1).strip()
    # Parse conditions
    conditions_match = re.search(r'conditions\s*\{([^}]*)\}', content, re.DOTALL)
    if conditions_match:
        conditions_content = conditions_match.group(1)
        conditions = []
        contains_matches = re.findall(r'contains\("([^"]+)"\s*,\s*"([^"]+)"\)', conditions_content)
        for prop, val in contains_matches:
            conditions.append({"type": "contains", "property": prop, "value": val})
        if conditions:
            step['conditions'] = conditions
    return step

def parse_general_step(content):
    step = {}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        step['name'] = name_match.group(1)
    id_match = re.search(r'id\s*=\s*"([^"]+)"', content)
    if id_match:
        step['id'] = id_match.group(1)
    type_match = re.search(r'type\s*=\s*"([^"]+)"', content)
    if type_match:
        step['type'] = type_match.group(1)
    enabled_match = re.search(r'enabled\s*=\s*(true|false)', content)
    if enabled_match:
        step['enabled'] = enabled_match.group(1) == 'true'
    execution_mode_match = re.search(r'executionMode\s*=\s*BuildStep\.ExecutionMode\.(\w+)', content)
    if execution_mode_match:
        step['executionMode'] = execution_mode_match.group(1)
    # Parse params in step
    params_match = re.search(r'params\s*\{([^}]*)\}', content, re.DOTALL)
    if params_match:
        params_content = params_match.group(1)
        step['params'] = parse_params(params_content)
    return step

def parse_kotlin_step(content):
    step = {'type': 'kotlinScript'}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        step['name'] = name_match.group(1)
    id_match = re.search(r'id\s*=\s*"([^"]+)"', content)
    if id_match:
        step['id'] = id_match.group(1)
    enabled_match = re.search(r'enabled\s*=\s*(true|false)', content)
    if enabled_match:
        step['enabled'] = enabled_match.group(1) == 'true'
    content_match = re.search(r'content\s*=\s*"""([^"]*)"""', content, re.DOTALL)
    if content_match:
        step['content'] = content_match.group(1).strip()
    return step

def parse_triggers(content):
    triggers = []
    vcs_matches = re.findall(r'vcs\s*\{([^}]*)\}', content, re.DOTALL)
    for vcs_content in vcs_matches:
        trigger = {'type': 'vcs'}
        enabled_match = re.search(r'enabled\s*=\s*(true|false)', vcs_content)
        if enabled_match:
            trigger['enabled'] = str(enabled_match.group(1) == 'true').lower()
        triggers.append(trigger)
    return triggers

def parse_features(content):
    features = []
    perfmon_matches = re.findall(r'perfmon\s*\{([^}]*)\}', content, re.DOTALL)
    for _ in perfmon_matches:
        features.append({'type': 'perfmon'})
    return features

def parse_params(content):
    params = []
    # Parse param("key", "value")
    param_matches = re.findall(r'param\("([^"]+)"\s*,\s*"([^"]+)"', content)
    for key, value in param_matches:
        params.append({"type": "param", "name": key, "value": value})
    # Parse select("key", "default", ...)
    select_matches = re.findall(r'select\("([^"]+)"\s*,\s*"([^"]+)"', content)
    for key, default in select_matches:
        params.append({"type": "select", "name": key, "value": default})
    # Parse checkbox("key", "value", ...)
    checkbox_matches = re.findall(r'checkbox\("([^"]+)"\s*,\s*"([^"]+)"', content)
    for key, value in checkbox_matches:
        params.append({"type": "checkbox", "name": key, "value": value})
    # Parse text("key", "default", ...)
    text_matches = re.findall(r'text\("([^"]+)"\s*,\s*"([^"]+)"', content)
    for key, default in text_matches:
        params.append({"type": "text", "name": key, "value": default})
    return params

def parse_vcs(content):
    vcs = {}
    root_match = re.search(r'root\(([^)]+)\)', content)
    if root_match:
        vcs['root'] = root_match.group(1).strip()
    return vcs

def parse_project(content):
    proj = {}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        proj['name'] = name_match.group(1)
    # Add buildTypes
    build_types = re.findall(r'buildType\(([^)]+)\)', content)
    if build_types:
        proj['buildTypes'] = [{'id': bt.strip()} for bt in build_types]
    # Add subProjects
    sub_projects = re.findall(r'subProject\(([^)]+)\)', content)
    if sub_projects:
        proj['subProjects'] = [{'id': sp.strip()} for sp in sub_projects]
    # Add vcsRoots
    vcs_roots = re.findall(r'vcsRoot\(([^)]+)\)', content)
    if vcs_roots:
        proj['vcsRoots'] = [{'id': vr.strip()} for vr in vcs_roots]
    return proj

def parse_vcs_root(content):
    vcs = {}
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    if name_match:
        vcs['name'] = name_match.group(1)
    url_match = re.search(r'url\s*=\s*"([^"]+)"', content)
    if url_match:
        vcs['url'] = url_match.group(1)
    branch_match = re.search(r'branch\s*=\s*"([^"]+)"', content)
    if branch_match:
        vcs['branch'] = branch_match.group(1)
    return vcs

def main():
    teamcity_dir = Path('example-repo/.teamcity')
    settings_file = teamcity_dir / 'settings.kts'

    if not settings_file.exists():
        print("settings.kts not found")
        return

    config = parse_kotlin_dsl(settings_file)
    if config:
        try:
            import yaml
            output_file = 'teamcity.yaml'
            with open(output_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            print("Converted to teamcity.yaml")
        except ImportError:
            output_file = 'teamcity.json'
            with open(output_file, 'w') as f:
                json.dump(config, f, indent=2)
            print("Converted to teamcity.json (install PyYAML for YAML output)")
        print("Output structure:")
        print(json.dumps(config, indent=2))
    else:
        print("Failed to parse")

if __name__ == '__main__':
    main()