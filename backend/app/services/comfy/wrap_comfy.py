

import copy
import json
from pathlib import Path
from typing import Any, List

from openai import BaseModel
from celery.utils.log import get_task_logger
    
logger = get_task_logger(__name__)

class WrapComfy:
    def __init__(self, workflow_path: str|Path):
        self.workflow = {}
        try:
            with open(workflow_path, 'r') as f:
                self.workflow = json.load(f)
        except Exception as e:
            logger.error(f'load workflow file:{workflow_path} failed.')
            logger.exception(f'load {workflow_path} failed.')
            raise
    
    def list_nodes(self) -> List[str]:
        return [node["_meta"]["title"] for node in self.workflow.values()]
    
    def set_node_param(self, title: str, param: str, value) -> bool:
        smth_changed = False
        for node in self.workflow.values():
            if node["_meta"]["title"] == title:
                logger.info(f"Setting parameter '{param}' of node '{title}' to '{value}'")
                node["inputs"][param] = value
                smth_changed = True
        if not smth_changed:
            raise ValueError(f"Node '{title}' not found.")
    
    def get_node_param(self, title: str, param: str) -> Any:
        for node in self.workflow.values():
            if node["_meta"]["title"] == title:
                return node["inputs"][param]
        raise ValueError(f"Node '{title}' not found.")
    

    def get_node_id(self, title: str) -> str:
        for id, node in self.workflow.items():
            print(f'get_node_id  {id}: {node["_meta"]["title"]}')
            if node["_meta"]["title"] == title:
                return id
        raise ValueError(f"Node '{title}' not found.")
    
    def save_to_file(self, path: str):
        workflow_str = json.dumps(self.workflow, indent=4)
        # Use UTF-8 when writing files to ensure consistent encoding.
        with open(path, "w+", encoding="utf-8") as f:
            f.write(workflow_str)
    
    def gen_new_node_id(self) -> str:
        key_list = [int(key) for key in self.workflow.keys()]
        return str(max(key_list) + 1)
    
    def copy_node(self, ori_title:str, new_title:str):
        new_node_id = self.gen_new_node_id()
        for node in self.workflow.values():
            if node["_meta"]["title"] == ori_title:
                new_node = copy.deepcopy(node)
                new_node["_meta"]["title"] = new_title
                self.workflow[new_node_id] = new_node
                return
        raise ValueError(f"Node '{ori_title}' not found.")
        
        