from math import floor


def round_down(num, ndigits):
    if isinstance(num, str):
        num = float(num)
    mul = 10 ** ndigits
    return floor(num * mul) / mul


def round_quantity(symbol, quantity):
    if 'USDT' in symbol:
        pass
    elif 'BTC' in symbol:
        pass
    elif 'ETH' in symbol:
        return round_down(quantity, 2)
    elif 'BNB' in symbol:
        pass
