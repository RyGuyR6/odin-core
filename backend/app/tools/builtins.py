from __future__ import annotations
import asyncio
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from .base import Tool
from .config import ToolSettings
from .exceptions import ToolExecutionError, ToolValidationError
from .models import ExecutionContext, RiskLevel, ToolDefinition
from .sandbox import WorkspaceSandbox

class FileReadTool(Tool):
    definition = ToolDefinition(name="fs.read", description="Read a UTF-8 file inside the workspace", tags=["filesystem"])
    def __init__(self, sandbox): self.sandbox=sandbox
    async def execute(self, arguments, context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        if not path.is_file(): raise ToolValidationError("Path is not a file")
        max_bytes=int(arguments.get("max_bytes",262144))
        data=path.read_bytes()[:max_bytes]
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"content":data.decode("utf-8",errors="replace"),"bytes":len(data),"truncated":path.stat().st_size>len(data)}

class FileListTool(Tool):
    definition = ToolDefinition(name="fs.list", description="List files inside the workspace", tags=["filesystem"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path",".")),must_exist=True)
        if not path.is_dir(): raise ToolValidationError("Path is not a directory")
        recursive=bool(arguments.get("recursive",False)); limit=min(int(arguments.get("limit",500)),2000)
        iterator=path.rglob("*") if recursive else path.iterdir()
        root=self.sandbox.workspace(context.workspace_id); items=[]
        for item in iterator:
            if len(items)>=limit: break
            items.append({"path":str(item.relative_to(root)),"type":"directory" if item.is_dir() else "file","bytes":item.stat().st_size if item.is_file() else None})
        return {"items":items,"count":len(items),"truncated":len(items)>=limit}

class FileSearchTool(Tool):
    definition=ToolDefinition(name="fs.search",description="Search text files in the workspace",tags=["filesystem"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        query=str(arguments.get("query",""))
        if not query: raise ToolValidationError("query is required")
        root=self.sandbox.resolve(context.workspace_id,str(arguments.get("path",".")),must_exist=True)
        pattern=str(arguments.get("glob","**/*")); limit=min(int(arguments.get("limit",100)),500)
        case_sensitive=bool(arguments.get("case_sensitive",False))
        needle=query if case_sensitive else query.lower(); results=[]
        for path in root.glob(pattern):
            if len(results)>=limit: break
            if not path.is_file() or path.stat().st_size>2_000_000: continue
            try: lines=path.read_text("utf-8").splitlines()
            except (UnicodeDecodeError,OSError): continue
            for lineno,line in enumerate(lines,1):
                hay=line if case_sensitive else line.lower()
                if needle in hay:
                    results.append({"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"line":lineno,"text":line[:500]})
                    if len(results)>=limit: break
        return {"matches":results,"count":len(results),"truncated":len(results)>=limit}

class FileWriteTool(Tool):
    definition=ToolDefinition(name="fs.write",description="Write a UTF-8 file inside the workspace",risk=RiskLevel.medium,requires_approval=True,tags=["filesystem","write"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")))
        content=str(arguments.get("content","")); overwrite=bool(arguments.get("overwrite",False))
        if path.exists() and not overwrite: raise ToolValidationError("File exists; set overwrite=true")
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(path.suffix+".odin-tmp"); tmp.write_text(content,"utf-8"); tmp.replace(path)
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"bytes":len(content.encode()),"sha256":hashlib.sha256(content.encode()).hexdigest()}

class FilePatchTool(Tool):
    definition=ToolDefinition(name="fs.patch",description="Replace one exact text block in a workspace file",risk=RiskLevel.medium,requires_approval=True,tags=["filesystem","write"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        old=str(arguments.get("old","")); new=str(arguments.get("new",""))
        if not old: raise ToolValidationError("old text is required")
        text=path.read_text("utf-8"); count=text.count(old)
        if count!=1: raise ToolValidationError(f"Expected exactly one match, found {count}")
        updated=text.replace(old,new,1); path.write_text(updated,"utf-8")
        return {"path":str(path.relative_to(self.sandbox.workspace(context.workspace_id))),"replacements":1,"sha256":hashlib.sha256(updated.encode()).hexdigest()}

class FileDeleteTool(Tool):
    definition=ToolDefinition(name="fs.delete",description="Delete a file or directory inside the workspace",risk=RiskLevel.high,requires_approval=True,tags=["filesystem","destructive"])
    def __init__(self,sandbox): self.sandbox=sandbox
    async def execute(self,arguments,context):
        path=self.sandbox.resolve(context.workspace_id,str(arguments.get("path","")),must_exist=True)
        root=self.sandbox.workspace(context.workspace_id)
        if path==root: raise ToolValidationError("Cannot delete workspace root")
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
        return {"deleted":str(path.relative_to(root))}

class ShellRunTool(Tool):
    definition=ToolDefinition(name="shell.run",description="Run an argv-based command in the workspace",risk=RiskLevel.high,requires_approval=True,tags=["execution"])
    def __init__(self,sandbox,settings): self.sandbox=sandbox; self.settings=settings
    async def execute(self,arguments,context):
        argv=arguments.get("argv")
        if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and x for x in argv):
            raise ToolValidationError("argv must be a non-empty list of strings")
        deny={"sudo","su","mount","umount","shutdown","reboot","mkfs","dd"}
        if Path(argv[0]).name in deny: raise ToolValidationError("Command is denied by policy")
        cwd=self.sandbox.resolve(context.workspace_id,str(arguments.get("cwd",".")),must_exist=True)
        env={"PATH":os.getenv("PATH",""),"HOME":str(self.sandbox.workspace(context.workspace_id)),"LANG":"C.UTF-8"}
        for key,value in dict(arguments.get("env",{})).items():
            if re.fullmatch(r"[A-Z_][A-Z0-9_]*",str(key)): env[str(key)]=str(value)
        proc=await asyncio.create_subprocess_exec(*argv,cwd=cwd,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await proc.communicate()
        limit=self.settings.max_output_bytes
        return {"argv":argv,"exit_code":proc.returncode,"stdout":stdout[:limit].decode(errors="replace"),"stderr":stderr[:limit].decode(errors="replace"),"truncated":len(stdout)>limit or len(stderr)>limit}

class PythonRunTool(Tool):
    definition=ToolDefinition(name="python.run",description="Run isolated Python source in the workspace",risk=RiskLevel.high,requires_approval=True,tags=["execution"])
    def __init__(self,sandbox,settings): self.sandbox=sandbox; self.settings=settings
    async def execute(self,arguments,context):
        source=str(arguments.get("source",""))
        if not source: raise ToolValidationError("source is required")
        cwd=self.sandbox.resolve(context.workspace_id,str(arguments.get("cwd",".")),must_exist=True)
        proc=await asyncio.create_subprocess_exec(sys.executable,"-I","-c",source,cwd=cwd,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await proc.communicate(); limit=self.settings.max_output_bytes
        return {"exit_code":proc.returncode,"stdout":stdout[:limit].decode(errors="replace"),"stderr":stderr[:limit].decode(errors="replace"),"truncated":len(stdout)>limit or len(stderr)>limit}

def register_builtin_tools(registry,sandbox,settings):
    for tool in [
        FileReadTool(sandbox),FileListTool(sandbox),FileSearchTool(sandbox),
        FileWriteTool(sandbox),FilePatchTool(sandbox),FileDeleteTool(sandbox),
        ShellRunTool(sandbox,settings),PythonRunTool(sandbox,settings),
    ]:
        registry.register(tool,replace=True)
