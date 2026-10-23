"""Small local SQLite store. Monetary numbers are Decimal strings, not floats."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from risk import calculate,number


def database_path():
    parent=Path(os.environ['LOCALAPPDATA']) if os.environ.get('LOCALAPPDATA') else Path.home()/'.local/share'
    return parent/'TradeWithAM/RiskManagementTradeJournalAgent/journal.sqlite3'


def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


def text(value,label,limit=100):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>limit:
        raise ValueError(f'{label} is required (maximum {limit} characters).')
    return value.strip()


class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else database_path()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(self.path)
        self.connection.row_factory=sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        version=self.connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,1):self.close();raise ValueError('Unsupported local database version.')
        if version==0:
            with self.connection:
                self.connection.executescript('''
                CREATE TABLE exchanges (
                    id INTEGER PRIMARY KEY, display_name TEXT NOT NULL UNIQUE,
                    starting_capital TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE trades (
                    id INTEGER PRIMARY KEY, exchange_id INTEGER REFERENCES exchanges(id) ON DELETE SET NULL,
                    exchange_name TEXT NOT NULL, symbol TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('LONG','SHORT')),
                    entry_price TEXT NOT NULL, stop_loss TEXT NOT NULL, risk_percent TEXT NOT NULL,
                    risk_usd TEXT NOT NULL, quantity TEXT NOT NULL, notional TEXT NOT NULL,
                    leverage TEXT NOT NULL, estimated_margin TEXT NOT NULL, starting_capital TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ACTIVE','COMPLETED')),
                    entry_time TEXT NOT NULL, completion_time TEXT,
                    exit_price TEXT, final_pnl TEXT, strategy TEXT NOT NULL DEFAULT '', comments TEXT NOT NULL DEFAULT '');
                PRAGMA user_version=1;
                ''')
                self.save_exchange('Binance','10000')
                self.save_exchange('Bybit Demo','5000')

    def close(self):self.connection.close()

    def exchanges(self):return [dict(row) for row in self.connection.execute('SELECT * FROM exchanges ORDER BY id')]

    def exchange(self,id):
        row=self.connection.execute('SELECT * FROM exchanges WHERE id=?',(id,)).fetchone()
        if row is None:raise ValueError('Select an existing exchange or add one in Settings.')
        return dict(row)

    def save_exchange(self,name,capital,id=None):
        name=text(name,'Exchange display name');capital=number(capital,'Starting Capital',positive=True)
        try:
            with self.connection:
                if id is None:
                    cursor=self.connection.execute('INSERT INTO exchanges(display_name,starting_capital,created_at,updated_at) VALUES(?,?,?,?)',
                                                   (name,str(capital),now(),now()))
                    return cursor.lastrowid
                self.exchange(id)
                self.connection.execute('UPDATE exchanges SET display_name=?,starting_capital=?,updated_at=? WHERE id=?',
                                        (name,str(capital),now(),id))
                return id
        except sqlite3.IntegrityError:
            raise ValueError('An exchange with this display name already exists.') from None

    def delete_exchange(self,id):
        self.exchange(id)
        with self.connection:self.connection.execute('DELETE FROM exchanges WHERE id=?',(id,))

    def record(self,exchange_id,symbol,position):
        symbol=text(symbol,'TradingView symbol')
        # No exchange-prefix matching: the exchange is a user-defined label.
        exchange=self.exchange(exchange_id)
        verified=calculate(exchange['starting_capital'],position.direction,position.entry,position.stop,position.risk_percent)
        if verified!=position:raise ValueError('Starting Capital changed; recalculate and confirm the trade again.')
        values=self._position_values(verified)
        with self.connection:
            cursor=self.connection.execute('''INSERT INTO trades
                (exchange_id,exchange_name,symbol,direction,entry_price,stop_loss,risk_percent,risk_usd,
                 quantity,notional,leverage,estimated_margin,starting_capital,status,entry_time)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?)''',
                (exchange_id,exchange['display_name'],symbol,*values,now()))
        return cursor.lastrowid

    @staticmethod
    def _position_values(p):
        return tuple(str(v) for v in (p.direction,p.entry,p.stop,p.risk_percent,p.risk_usd,p.quantity,p.notional,p.leverage,p.margin,p.capital))

    def trades(self,status):
        if status not in ('ACTIVE','COMPLETED'):raise ValueError('Invalid trade status.')
        return [dict(row) for row in self.connection.execute('SELECT * FROM trades WHERE status=? ORDER BY id DESC',(status,))]

    def trade(self,id):
        row=self.connection.execute('SELECT * FROM trades WHERE id=?',(id,)).fetchone()
        if row is None:raise ValueError('Trade record was not found.')
        return dict(row)

    def update_trade(self,id,*,direction,entry_price,stop_loss,risk_percent,status,exit_price='',final_pnl='',strategy='',comments=''):
        old=self.trade(id)
        p=calculate(old['starting_capital'],direction,entry_price,stop_loss,risk_percent)
        if status not in ('ACTIVE','COMPLETED'):raise ValueError('Select ACTIVE or COMPLETED.')
        if not isinstance(strategy,str) or len(strategy)>200 or not isinstance(comments,str) or len(comments)>10000:
            raise ValueError('Strategy must be at most 200 characters; notes at most 10,000.')
        exit_value=str(number(exit_price,'Exit Price',positive=True)) if str(exit_price).strip() else None
        pnl=str(number(final_pnl,'Final P&L')) if str(final_pnl).strip() else None
        completed=(old['completion_time'] or now()) if status=='COMPLETED' else None
        with self.connection:
            self.connection.execute('''UPDATE trades SET direction=?,entry_price=?,stop_loss=?,risk_percent=?,
                risk_usd=?,quantity=?,notional=?,leverage=?,estimated_margin=?,starting_capital=?,
                status=?,completion_time=?,exit_price=?,final_pnl=?,strategy=?,comments=? WHERE id=?''',
                (*self._position_values(p),status,completed,exit_value,pnl,strategy,comments,id))

    def delete_trade(self,id):
        self.trade(id)
        with self.connection:self.connection.execute('DELETE FROM trades WHERE id=?',(id,))
