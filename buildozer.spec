[app]
title = Binance Trading App
package.name = binance_trading_app
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,ico
version = 0.1
requirements = python3,kivy==2.2.1,ccxt,requests
orientation = portrait
android.arch = armeabi-v7a, arm64-v8a
icon.filename = binance_icon.png
presplash.filename = binance_icon.png

[buildozer]
log_level = 2
