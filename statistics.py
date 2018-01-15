from urllib.parse import urlencode

import requests

base_url = 'https://api.binance.com'


symbols = [symbol['symbol'] for symbol in requests.get('{}/api/v3/ticker/price'.format(base_url)).json()
           if symbol['symbol'].endswith('ETH')]

for symbol in symbols:
    kline_data = {'symbol': symbol, 'interval': '15m', 'limit': 500}
    for kline in requests.get('{}/api/v1/klines?{}'.format(base_url, urlencode(kline_data))).json():
        price_open = float(kline[1])
        price_high = float(kline[2])
        price_low = float(kline[3])

        if price_high / price_open - 1 > 0.1: