"""Task scheduler — cron-like scheduled execution with background thread."""
from __future__ import annotations
import re, subprocess, threading, time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from ._encoding import run as _run, popen as _popen

_CRON_RE = re.compile(r'^(\*|[0-9,/\-]+)\s+(\*|[0-9,/\-]+)\s+(\*|[0-9,/\-]+)\s+(\*|[0-9,/\-]+)\s+(\*|[0-9,/\-]+)$')

@dataclass
class CronTask:
    id: str; name: str; cron_expr: str; command: str
    enabled: bool = True; created_at: float = field(default_factory=time.time)
    last_run: float | None = None; run_count: int = 0; last_result: str = ""

@dataclass
class ScheduleEvent:
    task_id: str; task_name: str; command: str; timestamp: float; result: str = ""

class CronParser:
    @staticmethod
    def _parse(field, mn, mx):
        if field == "*": return set(range(mn, mx+1))
        r=set()
        for p in field.split(","):
            p=p.strip()
            if "/" in p:
                base,step=p.split("/",1); step=int(step)
                if "-" in base: a,b=base.split("-",1); rg=range(int(a),int(b)+1)
                elif base=="*": rg=range(mn,mx+1)
                else: rg=range(int(base),mx+1)
                for v in rg:
                    if (v-mn)%step==0: r.add(v)
            elif "-" in p: a,b=p.split("-",1); r.update(range(int(a),int(b)+1))
            else: r.add(int(p))
        return {v for v in r if mn<=v<=mx}

    @classmethod
    def match(cls,expr,dt):
        m=_CRON_RE.match(expr)
        if not m: return False
        minute,hour,dom,month,dow=m.groups()
        return (dt.minute in cls._parse(minute,0,59) and dt.hour in cls._parse(hour,0,23)
                and dt.day in cls._parse(dom,1,31) and dt.month in cls._parse(month,1,12)
                and dt.weekday() in cls._parse(dow,0,6))

    @staticmethod
    def describe(expr):
        m=_CRON_RE.match(expr)
        if not m: return f"无效: {expr}"
        minute,hour,dom,month,dow=m.groups(); parts=[]
        if minute!="*" and hour=="*": parts.append(f"每小时第{minute}分")
        elif minute=="*" and hour!="*": parts.append(f"每{hour}点")
        elif minute!="*" and hour!="*": parts.append(f"每天{hour}:{minute}")
        if dom!="*": parts.append(f"每月{dom}日")
        if month!="*": parts.append(f"{month}月")
        if dow!="*":
            nms=["周一","周二","周三","周四","周五","周六","周日"]
            try: parts.append(nms[int(dow)])
            except: pass
        return " ".join(parts) if parts else "每分钟"

class Scheduler:
    def __init__(self):
        self._tasks={}; self._events=[]; self._lock=threading.Lock()
        self._running=False; self._thread=None; self._counter=0; self._on_trigger=None

    def start(self,on_trigger=None):
        if self._running: return
        self._running=True; self._on_trigger=on_trigger; self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()

    def stop(self): self._running=False

    def add_task(self,name,expr,cmd):
        with self._lock:
            self._counter+=1; t=CronTask(id=f"task_{self._counter}",name=name,cron_expr=expr,command=cmd)
            self._tasks[t.id]=t; return t

    def remove_task(self,tid):
        with self._lock: return self._tasks.pop(tid,None) is not None

    def get_task(self,tid):
        with self._lock: return self._tasks.get(tid)

    def list_tasks(self):
        with self._lock: return list(self._tasks.values())

    def get_recent_events(self,limit=20):
        with self._lock: return self._events[-limit:]

    @property
    def is_running(self): return self._running

    def _loop(self):
        while self._running:
            try:
                now=datetime.now(); triggered=[]
                with self._lock:
                    for t in self._tasks.values():
                        if t.enabled and CronParser.match(t.cron_expr,now): triggered.append(t)
                for t in triggered:
                    ev=ScheduleEvent(task_id=t.id,task_name=t.name,command=t.command,timestamp=time.time())
                    try:
                        r=_run(["powershell","-NoProfile","-Command",t.command],capture_output=True,text=True,timeout=120)
                        ev.result=(r.stdout or "")[:1000]
                        if r.stderr: ev.result+=f"\nSTDERR: {r.stderr[:500]}"
                    except subprocess.TimeoutExpired: ev.result="超时"
                    except Exception as e: ev.result=f"错误: {e}"
                    with self._lock:
                        if t.id in self._tasks: self._tasks[t.id].last_run=time.time(); self._tasks[t.id].run_count+=1; self._tasks[t.id].last_result=ev.result[:500]
                        self._events.append(ev)
                        if len(self._events)>100: self._events=self._events[-100:]
                    if self._on_trigger:
                        try: self._on_trigger(ev)
                        except: pass
            except: pass
            time.sleep(30)

_scheduler=None
def get_scheduler():
    global _scheduler
    if _scheduler is None: _scheduler=Scheduler()
    return _scheduler
