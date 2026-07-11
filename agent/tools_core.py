"""tools_core — shared state, dispatch, utilities."""
from __future__ import annotations
import os
_TOOL_RESULT_MAX_LENGTH = 120000
_written_this_session=set()
_agent_spawned_pids=set()
_file_backups={}
_session_lessons=[]
_consecutive_fails={}
_last_heal_time=0
BUILTIN_HANDLERS={}
PLUGIN_HANDLERS={}
TOOL_DEFINITIONS=[
    {"name":"read","description":"读取文件。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"}},"required":["file_path"]}},
    {"name":"write","description":"写入文件。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"},"content":{"type":"string"}},"required":["file_path","content"]}},
    {"name":"edit","description":"编辑文件。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"}},"required":["file_path","old_string","new_string"]}},
    {"name":"glob","description":"搜索路径。","input_schema":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}},
    {"name":"grep","description":"搜索内容。","input_schema":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"glob_pattern":{"type":"string"},"output_mode":{"type":"string","enum":["content","files_with_matches"]}},"required":["pattern"]}},
    {"name":"bash","description":"执行命令。","input_schema":{"type":"object","properties":{"command":{"type":"string"},"timeout":{"type":"integer"}},"required":["command"]}},
    {"name":"think","description":"推理。","input_schema":{"type":"object","properties":{"thought":{"type":"string"},"content":{"type":"string"},"title":{"type":"string"}},"anyOf":[{"required":["thought"]},{"required":["content"]}]}},
    {"name":"project_memory","description":"项目记忆。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["read","write","append"]},"content":{"type":"string"}},"required":["action"]}},
    {"name":"system_info","description":"系统信息。","input_schema":{"type":"object","properties":{"category":{"type":"string","enum":["os","cpu","memory","disk","network","software","environment","all"]}}}},
    {"name":"process","description":"进程深度管理：list/top/tree/wait_exit/launch/kill。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["list","top","tree","tree_full","wait_exit","launch","kill","search"]},"name":{"type":"string"},"pid":{"type":"integer"},"sort_by":{"type":"string","enum":["cpu","mem","id"]}},"required":["action"]}},
    {"name":"web","description":"HTTP请求。","input_schema":{"type":"object","properties":{"url":{"type":"string"},"method":{"type":"string","enum":["GET","POST"]},"data":{"type":"string"},"headers":{"type":"string"}},"required":["url"]}},
    {"name":"screencap","description":"截图。","input_schema":{"type":"object","properties":{}}},
    {"name":"browser","description":"浏览器。","input_schema":{"type":"object","properties":{"action":{"type":"string"},"url":{"type":"string"},"selector":{"type":"string"},"text":{"type":"string"},"script":{"type":"string"}},"required":["action"]}},
    {"name":"background","description":"后台任务。","input_schema":{"type":"object","properties":{"action":{"type":"string"},"command":{"type":"string"},"task_id":{"type":"string"},"pattern":{"type":"string"},"timeout":{"type":"integer"}},"required":["action"]}},
    {"name":"plan","description":"计划。","input_schema":{"type":"object","properties":{"action":{"type":"string"},"title":{"type":"string"},"plan_id":{"type":"string"},"steps":{"type":"string"},"step_index":{"type":"integer"},"step_status":{"type":"string"}},"required":["action"]}},
    {"name":"task","description":"任务。","input_schema":{"type":"object","properties":{"status":{"type":"string"},"message":{"type":"string"}},"required":["status"]}},
    {"name":"ast","description":"AST分析。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"}},"required":["file_path"]}},
    {"name":"dep_graph","description":"依赖图。","input_schema":{"type":"object","properties":{"path":{"type":"string"}}}},
    {"name":"call_chain","description":"调用链。","input_schema":{"type":"object","properties":{"function_name":{"type":"string"},"direction":{"type":"string"},"path":{"type":"string"},"depth":{"type":"integer"}},"required":["function_name","direction"]}},
    {"name":"revert","description":"撤销。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"}}}},
    {"name":"web_search","description":"网络搜索。","input_schema":{"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer"}},"required":["query"]}},
    {"name":"ask_user","description":"提问用户（智能版：带分析+多选项+推荐）。","input_schema":{"type":"object","properties":{"question":{"type":"string"},"options":{"type":"string"},"analysis":{"type":"string"},"recommended":{"type":"string"}},"required":["question"]}},
    {"name":"trace_error","description":"错误分析。","input_schema":{"type":"object","properties":{"error_message":{"type":"string"},"file_path":{"type":"string"},"depth":{"type":"integer"}},"required":["error_message"]}},
    {"name":"replace","description":"SEARCH/REPLACE: 模糊搜索替换。","input_schema":{"type":"object","properties":{"file_path":{"type":"string"},"search":{"type":"string"},"replace_text":{"type":"string"},"partial":{"type":"boolean"}},"required":["file_path","search","replace_text"]}},
    {"name":"test","description":"测试驱动：发现/运行测试并解析结果。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["discover","run"]},"path":{"type":"string"},"test_name":{"type":"string"},"timeout":{"type":"integer"}},"required":["action"]}},
    {"name":"dep","description":"包依赖管理：自动检测缺失模块并安装。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["check","install","auto"]},"module_name":{"type":"string"},"text":{"type":"string"}},"required":["action"]}},
    {"name":"service","description":"Windows服务控制：list/search/status/start/stop/restart/set_startup。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["list","search","status","start","stop","restart","set_startup"]},"name":{"type":"string"},"start_type":{"type":"string"}},"required":["action"]}},
    {"name":"registry","description":"注册表操作：read/write/delete/list_keys。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["read","write","delete","list_keys"]},"key":{"type":"string"},"name":{"type":"string"},"value":{"type":"string"}},"required":["action","key"]}},
    {"name":"move","description":"移动/重命名文件或目录。","input_schema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"]}},
    {"name":"copy","description":"复制文件或目录（recursive=true 复制目录）。","input_schema":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"},"recursive":{"type":"boolean"}},"required":["source","destination"]}},
    {"name":"delete","description":"删除文件或目录（recursive=true 递归删除）。","input_schema":{"type":"object","properties":{"path":{"type":"string"},"recursive":{"type":"boolean"}},"required":["path"]}},
    {"name":"mkdir","description":"创建目录（parents=true 创建父目录）。","input_schema":{"type":"object","properties":{"path":{"type":"string"},"parents":{"type":"boolean"}},"required":["path"]}},
    {"name":"download","description":"从URL下载文件。","input_schema":{"type":"object","properties":{"url":{"type":"string"},"destination":{"type":"string"}},"required":["url","destination"]}},
    {"name":"gui","description":"GUI 自动化：鼠标点击/键盘输入/截图/窗口控制。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["info","click","double_click","right_click","move","drag","type","keypress","scroll","screenshot","locate","get_window"]},"x":{"type":"integer"},"y":{"type":"integer"},"text":{"type":"string"},"button":{"type":"string"},"key":{"type":"string"},"query":{"type":"string"}},"required":["action"]}},
    {"name":"monitor","description":"系统监控：resources/cpu/memory/disk/process_count/watch_file/network/uptime。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["resources","cpu","memory","disk","process_count","watch_file","network","uptime","process_events"]},"path":{"type":"string"},"interval":{"type":"integer"}},"required":["action"]}},
    {"name":"schedule","description":"定时任务管理：list/add/remove/events。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["list","add","remove","events"]},"name":{"type":"string"},"cron":{"type":"string"},"command":{"type":"string"},"task_id":{"type":"string"}},"required":["action"]}},
    {"name":"watch","description":"文件/进程监控：list/add/remove/events。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["list","add","remove","events"]},"name":{"type":"string"},"kind":{"type":"string","enum":["file","directory","log","process"]},"path":{"type":"string"},"pattern":{"type":"string"},"watch_id":{"type":"string"}},"required":["action"]}},
    {"name":"websocket","description":"WebSocket 客户端：connect/send/ping。","input_schema":{"type":"object","properties":{"action":{"type":"string","enum":["connect","send","ping"]},"url":{"type":"string"},"message":{"type":"string"},"timeout":{"type":"integer"}},"required":["action"]}},
]
def smart_truncate(text,max_len=_TOOL_RESULT_MAX_LENGTH):
    if not text or len(text)<=max_len:return text
    he=any(k in text.lower()[:2000] for k in("error","traceback","异常","失败"))
    if not he and len(text)>2000:he=any(k in text.lower()[-500:] for k in("error","traceback","异常","失败"))
    if not he:return text[:max_len]+f"\n\n...(截断,共{len(text)}字符)"
    tc=min(800,max_len//2);hc=max_len-tc
    return text[:hc]+f"\n...(智能截断:共{len(text)}字符)...\n"+text[-tc:]
_NODE_MODULES_WARNED=set()
def check_search_scope(path):
    n=path.replace("\\","/")
    if "/node_modules/" in n:
        if path not in _NODE_MODULES_WARNED:_NODE_MODULES_WARNED.add(path);return"含node_modules。"
        return"仍在node_modules。"
    if "/bin/" in n or "/obj/" in n:return"含编译输出。"
    if "/.git/" in n:return"含.git。"
    return""
def classify_tool_result(tool_name,result):
    if not result:return{"success":True,"error_type":"ok","suggestion":"","searched_node_modules":False}
    t=result.lower();snm="node_modules"in t[:200]or"node_modules"in t[-500:]
    if any(k in t[:300] for k in("找不到","not found","不存在","does not exist")):return{"success":False,"error_type":"file_not_found","suggestion":"文件不存在。","searched_node_modules":snm}
    if any(k in t for k in("exit code: 1","exit code: 2","超时","timeout")):return{"success":False,"error_type":"command_failed","suggestion":"命令失败。","searched_node_modules":snm}
    if any(k in t[:500] for k in("modulenotfound","importerror","cannot import")):return{"success":False,"error_type":"import_error","suggestion":"导入失败。","searched_node_modules":snm}
    if any(k in t for k in("工具执行错误","执行命令出错")):return{"success":False,"error_type":"tool_error","suggestion":"工具异常。","searched_node_modules":snm}
    if any(k in t[:300] for k in("错误:","error:","failed:","❌")):return{"success":False,"error_type":"error","suggestion":"错误。","searched_node_modules":snm}
    if"无结果"in t or"no results"in t:return{"success":False,"error_type":"no_results","suggestion":"无结果。","searched_node_modules":snm}
    return{"success":True,"error_type":"ok","suggestion":"","searched_node_modules":snm}
def guard_tool_call(name,params):
    if name=="grep":
        p=params.get("path","")
        if p:
            w=check_search_scope(p)
            if w and p in _NODE_MODULES_WARNED:return False,w
            if w:return True,w
    if name=="bash":
        c=params.get("command","").lower()
        if"select-string"in c and"node_modules"in c:return True,"不应搜node_modules。"
    if name=="read":
        p=params.get("file_path","")
        if p and not os.path.exists(p):return True,"文件不存在。"
    return True,""
def _load_plugins():
    try:
        from.plugin import load_plugins
        d,dp=load_plugins()
        if d:TOOL_DEFINITIONS.extend(d);PLUGIN_HANDLERS.update(dp)
    except:pass
