from math import floor


def order_precheck(symbol, quantity):
    min_qty = float(symbol['filters'][1]['minQty'])
    max_qty = float(symbol['filters'][1]['maxQty'])
    qty_step = float(symbol['filters'][1]['stepSize'])

    if min_qty <= quantity <= max_qty:
        return floor(quantity / qty_step) * qty_step
    return False


def handle_order_data(order_info):
    total_price = 0
    total_quantity = 0
    total_commission = 0
    for fill in order_info['fills']:
        total_price += float(fill['price'])
        total_quantity += float(fill['qty'])
        total_commission += float(fill['commission'])

    return total_price / total_quantity, total_commission


def qualify(klines, threshold_percent):
    current_price = float(klines[-1][4])
    lowest_price = 1000000000
    for kline in klines:
        price_low = float(kline[4])
        if price_low < lowest_price:
            lowest_price = price_low

    if current_price / lowest_price - 1 >= threshold_percent:
        return False
    return True