"""Focused offline V1 checks: temporary SQLite and mocked external discovery."""
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import database
from database import Store
import discovery
import main
from risk import calculate


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket,'socket',side_effect=AssertionError('No network')))
        self.enterContext(patch.object(subprocess,'Popen',side_effect=AssertionError('No external execution')))


class RiskTests(OfflineCase):
    def test_long_and_short_position_sizing(self):
        for direction,stop in (('LONG','199'),('SHORT','201')):
            p=calculate('10000',direction,'200',stop,'1.0')
            self.assertEqual((p.risk_usd,p.stop_distance,p.quantity,p.notional,p.leverage,p.margin),
                             (Decimal('100'),Decimal('1'),Decimal('100'),Decimal('20000'),2,Decimal('10000')))
        p=calculate('5000','LONG','100','90','1')
        self.assertEqual((p.leverage,p.margin),(1,Decimal('500')))

    def test_invalid_prices_capital_direction_and_risk(self):
        invalid=(('0','LONG','100','90','1'),('10000','LONG','0','90','1'),('10000','LONG','100','0','1'),
                 ('10000','LONG','100','100','1'),('10000','LONG','100','110','1'),('10000','SHORT','100','90','1'),
                 ('10000','BUY','100','90','1'),('10000','LONG','','90','1'),('10000','LONG','NaN','90','1'),
                 ('10000','LONG','Infinity','90','1'),('10000','LONG','-1','90','1'),('10000','LONG','100','90','0'),
                 ('10000','LONG','100','90','10'),('10000','LONG','100','90','1.05'))
        for args in invalid:
            with self.subTest(args=args),self.assertRaises(ValueError):calculate(*args)

    def test_risk_bounds_decimal_accuracy_and_ceiling(self):
        self.assertFalse(calculate('10000','LONG','100','90','4.9').high_risk)
        self.assertTrue(calculate('10000','LONG','100','90','5.0').high_risk)
        for risk in ('0.1','9.9'):self.assertEqual(calculate('10000','LONG','100','90',risk).risk_percent,Decimal(risk))
        p=calculate('10000','LONG','200.0000000000000000000000001','199.0000000000000000000000001','1')
        self.assertEqual(p.leverage,3)
        self.assertLessEqual(p.margin,p.capital)
        p=calculate('10000','LONG','0.00000002','0.00000001','1')
        self.assertEqual(p.quantity,Decimal('10000000000'))


class StoreTests(OfflineCase):
    def setUp(self):
        super().setUp();self.folder=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path=self.folder/'journal.sqlite3';self.store=Store(self.path);self.addCleanup(lambda:self.store.close())

    def trade(self):
        exchange=self.store.exchanges()[0]
        return self.store.record(exchange['id'],'UNRELATED:BTCUSDT.P',calculate(exchange['starting_capital'],'LONG','100','90','1'))

    def test_exchange_crud_capital_persistence_and_deleted_name_snapshot(self):
        id=self.store.save_exchange('Course Demo','3000.25')
        self.store.save_exchange('Course Demo Edited','6000',id)
        self.assertEqual(self.store.exchange(id)['starting_capital'],'6000')
        tid=self.store.record(id,'BYBIT:BTCUSDT.P',calculate('6000','SHORT','100','110','2'))
        self.store.save_exchange('Renamed','9000',id)
        old=self.store.trade(tid)
        self.assertEqual((old['exchange_name'],old['starting_capital'],old['risk_usd']),('Course Demo Edited','6000','120'))
        self.store.delete_exchange(id)
        self.assertIsNone(self.store.trade(tid)['exchange_id']);self.assertEqual(self.store.trade(tid)['exchange_name'],'Course Demo Edited')
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.trade(tid)['starting_capital'],'6000')

    def test_complete_edit_delete_and_static_capital(self):
        id=self.trade();before=self.store.trade(id);exchange_id=before['exchange_id']
        self.store.save_exchange('New display','20000',exchange_id)
        self.store.update_trade(id,direction='SHORT',entry_price='100',stop_loss='105',risk_percent='2',status='COMPLETED',
                                exit_price='95',final_pnl='-50.25',strategy='Turtle Soup',comments='Manual note')
        row=self.store.trade(id)
        self.assertEqual((row['status'],row['starting_capital'],row['risk_usd'],row['final_pnl']),('COMPLETED','10000','200','-50.25'))
        self.assertEqual(row['entry_time'],before['entry_time'])
        self.assertIsNotNone(datetime.fromisoformat(row['completion_time']).utcoffset())
        self.assertEqual(self.store.exchange(exchange_id)['starting_capital'],'20000')
        self.assertEqual(self.store.trades('ACTIVE'),[]);self.assertEqual(len(self.store.trades('COMPLETED')),1)
        completed=row['completion_time']
        self.store.update_trade(id,direction='SHORT',entry_price='100',stop_loss='105',risk_percent='2',status='COMPLETED',final_pnl='0')
        self.assertEqual(self.store.trade(id)['completion_time'],completed)
        self.store.delete_trade(id);self.assertEqual(self.store.trades('COMPLETED'),[])

    def test_invalid_or_stale_values_do_not_write(self):
        id=self.trade();original=self.store.trade(id)
        with self.assertRaises(ValueError):self.store.update_trade(id,direction='LONG',entry_price='100',stop_loss='110',risk_percent='1',status='COMPLETED')
        self.assertEqual(self.store.trade(id),original)
        with self.assertRaises(ValueError):self.store.save_exchange('Bad','NaN')
        with self.assertRaises(ValueError):self.store.save_exchange('Binance','5000')
        p=calculate('10000','LONG','100','90','1');self.store.save_exchange('Binance','12000',original['exchange_id'])
        with self.assertRaisesRegex(ValueError,'recalculate'):self.store.record(original['exchange_id'],'BTC',p)

    def test_empty_exchange_set_stays_empty_after_restart(self):
        for exchange in self.store.exchanges():self.store.delete_exchange(exchange['id'])
        self.store.close();self.store=Store(self.path);self.assertEqual(self.store.exchanges(),[])

    def test_storage_is_independent_and_has_no_credential_columns(self):
        with patch.dict('os.environ',{'LOCALAPPDATA':str(self.folder)}):
            path=database.database_path()
        self.assertEqual(path,self.folder/'TradeWithAM/RiskManagementTradeJournalAgent/journal.sqlite3')
        columns=[r[1] for r in self.store.connection.execute('PRAGMA table_info(exchanges)')]
        self.assertEqual(columns,['id','display_name','starting_capital','created_at','updated_at'])


class DiscoveryTests(OfflineCase):
    def test_reused_watchlist_is_readonly_and_models_are_local(self):
        with patch.object(discovery,'connector_directory',return_value=Path(__file__).parent),\
             patch.object(Path,'is_file',return_value=True),patch.object(discovery,'node_executable',return_value='node.exe'),\
             patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(dict(success=True,symbols=[dict(symbol='BYBIT:BTCUSDT.P')])))) as run:
            result=discovery.get_tradingview_watchlist()
        self.assertEqual(result['symbols'],['BYBIT:BTCUSDT.P']);self.assertEqual(run.call_args.args[0][-2:],['watchlist','get'])
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'models.json';file.write_text(json.dumps(dict(models=[dict(slug='test-model',visibility='list')])))
            self.assertEqual(discovery.load_codex_models(file)['models'],['test-model'])
        self.assertFalse(hasattr(discovery,'codex_command'));self.assertFalse(hasattr(discovery,'run_simple_smc_analysis'))


class GuiTests(OfflineCase):
    def setUp(self):
        super().setUp();self.folder=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store=Store(self.folder/'journal.sqlite3')
        self.watch=self.enterContext(patch.object(main,'get_tradingview_watchlist',return_value=dict(symbols=['BYBIT:BTCUSDT.P'],source='live')))
        self.models=self.enterContext(patch.object(main,'load_codex_models',return_value=dict(models=['model-a','model-b'])))
        self.confirm=self.enterContext(patch.object(main.dialogs,'askokcancel',return_value=True))
        self.info=self.enterContext(patch.object(main.dialogs,'showinfo'))
        self.warning=self.enterContext(patch.object(main.dialogs,'showwarning'))
        self.error=self.enterContext(patch.object(main.dialogs,'showerror'))
        self.root=main.ctk.CTk();self.root.withdraw();self.app=main.RiskJournalApp(self.root,self.store)
        self.addCleanup(self.close);self.pump(lambda:not self.app.refreshing)

    def close(self):
        for callback in self.root.tk.call('after','info'):self.root.tk.call('after','cancel',callback)
        self.root.destroy();self.store.close()

    def pump(self,predicate):
        until=time.monotonic()+3
        while time.monotonic()<until:
            self.root.update()
            if predicate():return
            time.sleep(.005)
        self.fail('Offline GUI discovery did not finish')

    def fill(self,entry='200',stop='199'):
        for widget,value in ((self.app.entry_box,entry),(self.app.stop_box,stop)):
            widget.delete(0,'end');widget.insert(0,value)

    def test_startup_selectors_defaults_and_placeholder_buttons(self):
        self.assertEqual(self.root.title(),main.TITLE);self.assertEqual(self.app.capital_text.get(),'Starting Capital: $10,000.00 USD')
        self.assertEqual(self.app.direction.get(),'LONG');self.assertEqual(self.app.risk_slider.get(),1.0)
        self.assertEqual(self.app.asset_box.cget('values'),['BYBIT:BTCUSDT.P'])
        self.app.asset.set('BYBIT:BTCUSDT.P');self.assertEqual(self.app.asset.get(),'BYBIT:BTCUSDT.P')
        self.assertEqual(self.app.model_box.cget('values'),['model-a','model-b']);self.app.model.set('model-b')
        self.assertEqual(self.app.all_charts.cget('state'),'disabled')
        self.assertEqual(self.app.entry_box.cget('placeholder_text'),'Entry Price')
        self.app.journal_button.invoke();self.app.reports_button.invoke()
        self.assertIn('Coming in Version 2',self.info.call_args_list[0].args[1]);self.assertIn('AI Reports',self.info.call_args_list[1].args[1])
        self.root.deiconify();self.root.update_idletasks();self.assertTrue(self.root.winfo_ismapped());self.root.withdraw()
        self.assertEqual(self.store.trades('ACTIVE'),[])

    def test_risk_warning_direction_exchange_and_enter_recalculation(self):
        self.fill();self.app.recalculate();self.assertEqual(self.app.position.leverage,2)
        self.app.risk_slider.set(5);self.app.risk_changed(self.app.risk_slider.get())
        self.assertEqual(self.app.capital_card.cget('fg_color'),main.RED);self.assertIn('HIGH RISK',self.app.high_warning.cget('text'))
        self.app.risk_slider.set(4.9);self.app.risk_changed(self.app.risk_slider.get())
        self.assertEqual(self.app.capital_card.cget('fg_color'),main.PANEL);self.assertEqual(self.app.high_warning.cget('text'),'')
        self.app.direction.set('SHORT');self.app.recalculate();self.assertIsNone(self.app.position)
        self.fill('200','201');self.app.recalculate();self.assertIsNotNone(self.app.position)
        self.app.exchange_name.set('Bybit Demo');self.app.exchange_changed();self.assertEqual(self.app.position.capital,Decimal('5000'))
        self.assertTrue(self.app.entry_box._entry.bind('<Return>'))
        self.app.risk_slider.set(100);self.assertEqual(self.app.risk_slider.get(),9.9)
        self.app.risk_slider.set(-1);self.assertAlmostEqual(self.app.risk_slider.get(),0.1)

    def test_confirmation_local_trade_and_completed_editor(self):
        self.app.asset.set('BYBIT:BTCUSDT.P');self.fill();self.app.risk_slider.set(5);self.app.risk_changed(5)
        self.app.execute_button.invoke()
        message=self.confirm.call_args.args[1]
        for value in ('HIGH RISK','Binance','BYBIT:BTCUSDT.P','LONG','Stop Loss','Position Quantity','Minimum Leverage','Estimated Margin',
                      'Version 1 records this trade locally. No exchange order will be submitted.'):self.assertIn(value,message)
        row=self.store.trades('ACTIVE')[0];self.assertEqual(len(self.app.tables['ACTIVE'].get_children()),1)
        editor=main.TradeEditor(self.app,row['id']);editor.variables['status'].set('COMPLETED')
        editor.variables['exit_price'].set('205');editor.variables['final_pnl'].set('25');editor.variables['strategy'].set('CRT')
        editor.notes.insert('end','Manual only');editor.save_button.invoke()
        self.assertEqual(self.app.tables['ACTIVE'].get_children(),());self.assertEqual(len(self.app.tables['COMPLETED'].get_children()),1)
        self.assertEqual(self.store.trade(row['id'])['comments'],'Manual only')
        self.assertEqual(self.store.exchanges()[0]['starting_capital'],'10000')
        editor=main.TradeEditor(self.app,row['id']);self.confirm.return_value=False;editor.delete_button.invoke()
        self.assertEqual(len(self.store.trades('COMPLETED')),1)
        self.confirm.return_value=True;editor.delete_button.invoke();self.assertEqual(self.store.trades('COMPLETED'),[])

    def test_invalid_inputs_and_cancel_never_save(self):
        self.fill('100','110');self.app.execute_button.invoke();self.warning.assert_called_once();self.confirm.assert_not_called()
        self.fill();self.confirm.return_value=False;self.app.execute_button.invoke();self.assertEqual(self.store.trades('ACTIVE'),[])

    def test_reused_dark_confirmation_closes_with_long_text(self):
        errors=[];self.root.report_callback_exception=lambda *args:errors.append(args)
        def cancel():
            widgets=list(self.root.winfo_children())
            for widget in widgets:
                widgets.extend(widget.winfo_children())
                if isinstance(widget,main.ctk.CTkButton) and widget.cget('text')=='Cancel':
                    widget.invoke();return
            self.fail('Dark confirmation Cancel button was not found')
        self.root.after(400,cancel)
        result=main.dialogs._show('Local confirmation test','Long confirmation line.\n'*20,parent=self.root,confirm=True)
        self.assertFalse(result);self.assertEqual(errors,[])

    def test_api_controls_toggle_mask_and_never_persist(self):
        editor=self.app.open_exchange_settings()
        self.assertEqual(editor.live_box.cget('text'),'Enable Live Trading')
        self.assertEqual([e.cget('state') for e in editor.api_entries],['disabled']*3)
        editor.live_box.toggle();self.assertEqual([e.cget('state') for e in editor.api_entries],['normal']*3)
        secret_values=('PRIVATE-KEY-NEVER-STORE','PRIVATE-SECRET-NEVER-STORE','https://private-api.invalid')
        for field,value in zip(editor.api_entries,secret_values):field.insert(0,value)
        self.assertEqual(editor.api_entries[1].cget('show'),'•')
        editor.live_box.toggle();self.assertEqual([e.cget('state') for e in editor.api_entries],['disabled']*3)
        def texts(widget):
            values=[]
            try:values.append(widget.cget('text'))
            except (ValueError,tkError):pass
            for child in widget.winfo_children():values.extend(texts(child))
            return values
        # Check only this exchange editor: unrelated report placeholders are allowed.
        import tkinter
        tkError=tkinter.TclError
        self.assertFalse(any('V2' in str(t) or 'Coming in' in str(t) or 'Version 1' in str(t) for t in texts(editor.window)))
        editor.name.set('Edited');editor.capital.set('12000');editor.save_button.invoke()
        dump='\n'.join(self.store.connection.iterdump())
        for secret in secret_values:self.assertNotIn(secret,dump);self.assertNotIn(secret,self.store.path.read_bytes().decode('latin1'))
        self.assertEqual(self.store.exchanges()[0]['starting_capital'],'12000')
        editor=self.app.open_exchange_settings();self.assertFalse(editor.live.get())
        self.assertTrue(all(e.get()=='' for e in editor.api_entries));editor.close()

    def test_exchange_editor_add_cancel_delete_and_empty_state(self):
        editor=self.app.open_exchange_settings();editor.add();editor.name.set('Temporary');editor.capital.set('7000');editor.close()
        self.assertEqual(len(self.store.exchanges()),2)
        editor=self.app.open_exchange_settings();editor.add();editor.name.set('Course Demo');editor.capital.set('7000');editor.save()
        self.assertEqual(self.app.exchange_name.get(),'Course Demo')
        editor=self.app.open_exchange_settings();self.confirm.return_value=False;editor.delete();self.assertEqual(len(self.store.exchanges()),3)
        self.confirm.return_value=True;editor.delete();self.assertEqual(len(self.store.exchanges()),2)
        for exchange in self.store.exchanges():self.store.delete_exchange(exchange['id'])
        self.app.refresh_exchanges();self.app.recalculate();self.assertIsNone(self.app.position)


if __name__=='__main__':unittest.main()
