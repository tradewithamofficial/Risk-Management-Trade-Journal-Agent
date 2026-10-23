"""Risk calculator and local trade records. No AI analysis or order execution."""
import argparse
from decimal import Decimal
from pathlib import Path
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import ui_dialogs as dialogs
from database import Store
from discovery import DEFAULT_SYMBOL,get_tradingview_watchlist,load_codex_models,fallback_symbols
from risk import calculate,money,quantity_text

TITLE='Trade With AM — Risk Management & Trade Journal Agent'
BG='#0f1520';PANEL='#172131';MUTED='#a6b6cb';RED='#782d3a'
FONT=('Segoe UI',16)
ctk.set_appearance_mode('Dark');ctk.set_default_color_theme('dark-blue')


def label(parent,text,**kwargs):return ctk.CTkLabel(parent,text=text,font=FONT,**kwargs)


def popup(owner,title,width=540,height=600):
    window=ctk.CTkToplevel(owner,fg_color=BG)
    window.title(title);window.geometry(f'{width}x{height}');window.minsize(width,450)
    window.transient(owner)
    try:window.iconbitmap(str(Path(__file__).resolve().parent/'assets/TradeWithAM_Robot.ico'))
    except (OSError,tk.TclError):pass
    window.after(200,lambda:window.grab_set() if window.winfo_exists() else None)
    return window


def dispose(window):
    """Cancel CTk's per-window callbacks before closing a short-lived editor."""
    # Child widgets (notably CTkTextbox) cancel their own timers in destroy().
    # Cancelling those twice leaves stale Tcl command names on Python 3.14.
    commands=set(getattr(window,'_tclCommands',None) or [])
    for callback in window.tk.call('after','info'):
        if str(window.tk.call('after','info',callback)[0]) in commands:window.after_cancel(callback)
    window.destroy()


class ExchangeSettings:
    def __init__(self,app):
        self.app=app;self.store=app.store;self.editing_id=app.exchange_id()
        self.window=popup(app.root,'Exchange Settings',560,660)
        body=ctk.CTkScrollableFrame(self.window,fg_color=PANEL);body.pack(fill='both',expand=True,padx=16,pady=16)
        body.columnconfigure(1,weight=1)
        self.names={e['display_name']:e['id'] for e in self.store.exchanges()}
        selected=next((n for n,id in self.names.items() if id==self.editing_id),'New exchange')
        self.choice=tk.StringVar(value=selected)
        self.selector=ctk.CTkOptionMenu(body,variable=self.choice,values=list(self.names) or ['New exchange'],command=self.choose,font=FONT)
        self.selector.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(8,12))
        actions=ctk.CTkFrame(body,fg_color='transparent');actions.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,14))
        self.add_button=ctk.CTkButton(actions,text='Add exchange',command=self.add,font=FONT)
        self.add_button.pack(side='left')
        self.delete_button=ctk.CTkButton(actions,text='Delete exchange',command=self.delete,font=FONT,fg_color='#703343')
        self.delete_button.pack(side='right')
        self.name=tk.StringVar();self.capital=tk.StringVar()
        for row,(title,variable) in enumerate((('Display name',self.name),('Starting Capital (USD)',self.capital)),2):
            label(body,title,anchor='w').grid(row=row,column=0,sticky='w',padx=(0,14),pady=10)
            ctk.CTkEntry(body,textvariable=variable,font=FONT).grid(row=row,column=1,sticky='ew',pady=10)
        self.live=tk.BooleanVar(value=False)
        self.live_box=ctk.CTkCheckBox(body,text='Enable Live Trading',variable=self.live,command=self.toggle_api,font=FONT)
        self.live_box.grid(row=4,column=0,columnspan=2,sticky='w',pady=(20,10))
        self.api_entries=[]
        for row,title in enumerate(('API Key','API Secret','API URL'),5):
            label(body,title,anchor='w').grid(row=row,column=0,sticky='w',padx=(0,14),pady=10)
            entry=ctk.CTkEntry(body,font=FONT,show='•' if title=='API Secret' else '',state='disabled')
            entry.grid(row=row,column=1,sticky='ew',pady=10);self.api_entries.append(entry)
        footer=ctk.CTkFrame(self.window,fg_color='transparent');footer.pack(fill='x',padx=20,pady=(0,16))
        self.save_button=ctk.CTkButton(footer,text='Save',command=self.save,font=FONT);self.save_button.pack(side='right',padx=(12,0))
        ctk.CTkButton(footer,text='Cancel',command=self.close,font=FONT,fg_color='#374151').pack(side='right')
        self.window.protocol('WM_DELETE_WINDOW',self.close);self.window.bind('<Escape>',lambda _:self.close())
        self.choose(selected)

    def toggle_api(self):
        for entry in self.api_entries:entry.configure(state='normal' if self.live.get() else 'disabled')

    def clear_api(self):
        for entry in self.api_entries:
            entry.configure(state='normal');entry.delete(0,'end');entry.configure(state='disabled')
        self.live.set(False)

    def choose(self,name):
        self.clear_api();self.editing_id=self.names.get(name)
        if self.editing_id is None:self.name.set('');self.capital.set('10000')
        else:
            e=self.store.exchange(self.editing_id);self.name.set(e['display_name']);self.capital.set(e['starting_capital'])
        self.delete_button.configure(state='normal' if self.editing_id is not None else 'disabled')

    def add(self):self.choice.set('New exchange');self.choose('New exchange')

    def save(self):
        try:
            # API widgets are intentionally never read or passed to storage.
            id=self.store.save_exchange(self.name.get(),self.capital.get(),self.editing_id)
            self.app.refresh_exchanges(id);self.close()
        except (ValueError,sqlite3.Error) as exc:dialogs.showwarning('Exchange not saved',str(exc),parent=self.window)

    def delete(self):
        if self.editing_id is None:return
        if dialogs.askokcancel('Delete exchange','Delete this exchange? Existing trade history and its saved exchange name/capital will remain.',parent=self.window):
            self.store.delete_exchange(self.editing_id);self.app.refresh_exchanges();self.close()

    def close(self):self.clear_api();dispose(self.window)


class TradeEditor:
    def __init__(self,app,id):
        self.app=app;self.id=id;record=app.store.trade(id)
        self.window=popup(app.root,'Edit Trade',600,780)
        body=ctk.CTkScrollableFrame(self.window,fg_color=PANEL);body.pack(fill='both',expand=True,padx=16,pady=16)
        body.columnconfigure(1,weight=1)
        label(body,f"{record['symbol']} · {record['exchange_name']}",wraplength=500).grid(row=0,column=0,columnspan=2,sticky='w',pady=8)
        label(body,'Recorded Starting Capital: '+money(record['starting_capital']),wraplength=500,text_color=MUTED).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
        self.variables={}
        fields=(('direction','Direction'),('entry_price','Entry Price'),('stop_loss','Stop Loss'),('risk_percent','Risk %'),
                ('status','Status'),('exit_price','Exit Price (optional)'),('final_pnl','Final P&L USD (optional)'),('strategy','Strategy (optional)'))
        for row,(key,title) in enumerate(fields,2):
            variable=tk.StringVar(value=record[key] if record[key] is not None else '');self.variables[key]=variable
            label(body,title,anchor='w').grid(row=row,column=0,sticky='w',padx=(0,12),pady=8)
            if key in ('direction','status'):
                control=ctk.CTkOptionMenu(body,variable=variable,values=['LONG','SHORT'] if key=='direction' else ['ACTIVE','COMPLETED'],font=FONT)
            else:control=ctk.CTkEntry(body,textvariable=variable,font=FONT)
            control.grid(row=row,column=1,sticky='ew',pady=8)
        label(body,'Trader notes',anchor='w').grid(row=10,column=0,columnspan=2,sticky='w',pady=(12,4))
        self.notes=ctk.CTkTextbox(body,height=110,font=FONT,wrap='word');self.notes.grid(row=11,column=0,columnspan=2,sticky='ew')
        self.notes.insert('1.0',record['comments'])
        label(body,'Edits use this record’s original capital snapshot.',text_color=MUTED,wraplength=500).grid(row=12,column=0,columnspan=2,sticky='w',pady=12)
        footer=ctk.CTkFrame(self.window,fg_color='transparent');footer.pack(fill='x',padx=16,pady=(0,16))
        self.delete_button=ctk.CTkButton(footer,text='Delete',command=self.delete,fg_color='#703343',width=100,font=FONT);self.delete_button.pack(side='left')
        self.save_button=ctk.CTkButton(footer,text='Save',command=self.save,width=100,font=FONT);self.save_button.pack(side='right')
        ctk.CTkButton(footer,text='Cancel',command=self.close,width=100,font=FONT,fg_color='#374151').pack(side='right',padx=10)
        self.window.protocol('WM_DELETE_WINDOW',self.close)

    def save(self):
        try:
            self.app.store.update_trade(self.id,**{k:v.get() for k,v in self.variables.items()},comments=self.notes.get('1.0','end-1c'))
            self.app.refresh_tables();self.close()
        except (ValueError,sqlite3.Error) as exc:dialogs.showwarning('Trade not saved',str(exc),parent=self.window)

    def delete(self):
        if dialogs.askokcancel('Delete trade','Permanently delete this local trade record?',parent=self.window):
            self.app.store.delete_trade(self.id);self.app.refresh_tables();self.close()

    def close(self):dispose(self.window)


class RiskJournalApp:
    def __init__(self,root,store,*,start_discovery=True):
        self.root=root;self.store=store;self.events=queue.Queue();self.refreshing=False;self.closed=False;self.position=None
        root.title(TITLE);root.geometry('1180x940');root.minsize(1020,720);root.configure(fg_color=BG)
        try:root.iconbitmap(str(Path(__file__).resolve().parent/'assets/TradeWithAM_Robot.ico'))
        except (OSError,tk.TclError):pass
        root.protocol('WM_DELETE_WINDOW',self.close)
        content=ctk.CTkScrollableFrame(root,fg_color=BG);content.pack(fill='both',expand=True,padx=14,pady=14)
        content.columnconfigure(0,weight=1)
        label(content,'TRADE WITH AM',text_color='#8fbfff',anchor='w').grid(row=0,column=0,sticky='w',padx=14,pady=(6,2))
        ctk.CTkLabel(content,text=TITLE,font=('Segoe UI',26,'bold'),wraplength=1020,justify='left',anchor='w').grid(row=1,column=0,sticky='ew',padx=14,pady=(0,16))
        self.capital_card=ctk.CTkFrame(content,fg_color=PANEL,corner_radius=12);self.capital_card.grid(row=2,column=0,sticky='ew',padx=10,pady=(0,12))
        self.capital_text=tk.StringVar()
        ctk.CTkLabel(self.capital_card,textvariable=self.capital_text,font=('Segoe UI',20,'bold'),anchor='w').pack(fill='x',padx=16,pady=14)
        form=ctk.CTkFrame(content,fg_color=PANEL,corner_radius=12);form.grid(row=3,column=0,sticky='ew',padx=10)
        form.columnconfigure(1,weight=1)
        label(form,'Exchange',anchor='w').grid(row=0,column=0,sticky='w',padx=16,pady=14)
        self.exchange_name=tk.StringVar()
        self.exchange_box=ctk.CTkOptionMenu(form,variable=self.exchange_name,values=[''],command=lambda _:self.exchange_changed(),font=FONT)
        self.exchange_box.grid(row=0,column=1,sticky='ew',padx=(0,12),pady=14)
        self.settings_button=ctk.CTkButton(form,text='⚙',width=50,font=('Segoe UI',22),command=self.open_exchange_settings)
        self.settings_button.grid(row=0,column=2,padx=(0,16),pady=14)
        self.asset=tk.StringVar(value=DEFAULT_SYMBOL)
        label(form,'TradingView asset',anchor='w').grid(row=1,column=0,sticky='w',padx=16,pady=8)
        self.asset_box=ctk.CTkComboBox(form,variable=self.asset,values=fallback_symbols(),font=FONT)
        self.asset_box.grid(row=1,column=1,sticky='ew',padx=(0,12),pady=8)
        options=ctk.CTkFrame(form,fg_color='transparent');options.grid(row=1,column=2,padx=(0,16),pady=8)
        self.all_charts=ctk.CTkCheckBox(options,text='All Charts',state='disabled',font=FONT,width=100);self.all_charts.pack(side='left',padx=(0,10))
        self.refresh_button=ctk.CTkButton(options,text='Refresh',width=90,command=self.refresh_sources,font=FONT);self.refresh_button.pack(side='left')
        self.source_status=tk.StringVar(value='Local fallback assets — use Refresh for the existing TradingView watchlist.')
        ctk.CTkLabel(form,textvariable=self.source_status,font=('Segoe UI',13),text_color=MUTED,wraplength=960,anchor='w',justify='left').grid(row=2,column=0,columnspan=3,sticky='ew',padx=16,pady=(0,12))
        riskrow=ctk.CTkFrame(form,fg_color='transparent');riskrow.grid(row=3,column=0,columnspan=3,sticky='ew',padx=16,pady=10);riskrow.columnconfigure(1,weight=1)
        label(riskrow,'Risk',width=100,anchor='w').grid(row=0,column=0,sticky='w')
        self.risk_value=tk.StringVar(value='1.0%')
        self.risk_slider=ctk.CTkSlider(riskrow,from_=0.1,to=9.9,number_of_steps=98,command=self.risk_changed)
        self.risk_slider.set(1.0);self.risk_slider.grid(row=0,column=1,sticky='ew',padx=12)
        ctk.CTkLabel(riskrow,textvariable=self.risk_value,font=('Segoe UI',20,'bold'),width=90).grid(row=0,column=2)
        self.high_warning=ctk.CTkLabel(form,text='',font=('Segoe UI',16,'bold'),text_color='#ffb3b8',anchor='w')
        self.high_warning.grid(row=4,column=0,columnspan=3,sticky='ew',padx=16,pady=(0,10))
        self.direction=tk.StringVar(value='LONG')
        directionrow=ctk.CTkFrame(form,fg_color='transparent');directionrow.grid(row=5,column=0,columnspan=3,sticky='w',padx=16,pady=8)
        for name in ('LONG','SHORT'):
            ctk.CTkRadioButton(directionrow,text=name,variable=self.direction,value=name,command=self.recalculate,font=FONT).pack(side='left',padx=(0,26))
        prices=ctk.CTkFrame(form,fg_color='transparent');prices.grid(row=6,column=0,columnspan=3,sticky='ew',padx=16,pady=(4,16))
        prices.columnconfigure((0,1),weight=1)
        self.entry_box=ctk.CTkEntry(prices,placeholder_text='Entry Price',font=FONT,height=38)
        self.stop_box=ctk.CTkEntry(prices,placeholder_text='Stop Loss Price',font=FONT,height=38)
        self.entry=self.entry_box;self.stop=self.stop_box
        for column,control in enumerate((self.entry_box,self.stop_box)):
            control.grid(row=0,column=column,sticky='ew',padx=(0,12) if column==0 else (0,0));control.bind('<Return>',lambda _:self.recalculate())
        self.calculation_status=tk.StringVar(value='Enter Entry Price and Stop Loss, then press Enter.')
        ctk.CTkLabel(content,textvariable=self.calculation_status,font=FONT,text_color=MUTED,anchor='w',justify='left',wraplength=1000).grid(row=4,column=0,sticky='ew',padx=24,pady=(14,6))
        results=ctk.CTkFrame(content,fg_color=PANEL);results.grid(row=5,column=0,sticky='ew',padx=10,pady=(0,12));results.columnconfigure((0,1),weight=1)
        self.result_values={}
        for row,(key,title) in enumerate((('risk_usd','Risk USD'),('quantity','Position Quantity'),('notional','Position Notional'),('leverage','Minimum Leverage (estimate)'),('margin','Estimated Margin Used'))):
            label(results,title,anchor='w').grid(row=row,column=0,sticky='w',padx=16,pady=7)
            variable=tk.StringVar(value='—');self.result_values[key]=variable
            ctk.CTkLabel(results,textvariable=variable,font=('Segoe UI',20,'bold'),anchor='e').grid(row=row,column=1,sticky='ew',padx=16,pady=7)
        label(content,'Linear USD quote · contract multiplier 1 · leverage/margin are estimates',text_color=MUTED,wraplength=1000,anchor='w').grid(row=6,column=0,sticky='ew',padx=24,pady=(0,12))
        self.execute_button=ctk.CTkButton(content,text='Execute Trade',command=self.execute,height=46,font=('Segoe UI',18,'bold'))
        self.execute_button.grid(row=7,column=0,sticky='ew',padx=10,pady=(0,18))
        self.tabs=ctk.CTkTabview(content,height=390);self.tabs.grid(row=8,column=0,sticky='ew',padx=10,pady=(0,12))
        self.tables={};self._style_tables()
        for status,title in (('ACTIVE','Active Trades'),('COMPLETED','Completed Trades')):
            tab=self.tabs.add(title);tab.columnconfigure(0,weight=1);tab.rowconfigure(0,weight=1)
            self.tables[status]=self.build_table(tab,status)
        footer=ctk.CTkFrame(self.tabs.tab('Completed Trades'),fg_color='transparent');footer.grid(row=1,column=0,sticky='ew',pady=(10,2))
        self.journal_button=ctk.CTkButton(footer,text='View Trade Journal',font=FONT,command=lambda:dialogs.showinfo('Trade Journal','Coming in Version 2',parent=self.root));self.journal_button.pack(side='left')
        self.reports_button=ctk.CTkButton(footer,text='Generate Reports',font=FONT,command=lambda:dialogs.showinfo('Generate Reports','AI Reports — Coming in Version 2',parent=self.root));self.reports_button.pack(side='left',padx=10)
        label(footer,'Codex model').pack(side='left',padx=(6,8))
        self.model=tk.StringVar(value='');self.model_box=ctk.CTkComboBox(footer,variable=self.model,values=[],width=180,state='readonly',font=FONT);self.model_box.pack(side='left')
        self.model_status=tk.StringVar(value='Refresh reads the local model catalogue; no AI is run.')
        ctk.CTkLabel(self.tabs.tab('Completed Trades'),textvariable=self.model_status,font=('Segoe UI',13),text_color=MUTED,anchor='w',wraplength=980).grid(row=2,column=0,sticky='ew',pady=(4,0))
        self.refresh_exchanges();self.refresh_tables()
        self.poll_id=root.after(100,self.poll_sources)
        if start_discovery:self.refresh_sources()

    def _style_tables(self):
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('Risk.Treeview',background='#101823',fieldbackground='#101823',foreground='#dbe7f4',rowheight=30,font=('Segoe UI',13),borderwidth=0)
        style.configure('Risk.Treeview.Heading',background='#293b52',foreground='#eef4ff',font=('Segoe UI',13,'bold'))
        style.map('Risk.Treeview',background=[('selected','#1f538d')],foreground=[('selected','white')])

    def build_table(self,parent,status):
        frame=ctk.CTkFrame(parent,fg_color=PANEL);frame.grid(row=0,column=0,sticky='nsew');frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        columns=('date','asset','exchange','direction','quantity','leverage','margin','risk','status','settings') if status=='ACTIVE' else ('date','asset','exchange','direction','quantity','risk','leverage','pnl','strategy','settings')
        titles={'date':'Entry time (UTC)' if status=='ACTIVE' else 'Completed time (UTC)','asset':'Asset','exchange':'Exchange','direction':'Direction','quantity':'Position qty','leverage':'Leverage est.','margin':'Est. margin USD','risk':'Risk USD / %','status':'Status','pnl':'Final P&L USD','strategy':'Strategy','settings':'⚙'}
        table=ttk.Treeview(frame,columns=columns,show='headings',height=6,style='Risk.Treeview',selectmode='browse')
        for key in columns:
            table.heading(key,text=titles[key]);table.column(key,width=180 if key=='date' else 60 if key=='settings' else 140,stretch=False,anchor='w')
        table.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(frame,orient='vertical',command=table.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=table.xview);horizontal.grid(row=1,column=0,sticky='ew')
        table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        table.bind('<ButtonRelease-1>',lambda event:self.table_click(event,table))
        table.bind('<Double-1>',lambda event:self.edit_selected(table))
        table.bind('<Return>',lambda event:self.edit_selected(table))
        return table

    def table_click(self,event,table):
        row=table.identify_row(event.y)
        if row and table.identify_column(event.x)==f'#{len(table["columns"])}':TradeEditor(self,int(row))

    def edit_selected(self,table):
        if table.selection():return TradeEditor(self,int(table.selection()[0]))

    def exchange_id(self):return self.exchange_ids.get(self.exchange_name.get())

    def refresh_exchanges(self,select_id=None):
        old=self.exchange_id() if hasattr(self,'exchange_ids') else None
        entries=self.store.exchanges();self.exchange_ids={e['display_name']:e['id'] for e in entries}
        selected=next((e['display_name'] for e in entries if e['id']==(select_id if select_id is not None else old)),entries[0]['display_name'] if entries else '')
        self.exchange_box.configure(values=list(self.exchange_ids) or ['']);self.exchange_name.set(selected);self.exchange_changed()

    def exchange_changed(self):
        id=self.exchange_id()
        self.capital_text.set('Starting Capital: '+money(self.store.exchange(id)['starting_capital']) if id is not None else 'Starting Capital: add an exchange')
        self.recalculate()

    def open_exchange_settings(self):return ExchangeSettings(self)

    def risk_changed(self,value):
        tick=max(1,min(99,round(float(value)*10)));self.risk_value.set(f'{tick/10:.1f}%')
        self.capital_card.configure(fg_color=RED if tick>=50 else PANEL)
        self.high_warning.configure(text='HIGH RISK — 5.0% or more of Starting Capital per trade.' if tick>=50 else '')
        self.recalculate()

    def recalculate(self):
        self.position=None
        try:
            exchange=self.store.exchange(self.exchange_id())
            self.position=calculate(exchange['starting_capital'],self.direction.get(),self.entry.get(),self.stop.get(),self.risk_value.get().removesuffix('%'))
            p=self.position
            values=dict(risk_usd=money(p.risk_usd),quantity=quantity_text(p.quantity),notional=money(p.notional),leverage=f'{p.leverage}×',margin=money(p.margin))
            for key,value in values.items():self.result_values[key].set(value)
            self.calculation_status.set('Calculated — press Execute Trade to review and record locally.')
            return p
        except (ValueError,sqlite3.Error) as exc:
            self.calculation_status.set(str(exc))
            for variable in self.result_values.values():variable.set('—')
            return None

    def execute(self):
        p=self.recalculate()
        if p is None:dialogs.showwarning('Check trade inputs',self.calculation_status.get(),parent=self.root);return
        symbol=self.asset.get().strip()
        if not symbol:dialogs.showwarning('Select asset','Select a TradingView symbol.',parent=self.root);return
        exchange=self.store.exchange(self.exchange_id())
        message=(f"Exchange: {exchange['display_name']}\nTradingView symbol: {symbol}\nDirection: {p.direction}\n"
                 f'Entry Price: {p.entry}\nStop Loss: {p.stop}\nRisk: {p.risk_percent}%\nRisk USD: {money(p.risk_usd)}\n'
                 f'Position Quantity: {quantity_text(p.quantity)}\nPosition Notional: {money(p.notional)}\n'
                 f'Minimum Leverage (estimate): {p.leverage}×\nEstimated Margin Used: {money(p.margin)}\n\n'
                 'Version 1 records this trade locally. No exchange order will be submitted.')
        if p.high_risk:message='HIGH RISK — 5.0% OR MORE OF STARTING CAPITAL.\n\n'+message
        if not dialogs.askokcancel('Confirm local trade',message,parent=self.root):return
        try:
            self.store.record(exchange['id'],symbol,p);self.refresh_tables();self.tabs.set('Active Trades')
            dialogs.showinfo('Trade recorded','The trade is now in Active Trades.',parent=self.root)
        except (ValueError,sqlite3.Error) as exc:dialogs.showerror('Trade not recorded',str(exc),parent=self.root)

    def refresh_tables(self):
        for status,table in self.tables.items():
            table.delete(*table.get_children())
            for row in self.store.trades(status):
                common=(row['entry_time'] if status=='ACTIVE' else row['completion_time'],row['symbol'],row['exchange_name'],row['direction'],quantity_text(row['quantity']))
                risk=f"{money(row['risk_usd'])} / {row['risk_percent']}%"
                tail=(f"{row['leverage']}×",money(row['estimated_margin']),risk,'ACTIVE','⚙') if status=='ACTIVE' else (risk,f"{row['leverage']}×",money(row['final_pnl']) if row['final_pnl'] is not None else '—',row['strategy'],'⚙')
                table.insert('','end',iid=str(row['id']),values=(*common,*tail))

    def refresh_sources(self):
        if self.refreshing:return
        self.refreshing=True;self.refresh_button.configure(state='disabled');self.source_status.set('Reading existing TradingView watchlist…')
        def worker():
            try:self.events.put((get_tradingview_watchlist(),load_codex_models()))
            except Exception:self.events.put((dict(symbols=fallback_symbols(),source='fallback',error='Discovery unavailable.'),dict(models=[],error='Local catalogue unavailable.')))
        threading.Thread(target=worker,daemon=True).start()

    def poll_sources(self):
        if self.closed:return
        try:
            watchlist,models=self.events.get_nowait()
            self.asset_box.configure(values=watchlist['symbols'])
            self.source_status.set('TradingView watchlist loaded.' if watchlist.get('source')=='live' else 'Fallback assets — '+watchlist.get('error','Watchlist unavailable.'))
            choices=models.get('models',[]);self.model_box.configure(values=choices)
            if self.model.get() not in choices:self.model.set(choices[0] if choices else '')
            self.model_status.set('Local Codex model selector — no AI execution in V1.' if choices else 'No local models found. '+models.get('error',''))
            self.refreshing=False;self.refresh_button.configure(state='normal')
        except queue.Empty:pass
        self.poll_id=self.root.after(100,self.poll_sources)

    def close(self):
        self.closed=True
        self.root.after_cancel(self.poll_id)
        self.store.close();self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description=TITLE);parser.add_argument('--database',type=Path,help='Optional local database path')
    args=parser.parse_args();root=ctk.CTk()
    try:store=Store(args.database)
    except (OSError,ValueError,sqlite3.Error) as exc:
        dialogs.showerror('Local database unavailable',str(exc),parent=root);root.destroy();return
    RiskJournalApp(root,store);root.mainloop()


if __name__=='__main__':main()
