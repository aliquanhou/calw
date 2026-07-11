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
def _handle_plan(action, title="", plan_id="", steps="", step_index=0, step_status=""):
    """持久化计划管理：文件存储，支持步骤依赖和自动推进。"""
    PLANS_DIR = os.path.join(os.path.dirname(__file__), "..", ".claude", "plans")
    global _pic
    if action == "create":
        if not title or not steps:
            return "需title/steps"
        try:
            sl = json.loads(steps)
        except:
            return "steps无效"
        if not isinstance(sl, list):
            return "steps须数组"
        for i, s in enumerate(sl):
            if isinstance(s, str):
                sl[i] = {"id": i, "step": s, "status": "pending", "depends_on": []}
            elif isinstance(s, dict):
                s.setdefault("id", i)
                s.setdefault("status", "pending")
                s.setdefault("depends_on", [])
        os.makedirs(PLANS_DIR, exist_ok=True)
        _pic += 1
        pid = f"plan-{_pic}"
        plan_data = {"id": pid, "title": title, "steps": sl,
                     "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
        plan_file = os.path.join(PLANS_DIR, f"{pid}.json")
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)
        d = sum(1 for s in sl if s.get("status") == "completed")
        lines = [f"计划:{pid}|{title}|{d}/{len(sl)}"]
        for i, s in enumerate(sl):
            dep = ""
            if s.get("depends_on"):
                dep = f" [依赖: {','.join(str(x) for x in s['depends_on'])}]"
            lines.append(f"  [{i}][{'x' if s.get('status') == 'completed' else '~' if s.get('status') == 'in_progress' else ' '}]{s['step']}{dep}")
        lines.append(f"  已持久化: {plan_file}")
        return "\n".join(lines)

    elif action == "update":
        plan_file = os.path.join(PLANS_DIR, f"{plan_id}.json")
        if os.path.exists(plan_file):
            with open(plan_file, "r", encoding="utf-8") as f:
                pl = json.load(f)
        else:
            pl = _plans.get(plan_id)
            if not pl:
                return f"未找到:{plan_id}"
        sl = pl["steps"]
        if step_index < 0 or step_index >= len(sl):
            return f"step{step_index}超范围"
        if step_status not in ("pending", "in_progress", "completed"):
            return f"无效状态:{step_status}"
        if step_status == "in_progress":
            deps = sl[step_index].get("depends_on", [])
            for dep in deps:
                if dep < len(sl) and sl[dep].get("status") != "completed":
                    return f"step{step_index} 的依赖 step{dep} 尚未完成"
        sl[step_index]["status"] = step_status
        pl["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if os.path.exists(os.path.dirname(plan_file)):
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(pl, f, ensure_ascii=False, indent=2)
        d = sum(1 for s in sl if s.get("status") == "completed")
        result = f"计划[{plan_id}] step{step_index}->{step_status}({d}/{len(sl)})"
        if step_status == "completed":
            for i, s in enumerate(sl):
                if s.get("status") == "pending":
                    deps = s.get("depends_on", [])
                    if all(dep < len(sl) and sl[dep].get("status") == "completed" for dep in deps):
                        result += f"\n  下一步: step{i}「{s['step']}」已就绪"
                        break
        return result

    elif action == "list":
        lines = []
        if os.path.exists(PLANS_DIR):
            for fn in sorted(os.listdir(PLANS_DIR)):
                if fn.endswith(".json"):
                    try:
                        with open(os.path.join(PLANS_DIR, fn), "r", encoding="utf-8") as f:
                            p = json.load(f)
                        d = sum(1 for s in p.get("steps", []) if s.get("status") == "completed")
                        lines.append(f"[{p['id']}]{p['title']}({d}/{len(p['steps'])})")
                    except:
                        pass
        for pid, p in _plans.items():
            if not any(pid in l for l in lines):
                d = sum(1 for s in p.get("steps", []) if s.get("status") == "completed")
                lines.append(f"[{pid}]{p['title']}({d}/{len(p['steps'])})")
        return "\n".join(lines) if lines else "无计划"

    elif action == "show":
        plan_file = os.path.join(PLANS_DIR, f"{plan_id}.json")
        if os.path.exists(plan_file):
            with open(plan_file, "r", encoding="utf-8") as f:
                pl = json.load(f)
        else:
            pl = _plans.get(plan_id)
            if not pl:
                return f"未找到:{plan_id}"
        sl = pl["steps"]
        m = {"pending": " ", "in_progress": "~", "completed": "x"}
        d = sum(1 for s in sl if s.get("status") == "completed")
        lines = [f"计划:{pl['title']}|{d}/{len(sl)}"]
        lines.append(f"创建: {pl.get('created', '?')}")
        for i, s in enumerate(sl):
            dep = ""
            if s.get("depends_on"):
                dep = f" [依赖: {','.join(str(x) for x in s['depends_on'])}]"
            lines.append(f"  [{i}][{m.get(s.get('status', 'pending'), ' ')}]{s['step']}{dep}")
        return "\n".join(lines)

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
