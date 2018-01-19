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
        total_price += float(fill['price']) * float(fill['qty'])
        total_quantity += float(fill['qty'])
        total_commission += float(fill['commission'])

    return total_price / total_quantity, total_commission


def qualify(klines, threshold_percent):
    lowest_price = 1000000000
    highest_price = 0
    for kline in klines:
        price_low = float(kline[4])
        price_high = float(kline[2])
        if price_low < lowest_price:
            lowest_price = price_low
        if price_high > highest_price:
            highest_price = price_high

    if highest_price / lowest_price - 1 >= threshold_percent:
        return False
    return True
