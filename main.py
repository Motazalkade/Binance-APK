from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.clock import Clock
import threading, time, os, sys

sys.path.insert(0, os.path.dirname(__file__))
from binance_backend import Backend

class CoinRow(BoxLayout):
    def __init__(self, symbol, icon_path=None, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=64, padding=6, spacing=8, **kwargs)
        if icon_path and os.path.exists(icon_path):
            self.add_widget(Image(source=icon_path, size_hint=(None, None), size=(48,48)))
        else:
            self.add_widget(Label(text='🪙', size_hint=(None, None), width=48))
        self.symbol_label = Label(text=symbol, size_hint_x=0.3)
        self.price_label = Label(text='--', size_hint_x=0.4)
        self.add_widget(self.symbol_label)
        self.add_widget(self.price_label)

    def set_price(self, price):
        try:
            self.price_label.text = f'{price:.6f}'
        except Exception:
            self.price_label.text = str(price)

class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=8, spacing=8, **kwargs)
        self.backend = Backend()

        self.add_widget(Label(text='تطبيق SKY - تداول باينانس', font_size='20sp', size_hint_y=None, height=44))

        # API inputs
        api_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=44, spacing=8)
        self.api_key = TextInput(hint_text='API Key', multiline=False)
        self.api_secret = TextInput(hint_text='API Secret', multiline=False, password=True)
        save_btn = Button(text='حفظ المفاتيح', size_hint_x=None, width=140)
        save_btn.bind(on_release=self.save_keys)
        api_box.add_widget(self.api_key)
        api_box.add_widget(self.api_secret)
        api_box.add_widget(save_btn)
        self.add_widget(api_box)

        # Controls
        ctrl_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=48, spacing=8)
        self.start_btn = Button(text='بدء التتبع', on_release=self.start_fetch)
        self.stop_btn = Button(text='إيقاف', on_release=self.stop_fetch, disabled=True)
        self.enable_trade_btn = Button(text='تفعيل التداول (مغلق)', on_release=self.toggle_trading)
        ctrl_box.add_widget(self.start_btn)
        ctrl_box.add_widget(self.stop_btn)
        ctrl_box.add_widget(self.enable_trade_btn)
        self.add_widget(ctrl_box)

        # Coin list (scrollable)
        self.coin_area = GridLayout(cols=1, spacing=6, size_hint_y=None)
        self.coin_area.bind(minimum_height=self.coin_area.setter('height'))
        self.coins = {}
        self.populate_coins(['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'XRP/USDT', 'DOGE/USDT', 'SOL/USDT', 'MATIC/USDT'])

        scroll = ScrollView(size_hint=(1, 0.45))
        scroll.add_widget(self.coin_area)
        self.add_widget(scroll)

        # Log area with clear button
        log_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40)
        self.clear_log_btn = Button(text='مسح السجل', size_hint_x=None, width=120)
        self.clear_log_btn.bind(on_release=self.clear_log)
        log_box.add_widget(Label(text='سجل الرسائل:'))
        log_box.add_widget(self.clear_log_btn)
        self.add_widget(log_box)

        self.log = TextInput(text='...', readonly=True, size_hint=(1, 0.28))
        self.add_widget(self.log)

        # Periodic UI update scheduler
        self.ui_event = None

    def populate_coins(self, symbols):
        for sym in symbols:
            icon_file = os.path.join('coin_icons', sym.split('/')[0].lower() + '-logo.png')
            row = CoinRow(sym, icon_path=icon_file if os.path.exists(icon_file) else None)
            self.coins[sym] = row
            self.coin_area.add_widget(row)

    def save_keys(self, *a):
        key = self.api_key.text.strip()
        secret = self.api_secret.text.strip()
        self.backend.set_keys(key, secret)
        self.log_message('تم حفظ المفاتيح (لم يتم تفعيل التداول تلقائياً).')

    def start_fetch(self, *a):
        if self.backend.running:
            self.log_message('التتبع يعمل بالفعل.')
            return
        self.backend.start_loop()
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.log_message('بدأ تتبع الأسعار.')
        self.ui_event = Clock.schedule_interval(lambda dt: self.refresh_ui(), 1.0)

    def stop_fetch(self, *a):
        self.backend.stop_loop()
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.log_message('أوقف التتبع.')
        if self.ui_event:
            self.ui_event.cancel()
            self.ui_event = None

    def toggle_trading(self, *a):
        self.backend.enable_trading = not self.backend.enable_trading
        state = 'مفعل' if self.backend.enable_trading else 'متوقف'
        self.enable_trade_btn.text = f'تفعيل التداول ({state})' if self.backend.enable_trading else 'تفعيل التداول (مغلق)'
        self.log_message(f'حالة التداول: {state}')

    def refresh_ui(self):
        tickers = self.backend.latest_tickers()
        for sym, price in tickers.items():
            if sym in self.coins:
                try:
                    self.coins[sym].set_price(price)
                except Exception:
                    pass
        logs = self.backend.drain_logs()
        for ln in logs:
            self.log_message(ln)

    def log_message(self, msg):
        ts = time.strftime('%H:%M:%S')
        self.log.text = f'[{ts}] {msg}\n' + self.log.text

    def clear_log(self, *a):
        self.log.text = ''

class SkyApp(App):
    def build(self):
        return MainLayout()

if __name__ == '__main__':
    SkyApp().run()
