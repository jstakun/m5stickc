import network
import urequests
import time
import ujson
import sys
import _thread
import utime
from machine import Pin, PWM
import usocket as socket
import ustruct as struct

def currentTime():
  NTP_QUERY = bytearray(48)
  NTP_QUERY[0] = 0x1B
  addr = socket.getaddrinfo("pool.ntp.org", 123)[0][-1]
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  try:
      s.settimeout(1)
      res = s.sendto(NTP_QUERY, addr)
      msg = s.recv(48)
  finally:
      s.close()
  val = struct.unpack("!I", msg[40:44])[0]
  EPOCH_YEAR = utime.localtime(0)[0]
  if EPOCH_YEAR == 2000:
      # (date(2000, 1, 1) - date(1900, 1, 1)).days * 24*60*60
      NTP_DELTA = 3155673600
  elif EPOCH_YEAR == 1970:
      # (date(1970, 1, 1) - date(1900, 1, 1)).days * 24*60*60
      NTP_DELTA = 2208988800
  else:
      raise Exception("Unsupported epoch: {}".format(EPOCH_YEAR))
  return val - NTP_DELTA

def isOlderThanHour(date_str): 
  global rtc
  [yyyy, mm, dd] = [int(i) for i in date_str.split('T')[0].split('-')]
  [HH, MM, SS] = [int(i) for i in date_str.split('T')[1].split(':')]
  the_date = (yyyy, mm, dd, HH, MM, SS, 0, 0, 0)
  seconds = utime.mktime(the_date) #UTC+1
  now = utime.time() #UTC
  #print(str(rtc.datetime()) + " " + str(the_date))
  diff = (now - seconds + 3600)
  print('Current entry is ' + str(diff) + ' seconds old')
  return diff > 3600  

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
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX

  sgv = response['sgv']
  sgvStr = str(response['sgv'])
  if "ago" in response: dateStr = response['ago']
  else: dateStr = response['date']
  directionStr = response['direction']

  olderThanHour = False
  try:
    olderThanHour = isOlderThanHour(response['date'])
  except Exception as e:
    sys.print_exception(e)

  axp.setLcdBrightness(brightness)

  if olderThanHour: backgroundColor=lcd.DARKGREY; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on(); emergency=False
  elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on(); emergency=(utime.time() > emergencyPause)
  elif sgv > EMERGENCY_MIN and sgv <= MIN: backgroundColor=lcd.RED; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on(); emergency=False
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); emergency=False; M5Led.off() 
  elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on(); emergency=False
  elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; lcd.clear(backgroundColor); lcd.setTextColor(lcd.WHITE); M5Led.on(); emergency=(utime.time() > emergencyPause)  

  if mode == 0:  
    #full mode
    #sgv
    if sgv < 100: sgvStr = " " + sgvStr
    lcd.font(lcd.FONT_DejaVu56, rotate=90)
    lcd.text((int)(136-48+(lcd.fontSize()[1]/2)), 24, sgvStr)

    #direction
    x=88
    y=176
    lcd.circle(x, y, 40, fillcolor=lcd.WHITE)
    
    if directionStr == 'Flat':
      lcd.triangle(x-20, y-15, x+20, y-15, x, y+25, fillcolor=backgroundColor, color=backgroundColor)
    elif directionStr == 'FortyFiveDown' or directionStr == 'FortyFiveUp':
      lcd.triangle(x-22, y+15, x+22, y+15, x, y-27, fillcolor=backgroundColor, color=backgroundColor)
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
    lcd.font(lcd.FONT_DejaVu24, rotate=90)
    w = lcd.textWidth(dateStr)
    lcd.text(12+lcd.fontSize()[1], (int)((241-w)/2), dateStr)
  elif mode == 2:
    #battery mode
    lcd.font(lcd.FONT_DejaVu24, rotate=90)
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

def onBtnAPressed():
  global mode, MODES, emergency 
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + 1800 #30 mins
  else:   
    if mode == 2: mode = 0
    elif mode < 2: mode += 1 
    print('Selected mode ' + MODES[mode])
    printScreen()

def onBtnBPressed():
  global emergency
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + 1800 #30 mins
  else:   
    global brightness
    brightness += 16
    if brightness > 96: brightness = 16
    axp.setLcdBrightness(brightness)

def emergencyMonitor():
  global emergency, beeper, response
  while True:
    if emergency:
      print('Emergency glucose level ' + str(response['sgv']) + '!!!')
      beeper.resume()
      M5Led.on()
      time.sleep(0.5)
      beeper.pause()
      M5Led.off()
      time.sleep(0.5)
    else:
      #print('No emergency')
      beeper.pause()
      time.sleep(1)

########################################    

confFile = open('config.json', 'r')
config = ujson.loads(confFile.read())

WIFI = config["wifi"]
API_ENDPOINT = config["api-endpoint"]
API_TOKEN = config["api-token"]
LOCALE = config["locale"]
INTERVAL = config["interval"]
MIN = config["min"]
MAX = config["max"]
EMERGENCY_MIN = config["emergencyMin"]
EMERGENCY_MAX = config["emergencyMax"] 

MODES = ["full", "basic", "battery"]
mode = 0
response = {}
brightness = 32
emergency = False
emergencyPause = 0

beeper = PWM(Pin(2), freq=1000, duty=50)
beeper.pause()

axp.setLcdBrightness(brightness)
lcd.clear(lcd.WHITE)
lcd.setTextColor(lcd.WHITE)
lcd.font(lcd.FONT_DejaVu24, rotate=90)

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
   ssid = result[0].decode() 
   if ssid in WIFI: found = True; SSID=ssid; WIFI_PASSWORD=WIFI[ssid]; break
 if not found: time.sleep(1)

lcd.clear(lcd.OLIVE)
msg = "Connecting wifi..."
w = lcd.textWidth(msg)
lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)
nic.connect(SSID, WIFI_PASSWORD)
print('Connecting wifi ' + SSID)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)

lcd.clear(lcd.GREENYELLOW)
msg = "Loading data..."
w = lcd.textWidth(msg)
lcd.text(54+lcd.fontSize()[1], (int)((241-w)/2), msg)

print('Setting time...')
rtc = machine.RTC()
tm = utime.localtime(currentTime())
rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
print("Current time " +  str(rtc.datetime()))

_thread.start_new_thread(callBackend, ())
_thread.start_new_thread(emergencyMonitor, ())

btnA.wasPressed(onBtnAPressed)
btnB.wasPressed(onBtnBPressed)

