"""tools_file"""
from __future__ import annotations
import difflib,glob,hashlib,json,os,re,subprocess,sys
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
def _make_diff(old: str, new: str, filepath: str, max_lines: int = 20) -> str:
    """Generate a unified diff string between old and new content."""
    old_lines = old.split("\n") if old else []
    new_lines = new.split("\n") if new else []
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=filepath, tofile=filepath,
        lineterm="", n=2,
    ))
    if not diff:
        return "[无差异]"
    output = "\n".join(diff[:max_lines])
    if len(diff) > max_lines:
        output += f"\n... (diff 共 {len(diff)} 行)"
    return output

def _handle_write(file_path, content):
    fp = os.path.normpath(os.path.abspath(file_path))
    if os.name == "nt" and len(fp) >= 2 and fp[1] == ":":
        fp = fp[0].upper() + fp[1:]
    d = os.path.dirname(fp)
    if d: os.makedirs(d, exist_ok=True)
    oc = None
    is_update = os.path.exists(fp)
    if is_update:
        try: oc = open(fp, "r", encoding="utf-8").read()
        except: pass
    _file_backups[fp] = oc
    ch = hashlib.md5(content.encode("utf-8")).hexdigest()
    fk = f"{fp}:{ch}"
    if fk in _written_this_session:
        return f"相同内容已写入过{fp}。"
    _written_this_session.add(fk)
    try:
        open(fp, "w", encoding="utf-8").write(content)
        r = ""
        if is_update and oc is not None:
            diff = _make_diff(oc, content, fp)
            r += f"📝 {fp}\n{diff}\n"
        r += f"✅ 写入完成: {len(content.encode('utf-8'))} 字节"
        he, ws = _rv(fp)
        if he:
            _rb(fp); _consecutive_fails[fk] = _consecutive_fails.get(fk, 0) + 1
            _session_lessons.append({"type": "write_failed", "file": fp, "hash": ch,
                                      "error": he[:200], "attempt": _consecutive_fails[fk],
                                      "timestamp": __import__("time").time()})
            return f"验证失败:已回滚\n{he}" + (f"\n[教训#{_consecutive_fails[fk]}]需换方案" if _consecutive_fails[fk] >= 2 else "")
        if ws: r += f"\n{ws}"
        refs = _cr(fp)
        if refs:
            r += "\n" + f"\n{len(refs)}个文件可能引用:" + "".join(f"\n  {r}" for r in refs[:6])
        for k in list(_consecutive_fails.keys()):
            if fp in k: del _consecutive_fails[k]
        return r
    except Exception as e:
        return f"写入出错:{e}"
def _handle_edit(file_path, old_string, new_string):
    fp = os.path.normpath(os.path.abspath(file_path))
    if os.name == "nt" and len(fp) >= 2 and fp[1] == ":":
        fp = fp[0].upper() + fp[1:]
    if not os.path.exists(fp):
        return f"错误:文件不存在:{fp}"
    try:
        content = open(fp, "r", encoding="utf-8").read()
    except Exception as e:
        return f"读取出错:{e}"
    c = content.count(old_string)
    if c == 0:
        return f"错误:未找到替换字符串:{fp}"
    if c > 1:
        return f"错误:字符串出现{c}次,必须唯一"
    _file_backups[fp] = content
    nc = content.replace(old_string, new_string)
    ch = hashlib.md5(nc.encode("utf-8")).hexdigest()
    diff = _make_diff(content, nc, fp)
    try:
        open(fp, "w", encoding="utf-8").write(nc)
        try:
            v = open(fp, "r", encoding="utf-8").read()
        except:
            v = ""
        if old_string in v:
            try:
                open(fp, "w", encoding="utf-8").write(nc)
                v2 = open(fp, "r", encoding="utf-8").read()
                if old_string in v2:
                    return f"写入后验证仍失败,请用write重写。"
            except Exception as e:
                return f"写入失败(重试):{e}"
        r = f"✅ 编辑成功 (1处)\n{diff}"
        he, ws = _rv(fp)
        if he:
            _rb(fp)
            _consecutive_fails[f"edit:{fp}:{ch}"] = _consecutive_fails.get(f"edit:{fp}:{ch}", 0) + 1
            return f"验证失败:已回滚\n{he}"
        if ws:
            r += f"\n{ws}"
        refs = _cr(fp)
        if refs:
            r += f"\n{len(refs)}个文件可能引用:" + "".join(f"\n  {r}" for r in refs[:6])
        for k in list(_consecutive_fails.keys()):
            if fp in k:
                del _consecutive_fails[k]
        return r
    except Exception as e:
        return f"写入出错:{e}"

# ── SEARCH/REPLACE 引擎 ──────────────────────────────────────
# 多策略智能替换：精确匹配 → 锚点匹配 → 模糊行匹配 → 行号引用
# 成功后输出 diff，自动回滚+重试

def _handle_replace(file_path, search, replace_text, partial=False):
    """SEARCH/REPLACE: 多策略智能替换引擎。"""
    fp = os.path.normpath(os.path.abspath(file_path))
    if os.name == "nt" and len(fp) >= 2 and fp[1] == ":":
        fp = fp[0].upper() + fp[1:]
    if not os.path.exists(fp):
        return f"错误:文件不存在:{fp}"
    try:
        content = open(fp, "r", encoding="utf-8").read()
    except Exception as e:
        return f"读取出错:{e}"

    search = search.rstrip("\n")
    old_content = content
    _file_backups[fp] = old_content

    # no-op
    if search == replace_text:
        return "✅ 替换成功 [no-op: 内容相同，无需修改]"
    if not search:
        return "✅ 替换成功 [no-op: search 为空]"

    # ── strategy 1: 精确匹配 ──
    count = content.count(search)
    if count == 1:
        return _do_replace(fp, old_content, content.replace(search, replace_text, 1),
                           search, replace_text, "精确匹配")

    # ── strategy 2: 锚点匹配 ──
    if count == 0:
        search_lines = search.split("\n")
        for anchor in search_lines:
            anchor_s = anchor.strip()
            if not anchor_s or len(anchor_s) < 8:
                continue
            ac = content.count(anchor_s)
            if ac == 1:
                cl = content.split("\n")
                found_idx = -1
                for i, line in enumerate(cl):
                    if anchor_s in line or line.strip() == anchor_s:
                        found_idx = i
                        break
                if found_idx >= 0:
                    new_lines = cl[:found_idx] + [replace_text] + cl[found_idx + len(search_lines):]
                    return _do_replace(fp, old_content, "\n".join(new_lines),
                                       search, replace_text,
                                       f"锚点匹配(行{found_idx+1}:{anchor_s[:40]})")

    # ── strategy 3: 模糊行匹配 ──
    search_lines_stripped = [s.strip() for s in search.split("\n") if s.strip()]
    if len(search_lines_stripped) >= 1:
        content_lines = old_content.split("\n")
        best_idx = -1
        best_score = 0
        for i in range(len(content_lines) - len(search_lines_stripped) + 1):
            score = sum(
                1 for j, s in enumerate(search_lines_stripped)
                if s in content_lines[i + j] or content_lines[i + j].strip() == s
            )
            if score > best_score:
                best_score = score
                best_idx = i
        threshold = max(1, len(search_lines_stripped) * 0.6)
        if best_idx >= 0 and best_score >= threshold:
            new_lines = content_lines[:best_idx] + [replace_text] + content_lines[best_idx + len(search_lines_stripped):]
            return _do_replace(fp, old_content, "\n".join(new_lines),
                               search, replace_text,
                               f"模糊匹配(置信度{best_score}/{len(search_lines_stripped)},行{best_idx+1})")

    # ── strategy 4: 行号引用 ──
    if search.startswith(":") and search[1:].strip().isdigit():
        line_no = int(search[1:].strip())
        content_lines = old_content.split("\n")
        if 1 <= line_no <= len(content_lines):
            old_line = content_lines[line_no - 1]
            new_lines = content_lines[:line_no - 1] + [replace_text] + content_lines[line_no:]
            return _do_replace(fp, old_content, "\n".join(new_lines),
                               old_line, replace_text,
                               f"行号替换(L{line_no})")

    # ── all strategies failed ──
    hint = ""
    if len(search) > 50:
        hint = f"  search前50字符:{search[:50]}"
    return f"错误:无法定位匹配内容 (精确匹配出现{count}次){hint}"


def _do_replace(file_path: str, old_content: str, new_content: str,
                search: str, replace_text: str, strategy: str) -> str:
    """执行替换写入，生成 diff，语法验证，返回结果。"""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return f"写入出错:{e}"

    # 生成 diff
    old_lines = old_content.split("\n")
    new_lines_res = new_content.split("\n")
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines_res,
        fromfile=file_path, tofile=file_path,
        lineterm="",
        n=2,
    ))
    diff_output = "\n".join(diff_lines[:30])
    if len(diff_lines) > 30:
        diff_output += f"\n... (diff 共 {len(diff_lines)} 行)"

    # 语法验证
    he, ws = _rv(file_path)
    warnings = ""
    if he:
        _restore_backup(file_path)
        return f"验证失败:语法错误,已回滚\n{he}\n策略:{strategy}"
    if ws:
        warnings = "\n" + ws

    # 引用检查
    refs = _cr(file_path)
    if refs:
        warnings += f"\n{len(refs)}个文件可能引用:" + "".join(f"\n  {r}" for r in refs[:6])

    return f"✅ 替换成功 [{strategy}]\n{diff_output}{warnings}"

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

# ── 文件系统全操作 ────────────────────────────────────

def _handle_move(source, destination):
    """移动/重命名文件或目录。"""
    src = os.path.abspath(source)
    dst = os.path.abspath(destination)
    if not os.path.exists(src):
        return f"错误:源不存在:{src}"
    try:
        _file_backups[src] = open(src, "r", encoding="utf-8").read() if os.path.isfile(src) else None
    except: pass
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        return f"✅ 移动成功: {src} → {dst}"
    except Exception as e:
        return f"错误:移动失败:{e}"

def _handle_copy(source, destination, recursive=False):
    """复制文件或目录。"""
    import shutil
    src = os.path.abspath(source); dst = os.path.abspath(destination)
    if not os.path.exists(src):
        return f"错误:源不存在:{src}"
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            if not recursive:
                return f"错误:是目录,需 recursive=true"
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return f"✅ 复制成功: {src} → {dst}"
    except Exception as e:
        return f"错误:复制失败:{e}"

def _handle_delete(path, recursive=False):
    """删除文件或空目录。"""
    target = os.path.abspath(path)
    if not os.path.exists(target):
        return f"错误:不存在:{target}"
    try:
        if os.path.isdir(target):
            if not recursive:
                os.rmdir(target)
            else:
                import shutil; shutil.rmtree(target)
        else:
            os.remove(target)
        return f"✅ 已删除: {target}"
    except OSError as e:
        if "directory not empty" in str(e).lower():
            return f"错误:目录非空,需 recursive=true"
        return f"错误:删除失败:{e}"
    except Exception as e:
        return f"错误:删除失败:{e}"

def _handle_mkdir(path, parents=False):
    """创建目录。"""
    target = os.path.abspath(path)
    try:
        if parents:
            os.makedirs(target, exist_ok=True)
        else:
            os.mkdir(target)
        return f"✅ 已创建目录: {target}"
    except FileExistsError:
        return f"目录已存在:{target}"
    except Exception as e:
        return f"错误:创建失败:{e}"

def _handle_download(url, destination):
    """从 URL 下载文件。"""
    import urllib.request
    dst = os.path.abspath(destination)
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        urllib.request.urlretrieve(url, dst)
        size = os.path.getsize(dst) if os.path.exists(dst) else 0
        return f"✅ 下载成功: {url} → {dst} ({size} 字节)"
    except Exception as e:
        return f"错误:下载失败:{e}"
