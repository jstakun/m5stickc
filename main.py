import network
import urequests
import time
import ujson
import sys
import _thread
from machine import Pin

def getBatteryLevel():
  volt = axp.getBatVoltage()
  if volt < 3.20: return -1
  if volt < 3.27: return 0
  if volt < 3.61: return 5
  if volt < 3.69: return 10
  if volt < 3.71: return 15
  if volt < 3.73: return 20
  if volt < 3.75: return 25
  if volt < 3.77: return 30
  if volt < 3.79: return 35
  if volt < 3.80: return 40
  if volt < 3.82: return 45
  if volt < 3.84: return 50
  if volt < 3.85: return 55
  if volt < 3.87: return 60
  if volt < 3.91: return 65
  if volt < 3.95: return 70
  if volt < 3.98: return 75
  if volt < 4.02: return 80
  if volt < 4.08: return 85
  if volt < 4.11: return 90
  if volt < 4.15: return 95
  if volt < 4.20: return 100
  if volt >= 4.20: return 101

def printScreen():
  global response, mode, MIN, MAX

  sgv = response['sgv']
  sgvStr = str(response['sgv'])
  if "ago" in response: dateStr = response['ago']
  else: dateStr = response['date']
  directionStr = response['direction']

  if sgv <= MIN: backgroundColor=lcd.RED; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on()
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.off() 
  else: backgroundColor=lcd.ORANGE; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on()
  
  if mode == 0:  
    #full mode
    #sgv
    lcd.text((int)(136-48+(lcd.fontSize()[1]/2)), 44, sgvStr)

    #direction
    x=88
    y=156
    lcd.circle(x, y, 40, fillcolor=lcd.WHITE)
    
    if directionStr == 'Flat':
      lcd.triangle(x-20, y-15, x+20, y-15, x, y+25, fillcolor=backgroundColor, color=backgroundColor)
    elif directionStr == 'FortyFiveDown' or directionStr == 'FortyFiveUp':
      lcd.triangle(x-20, y+15, x+25, y+15, x, y-27, fillcolor=backgroundColor, color=backgroundColor)
    elif directionStr == 'DoubleDown': 
      lcd.triangle(x+25, y-20, x+25, y+20, x-10, y, fillcolor=lcd.RED, color=lcd.RED)
      lcd.triangle(x, y-20, x, y+20, x-30, y, fillcolor=lcd.RED, color=lcd.RED)
    elif directionStr == 'DoubleUp':
      lcd.triangle(x, y-20, x, y+20, x+30, y, fillcolor=lcd.RED, color=lcd.RED)
      lcd.triangle(x-25, y-20, x-25, y+20, x+5, y, fillcolor=lcd.RED, color=lcd.RED)
    elif directionStr == 'SingleUp':
      lcd.triangle(x-15, y-20, x-15, y+20, x+25, y, fillcolor=lcd.ORANGE, color=lcd.ORANGE)
    elif directionStr == 'SingleDown':
      lcd.triangle(x+15, y-20, x+15, y+20, x-25, y, fillcolor=lcd.ORANGE, color=lcd.ORANGE)
    else:
      print("Unknown direction: " + directionStr)

    #ago or date
    w = lcd.textWidth(dateStr)
    lcd.text(12+lcd.fontSize()[1], (int)((241-w)/2), dateStr)
  elif mode == 2:
    #battery mode
    msg = 'Battery: ' + str(getBatteryLevel()) + '%'
    w = lcd.textWidth(msg)
    lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)

def callBackend():
  global response, INTERVAL, API_ENDPOINT, API_TOKEN, LOCALE
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      response = urequests.get(API_ENDPOINT + "/1/api/v1/entries.json?count=1",headers={'api-secret': API_TOKEN,'accept-language': LOCALE}).json()
      print('Sgv: ', response['sgv'])
      print('Read: ', response['date'])
      print('Direction: ', response['direction'])
      printScreen()
      time.sleep(INTERVAL)
    except Exception as e:
      sys.print_exception(e)
      retry = (int)(INTERVAL/4)
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Network error. Retry in ' + str(retry) + ' sec...')
      time.sleep(retry)

def onBtnWasPressed(p):
  global mode, MODES 
  if mode==2: mode = 0
  elif mode<2: mode += 1 
  print('Selected mode ' + MODES[mode] + ' with button ', p)
  printScreen()

confFile = open('config.json', 'r')
config = ujson.loads(confFile.read())

SSID = config["ssid"]
WIFI_PASSWORD = config["wifi-password"]
API_ENDPOINT = config["api-endpoint"]
API_TOKEN = config["api-token"]
LOCALE = config["locale"]
INTERVAL = config["interval"]
MIN = config["min"]
MAX = config["max"]

MODES = ["full", "basic", "battery"]
mode = 0
response = {}

lcd.clear(lcd.WHITE)
lcd.setTextColor(lcd.WHITE)
lcd.font(lcd.FONT_DejaVu24, rotate=90)
lcd.orient(lcd.PORTRAIT)

nic = network.WLAN(network.STA_IF)
nic.active(True)

lcd.clear(lcd.DARKGREY)
msg = "Scanning wifi..."
w = lcd.textWidth(msg)
lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)
found = False
while not found:
 nets = nic.scan()
 for result in nets:
   if result[0].decode() == SSID: found = True; break
 time.sleep(0.25)

lcd.clear(lcd.OLIVE)
msg = "Connecting wifi..."
w = lcd.textWidth(msg)
lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)
nic.connect(SSID, WIFI_PASSWORD)
print('Connecting wifi ' + SSID)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)

lcd.clear(lcd.DARKGREEN)
msg = "Loading data..."
w = lcd.textWidth(msg)
lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)

_thread.start_new_thread(callBackend, ())

btnM5 = Pin(37, Pin.IN)
btnM5.irq(trigger=Pin.IRQ_RISING, handler=onBtnWasPressed)
