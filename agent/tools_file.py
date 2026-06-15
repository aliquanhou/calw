"""tools_file"""
from __future__ import annotations
import glob,hashlib,json,os,re,subprocess,sys
from.tools_core import _file_backups,_written_this_session,_consecutive_fails,_session_lessons,_TOOL_RESULT_MAX_LENGTH,smart_truncate
def _cr(f,m=10):
    b=os.path.basename(f);n=os.path.splitext(b)[0]
    if not n or n=="index":return[]
    r=[]
    try:
        cwd=os.getcwd()
        for rt,ds,fs in os.walk(cwd):
            ds[:]=[d for d in ds if d not in(".git","node_modules","__pycache__",".venv",".claude")]
            for fn in fs:
                if not fn.endswith((".ts",".tsx",".js",".jsx",".py")):continue
                fp=os.path.join(rt,fn)
                try:
                    with open(fp,"r",encoding="utf-8",errors="replace")as fh:
                        if n in fh.read(16384):
                            rel=os.path.relpath(fp,cwd)
                            if rel!=os.path.relpath(f,cwd):r.append(rel)
                            if len(r)>=m:return r
                except:continue
    except:pass
    return r
def _rv(f,oc=None):
    e=os.path.splitext(f)[1].lower();he=[];ws=[]
    if e==".py":
        try:
            r=subprocess.run([sys.executable,"-m","py_compile",f],capture_output=True,text=True,errors="replace",timeout=15)
            if r.returncode:he.append(f"Python语法错:\n{r.stderr.strip()}")
        except:pass
    if e==".json"and"package"in os.path.basename(f).lower():
        try:
            with open(f,encoding="utf-8")as fh:json.load(fh)
        except json.JSONDecodeError as e:he.append(f"JSON无效:{e}")
    return"\n".join(he),"\n".join(ws)
def _rb(f):
    o=_file_backups.get(f)
    try:
        if o is not None:
            with open(f,"w",encoding="utf-8")as fh:fh.write(o)
            return"已恢复"
        else:
            if os.path.exists(f):os.remove(f)
            return"已删除新文件"
    except Exception as e:return f"回滚失败:{e}"
_check_references=_cr;_run_validation=_rv;_restore_backup=_rb
def _handle_read(file_path):
    fp=os.path.abspath(file_path)
    if not os.path.exists(fp):return f"错误:文件不存在:{fp}"
    if not os.path.isfile(fp):return f"错误:不是文件:{fp}"
    try:
        with open(fp,"r",encoding="utf-8",errors="replace")as f:return smart_truncate(f.read(),_TOOL_RESULT_MAX_LENGTH)
    except Exception as e:return f"读取出错:{e}"
def _handle_write(file_path,content):
    fp=os.path.normpath(os.path.abspath(file_path))
    if os.name=="nt"and len(fp)>=2 and fp[1]==":":fp=fp[0].upper()+fp[1:]
    d=os.path.dirname(fp)
    if d:os.makedirs(d,exist_ok=True)
    oc=None
    if os.path.exists(fp):
        try:oc=open(fp,"r",encoding="utf-8").read()
        except:pass
    _file_backups[fp]=oc;ch=hashlib.md5(content.encode("utf-8")).hexdigest();fk=f"{fp}:{ch}"
    if fk in _written_this_session:return f"相同内容已写入过{fp}。"
    _written_this_session.add(fk)
    try:
        open(fp,"w",encoding="utf-8").write(content)
        r=f"成功写入{len(content.encode('utf-8'))}字节到{fp}"
        he,ws=_rv(fp)
        if he:
            _rb(fp);_consecutive_fails[fk]=_consecutive_fails.get(fk,0)+1
            _session_lessons.append({"type":"write_failed","file":fp,"hash":ch,"error":he[:200],"attempt":_consecutive_fails[fk],"timestamp":__import__('time').time()})
            return f"验证失败:已回滚\n{he}"+(f"\n[教训#{_consecutive_fails[fk]}]需换方案"if _consecutive_fails[fk]>=2 else"")
        if ws:r+=f"\n{ws}"
        refs=_cr(fp)
        if refs:r+=f"\n{len(refs)}个文件可能引用:"+''.join(f"\n  {ref}"for ref in refs[:6])
        for k in list(_consecutive_fails.keys()):
            if fp in k:del _consecutive_fails[k]
        return r
    except Exception as e:return f"写入出错:{e}"
def _handle_edit(file_path,old_string,new_string):
    fp=os.path.normpath(os.path.abspath(file_path))
    if os.name=="nt"and len(fp)>=2 and fp[1]==":":fp=fp[0].upper()+fp[1:]
    if not os.path.exists(fp):return f"错误:文件不存在:{fp}"
    try:content=open(fp,"r",encoding="utf-8").read()
    except Exception as e:return f"读取出错:{e}"
    c=content.count(old_string)
    if c==0:return f"错误:未找到替换字符串:{fp}"
    if c>1:return f"错误:字符串出现{c}次,必须唯一"
    _file_backups[fp]=content;nc=content.replace(old_string,new_string);ch=hashlib.md5(nc.encode("utf-8")).hexdigest()
    try:
        open(fp,"w",encoding="utf-8").write(nc)
        try:v=open(fp,"r",encoding="utf-8").read()
        except:v=""
        if old_string in v:
            try:
                open(fp,"w",encoding="utf-8").write(nc);v2=open(fp,"r",encoding="utf-8").read()
                if old_string in v2:return f"写入后验证仍失败,请用write重写。"
            except Exception as e:return f"写入失败(重试):{e}"
        r="成功替换1处"
        he,ws=_rv(fp)
        if he:_rb(fp);_consecutive_fails[f"edit:{fp}:{ch}"]=_consecutive_fails.get(f"edit:{fp}:{ch}",0)+1;return f"验证失败:已回滚\n{he}"
        if ws:r+=f"\n{ws}"
        refs=_cr(fp)
        if refs:r+=f"\n{len(refs)}个文件可能引用:"+''.join(f"\n  {ref}"for ref in refs[:6])
        for k in list(_consecutive_fails.keys()):
            if fp in k:del _consecutive_fails[k]
        return r
    except Exception as e:return f"写入出错:{e}"

def _handle_replace(file_path,search,replace_text,partial=False):
    fp=os.path.normpath(os.path.abspath(file_path))
    if os.name=="nt"and len(fp)>=2 and fp[1]==":":fp=fp[0].upper()+fp[1:]
    if not os.path.exists(fp):return f"错误:文件不存在:{fp}"
    try:content=open(fp,"r",encoding="utf-8").read()
    except Exception as e:return f"读取出错:{e}"
    if not partial and content.count(search)==1:return _handle_edit(file_path,search,replace_text)
    search_lines=[l.strip()for l in search.split('\n')if l.strip()]
    content_lines=content.split('\n')
    best_idx=-1;best_score=0
    for i in range(len(content_lines)-len(search_lines)+1):
        score=sum(1 for j,s in enumerate(search_lines)if s in content_lines[i+j]or content_lines[i+j].strip()==s)
        if score>best_score:best_score=score;best_idx=i
    if best_idx<0 or best_score<len(search_lines)*0.5:return f"错误:无法定位匹配内容(最佳{best_score}/{len(search_lines)})"
    _file_backups[fp]=content
    new_lines=content_lines[:best_idx]+[replace_text]+content_lines[best_idx+len(search_lines):]
    try:
        open(fp,"w",encoding="utf-8").write('\n'.join(new_lines))
        return f"成功替换1处(模糊匹配,置信度{best_score}/{len(search_lines)})"
    except Exception as e:return f"写入出错:{e}"

def _handle_glob(pattern,path=None):
    root=os.path.abspath(path)if path else os.getcwd()
    if os.name=="nt":root=root.replace("\\","/")
    def eb(p):
        m=re.search(r'\{([^}]+)\}',p)
        if not m:return[p]
        alts=m.group(1).split(',');pre=p[:m.start()];suf=p[m.end():]
        return[x for a in alts for x in eb(pre+a+suf)]
    ms=sorted(set(x for p in eb(pattern)for x in glob.glob((p.replace("\\","/")if os.name=="nt"else p)if os.path.isabs(p)else root+"/"+p,recursive=True)or[]))
    if not ms:return"无匹配"
    rl=[]
    for m in ms:
        try:rl.append(os.path.relpath(m,root))
        except:rl.append(m)
    return"\n".join(rl)
def _handle_grep(pattern,path=None,glob_pattern=None,output_mode="content"):
    sp=os.path.abspath(path)if path else os.getcwd()
    try:cp=re.compile(pattern)
    except re.error as e:return f"正则无效:{e}"
    SKIP={".git","__pycache__","node_modules",".venv",".env","venv",".tox","build","dist",".idea",".vscode"}
    ms=[];seen=set()
    try:
        if os.path.isfile(sp):fs=[sp]
        else:
            fs=[]
            for rt,ds,fns in os.walk(sp):
                ds[:]=[d for d in ds if d not in SKIP]
                for fn in fns:
                    fp=os.path.join(rt,fn)
                    if glob_pattern:
                        if glob.fnmatch.fnmatch(fn,glob_pattern):fs.append(fp)
                    else:
                        try:
                            if b"\x00"not in open(fp,"rb").read(8192):fs.append(fp)
                        except:pass
        for fp in fs:
            try:
                with open(fp,"r",encoding="utf-8",errors="replace")as f:
                    for ln,line in enumerate(f,1):
                        if cp.search(line):
                            rp=os.path.relpath(fp,os.getcwd())
                            if output_mode=="files_with_matches":
                                if rp not in seen:seen.add(rp);ms.append(rp)
                            else:ms.append(f"{rp}:{ln}:{line.rstrip()}")
            except:continue
        return smart_truncate("\n".join(ms),_TOOL_RESULT_MAX_LENGTH)if ms else"无匹配"
    except Exception as e:return f"grep出错:{e}"
def _handle_revert(file_path=""):
    if not file_path:
        if not _file_backups:return"无备份"
        return"\n".join([f"可恢复({len(_file_backups)}个):"]+[f"  {k}[{'有备份'if v else'新文件'}]"for k,v in sorted(_file_backups.items())])
    ap=os.path.abspath(file_path)
    return _rb(ap)if ap in _file_backups else"错误:无备份。"
