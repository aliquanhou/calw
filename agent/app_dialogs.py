"""Extended dialogs for Calw."""
from __future__ import annotations
import os, re, threading, time, tkinter as tk, json
import customtkinter as ctk
FONT_FAMILY="Microsoft YaHei"; FONT_MONO="Consolas"; COLOR_OK="#4CAF50"

class CodeReviewDialog(ctk.CTkToplevel):
    def __init__(self,parent,agent,_scb=None):
        super().__init__(parent); self.title("\U0001f50d 代码审查"); self.geometry("900x700")
        self.minsize(700,500); self.transient(parent); self.grab_set(); self.agent=agent; self._busy=False; self._last=""
        self._build()
    def _build(self):
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(4,weight=1)
        c=ctk.CTkFrame(self,fg_color="transparent"); c.grid(row=0,column=0,sticky="ew",padx=16,pady=(16,4))
        self.eff=ctk.StringVar(value="medium")
        ctk.CTkLabel(c,text="深度:",font=(FONT_FAMILY,13)).pack(side="left")
        for v,l in [("low","快速"),("medium","中等"),("high","深入")]: ctk.CTkRadioButton(c,text=l,value=v,variable=self.eff,font=(FONT_FAMILY,12)).pack(side="left",padx=4)
        b=ctk.CTkFrame(self,fg_color="transparent"); b.grid(row=1,column=0,sticky="ew",padx=16,pady=(4,8))
        for i in range(4): b.grid_columnconfigure(i,weight=1)
        self.b1=ctk.CTkButton(b,text="\U0001f4dd 审查变更",command=self._diff,fg_color="#2a2a4a"); self.b1.grid(row=0,column=0,padx=2,sticky="ew")
        self.b2=ctk.CTkButton(b,text="\U0001f4c4 审查文件",command=self._file,fg_color="#2a2a4a"); self.b2.grid(row=0,column=1,padx=2,sticky="ew")
        self.b3=ctk.CTkButton(b,text="\U0001f4be 导出",command=self._export,fg_color="#333"); self.b3.grid(row=0,column=2,padx=2,sticky="ew")
        ctk.CTkButton(b,text="关闭",command=self.destroy,fg_color="#555").grid(row=0,column=3,padx=2,sticky="ew")
        pf=ctk.CTkFrame(self,fg_color="transparent"); pf.grid(row=2,column=0,sticky="ew",padx=16)
        pf.grid_columnconfigure(1,weight=1); self.fp=ctk.StringVar(value=os.getcwd())
        ctk.CTkLabel(pf,text="路径:",font=(FONT_FAMILY,12)).grid(row=0,column=0,padx=(0,4))
        ctk.CTkEntry(pf,textvariable=self.fp,font=(FONT_MONO,12),height=30).grid(row=0,column=1,sticky="ew")
        self.sb=ctk.CTkLabel(self,text="就绪",font=(FONT_FAMILY,11),text_color="#888",anchor="w"); self.sb.grid(row=3,column=0,sticky="ew",padx=16)
        self.tx=ctk.CTkTextbox(self,font=(FONT_MONO,12),wrap="word"); self.tx.grid(row=4,column=0,sticky="nsew",padx=16,pady=(0,16))
        self.tx.insert("1.0","点击「审查变更」或「审查文件」开始。")
    def _busy(self,b):
        self._b=b; [w.configure(state="disabled" if b else "normal") for w in (self.b1,self.b2,self.b3)]
        self.sb.configure(text="审查中..." if b else "就绪")
    def _diff(self):
        if self._b or not self.agent: return
        self._busy(True); self.tx.delete("1.0","end"); self.tx.insert("1.0","获取变更差异...\n"); threading.Thread(target=self._do_diff,daemon=True).start()
    def _do_diff(self):
        from .reviewer import review_working_tree, format_report
        def s(sp,ms,ts): return self.agent.provider.stream_chat(sp,ms,ts)
        r,_=review_working_tree(None,s,self.eff.get()); self.after(0,lambda: self._show(r))
    def _file(self):
        if self._b or not self.agent: return
        p=self.fp.get().strip()
        if not os.path.exists(p): self.tx.delete("1.0","end"); self.tx.insert("1.0",f"❌ 文件不存在: {p}"); return
        self._busy(True); self.tx.delete("1.0","end"); self.tx.insert("1.0",f"审查: {p}\n"); threading.Thread(target=self._do_file,args=(p,),daemon=True).start()
    def _do_file(self,p):
        from .reviewer import review_file, format_report
        def s(sp,ms,ts): return self.agent.provider.stream_chat(sp,ms,ts)
        r=review_file(p,s,self.eff.get()); self.after(0,lambda: self._show(r))
    def _show(self,r):
        self._busy(False); from .reviewer import format_report; self._last=format_report(r)
        self.tx.delete("1.0","end"); self.tx.insert("1.0",self._last); self.sb.configure(text=r.summary)
    def _export(self):
        if not self._last: return
        from tkinter import filedialog, messagebox
        p=filedialog.asksaveasfilename(defaultextension=".md",filetypes=[("Markdown","*.md")])
        if p:
            with open(p,"w",encoding="utf-8") as f: f.write(self._last)
            messagebox.showinfo("成功",f"已保存 {p}")

class ResearchDialog(ctk.CTkToplevel):
    def __init__(self,parent,agent,_scb=None):
        super().__init__(parent); self.title("\U0001f4ca 深度研究"); self.geometry("850x750")
        self.minsize(650,500); self.transient(parent); self.grab_set(); self.agent=agent; self._busy=False; self._last=""
        self._build()
    def _build(self):
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(3,weight=1)
        i=ctk.CTkFrame(self,fg_color="transparent"); i.grid(row=0,column=0,sticky="ew",padx=16,pady=(16,4)); i.grid_columnconfigure(0,weight=1)
        ctk.CTkLabel(i,text="研究问题:",font=(FONT_FAMILY,14,"bold")).grid(row=0,column=0,sticky="w")
        self.e=ctk.CTkEntry(i,font=(FONT_MONO,14),height=38,placeholder_text="输入研究问题...")
        self.e.grid(row=1,column=0,sticky="ew"); self.e.bind("<Return>",lambda e:self._go())
        self.bg=ctk.CTkButton(i,text="\U0001f50d 开始",width=100,height=38,font=(FONT_FAMILY,14),fg_color="#1565C0",command=self._go)
        self.bg.grid(row=1,column=1,padx=(8,0))
        o=ctk.CTkFrame(self,fg_color="transparent"); o.grid(row=1,column=0,sticky="ew",padx=16,pady=(4,8))
        self.sv=ctk.StringVar(value="5"); self.fv=ctk.BooleanVar(value=True)
        ctk.CTkLabel(o,text="来源:",font=(FONT_FAMILY,12)).pack(side="left")
        ctk.CTkOptionMenu(o,variable=self.sv,values=["3","5","8","10"],width=60,font=(FONT_FAMILY,12),dropdown_font=(FONT_FAMILY,12)).pack(side="left",padx=4)
        ctk.CTkCheckBox(o,text="事实核查",variable=self.fv,font=(FONT_FAMILY,12)).pack(side="left",padx=8)
        self.pl=ctk.CTkLabel(self,text="",font=(FONT_FAMILY,12),text_color="#888",anchor="w"); self.pl.grid(row=2,column=0,sticky="ew",padx=16)
        self.pb=ctk.CTkProgressBar(self,height=6); self.pb.grid(row=2,column=0,sticky="ew",padx=16,pady=(16,4)); self.pb.set(0)
        self.tx=ctk.CTkTextbox(self,font=(FONT_MONO,12),wrap="word"); self.tx.grid(row=3,column=0,sticky="nsew",padx=16,pady=(0,16))
    def _go(self):
        if self._busy or not self.agent: return
        q=self.e.get().strip()
        if not q: return
        self._busy=True; self.bg.configure(state="disabled",text="研究中..."); self.tx.delete("1.0","end"); self.pb.set(0); self.pl.configure(text="")
        threading.Thread(target=self._run,args=(q,),daemon=True).start()
    def _run(self,q):
        from .researcher import deep_research, format_report
        def s(sp,ms,ts): return self.agent.provider.stream_chat(sp,ms,ts)
        st=[]; lk=threading.Lock()
        def pr(m):
            with lk: st.append(m)
            self.after(0,lambda: self._up(m,min(len(st)*2,6)/6))
        r=deep_research(q,s,int(self.sv.get()),self.fv.get(),pr); self._last=format_report(r); self.after(0,self._done)
    def _up(self,m,p): self.pl.configure(text=m); self.pb.set(p); self.tx.insert("end",f"{m}\n"); self.tx.see("end")
    def _done(self):
        self._busy=False; self.bg.configure(state="normal",text="\U0001f50d 开始"); self.tx.delete("1.0","end"); self.tx.insert("1.0",self._last)

class SchedulerDialog(ctk.CTkToplevel):
    def __init__(self,parent,sched):
        super().__init__(parent); self.title("⏰ 定时任务"); self.geometry("780x650"); self.minsize(600,450)
        self.transient(parent); self.grab_set(); self.s=sched; self._build(); self._ref()
    def _build(self):
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(1,weight=1)
        t=ctk.CTkFrame(self,fg_color="transparent"); t.grid(row=0,column=0,sticky="ew",padx=16,pady=(16,8))
        ctk.CTkLabel(t,text="名称:",font=(FONT_FAMILY,12)).grid(row=0,column=0)
        self.ne=ctk.CTkEntry(t,font=(FONT_FAMILY,12),height=30); self.ne.grid(row=0,column=1,sticky="ew",padx=4); self.ne.insert(0,"任务")
        ctk.CTkLabel(t,text="Cron:",font=(FONT_FAMILY,12)).grid(row=0,column=2,padx=4)
        self.ce=ctk.CTkEntry(t,font=(FONT_MONO,12),height=30,placeholder_text="*/5 * * * *"); self.ce.grid(row=0,column=3,sticky="ew",padx=4)
        ctk.CTkButton(t,text="添加",width=60,command=self._add,fg_color="#1565C0").grid(row=0,column=4,padx=2)
        ctk.CTkButton(t,text="?",width=30,command=self._help,fg_color="#444").grid(row=0,column=5)
        ctk.CTkLabel(t,text="命令:",font=(FONT_FAMILY,12)).grid(row=1,column=0,pady=(4,0))
        self.cde=ctk.CTkEntry(t,font=(FONT_MONO,12),height=30,placeholder_text="Write-Host 'Hello'"); self.cde.grid(row=1,column=1,columnspan=5,sticky="ew",pady=(4,0))
        self._desc_var=ctk.CTkLabel(t,text="",font=(FONT_FAMILY,11),text_color="#888"); self._desc_var.grid(row=2,column=0,columnspan=6,sticky="w")
        self.ce.bind("<KeyRelease>",lambda e:self._desc())
        m=ctk.CTkFrame(self,fg_color="transparent"); m.grid(row=1,column=0,sticky="nsew",padx=16,pady=4); m.grid_columnconfigure(0,weight=1); m.grid_rowconfigure(1,weight=1)
        ctk.CTkLabel(m,text="\U0001f4cb 任务列表",font=(FONT_FAMILY,13,"bold")).grid(row=0,column=0,sticky="w")
        self.lb=tk.Listbox(m,font=(FONT_MONO,11),bg="#1e1e1e",fg="#e0e0e0",selectbackground="#2a2a4a",borderwidth=0,highlightthickness=0)
        self.lb.grid(row=1,column=0,sticky="nsew"); self.lb.bind("<Delete>",lambda e:self._del())
        br=ctk.CTkFrame(m,fg_color="transparent"); br.grid(row=2,column=0,sticky="ew",pady=4)
        ctk.CTkButton(br,text="\U0001f5d1 删除",command=self._del,fg_color="#5a2020").pack(side="left",padx=2)
        ctk.CTkButton(br,text="⏯ 切换",command=self._tog,fg_color="#333").pack(side="left",padx=2)
        ctk.CTkButton(br,text="\U0001f504 刷新",command=self._ref,fg_color="#333").pack(side="left",padx=2)
        bo=ctk.CTkFrame(self,fg_color="transparent"); bo.grid(row=2,column=0,sticky="nsew",padx=16,pady=(4,16)); bo.grid_columnconfigure(0,weight=1); bo.grid_rowconfigure(1,weight=1)
        ctk.CTkLabel(bo,text="\U0001f4dc 事件",font=(FONT_FAMILY,12,"bold")).grid(row=0,column=0,sticky="w")
        self.et=ctk.CTkTextbox(bo,font=(FONT_MONO,11),height=120); self.et.grid(row=1,column=0,sticky="nsew")
        self.st=ctk.CTkLabel(self,text="就绪",font=(FONT_FAMILY,11),text_color="#888",anchor="w"); self.st.grid(row=3,column=0,sticky="ew",padx=16)
        self.s.start(on_trigger=lambda e:self.after(0,self._ref))
    def _desc(self):
        from .scheduler import CronParser; e=self.ce.get().strip(); self._desc_var.configure(text=CronParser.describe(e) if e else "")
    def _add(self):
        n=self.ne.get().strip() or "任务"; c=self.ce.get().strip(); cmd=self.cde.get().strip()
        if not c or not cmd: return
        self.s.add_task(n,c,cmd); self._ref(); self.st.configure(text=f"✅ 已添加: {n} [{c}]")
    def _del(self):
        s=self.lb.curselection()
        if not s: return
        tasks=self.s.list_tasks()
        if s[0]<len(tasks): self.s.remove_task(tasks[s[0]].id); self._ref()
    def _tog(self):
        s=self.lb.curselection()
        if not s: return
        tasks=self.s.list_tasks()
        if s[0]<len(tasks): t=self.s.get_task(tasks[s[0]].id);
        if t: t.enabled=not t.enabled; self._ref()
    def _ref(self):
        self.lb.delete(0,"end")
        for t in self.s.list_tasks():
            st="\U0001f7e2" if t.enabled else "\U0001f534"; last=time.strftime("%H:%M",time.localtime(t.last_run)) if t.last_run else "--"
            self.lb.insert("end",f"{st} {t.name}  {t.cron_expr}  上次:{last} ({t.run_count}次)")
        self.et.delete("1.0","end")
        for ev in reversed(self.s.get_recent_events(15)):
            ts=time.strftime("%H:%M:%S",time.localtime(ev.timestamp)); self.et.insert("end",f"[{ts}] {ev.task_name}: {ev.result[:100]}\n")
    @staticmethod
    def _help():
        w=ctk.CTkToplevel(); w.title("Cron"); w.geometry("400x350")
        t=ctk.CTkTextbox(w,font=(FONT_MONO,12)); t.pack(fill="both",expand=True,padx=16,pady=16)
        t.insert("1.0","Cron: 分 时 日 月 周\n\n*/5 * * * *   每5分钟\n0 * * * *     每小时\n0 9 * * *     每天9:00\n0 9 * * 1-5   工作日9:00\n")

class WatcherDialog(ctk.CTkToplevel):
    def __init__(self,parent,w):
        super().__init__(parent); self.title("\U0001f441 实时监控"); self.geometry("780x680"); self.minsize(600,450)
        self.transient(parent); self.grab_set(); self.w=w; self._build(); self._ref()
    def _build(self):
        self.grid_columnconfigure(0,weight=1); self.grid_rowconfigure(1,weight=1)
        t=ctk.CTkFrame(self,fg_color="transparent"); t.grid(row=0,column=0,sticky="ew",padx=16,pady=(16,8))
        for i in range(6): t.grid_columnconfigure(i,weight=1 if i in(1,3) else 0)
        ctk.CTkLabel(t,text="名称:",font=(FONT_FAMILY,12)).grid(row=0,column=0)
        self.ne=ctk.CTkEntry(t,font=(FONT_FAMILY,12),height=30); self.ne.grid(row=0,column=1,sticky="ew",padx=4); self.ne.insert(0,"监控")
        ctk.CTkLabel(t,text="类型:",font=(FONT_FAMILY,12)).grid(row=0,column=2,padx=4)
        self.tv=ctk.StringVar(value="file")
        ctk.CTkOptionMenu(t,variable=self.tv,values=["file","log","directory","process"],font=(FONT_FAMILY,12),dropdown_font=(FONT_FAMILY,12),width=90).grid(row=0,column=3,sticky="ew")
        ctk.CTkButton(t,text="添加",width=60,command=self._add,fg_color="#1565C0").grid(row=0,column=4,padx=2)
        ctk.CTkButton(t,text="清空",width=60,command=self._ce,fg_color="#333").grid(row=0,column=5)
        ctk.CTkLabel(t,text="路径:",font=(FONT_FAMILY,12)).grid(row=1,column=0,pady=(4,0))
        self.pe=ctk.CTkEntry(t,font=(FONT_MONO,12),height=30,placeholder_text="path"); self.pe.grid(row=1,column=1,columnspan=3,sticky="ew",pady=(4,0))
        self.pate=ctk.CTkEntry(t,font=(FONT_MONO,12),height=30,width=120,placeholder_text="正则"); self.pate.grid(row=1,column=4,columnspan=2,pady=(4,0))
        m=ctk.CTkFrame(self,fg_color="transparent"); m.grid(row=1,column=0,sticky="nsew",padx=16,pady=4); m.grid_columnconfigure(0,weight=1); m.grid_rowconfigure(1,weight=1)
        ctk.CTkLabel(m,text="\U0001f4cb 监控列表",font=(FONT_FAMILY,13,"bold")).grid(row=0,column=0,sticky="w")
        self.lb=tk.Listbox(m,font=(FONT_MONO,11),bg="#1e1e1e",fg="#e0e0e0",selectbackground="#2a2a4a",borderwidth=0,highlightthickness=0)
        self.lb.grid(row=1,column=0,sticky="nsew"); self.lb.bind("<<ListboxSelect>>",self._sel)
        br=ctk.CTkFrame(m,fg_color="transparent"); br.grid(row=2,column=0,sticky="ew",pady=4)
        ctk.CTkButton(br,text="\U0001f5d1 删除",command=self._del,fg_color="#5a2020").pack(side="left",padx=2)
        ctk.CTkButton(br,text="▶ 运行/停止",command=self._tw,fg_color="#333").pack(side="left",padx=2)
        self.ws=ctk.CTkLabel(br,text="停止",font=(FONT_FAMILY,11),text_color="#888"); self.ws.pack(side="right",padx=4)
        bo=ctk.CTkFrame(self,fg_color="transparent"); bo.grid(row=2,column=0,sticky="nsew",padx=16,pady=(4,16)); bo.grid_columnconfigure(0,weight=1); bo.grid_rowconfigure(1,weight=1)
        ctk.CTkLabel(bo,text="\U0001f4dc 事件",font=(FONT_FAMILY,12,"bold")).grid(row=0,column=0,sticky="w")
        self.et=ctk.CTkTextbox(bo,font=(FONT_MONO,11)); self.et.grid(row=1,column=0,sticky="nsew")
        self.st=ctk.CTkLabel(self,text="就绪",font=(FONT_FAMILY,11),text_color="#888",anchor="w"); self.st.grid(row=3,column=0,sticky="ew",padx=16)
    def _add(self):
        n=self.ne.get().strip() or "监控"; k=self.tv.get(); p=self.pe.get().strip(); pat=self.pate.get().strip()
        if not p: self.st.configure(text="❌ 输入路径"); return
        self.w.add_watch(n,k,p,pat); self._ref(); self.st.configure(text=f"✅ 已添加 [{k}] {n}")
    def _del(self):
        s=self.lb.curselection()
        if not s: return
        ws=self.w.list_watches()
        if s[0]<len(ws): self.w.remove_watch(ws[s[0]].id); self.et.delete("1.0","end"); self._ref()
    def _sel(self,_=None):
        s=self.lb.curselection()
        if not s: return
        ws=self.w.list_watches()
        if s[0]>=len(ws): return
        evs=self.w.get_events(ws[s[0]].id); self.et.delete("1.0","end")
        for ev in evs: self.et.insert("end",f"[{time.strftime('%H:%M:%S',time.localtime(ev.timestamp))}] [{ev.event_type}] {ev.detail}\n")
    def _tw(self):
        if self.w._running: self.w.stop(); self.ws.configure(text="停止",text_color="#888")
        else: self.w.start(on_event=lambda e:self.after(0,lambda:self._push(e))); self.ws.configure(text="\U0001f7e2 运行中",text_color=COLOR_OK)
    def _push(self,ev): self.et.insert("end",f"[{time.strftime('%H:%M:%S',time.localtime(ev.timestamp))}] [{ev.event_type}] {ev.detail[:200]}\n"); self.et.see("end")
    def _ce(self): self.et.delete("1.0","end")
    def _ref(self):
        self.lb.delete(0,"end")
        for w in self.w.list_watches(): self.lb.insert("end",f"{'\U0001f7e2' if w.active else '\U0001f534'} [{w.kind}] {w.name}  ({len(w.events)}事件)")
