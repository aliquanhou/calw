"""tools_shell"""
from __future__ import annotations
import os,subprocess,sys,threading,time
from.tools_core import _agent_spawned_pids,_TOOL_RESULT_MAX_LENGTH,smart_truncate
def _self_heal(ht="build"):
    if sys.platform!="win32":return""
    try:
        a=[];cp=os.getpid()
        def kp(p):return subprocess.run(['taskkill','/F','/PID',str(p)],capture_output=True,timeout=5).returncode==0
        r=subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Process -Filter "Name=\'node.exe\'"|Where-Object{$_.CommandLine-match\'expo\'}|Select-Object-ExpandProperty ProcessId'],capture_output=True,text=True,timeout=10,errors='replace')
        for l in r.stdout.strip().split('\n'):
            p=l.strip()
            if p and p.isdigit():
                pi=int(p)
                if pi!=cp and pi not in _agent_spawned_pids and kp(pi):a.append(f"杀expo PID{pi}")
        r=subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'"|Where-Object{$_.ProcessId -ne '+str(cp)+' -and$_.CommandLine-match\'agent.app\'}|Select-Object-ExpandProperty ProcessId'],capture_output=True,text=True,timeout=10,errors='replace')
        for l in r.stdout.strip().split('\n'):
            p=l.strip()
            if p and p.isdigit():
                pi=int(p)
                if pi not in _agent_spawned_pids and kp(pi):a.append(f"杀旧Claw PID{pi}")
        return f"[自愈]{';'.join(a)}"if a else""
    except:return""
class BuildRunner:
    def __init__(s):s.attempt=0;s.max_retries=2
    def run(s,cmd,scmd,to,oc=None):
        s.attempt=0;lr=""
        while s.attempt<=s.max_retries:
            s.attempt+=1
            if s.attempt>1:
                hr=_self_heal()
                if hr and oc:oc(f"[重试{s.attempt}/{s.max_retries}]{hr}")
            r=s._run_once(cmd,scmd,to,oc);lr=r
            if s.attempt<=s.max_retries and s._is_retryable(r):
                if oc:oc(f"[重试{s.attempt}/{s.max_retries}]清理...");s._cleanup(cmd);continue
            break
        return lr
    def _run_once(s,cmd,scmd,to,oc=None):
        hs=threading.Event()
        try:
            p=subprocess.Popen(scmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,"CREATE_NO_WINDOW")else 0)
            if oc:
                def hb():
                    while not hs.is_set():
                        hs.wait(30)
                        if not hs.is_set():
                            try:oc("")
                            except:pass
                threading.Thread(target=hb,daemon=True).start()
            sl=[];dl=time.time()+to
            assert p.stdout
            for rl in iter(p.stdout.readline,""):
                if time.time()>dl:p.kill();return f"超时({to}s)\n"+"".join(sl)
                l=rl.rstrip()
                if l:sl.append(l+"\n")
                if oc:oc(l+"\n")
            p.stdout.close();se=p.stderr.read()if p.stderr else"";p.wait()
            r="".join(sl)
            if se:r+="\nSTDERR:\n"+se.rstrip()
            r+=f"\nExit code:{p.returncode}"
            hs.set()
            if p.returncode and r.strip():
                try:
                    from.build_patterns import get_engine
                    m=get_engine().match(r)
                    if m and m.get("fix"):r+=f"\n[模式]{m['label']}\n建议:{m['fix']}"
                except:pass
            return r
        except Exception as e:return f"执行出错:{e}"
        finally:hs.set()
    def _is_retryable(s,r):
        for s2 in["EADDRINUSE","port already in use","address already in use","watchdog","timed out","超时","Connection refused","socket hang up","EPIPE","ECONNRESET","ETIMEDOUT"]:
            if s2.lower() in r.lower():return True
        return False
    def _cleanup(s,cmd):
        try:
            if"expo"in cmd:
                r=subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Process -Filter"Name=\'node.exe\'"|Where-Object{$_.CommandLine-match\'expo\'}|Select-Object-ExpandProperty ProcessId'],capture_output=True,text=True,timeout=10,errors='replace')
                for l in r.stdout.strip().split('\n'):
                    p=l.strip()
                    if p and p.isdigit():
                        pi=int(p)
                        if pi not in _agent_spawned_pids:subprocess.run(['taskkill','/F','/PID',str(pi)],capture_output=True,timeout=5)
        except:pass
def _run_powershell(script):
    try:
        p=subprocess.run(["powershell","-NoProfile","-Command",script],capture_output=True,text=True,errors='replace',timeout=30)
        o=p.stdout.rstrip()if p.stdout else"";e=p.stderr.rstrip()if p.stderr else""
        if e:o+=f"\n[stderr]\n{e}"
        if p.returncode and not o:o+=f"\nExit code:{p.returncode}"
        return o or"(无输出)"
    except subprocess.TimeoutExpired:return"超时"
    except Exception as ex:return f"错误:{ex}"
def _handle_bash(command,timeout=120,output_callback=None):
    if"pip install"in command or"npm install"in command:timeout=max(timeout,300)
    timeout=min(timeout,600)
    hr="";is_b=any(k in command for k in['expo','npx ','npm ','pip ','npx'])
    if is_b:
        hr=_self_heal()
        if hr and output_callback:output_callback(f"{hr}")
    ir=is_b and any(k in command for k in['expo','npx ','npm install','pip install'])
    try:
        if sys.platform=="win32":n=command.replace(" && "," ; ")if" && "in command else command;sc=["powershell","-NoProfile","-Command",n]
        else:sc=["bash","-c",command]
        if output_callback and ir:return smart_truncate(BuildRunner().run(command,sc,timeout,output_callback),_TOOL_RESULT_MAX_LENGTH)or"(无输出)"
        elif output_callback:
            hs=threading.Event()
            def hb():
                while not hs.is_set():
                    hs.wait(30)
                    if not hs.is_set():
                        try:output_callback("")
                        except:pass
            threading.Thread(target=hb,daemon=True).start()
            p=subprocess.Popen(sc,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,"CREATE_NO_WINDOW")else 0)
            sl=[];dl=time.time()+timeout
            try:
                assert p.stdout
                for rl in iter(p.stdout.readline,""):
                    if time.time()>dl:p.kill();return f"超时({timeout}s)\n"+"".join(sl)
                    l=rl.rstrip()
                    if l:sl.append(l+"\n");output_callback(l+"\n")
                p.stdout.close();se=p.stderr.read()if p.stderr else"";p.wait()
                r="".join(sl)
                if se and se.strip():r+="\nSTDERR:\n"+se.rstrip()
                if p.returncode:r+=f"\nExit code:{p.returncode}"
                if p.returncode and r.strip():
                    try:
                        from.build_patterns import get_engine
                        m=get_engine().match(r)
                        if m and m.get("fix"):r+=f"\n[模式]{m['label']}\n建议:{m['fix']}"
                    except:pass
            except:r="执行命令出错"
            finally:hs.set()
        else:
            proc=subprocess.run(sc,capture_output=True,text=True,errors='replace',timeout=timeout)
            pts=[]
            if proc.stdout:pts.append(proc.stdout.rstrip())
            if proc.stderr:pts.append(f"STDERR:\n{proc.stderr.rstrip()}")
            if proc.returncode:pts.append(f"Exit code:{proc.returncode}")
            r="\n".join(pts)if pts else"(无输出)"
            if hr:r=hr+"\n"+r
            if proc.returncode and r.strip():
                try:
                    from.build_patterns import get_engine
                    m=get_engine().match(r)
                    if m and m.get("fix"):r+=f"\n[模式]{m['label']}\n建议:{m['fix']}"
                except:pass
        return smart_truncate(r,_TOOL_RESULT_MAX_LENGTH)or"(无输出)"
    except subprocess.TimeoutExpired:return f"命令超时({timeout}秒)"
    except Exception as e:return f"执行错误:{e}"
