"""tools_plan"""
from __future__ import annotations
import json,os,re,subprocess,threading,time,uuid
from.tools_core import _agent_spawned_pids
_bt={};_bl=threading.Lock();_plans={};_pic=0
_background_tasks=_bt
def _handle_background(action,command="",task_id="",pattern="",timeout=300):
    global _bt
    if action=="start":
        if not command:return"start需command"
        tid=uuid.uuid4().hex[:8]
        try:
            p=subprocess.Popen(["powershell","-NoProfile","-Command",command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,"CREATE_NO_WINDOW")else 0)
            _agent_spawned_pids.add(p.pid)
            with _bl:_bt[tid]={"proc":p,"command":command[:100],"started":time.strftime("%H:%M:%S"),"stdout":[],"stderr":[],"done":False}
            def _c(s,t):
                for l in iter(s.readline,""):
                    with _bl:
                        if tid in _bt:_bt[tid][t].append(l.rstrip())
                s.close()
                with _bl:
                    if tid in _bt:_bt[tid]["done"]=True
            threading.Thread(target=_c,args=(p.stdout,"stdout"),daemon=True).start()
            threading.Thread(target=_c,args=(p.stderr,"stderr"),daemon=True).start()
            return f"后台任务启动\nID:{tid}\n命令:{command[:200]}"
        except Exception as e:return f"启动失败:{e}"
    elif action=="list":
        with _bl:return"\n".join(f"[{tid}]{'完成'if t['done']else'运行'}|{t['started']}|{t['command']}"for tid,t in _bt.items())if _bt else"无任务"
    elif action=="output":
        with _bl:t=_bt.get(task_id)
        return(f"任务{task_id}:{'完成'if t['done']else'运行'}\n命令:{t['command']}\nstdout:{' '.join(t['stdout'][-50:])}\nstderr:{' '.join(t['stderr'][-20:])}"if t else f"未找到:{task_id}")
    elif action=="stop":
        with _bl:t=_bt.get(task_id)
        if not t:return f"未找到:{task_id}"
        try:_agent_spawned_pids.discard(t["proc"].pid);t["proc"].terminate();t["done"]=True;return"已终止"
        except Exception as e:return f"终止失败:{e}"
    elif action=="stop_all":
        with _bl:tids=list(_bt.keys())
        for tid in tids:
            with _bl:t=_bt.get(tid)
            if t and not t["done"]:
                try:_agent_spawned_pids.discard(t["proc"].pid);t["proc"].terminate();t["done"]=True
                except:pass
        return f"已终止{len(tids)}个"
    elif action=="wait":
        with _bl:t=_bt.get(task_id)
        if not t:return f"未找到:{task_id}"
        if t["done"]:return"已完成"
        dl=time.time()+timeout
        while time.time()<dl:
            with _bl:t=_bt.get(task_id)
            if t and t["done"]:return"已完成"
            if pattern and t and re.search(pattern,"\n".join(t["stdout"]),re.I):return"匹配"
            time.sleep(0.5)
        return"超时"
    return f"未知:{action}"
def _handle_plan(action,title="",plan_id="",steps="",step_index=0,step_status=""):
    global _pic
    if action=="create":
        if not title or not steps:return"需title/steps"
        try:sl=json.loads(steps)
        except:return"steps无效"
        if not isinstance(sl,list):return"steps须数组"
        _pic+=1;pid=f"plan-{_pic}";_plans[pid]={"title":title,"steps":sl,"created":time.strftime("%H:%M:%S")}
        d=sum(1 for s in sl if s.get("status")=="completed")
        lines=[f"计划:{pid}|{title}|{d}/{len(sl)}"]
        for i,s in enumerate(sl):lines.append(f"  [{i}][{'x'if s.get('status')=='completed'else' '}]{s['step']}")
        return"\n".join(lines)
    elif action=="update":
        pl=_plans.get(plan_id)
        if not pl:return f"未找到:{plan_id}"
        sl=pl["steps"]
        if step_index<0 or step_index>=len(sl):return f"step{step_index}超范围"
        if step_status not in("pending","in_progress","completed"):return f"无效状态:{step_status}"
        sl[step_index]["status"]=step_status;d=sum(1 for s in sl if s.get("status")=="completed")
        return f"计划[{plan_id}] step{step_index}->{step_status}({d}/{len(sl)})"
    elif action=="list":return"\n".join(f"[{pid}]{p['title']}({sum(1 for s in p['steps'] if s.get('status')=='completed')}/{len(p['steps'])})"for pid,p in _plans.items())if _plans else"无计划"
    elif action=="show":
        pl=_plans.get(plan_id)
        if not pl:return f"未找到:{plan_id}"
        m={"pending":" ","in_progress":"~","completed":"x"};d=sum(1 for s in pl["steps"] if s.get("status")=="completed")
        lines=[f"计划:{pl['title']}|{d}/{len(pl['steps'])}"]
        for i,s in enumerate(pl["steps"]):lines.append(f"  [{i}][{m.get(s.get('status','pending'),' ')}]{s['step']}")
        return"\n".join(lines)
    return f"未知:{action}"
def _handle_task(status,message=""):
    icons={"start":">","progress":"~","done":"x","fail":"!"}
    return f"[{icons.get(status,'?')}]{status}{'  '+message if message else''}"
def _handle_project_memory(action="read",content=""):
    from.memory import save_project_memory as spm,load_project_memory as lpm
    if action=="read":m=lpm();return f"## 项目记忆\n\n{m}"if m else"记忆为空。"
    if action=="write":return spm(content)if content else"需content"
    if action=="append":c=lpm();return spm((c+"\n"+content)if c else content)
    return f"未知:{action}"
