"""File/process/log monitor — polling-based watch engine with event callback."""
from __future__ import annotations
import os, re, subprocess, threading, time
from dataclasses import dataclass, field
from typing import Callable
from ._encoding import run as _run, popen as _popen

@dataclass
class WatchEvent:
    watch_id: str; watch_name: str; event_type: str; detail: str = ""
    timestamp: float = field(default_factory=time.time)

@dataclass
class WatchTarget:
    id: str; name: str; kind: str; path: str; pattern: str = ""
    active: bool = True; created_at: float = field(default_factory=time.time)
    events: list[WatchEvent] = field(default_factory=list)

class FileWatcher:
    def __init__(self, poll=1.0):
        self._targets={}; self._snapshots={}; self._lock=threading.Lock()
        self._running=False; self._thread=None; self._on_event=None; self._poll=poll; self._counter=0
        self._wd_observer=None

    def start(self, on_event=None):
        if self._running: return
        self._running=True; self._on_event=on_event
        if self._try_watchdog(): return
        self._thread=threading.Thread(target=self._loop,daemon=True); self._thread.start()

    def stop(self):
        self._running=False
        if self._wd_observer:
            try:self._wd_observer.stop()
            except:pass
            self._wd_observer=None

    def _try_watchdog(self) -> bool:
        try:
            import watchdog.observers as wo, watchdog.events as we
            paths=set()
            with self._lock:
                for t in self._targets.values():
                    if t.kind in("file","directory","log"): paths.add(os.path.dirname(t.path)if os.path.isfile(t.path)else t.path)
            if not paths: return False
            class H(we.FileSystemEventHandler):
                def __init__(s2,w):s2.w=w
                def on_modified(s2,ev):
                    if not ev.is_directory:s2.w._fire(WatchEvent("wd","wd","mod",ev.src_path))
                def on_created(s2,ev):s2.w._fire(WatchEvent("wd","wd","create",ev.src_path))
                def on_deleted(s2,ev):s2.w._fire(WatchEvent("wd","wd","delete",ev.src_path))
            self._wd_observer=wo.Observer()
            for p in paths: self._wd_observer.schedule(H(self),p,recursive=True)
            self._wd_observer.start(); return True
        except ImportError: return False
        except: return False

    def add_watch(self,name,kind,path,pattern=""):
        with self._lock:
            self._counter+=1; wid=f"watch_{self._counter}"
            self._targets[wid]=WatchTarget(id=wid,name=name,kind=kind,path=path,pattern=pattern)
            if kind=="file" and os.path.isfile(path): st=os.stat(path); self._snapshots[path]={"mtime":st.st_mtime,"size":st.st_size}
            return wid

    def remove_watch(self,wid):
        with self._lock: return self._targets.pop(wid,None) is not None

    def list_watches(self):
        with self._lock: return list(self._targets.values())

    def get_events(self,wid,limit=50):
        with self._lock: t=self._targets.get(wid); return t.events[-limit:] if t else []

    def _fire(self,ev):
        if self._on_event:
            try: self._on_event(ev)
            except: pass
        with self._lock:
            t=self._targets.get(ev.watch_id)
            if t: t.events.append(ev); 
            if len(t.events)>200: t.events=t.events[-100:]

    def _loop(self):
        while self._running:
            try:
                with self._lock: targets=list(self._targets.values())
                for t in targets:
                    if not t.active: continue
                    try:
                        if t.kind=="file": self._check_file(t)
                        elif t.kind=="directory": self._check_dir(t)
                        elif t.kind=="log": self._check_log(t)
                        elif t.kind=="process": self._check_process(t)
                    except: pass
            except: pass
            time.sleep(self._poll)

    def _check_file(self,t):
        if not os.path.isfile(t.path): return
        st=os.stat(t.path); prev=self._snapshots.get(t.path)
        if prev and (st.st_mtime!=prev.get("mtime") or st.st_size!=prev.get("size")):
            self._fire(WatchEvent(t.id,t.name,"modified",f"mtime:{st.st_mtime}"))
        self._snapshots[t.path]={"mtime":st.st_mtime,"size":st.st_size}

    def _check_dir(self,t):
        if not os.path.isdir(t.path): return
        cur=set()
        for root,dirs,files in os.walk(t.path):
            for f in files: cur.add(os.path.join(root,f))
        prev=self._snapshots.get(t.path,set())
        if prev and cur!=prev:
            for f in list(cur-prev)[:5]: self._fire(WatchEvent(t.id,t.name,"modified",f"新增: {os.path.basename(f)}"))
            for f in list(prev-cur)[:5]: self._fire(WatchEvent(t.id,t.name,"modified",f"删除: {os.path.basename(f)}"))
        self._snapshots[t.path]=cur

    def _check_log(self,t):
        if not os.path.isfile(t.path): return
        pk=f"{t.path}_pos"; pp=self._snapshots.get(pk,0); s=os.path.getsize(t.path)
        if s<pp: pp=0
        if s>pp:
            with open(t.path,"r",encoding="utf-8",errors="replace") as f:
                f.seek(pp)
                for l in f:
                    l=l.rstrip()
                    if l:
                        if t.pattern and re.search(t.pattern,l,re.I): self._fire(WatchEvent(t.id,t.name,"match",l[:500]))
                        elif not t.pattern: self._fire(WatchEvent(t.id,t.name,"modified",l[:500]))
            self._snapshots[pk]=s

    def _check_process(self,t):
        try:
            r=_run(["powershell","-NoProfile","-Command",f"@(Get-Process -Name '{t.path}' -ErrorAction SilentlyContinue).Count"],capture_output=True,text=True,timeout=10)
            c=r.stdout.strip(); running=c.isdigit() and int(c)>0; prev=self._snapshots.get(f"proc_{t.path}",False)
            if running and not prev: self._fire(WatchEvent(t.id,t.name,"process_started",f"{t.path} 启动"))
            elif not running and prev: self._fire(WatchEvent(t.id,t.name,"process_stopped",f"{t.path} 停止"))
            self._snapshots[f"proc_{t.path}"]=running
        except: pass

_watcher=None
def get_watcher():
    global _watcher
    if _watcher is None: _watcher=FileWatcher()
    return _watcher
