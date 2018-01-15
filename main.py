import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
import threading
import uuid
from datetime import datetime
from time import sleep
from urllib.parse import urlencode

import requests

import utils

LOGGER = logging.getLogger(__name__)


class Binance(object):
    trigger_percent = 1.1
    stop_loss_percent = 0.5
    take_profit_low_percent = 1.5
    take_profit_high_percent = 2
    kline_interval = '15m'
    total_eth_earning = 0
    symbols = []
    base_url = 'https://api.binance.com'
    api_key = None
    secret_key = None
    lock = threading.Lock()

    def __init__(self, config_file_path):
        with open(config_file_path) as config_file:
            config = json.load(config_file)

        self.secret_key = config['secret_key'].encode()
        self.api_key = config['api_key']
        self.symbols = config['symbols']
        fh = logging.FileHandler('log-{}.log'.format(uuid.uuid4()))
        fh.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
        LOGGER.addHandler(fh)

    def log(self, symbol, msg):
        with self.lock:
            LOGGER.info('{}: {}'.format(symbol, msg))

    def get_account_info(self):
        data = self.generate_sign_data({})
        response = requests.get('{}/api/v3/account?{}'.format(self.base_url, urlencode(data)),
                                headers={'X-MBX-APIKEY': self.api_key})
        if response.status_code != 200:
            raise RuntimeError('Failed to get account info')
        return response.json()

    def generate_sign_data(self, data):
        data['timestamp'] = int(round(datetime.now().timestamp() * 1000))
        data['recvWindow'] = 5000

        signature = base64.b16encode(hmac.new(self.secret_key, urlencode(data).encode(),
                                              digestmod=hashlib.sha256).digest())
        data['signature'] = signature
        return data

    def place_limit_order(self, symbol, side, quantity, order_type, price):
        quantity = utils.round_quantity(symbol, quantity)
        data = {'symbol': symbol, 'side': side, 'quantity': quantity,
                'type': order_type, 'price': price, 'timeInForce': 'GTC'}

        data = self.generate_sign_data(data)
        order_response = requests.post('{}/api/v3/order?{}'.format(self.base_url, urlencode(data)),
                                       headers={'X-MBX-APIKEY': self.api_key})

        if order_response.status_code != 200:
            raise RuntimeError('Failed to place order: {}, {}, {}, {}'.format(symbol, quantity, side, price))

        return order_response.json()

    def place_market_order(self, symbol, side, quantity):
        quantity = utils.round_quantity(symbol, quantity)
        data = {'symbol': symbol, 'side': side, 'quantity': quantity,
                'type': 'MARKET'}
        data = self.generate_sign_data(data)
        order_response = requests.post('{}/api/v3/order/test?{}'.format(self.base_url, urlencode(data)),
                                       headers={'X-MBX-APIKEY': self.api_key})

        if order_response.status_code != 200:
            raise RuntimeError('Failed to place order: {}, {}, {}'.format(symbol, quantity, side))

        return order_response.json()

    def monitor(self, symbol):
        asset = {'name': symbol, 'possess': False}
        while True:
            kline_data = {'symbol': symbol, 'interval': self.kline_interval, 'limit': 1}
            kline_response = requests.get('{}/api/v1/klines?{}'.format(self.base_url, urlencode(kline_data)))

            if kline_response.status_code != 200:
                raise RuntimeError('Failed to get {} kline'.format(symbol))

            kline = kline_response.json()[0]
            price_open = float(kline[1])
            price_now = float(kline[4])
            price_low = float(kline[3])

            if not asset['possess'] and price_now >= price_open * self.trigger_percent:
                account_info = self.get_account_info()
                # eth_asset = next((balance for balance in account_info['balances'] if balance['asset'] == 'ETH'))
                eth_asset = {'free': 10}
                eth_balance = eth_asset['free'] / len(self.symbols)

                if eth_balance >= 1:
                    quantity = int(float(eth_balance) / price_now)
                    order_info = self.place_market_order(symbol, 'BUY', quantity)
                    asset['possess'] = True
                    # asset['buy_price'] = order_info['price']
                    # asset['quantity'] = order_info['executedQty']
                    asset['buy_price'] = price_now
                    asset['quantity'] = quantity
                    asset['eth_spent'] = asset['buy_price'] * asset['quantity']
                    asset['eth_earning'] = 0
                    asset['stop_loss_price'] = asset['buy_price'] * self.stop_loss_percent
                    asset['profit_low_taken'] = False
                    self.log(symbol, 'Buy {} at price {} ETH'.format(asset['quantity'], asset['buy_price']))

            if asset['possess']:
                asset['low_price'] = price_low
                asset['take_profit_price_low'] = price_low * self.take_profit_low_percent
                asset['take_profit_price_high'] = price_low * self.take_profit_high_percent

                if not asset['profit_low_taken'] and price_now >= asset['take_profit_price_low']:
                    order_info = self.place_market_order(symbol, 'SELL', asset['quantity'] * 0.5)
                    # asset['eth_earning'] += order_info['price'] * order_info['executedQty']
                    asset['eth_earning'] += price_now * asset['quantity']
                    # asset['quantity'] -= order_info['executedQty']
                    asset['quantity'] -= asset['quantity'] * 0.5
                    asset['profit_low_taken'] = True
                    with self.lock:
                        self.total_eth_earning += asset['eth_earning']
                    # self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                    #     order_info['executedQty'], order_info['price'], self.total_eth_earning))
                    self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                        asset['quantity'] * 0.5, price_now, self.total_eth_earning))

                if price_now >= asset['take_profit_price_high']:
                    order_info = self.place_market_order(symbol, 'SELL', asset['quantity'])
                    # asset['eth_earning'] += order_info['price'] * order_info['executedQty']
                    asset['eth_earning'] += price_now * asset['quantity']
                    asset = {'name': symbol, 'possess': False}
                    with self.lock:
                        self.total_eth_earning += asset['eth_earning']
                    # self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                    #     order_info['executedQty'], order_info['price'], self.total_eth_earning))
                    self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                        asset['quantity'], price_now, self.total_eth_earning))
                    continue

                if price_now <= asset['stop_loss_price']:
                    order_info = self.place_market_order(symbol, 'SELL', asset['quantity'])
                    # asset['eth_earning'] += order_info['price'] * order_info['executedQty']
                    asset['eth_earning'] += price_now * asset['quantity']
                    asset = {'name': symbol, 'possess': False}
                    with self.lock:
                        self.total_eth_earning += asset['eth_earning']
                    # self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                    #     order_info['executedQty'], order_info['price'], self.total_eth_earning))
                    self.log(symbol, 'Sell {} at price {} ETH, total earning: {} ETH'.format(
                        asset['quantity'], price_now, self.total_eth_earning))
            sleep(5)

    def start(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.symbols)) as executor:
            monitor_futures = [executor.submit(self.monitor, symbol) for symbol in self.symbols]

            for future in concurrent.futures.as_completed(monitor_futures):
                try:
                    future.result()
                except:
                    raise


if __name__ == '__main__':
    binance = Binance('config.json')
    binance.start()
