"""tools — facade assembling sub-modules. Re-exports for backward compat."""
from __future__ import annotations
import os,time
from typing import Any
from .tools_core import (TOOL_DEFINITIONS,BUILTIN_HANDLERS,PLUGIN_HANDLERS,_written_this_session,_agent_spawned_pids,_file_backups,_session_lessons,_consecutive_fails,_last_heal_time,_NODE_MODULES_WARNED,smart_truncate,check_search_scope,classify_tool_result,guard_tool_call,_load_plugins,_TOOL_RESULT_MAX_LENGTH)
from .tools_file import (_handle_read,_handle_write,_handle_edit,_handle_glob,_handle_grep,_handle_revert,_check_references,_run_validation,_restore_backup)
from .tools_shell import (_handle_bash,_handle_system_info,_handle_process,_handle_think,_run_powershell,BuildRunner,_self_heal)
from .tools_web import (_handle_web,_handle_web_search,_handle_screencap,_handle_ask_user)
from .tools_browser import (_handle_browser,_browser,_browser_context,_browser_page,_browser_console_logs,_browser_network_errors,_browser_page_errors)
from .tools_plan import (_handle_background,_handle_plan,_handle_task,_handle_project_memory,_background_tasks,_plans)
from .tools_analysis import (_handle_ast,_handle_dep_graph,_handle_call_chain,_handle_trace_error,_find_cycles)

BUILTIN_HANDLERS.update({
    "read":_handle_read,"write":_handle_write,"edit":_handle_edit,
    "glob":_handle_glob,"grep":_handle_grep,"bash":_handle_bash,
    "think":_handle_think,"project_memory":_handle_project_memory,
    "system_info":_handle_system_info,"process":_handle_process,
    "web":_handle_web,"web_search":_handle_web_search,
    "ask_user":_handle_ask_user,"screencap":_handle_screencap,
    "browser":_handle_browser,"background":_handle_background,
    "plan":_handle_plan,"task":_handle_task,"ast":_handle_ast,
    "dep_graph":_handle_dep_graph,"call_chain":_handle_call_chain,
    "revert":_handle_revert,"trace_error":_handle_trace_error,
})

def handle_tool_call(name,params,output_callback=None):
    allowed,guard_msg=guard_tool_call(name,params)
    if not allowed: return f"已阻止: {guard_msg}"
    global _last_heal_time; now=time.time()
    if now-_last_heal_time>60 and name not in('think','read','glob'):
        _last_heal_time=now
        try: _self_heal()
        except: pass
    lp=""
    if name in("write","edit") and "file_path" in params:
        fp=os.path.abspath(params["file_path"])
        r=[l for l in _session_lessons if l.get("file")==fp and l.get("attempt",0)>=2]
        if r: lp=f"[记忆]文件连续失败{r[-1]['attempt']}次。建议换方案。\n"
    handler=PLUGIN_HANDLERS.get(name) or BUILTIN_HANDLERS.get(name)
    if not handler: return f"未知工具: {name}"
    try:
        if output_callback and name=="bash": params={**params,"output_callback":output_callback}
        result=handler(params) if name in PLUGIN_HANDLERS else handler(**params)
        if guard_msg: result=guard_msg+"\n"+result
        return smart_truncate(lp+(result if isinstance(result,str) else str(result)),_TOOL_RESULT_MAX_LENGTH)
    except Exception as e: return f"执行{name}出错: {e}"

_load_plugins()
