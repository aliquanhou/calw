"""tools_analysis"""
from __future__ import annotations
import ast,os,re
from collections import defaultdict
def _find_cycles(g):
    v=set();p=[];cy=[]
    def dfs(n):
        if n in p:i=p.index(n);cy.append(p[i:]+[n]);return
        if n in v:return
        v.add(n);p.append(n)
        for nb in g.get(n,set()):
            if nb in g:dfs(nb)
        p.pop()
    for n in g:dfs(n)
    s=set();u=[]
    for c in cy:
        k=tuple(sorted(c[:-1]))
        if k not in s:s.add(k);u.append(c)
    return u
def _handle_ast(file_path):
    try:
        with open(file_path,encoding="utf-8")as f:src=f.read()
    except FileNotFoundError:return f"找不到:{file_path}"
    except Exception as e:return f"错:{e}"
    try:tree=ast.parse(src)
    except SyntaxError as e:return f"语法错:{e}"
    lines=[f"文件:{file_path}",f"行数:{len(src.splitlines())}"]
    imps=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):
            for a in n.names:imps.append(a.name)
        elif isinstance(n,ast.ImportFrom):
            for a in n.names:imps.append(f"{n.module or ''}.{a.name}")
    if imps:
        lines.append(f"\n---导入({len(imps)})---")
        for i in sorted(set(imps)):lines.append(f"  import {i}")
    for n in ast.iter_child_nodes(tree):
        if isinstance(n,ast.FunctionDef):
            args=[a.arg for a in n.args.args];dcs=[d.id if isinstance(d,ast.Name)else ast.dump(d)for d in n.decorator_list];ds=f" @{', '.join(dcs)}"if dcs else""
            lines.append(f"\n  def {n.name}({', '.join(args)}){ds}");lines.append(f"    L{n.lineno}-L{n.end_lineno}|body={len(n.body)}")
        elif isinstance(n,ast.AsyncFunctionDef):
            args=[a.arg for a in n.args.args];lines.append(f"\n  async def {n.name}({', '.join(args)})");lines.append(f"    L{n.lineno}-L{n.end_lineno}")
        elif isinstance(n,ast.ClassDef):
            bases=[ast.dump(b)for b in n.bases];bs=f"({', '.join(bases)})"if bases else"";lines.append(f"\n  class {n.name}{bs}");lines.append(f"    L{n.lineno}-L{n.end_lineno}")
            for item in ast.iter_child_nodes(n):
                if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    args=[a.arg for a in item.args.args];kd="async def"if isinstance(item,ast.AsyncFunctionDef)else"def"
                    dcs=[d.id if isinstance(d,ast.Name)else ast.dump(d)for d in item.decorator_list];ds=f" @{', '.join(dcs)}"if dcs else""
                    lines.append(f"    {kd} {item.name}({', '.join(args)}){ds}")
    return"\n".join(lines)
def _handle_dep_graph(path=""):
    t=path or os.getcwd()
    if not os.path.exists(t):return f"路径不存在:{t}"
    if os.path.isfile(t):ts=[t];rd=os.path.dirname(t)
    else:
        rd=t;ts=[]
        for rt,_,fs in os.walk(t):
            for f in fs:
                if f.endswith(".py"):ts.append(os.path.join(rt,f))
                if len(ts)>200:break
    if not ts:return"无py文件"
    fm={};mf={}
    for fp in ts:
        rel=os.path.relpath(fp,rd);mod=rel.replace("\\","/").replace("/",".").replace(".py","")
        if mod.endswith(".__init__"):mod=mod[:-9]
        mf[mod]=fp;mf[os.path.basename(fp).replace(".py","")]=fp
    for fp in ts:
        try:
            with open(fp,encoding="utf-8")as f:tree=ast.parse(f.read())
        except:continue
        imps=set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                for a in n.names:imps.add(a.name.split(".")[0])
            elif isinstance(n,ast.ImportFrom):
                if n.module:imps.add(n.module.split(".")[0])
        fm[fp]=imps
    lf=set(ts);id_={}
    for fp in lf:
        int_=set()
        for imp in fm.get(fp,set()):
            if imp in mf:int_.add(mf[imp])
        id_[fp]=int_
    cy=_find_cycles({fp:id_[fp]for fp in lf})
    lines=[f"依赖:{t}",f"文件:{len(ts)}",""]
    dc={}
    for fp in lf:
        for d in id_[fp]:dc[d]=dc.get(d,0)+1
    hub=sorted(dc.items(),key=lambda x:-x[1])[:10]
    if hub:
        lines.append("---核心模块---")
        for fp,c in hub:lines.append(f"  {os.path.relpath(fp,rd)}:{c}处")
    leaves=[fp for fp in lf if not id_.get(fp)]
    if leaves:
        lines.append("\n---叶子模块---")
        for fp in sorted(leaves)[:10]:lines.append(f"  {os.path.relpath(fp,rd)}")
    if cy:
        lines.append(f"\n---循环依赖({len(cy)}个)---")
        for c in cy[:5]:lines.append(f"  {' ->'.join(os.path.relpath(n,rd)for n in c)}")
    all_ext=set()
    for fp in lf:all_ext.update(fm.get(fp,set())-set(mf.keys()))
    if all_ext:
        lines.append(f"\n---外部依赖({len(all_ext)})---")
        for n in sorted(all_ext)[:30]:lines.append(f"  {n}")
    return"\n".join(lines)
def _handle_call_chain(function_name,direction="forward",path="",depth=3):
    t=path or os.getcwd()
    if not os.path.exists(t):return f"不存在:{t}"
    pfs=[]
    if os.path.isfile(t):pfs=[t]if t.endswith(".py")else[]
    else:
        for rt,_,fs in os.walk(t):
            for f in fs:
                if f.endswith(".py"):pfs.append(os.path.join(rt,f))
                if len(pfs)>500:break
    if not pfs:return"无py文件"
    c=defaultdict(lambda:{"calls":set(),"called_by":set(),"file":"","line":0})
    def gfn(n):
        if isinstance(n,ast.Attribute):return gfn(n.value)+"."+n.attr
        elif isinstance(n,ast.Name):return n.id
        return ast.dump(n)
    for fp in pfs:
        try:
            with open(fp,encoding="utf-8")as f:tree=ast.parse(f.read())
        except:continue
        for n in ast.walk(tree):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
                c[n.name]["file"]=os.path.relpath(fp,t if os.path.isdir(t)else os.path.dirname(t));c[n.name]["line"]=n.lineno
        for n in ast.walk(tree):
            if isinstance(n,ast.Call):
                cl=gfn(n.func)
                if cl:
                    for a in ast.walk(tree):
                        if isinstance(a,(ast.FunctionDef,ast.AsyncFunctionDef))and a.lineno<=n.lineno<=(getattr(a,'end_lineno',a.lineno)):
                            c[a.name]["calls"].add(cl);c[cl]["called_by"].add(a.name);break
    rl=[];vis=set()
    if direction=="forward":
        rl.append(f"正向:{function_name}(深度<={depth})\n");_tf(function_name,c,0,depth,rl,vis)
    elif direction=="backward":
        rl.append(f"反向:谁调了{function_name}(深度<={depth})\n");_tb(function_name,c,0,depth,rl,vis)
    else:return"direction须forward/backward"
    if len(rl)==1:rl.append(f"(未找到'{function_name}')")
    return"\n".join(rl)
def _tf(n,c,d,md,l,v):
    if d>md or n in v:return
    v.add(n);p="  "*d+("└ "if d else"");loc=c.get(n,{});fi=f"({loc.get('file','?')}:{loc.get('line','?')})"if loc.get('file')else""
    l.append(f"{p}{n}{fi}")
    for cl in sorted(c.get(n,{}).get("calls",set())):_tf(cl,c,d+1,md,l,v)
def _tb(n,c,d,md,l,v):
    if d>md or n in v:return
    v.add(n);p="  "*d+("└ "if d else"");loc=c.get(n,{});fi=f"({loc.get('file','?')}:{loc.get('line','?')})"if loc.get('file')else""
    l.append(f"{p}{n}{fi}{' (目标)'if d==0 else''}")
    for cr in sorted(c.get(n,{}).get("called_by",set())):_tb(cr,c,d+1,md,l,v)
def _handle_trace_error(error_message,file_path="",depth=2):
    lines=["===错误根因分析===","",f"错误:{error_message[:500]}",""]
    el=error_message.lower();et=""
    for kw,t in[("modulenotfound","import"),("importerror","import"),("attributeerror","attr"),("typeerror","type"),("keyerror","key"),("filenotfound","file"),("syntaxerror","syntax"),("valueerror","value")]:
        if kw in el:et=t;break
    lines.append(f"类型:{et or'未知'}");lines.append("")
    sym=set()
    for m in re.finditer(r"'(\\w+(?:\\.\\w+)*)'",error_message):sym.add(m.group(1))
    for m in re.finditer(r'"(\\w+(?:\\.\\w+)*)"',error_message):sym.add(m.group(1))
    tf=re.findall(r'File "([^"]+)", line (\d+)',error_message)
    if tf:
        lines.append("堆栈:")
        for f,l in tf[:10]:lines.append(f"  {f}:{l}");lines.append("")
    if sym:lines.append(f"符号:{', '.join(list(sym)[:10])}");lines.append("")
    from.tools_shell import _run_powershell
    find=[]
    for s in list(sym)[:5]:
        sn=s.split(".")[-1]
        try:
            r=_run_powershell(f"Select-String -Path '*.py' -Pattern '(class |def |^|\\s+){sn}\\b' -Recurse -SimpleMatch -ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty Line")
            if r and"找不到"not in r:find.append(f"'{s}':{r[:300]}")
        except:pass
    if not find:lines.append("未找到相关定义。")
    else:
        for f in find[:5]:lines.append(f);lines.append("")
    if et=="import"and sym:
        mb=list(sym)[0].split(".")[0];lines.append(f"检查'{mb}':")
        try:
            ck=_run_powershell(f"pip list 2>$null | Select-String '{mb}'")
            if ck and mb.lower() in ck.lower():lines.append("  ok")
            else:lines.append(f"  {mb}未安装\n  建议:pip install {mb}")
        except:pass
    for m in re.finditer(r"(?:No such file|ENOENT).*'([^']+)'",error_message):
        mp=m.group(1);lines.append(f"缺文件:{mp}")
        alt=os.path.join(os.getcwd(),mp.lstrip("./\\"))
        if os.path.exists(alt):lines.append(f"  在{alt}找到");lines.append("")
    lines.append("===完成===");return"\n".join(lines)
