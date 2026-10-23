"""Linear USD-quoted position sizing, multiplier 1. No broker/API operations."""
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext


def number(value, label, *, positive=False):
    try:
        result=Decimal(str(value).strip())
        if not result.is_finite() or (positive and result<=0):raise ValueError
        # Bound input precision/exponents to keep malformed inputs manageable.
        if len(result.as_tuple().digits)>28 or (result and not -28<=result.adjusted()<=28):raise ValueError
        return result
    except (DecimalException,ValueError,TypeError):
        raise ValueError(f'{label} must be a finite '+('positive ' if positive else '')+'number (up to 28 significant digits).') from None


@dataclass(frozen=True)
class Position:
    capital: Decimal
    direction: str
    entry: Decimal
    stop: Decimal
    risk_percent: Decimal
    risk_usd: Decimal
    stop_distance: Decimal
    quantity: Decimal
    notional: Decimal
    leverage: int
    margin: Decimal

    @property
    def high_risk(self):return self.risk_percent>=Decimal('5.0')


def calculate(capital,direction,entry,stop,risk_percent):
    capital=number(capital,'Starting Capital',positive=True)
    entry=number(entry,'Entry Price',positive=True)
    stop=number(stop,'Stop Loss',positive=True)
    risk_percent=number(risk_percent,'Risk percentage',positive=True)
    if not Decimal('0.1')<=risk_percent<=Decimal('9.9') or risk_percent%Decimal('0.1'):
        raise ValueError('Risk must be 0.1%–9.9% in steps of 0.1%.')
    if direction not in ('LONG','SHORT'):raise ValueError('Select LONG or SHORT.')
    if direction=='LONG' and stop>=entry:raise ValueError('LONG: Stop Loss must be below Entry Price.')
    if direction=='SHORT' and stop<=entry:raise ValueError('SHORT: Stop Loss must be above Entry Price.')
    try:
        with localcontext() as context:
            context.prec=80
            risk_usd=capital*risk_percent/100
            distance=abs(entry-stop)
            quantity=risk_usd/distance
            notional=quantity*entry
            # Exact integer ceiling from Decimal ratios avoids rounding an
            # infinitesimal amount above a leverage boundary down to an integer.
            numerator= risk_usd*entry
            denominator=distance*capital
            a,b=numerator.as_integer_ratio();c,d=denominator.as_integer_ratio()
            leverage=max(1,-(-(a*d)//(b*c)))
            margin=notional/Decimal(leverage)
        return Position(capital,direction,entry,stop,risk_percent,risk_usd,distance,quantity,notional,leverage,margin)
    except DecimalException:
        raise ValueError('These inputs cannot be calculated safely; check their size and precision.') from None


def money(value):return f'${Decimal(value):,.2f} USD'


def quantity_text(value):return f'{Decimal(value):,.8f}'.rstrip('0').rstrip('.')
