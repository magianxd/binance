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


class Binance(object):
    trigger_percent = 0.1
    stop_loss_percent = 0.3
    take_profit_low_percent = 0.3
    take_profit_high_percent = 1
    kline_interval = '1h'
    base_symbol = 'ETH'
    total_earning = 0
    assets = []
    symbols = []
    worker_num = 1
    base_url = 'https://api.binance.com'
    api_key = None
    secret_key = None
    market_type = 'BULL'
    fluctuation_restrict = 1.3
    lock = threading.Lock()

    def __init__(self, config_file_path, market_type):
        with open(config_file_path) as config_file:
            config = json.load(config_file)

        self.secret_key = config['secret_key'].encode()
        self.api_key = config['api_key']

        self.log('Main', 'Initializing...')
        self.session = requests.session()
        self.market_type = market_type
        if self.market_type == 'BEAR':
            self.fluctuation_restrict = 10000000000
            self.trigger_percent = 0.2
            self.kline_interval = '6h'
            self.base_symbol = 'USDT'
            self.worker_num = 1
        self.session.headers.update({'X-MBX-APIKEY': self.api_key})
        self.symbols = [symbol for symbol in self.session.get(
            '{}/api/v1/exchangeInfo'.format(self.base_url)).json()['symbols']
                        if symbol['symbol'].endswith(self.base_symbol)]
        if self.market_type == 'BEAR':
            self.symbols = [symbol for symbol in self.symbols if symbol['symbol'] == 'BTCUSDT']
        self.get_account_info()

    def log(self, symbol, msg):
        with self.lock:
            with open('main_log.log'.format(uuid.uuid4()), 'a+') as log_file:
                log_file.write('{}-{}: {}\n'.format(datetime.now(), symbol, msg))

    def get_account_info(self):
        data = self.generate_sign_data({})
        response = self.session.get('{}/api/v3/account?{}'.format(self.base_url, urlencode(data)))
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
        quantity = utils.order_precheck(symbol, quantity)
        data = {'symbol': symbol['symbol'], 'side': side, 'quantity': quantity,
                'type': order_type, 'price': price, 'timeInForce': 'GTC',
                'newOrderRespType': 'FULL'}

        data = self.generate_sign_data(data)
        order_response = self.session.post('{}/api/v3/order?{}'.format(self.base_url, urlencode(data)))

        if order_response.status_code != 200:
            self.log('ERROR', 'Failed to place order: {}, {}, {}'.format(symbol, quantity, side))
            return

        order_info = order_response.json()

        if order_info['status'] != 'FILLED':
            return
        return order_info

    def place_market_order(self, symbol, side, quantity):
        quantity = utils.order_precheck(symbol, quantity)
        data = {'symbol': symbol['symbol'], 'side': side, 'quantity': quantity,
                'type': 'MARKET', 'newOrderRespType': 'FULL'}
        data = self.generate_sign_data(data)
        order_response = self.session.post('{}/api/v3/order?{}'.format(self.base_url, urlencode(data)))

        if order_response.status_code != 200:
            self.log('ERROR', 'Failed to place order: {}, {}, {}'.format(symbol, quantity, side))
            return

        order_info = order_response.json()

        if order_info['status'] != 'FILLED':
            return
        return order_info

    def monitor(self):
        self.log('Worker', 'Starting to monitor trading pairs')
        while self.symbols:
            asset = {}
            symbol = self.symbols.pop(0)
            kline_data = {'symbol': symbol['symbol'], 'interval': self.kline_interval, 'limit': 1}
            kline_response = self.session.get('{}/api/v1/klines?{}'.format(self.base_url, urlencode(kline_data)))

            if kline_response.status_code != 200:
                self.log('ERROR', 'Failed to get {} kline. status code: {}'.format(symbol['symbol'],
                                                                                   kline_response.status_code))
                self.symbols.append(symbol)
                sleep(1)
                continue

            kline = kline_response.json()[0]
            timestamp = int(kline[0])

            sold_asset = next((possessed_asset for possessed_asset in self.assets
                               if possessed_asset['name'] == symbol['symbol']), None)
            if sold_asset and sold_asset['sold'] and sold_asset['buy_timestamp'] != timestamp:
                self.log(sold_asset['name'],
                         'Found sold pairs, removing from assets. asset lifecycle details: {}'.format(asset))
                self.log('Total earnings so far: {}'.format(self.total_earning))
                self.assets.remove(sold_asset)

            price_open = float(kline[1])
            price_now = float(kline[4])

            if self.market_type == 'BULL':
                percent_fluctuation = price_now / price_open - 1
            elif self.market_type == 'BEAR':
                percent_fluctuation = price_open / price_now - 1
            else:
                raise RuntimeError('Unsupported market type')

            if self.trigger_percent <= percent_fluctuation < self.trigger_percent * self.fluctuation_restrict:
                self.log(symbol['symbol'], 'Buy operation triggered')
                account_info = self.get_account_info()
                balance = next((balance for balance in account_info['balances']
                                if balance['asset'] == self.base_symbol))
                balance_used = float(balance['free']) / self.worker_num

                if float(symbol['filters'][0]['minPrice']) <= balance_used <= float(symbol['filters'][0]['maxPrice']):
                    quantity = float(balance_used) / price_now
                    order_info = self.place_market_order(symbol, 'BUY', quantity)

                    if order_info:
                        asset['buy_price'], asset['commission'] = utils.handle_order_data(order_info)
                        asset['quantity'] = float(order_info['executedQty'])
                        asset['name'] = symbol['symbol']
                        asset['buy_timestamp'] = timestamp
                        asset['sold'] = False
                        asset['spent'] = asset['buy_price'] * asset['quantity']
                        asset['earning'] = 0
                        asset['stop_loss_price'] = asset['buy_price'] * self.stop_loss_percent
                        asset['profit_low_taken'] = False
                        self.log(symbol['symbol'], 'Buy {} at price {} ETH'.format(asset['quantity'],
                                                                                   asset['buy_price']))
                        self.assets.append(asset)
                        self.log(symbol['symbol'], 'Buy details: {}'.format(asset))
                        if self.market_type == 'BULL':
                            self.operator_bull(asset)
                        else:
                            self.operator_bear(asset)
                        continue

            self.symbols.append(symbol)
            sleep(1)

    def operator_bear(self, asset):
        self.log(asset['name'], 'Starting to operate trading pairs')
        while True:
            kline_data = {'symbol': asset['name'], 'interval': self.kline_interval, 'limit': 1}
            kline_response = self.session.get('{}/api/v1/klines?{}'.format(self.base_url, urlencode(kline_data)))

            if kline_response.status_code != 200:
                self.log('ERROR', 'Failed to get {} kline. status code: {}'.format(asset['name'],
                                                                                   kline_response.status_code))
                sleep(1)
                continue
            kline = kline_response.json()[0]
            timestamp = int(kline[0])
            price_now = float(kline[4])

            if asset['buy_timestamp'] < timestamp:
                self.log(asset['name'], 'Sell triggered at price: {}'.format(price_now))
                order_info = self.place_market_order(asset['name'], 'SELL', asset['quantity'])

                if order_info:
                    quantity = float(order_info['executedQty'])
                    sell_price, commission = utils.handle_order_data(order_info)
                    asset['commission'] += commission
                    asset['earning'] += sell_price * quantity
                    asset['quantity'] -= quantity
                    asset['sold'] = True
                    with self.lock:
                        self.total_earning += asset['earning'] - asset['spent']
                    self.log(asset['name'], 'Sell {} at price {} USDT, earning: {} USDT, total earning: {} USDT'.format(
                        quantity, sell_price, asset['earning'], self.total_earning))
                    break
            sleep(5)

    def operator_bull(self, asset):
        self.log(asset['name'], 'Starting to operate trading pairs')
        while True:
            kline_data = {'symbol': asset['name'], 'interval': self.kline_interval, 'limit': 1}
            kline_response = self.session.get('{}/api/v1/klines?{}'.format(self.base_url, urlencode(kline_data)))

            if kline_response.status_code != 200:
                self.log('ERROR', 'Failed to get {} kline. status code: {}'.format(asset['name'],
                                                                                   kline_response.status_code))
                sleep(1)
                continue
            kline = kline_response.json()[0]
            price_now = float(kline[4])

            if not asset['profit_low_taken'] and price_now / asset['buy_price'] - 1 >= self.take_profit_low_percent:
                self.log(asset['name'], 'Sell at profit {} triggered'.format(self.take_profit_low_percent))
                order_info = self.place_market_order(asset['name'], 'SELL', asset['quantity'] * 0.5)

                if order_info:
                    quantity = float(order_info['executedQty'])
                    sell_price, commission = utils.handle_order_data(order_info)
                    asset['commission'] += commission
                    asset['earning'] += sell_price * quantity
                    asset['quantity'] -= quantity
                    asset['profit_low_taken'] = True
                    self.log(asset['name'], 'Sell {} at price {} ETH, earning: {} ETH'.format(
                        quantity, sell_price, asset['earning']))

            if price_now / asset['buy_price'] - 1 >= self.take_profit_high_percent:
                self.log(asset['name'], 'Sell at profit {} triggered'.format(self.take_profit_high_percent))
                order_info = self.place_market_order(asset['name'], 'SELL', asset['quantity'])

                if order_info:
                    quantity = float(order_info['executedQty'])
                    sell_price, commission = utils.handle_order_data(order_info)
                    asset['commission'] += commission
                    asset['earning'] += sell_price * quantity
                    asset['sold'] = True
                    with self.lock:
                        self.total_earning += asset['earning'] - asset['spent']
                    self.log(asset['name'], 'Sell {} at price {} ETH, earning: {} ETH, total earning: {} ETH'.format(
                        quantity, sell_price, asset['earning'], self.total_earning))
                    break

            if price_now <= asset['stop_loss_price']:
                self.log(asset['name'], 'Sell at stop loss {} triggered'.format(self.stop_loss_percent))
                order_info = self.place_market_order(asset['name'], 'SELL', asset['quantity'])

                if order_info:
                    quantity = float(order_info['executedQty'])
                    sell_price, commission = utils.handle_order_data(order_info)
                    asset['commission'] += commission
                    asset['earning'] += sell_price * quantity
                    asset['sold'] = True
                    with self.lock:
                        self.total_earning += asset['earning'] - asset['spent']
                    self.log(asset['name'], 'Sell {} at price {} ETH, earning: {} ETH, total earning: {} ETH'.format(
                        quantity, sell_price, asset['earning'], self.total_earning))
                    break
            sleep(5)

    def start(self):
        self.log('Main', 'Starting worker threads to monitor trading pairs. Worker number: {}'.format(self.worker_num))
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.worker_num) as executor:
            monitor_futures = [executor.submit(self.monitor) for _ in range(self.worker_num)]

            for future in concurrent.futures.as_completed(monitor_futures):
                try:
                    future.result()
                except:
                    raise


if __name__ == '__main__':
    binance = Binance('config.json', 'BULL')
    binance.start()
