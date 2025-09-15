"""منطـق التداول المدمـج من Binance AI.py -- منظم داخل كلاس Backend لاستخدامه من واجهة Kivy
ملاحظات:
- يستخدم ccxt للتواصل مع Binance (يفضل تثبيت ccxt في بيئة البناء).
- التداول الحقيقي معطّل افتراضياً (enable_trading=False). لتفعيله يجب تشغيله من الواجهة.
- بعض وظائف السحب قد لا تكون مدعومة بواسطة ccxt بنفس الطريقة مثل python-binance، فوضعت نقاطًا واضحة تحتاج مراجعة عند الاختبار الحقيقي.
"""
import time
from decimal import Decimal, ROUND_DOWN
from collections import deque
import threading
import ccxt
import traceback

class Backend:
    BANNED_ASSETS = {
        'BCD', 'CND', 'MTH', 'NCASH', 'YOYO', 'COVER', 'DLT', 'GVT', 'SKY', 'POA',
        'GRS', 'NAS', 'GO', 'HOOK', 'PDA', 'ALGO', 'CHR', 'DGB', 'GMX', 'DCR',
        'PEPE', 'ZEN', 'AKRO', 'BLZ', 'WRX', 'BADGER', 'BAL', 'BETA', 'CREAM',
        'CTXC', 'ELF', 'FIRO', 'HARD', 'NULS', 'PROS', 'SNT', 'TROY', 'UFT', 'VIDT',
        'ANIME', 'STRK', 'THE', 'ALPHA', 'BSW', 'KMD', 'LEVER', 'LTO', 'AION'
    }

    def __init__(self):
        self.api_key = ''
        self.api_secret = ''
        self.exchange = None
        self._loop_thread = None
        self._stop_event = threading.Event()
        self._tickers = {}
        self._logs = deque(maxlen=2000)
        self.running = False
        self.enable_trading = False  # safety default
        self.markets = {}  # loaded markets info

    def log(self, msg):
        ts = time.strftime('%H:%M:%S')
        self._logs.appendleft(f'[{ts}] {msg}')

    def drain_logs(self):
        items = []
        while self._logs:
            items.append(self._logs.pop())
        return items

    def set_keys(self, key, secret):
        self.api_key = key or ''
        self.api_secret = secret or ''
        try:
            if self.api_key and self.api_secret:
                self.exchange = ccxt.binance({
                    'apiKey': self.api_key,
                    'secret': self.api_secret,
                    'enableRateLimit': True,
                    'options': {'adjustForTimeDifference': True}
                })
                # load markets for symbol info
                self.markets = self.exchange.load_markets()
                self.log('تم تهيئة اتصال Binance مع مفاتيح API.')
            else:
                # public exchange instance (read-only)
                self.exchange = ccxt.binance({'enableRateLimit': True})
                self.markets = self.exchange.load_markets()
                self.log('تم تهيئة اتصال Binance عام (بدون مفاتيح).')
        except Exception as e:
            tb = traceback.format_exc()
            self.log(f'فشل تهيئة Binance: {e}')
            self.log(tb)

    def start_loop(self, interval=5):
        if self.running:
            return
        self._stop_event.clear()
        self._loop_thread = threading.Thread(target=self._run_loop, args=(interval,), daemon=True)
        self.running = True
        self._loop_thread.start()
        self.log('تشغيل حلقة جلب الأسعار.')

    def stop_loop(self):
        if not self.running:
            return
        self._stop_event.set()
        self.running = False
        self.log('إيقاف حلقة جلب الأسعار.')

    def _run_loop(self, interval):
        while not self._stop_event.is_set():
            try:
                # default symbols if empty
                symbols = list(self._tickers.keys()) or ['BTC/USDT','ETH/USDT','BNB/USDT','ADA/USDT','XRP/USDT','DOGE/USDT']
                for sym in symbols:
                    try:
                        price = self.fetch_ticker(sym)
                        if price is not None:
                            self._tickers[sym] = price
                    except Exception as e:
                        self.log(f'خطأ عند جلب {sym}: {e}')
            except Exception as ex:
                self.log(f'خطأ عام في حلقة الخلفية: {ex}')
            self._stop_event.wait(interval)

    def fetch_ticker(self, symbol):
        try:
            if not self.exchange:
                self.set_keys('','')
            # ccxt uses market ids like 'BTC/USDT'
            ticker = self.exchange.fetch_ticker(symbol)
            price = ticker.get('last') or ticker.get('close') or None
            return Decimal(str(price)) if price is not None else None
        except Exception as e:
            self.log(f'fetch_ticker خطأ لـ {symbol}: {e}')
            return None

    def latest_tickers(self):
        return dict(self._tickers)

    # utilities adapted from original script
    def get_symbol_info(self, market_symbol):
        # market_symbol expected like 'BTC/USDT' or 'BTCUSDT'
        if '/' not in market_symbol and market_symbol.endswith('USDT'):
            market_symbol = market_symbol[:-4] + '/USDT'
        return self.markets.get(market_symbol)

    def get_min_notional(self, market_symbol):
        try:
            info = self.get_symbol_info(market_symbol)
            if not info: 
                return Decimal('0')
            # ccxt market info contains 'limits' -> 'cost' for minimum cost
            cost_limit = info.get('limits', {}).get('cost')
            if cost_limit and cost_limit.get('min') is not None:
                return Decimal(str(cost_limit.get('min')))
            # fallback to 0
            return Decimal('0')
        except Exception:
            return Decimal('0')

    def get_symbol_precision(self, market_symbol):
        try:
            info = self.get_symbol_info(market_symbol)
            if not info:
                return 8
            # amountPrecision not always present; infer from step size
            step = info.get('limits', {}).get('amount', {}).get('min')
            if step is None:
                # fallback to 8
                return 8
            # calculate precision from step like 0.001 => 3
            s = str(step)
            if '.' in s:
                return len(s.split('.')[1].rstrip('0'))
            return 0
        except Exception:
            return 8

    def format_quantity(self, quantity, precision):
        fmt_str = f"{{:.{precision}f}}"
        formatted = fmt_str.format(quantity)
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted

    def cancel_all_pending_orders(self):
        try:
            if not self.exchange:
                self.log('لم يتم تهيئة Exchange لإلغاء الأوامر.')
                return False
            open_orders = self.exchange.fetch_open_orders()
            if not open_orders:
                self.log('لا توجد أوامر معلقة.')
                return True
            for o in open_orders:
                try:
                    symbol = o.get('symbol')
                    order_id = o.get('id')
                    self.exchange.cancel_order(order_id, symbol)
                    self.log(f'تم إلغاء الأمر المعلق: {symbol} (ID: {order_id})')
                except Exception as e:
                    self.log(f'فشل إلغاء أمر {o}: {e}')
            time.sleep(2)
            return True
        except Exception as e:
            self.log(f'خطأ في cancel_all_pending_orders: {e}')
            return False

    def calculate_total_asset_value(self):
        try:
            if not self.exchange:
                self.log('Exchange غير مهيأ لحساب الأصول.')
                return Decimal('0')
            # fetch balances via ccxt (fetch_balance)
            bal = self.exchange.fetch_balance()
            total = Decimal('0')
            # get tickers for pricing
            tickers = self.exchange.fetch_tickers()
            for asset, info in bal.get('total', {}).items():
                if asset in self.BANNED_ASSETS:
                    continue
                amt = Decimal(str(info or 0))
                if amt <= 0:
                    continue
                if asset == 'USDT':
                    total += amt
                else:
                    pair = f"{asset}/USDT"
                    price = tickers.get(pair, {}).get('last') if isinstance(tickers, dict) else None
                    if price is None:
                        # try without slash
                        price = tickers.get(asset+'USDT', {}).get('last') if isinstance(tickers, dict) else None
                    if price:
                        total += amt * Decimal(str(price))
            return total
        except Exception as e:
            self.log(f'خطأ في calculate_total_asset_value: {e}')
            return Decimal('0')

    def convert_to_usdt(self, min_value_threshold=5):
        """محاولة تحويل جميع الأصول غير USDT إلى USDT
        - تحاول البيع مباشرة في زوج ASSET/USDT، وإن لم يكن متاحاً تحاول عبر وسطاء (BTC, ETH, BNB, BUSD)
        - إذا enable_trading==False لا تُرسل أوامر حقيقية بل تُسجّل فقط (محاكاة)
        """
        results = []
        try:
            if not self.exchange:
                self.log('Exchange غير مهيأ للـ convert_to_usdt.')
                return False, 'Exchange غير مهيأ'
            # cancel pending orders first
            self.cancel_all_pending_orders()
            bal = self.exchange.fetch_balance()
            totals = bal.get('total', {})
            tickers = self.exchange.fetch_tickers()
            intermediates = ['BTC','ETH','BNB','BUSD']
            for asset, amt in totals.items():
                try:
                    if asset in self.BANNED_ASSETS:
                        continue
                    amount = Decimal(str(amt or 0))
                    if amount <= 0 or asset == 'USDT':
                        continue
                    # compute USD value
                    pair = f"{asset}/USDT"
                    price = None
                    if pair in tickers:
                        price = tickers[pair].get('last')
                    if price:
                        value = amount * Decimal(str(price))
                    else:
                        value = Decimal('0')
                    if value < Decimal(str(min_value_threshold)):
                        self.log(f'تخطي {asset} لأن قيمته {value} (أقل من {min_value_threshold})')
                        continue
                    # attempt direct sell
                    if pair in self.markets:
                        precision = self.get_symbol_precision(pair)
                        qty_str = self.format_quantity(amount, precision)
                        self.log(f'محاولة بيع مباشر: {asset} -> USDT qty={qty_str}')
                        if self.enable_trading:
                            try:
                                order = self.exchange.create_market_sell_order(pair, float(qty_str))
                                self.log(f'أمر بيع مُرسل: {order}')
                                results.append(f'[نجاح] {asset} -> USDT')
                            except Exception as e:
                                self.log(f'فشل عند إرسال أمر البيع المباشر: {e}')
                                # fallthrough to intermediates
                        else:
                            self.log(f'(محاكاة) لن يتم إرسال أمر بيع مباشر لـ {asset}')
                            results.append(f'[محاكاة] {asset} -> USDT (لم تُرسل أمرًا)')
                            continue
                    else:
                        # try via intermediates
                        converted = False
                        for inter in intermediates:
                            try:
                                pair1 = f"{asset}/{inter}"
                                pair2 = f"{inter}/USDT"
                                if pair1 in self.markets and pair2 in self.markets:
                                    precision1 = self.get_symbol_precision(pair1)
                                    qty1 = self.format_quantity(amount, precision1)
                                    self.log(f'محاولة تحويل عبر وسيط {inter}: {asset} -> {inter} (qty={qty1}) ثم {inter} -> USDT')
                                    if self.enable_trading:
                                        try:
                                            o1 = self.exchange.create_market_sell_order(pair1, float(qty1))
                                            # after sell, determine intermediate amount from balance
                                            time.sleep(1)
                                            bal2 = self.exchange.fetch_balance()
                                            inter_amount = Decimal(str(bal2.get('free', {}).get(inter, 0))) or Decimal('0')
                                            if inter_amount <= 0:
                                                continue
                                            precision2 = self.get_symbol_precision(pair2)
                                            qty2 = self.format_quantity(inter_amount, precision2)
                                            o2 = self.exchange.create_market_sell_order(pair2, float(qty2))
                                            self.log(f'أوامر وسيط مُرسلة: {o1}, {o2}')
                                            results.append(f'[نجاح] {asset} -> {inter} -> USDT')
                                            converted = True
                                            break
                                        except Exception as e:
                                            self.log(f'فشل تحويل عبر الوسيط {inter}: {e}')
                                            continue
                                    else:
                                        self.log(f'(محاكاة) تحويل عبر {inter} لـ {asset} (لن يُرسل أمر حقيقي)')
                                        results.append(f'[محاكاة] {asset} -> {inter} -> USDT')
                                        converted = True
                                        break
                            except Exception as e:
                                self.log(f'استثناء داخل محاولات الوسيط: {e}')
                                continue
                        if not converted:
                            self.log(f'[فشل] لم يتم تحويل {asset}')
                            results.append(f'[فشل] {asset}')
                except Exception as e:
                    self.log(f'خطأ عند معالجة {asset}: {e}')
                    continue
            summary = '\n'.join(results) if results else 'لم يتم تحويل أي عملات'
            self.log('انتهاء محاولة التحويل إلى USDT.')
            return True, summary
        except Exception as e:
            tb = traceback.format_exc()
            self.log(f'استثناء في convert_to_usdt: {e}')
            self.log(tb)
            return False, str(e)

    def place_order(self, symbol, side, amount, price=None):
        """تنفيذ أمر سوقي أو محدد. side = 'buy' or 'sell'"""
        try:
            if not self.exchange:
                return {'error': 'Exchange غير مهيأ'}
            self.log(f'طلب تنفيذ أمر: {side} {symbol} qty={amount} price={price}')
            if not self.enable_trading:
                self.log('التداول الحقيقي غير مفعل - الأمر لن يُرسل (محاكاة).')
                return {'status':'simulated'}
            if price is None:
                order = self.exchange.create_market_order(symbol, side, float(amount))
            else:
                order = self.exchange.create_limit_order(symbol, side, float(amount), float(price))
            self.log(f'أمر مُرسل: {order}')
            return order
        except Exception as e:
            self.log(f'فشل عند إرسال الأمر: {e}')
            return {'error': str(e)}

    def send_usdt_via_arbitrum(self, address, min_withdraw=0.0):
        """محاولة سحب USDT عبر شبكة Arbitrum (قد لا يدعم ccxt كل المنصات بنفس API)."""
        try:
            if not self.exchange:
                self.log('Exchange غير مهيأ للسحب.')
                return False
            if not self.enable_trading:
                self.log('التداول/السحب معطّل (محاكاة).')
                return False
            # ccxt withdraw usage varies; here we try a generic withdraw call
            balance = self.exchange.fetch_balance()
            free_usdt = balance.get('free', {}).get('USDT', 0)
            if free_usdt <= min_withdraw:
                self.log(f'الرصيد أقل من الحد الأدنى للسحب: {free_usdt}')
                return False
            # attempt withdraw (this may require exchange-specific params)
            try:
                tx = self.exchange.withdraw('USDT', float(free_usdt), address, {'network': 'ARBITRUM'})
                self.log(f'تم تنفيذ السحب: {tx}')
                return Decimal(str(free_usdt))
            except Exception as e:
                self.log(f'فشل السحب عبر ccxt: {e}')
                return False
        except Exception as e:
            self.log(f'خطأ في send_usdt_via_arbitrum: {e}')
            return False
