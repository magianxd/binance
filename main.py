from time import sleep

import requests
import hashlib
import hmac
import base64
from urllib.parse import urlencode
from datetime import datetime
import logging

trigger_percent = 1.1
stop_loss_percent = 0.5
take_profit_low_percent = 1.5
take_profit_high_percent = 2
kline_interval = '15m'
total_eth_earning = 0
symbols = ['WAVESETH']
base_url = 'https://api.binance.com'
api_key = 'SGc5VKlmaTRcbysi9xMamV4IniNVEtpi0bEGI8TUG1CSLfEcI9V7NELfkNPzBmkT'
secret_key = bytes(''.encode())
LOGGER = logging.getLogger(__name__)


def get_account_info():
    data = {'timestamp': int(round(datetime.now().timestamp() * 1000)), 'recvWindow': 5000}
    query_string = urlencode(data)
    signature = base64.b16encode(hmac.new(secret_key, query_string.encode(), digestmod=hashlib.sha256).digest())
    data['signature'] = signature
    response = requests.get('{}/api/v3/account?{}'.format(base_url, urlencode(data)), headers={'X-MBX-APIKEY': api_key})
    if response.status_code != 200:
        raise RuntimeError()
    return response.json()


def get_config():
    with open('config.json') as config_file:
        pass


def monitor(symbol):
    asset = {'name': symbol, 'possess': False}
    while True:
        kline_data = {'symbol': symbol, 'interval': kline_interval, 'limit': 1}
        kline_response = requests.get('{}/api/v1/klines?{}'.format(base_url, urlencode(kline_data)))

        if kline_response.status_code != 200:
            raise RuntimeError()

        kline = kline_response.json()[0]
        price_open = kline[1]
        price_now = kline[4]
        price_low = kline[3]

        if not asset['possess'] and price_now >= price_open * trigger_percent:
            LOGGER.info('Buy {} {} at price {} ETH'.format(1000, symbol, price_now))
            asset['possess'] = True
            asset['buy_price'] = price_now
            asset['quality'] = 1000
            asset['eth_spent'] = price_now * 1000
            asset['eth_earning'] = 0
            asset['stop_loss_price'] = price_now * stop_loss_percent
            asset['profit_low_taken'] = False

        if asset['possess']:
            asset['low_price'] = price_low
            asset['take_profit_price_low'] = price_low * take_profit_low_percent
            asset['take_profit_price_high'] = price_low * take_profit_high_percent

            if not asset['profit_low_taken'] and price_now >= asset['take_profit_price_low']:
                asset['eth_earning'] += price_now * 500
                asset['profit_low_taken'] = True

            if price_now >= asset['take_profit_price_high']:
                asset['eth_earning'] += price_now * 500
                asset = {'name': symbol, 'possess': False}
                total_eth_earning += asset['eth_earning']
                continue

            if price_now <= asset['stop_loss_price']:
                asset['eth_earning'] += price_now * 1000
                asset = {'name': symbol, 'possess': False}
                total_eth_earning += asset['eth_earning']




        sleep(30)

monitor('WAVESETH')