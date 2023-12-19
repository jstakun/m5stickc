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

def printCenteredText(msg, font=lcd.FONT_DejaVu24, rotateAngle=0, backgroundColor=lcd.BLACK, textColor=lcd.WHITE):
  lcd.font(font, rotate=rotateAngle)
  lcd.clear(backgroundColor)
  lcd.setTextColor(textColor)
  w = lcd.textWidth(msg)
  if rotateAngle==180:
    lcd.text((int)(w+((240-w)/2)), 80, msg)
  else:
    f = lcd.fontSize()
    lcd.text((int)((240-w)/2), (int)(80-f[0]), msg)

def drawDirection(x, y, direction, backgroundColor, fillColor=lcd.WHITE):
    lcd.circle(x, y, 40, fillcolor=fillColor)
    lcd.triangle(direction[0], direction[1], direction[2], direction[3], direction[4], direction[5], fillcolor=backgroundColor, color=backgroundColor)
    if len(direction) == 12:
      lcd.triangle(direction[6], direction[7], direction[8], direction[9], direction[10], direction[11], fillcolor=backgroundColor, color=backgroundColor)

def printScreen():
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, basicModeBackgroudColor

  sgv = response['sgv']
  sgvStr = str(response['sgv'])
  if sgv < 100: sgvStr = " " + sgvStr

  directionStr = response['direction']

  if "ago" in response and (mode == 0 or mode == 4): 
    dateStr = response['ago']
  elif mode == 2 or mode == 6:
    dateStr = "Battery: " + str(getBatteryLevel()) + "%"
  else:   
    dateStr = response['date'].replace("T", " ")[:-3] #remove seconds to fit screen

  olderThanHour = False
  try:
    olderThanHour = isOlderThanHour(response['date'])
  except Exception as e:
    sys.print_exception(e)

  axp.setLcdBrightness(brightness)

  if olderThanHour: backgroundColor=lcd.DARKGREY; M5Led.on(); emergency=False
  elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=(utime.time() > emergencyPause)  
  elif sgv > EMERGENCY_MIN and sgv <= MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=False
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off() 
  elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=False
  elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=(utime.time() > emergencyPause)  

  #if emergency change to one of full modes 
  if emergency==True and mode==3: mode=0

  #in basic mode skip background clearing if color doesn't change  
  if (mode != 3 or basicModeBackgroudColor != backgroundColor):
     lcd.clear(backgroundColor)
     lcd.setTextColor(lcd.WHITE)
  if mode == 3:   
     basicModeBackgroudColor = backgroundColor
     print("Skipping background clearing")
  else:
     basicModeBackgroudColor = -1   

  if mode in range (0,3):  
    #full mode
    
    #direction
    x=178
    y=48
    
    directions = {'Flat': (x-15, y-20, x-15, y+20, x+25, y), 
        'FortyFiveDown': (x+15, y-20, x+15, y+20, x-25, y),
        'FortyFiveUp': (x+15, y-20, x+15, y+20, x-25, y), 
        'DoubleDown': (x-20, y, x+20, y, x, y+30, x-20, y-25, x+20, y-25, x, y+10),
        'DoubleUp': (x-20, y+18, x+20, y+18, x, y-7, x-20, y-5, x+20, y-5, x, y-30), 
        'SingleUp': (x-20, y+15, x+20, y+15, x, y-25),
        'SingleDown': (x-20, y-15, x+20, y-15, x, y+25)} 
    
    direction = directions[directionStr] 
    
    if not olderThanHour and (directionStr == 'DoubleDown' or directionStr == 'DoubleUp'): 
      backgroundColor=lcd.RED
    elif not olderThanHour and (directionStr == 'SingleUp' or directionStr == 'SingleDown'):
      backgroundColor=lcd.ORANGE
    
    drawDirection(x, y, direction, backgroundColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=0)
    lcd.text(12, 24, sgvStr)
    
    #ago or date
    lcd.font(lcd.FONT_DejaVu24, rotate=0)
    lcd.text((int)((240-lcd.textWidth(dateStr))/2), 100, dateStr)
  elif mode in range(4,7):
    #flip mode

    #direction
    x=58
    y=44
    
    directions = {'Flat': (x+15, y-20, x+15, y+20, x-25, y), 
        'FortyFiveDown': (x-15, y-20, x-15, y+20, x+25, y),
        'FortyFiveUp': (x-15, y-20, x-15, y+20, x+25, y), 
        'DoubleDown': (x-20, y+18, x+20, y+18, x, y-7, x-20, y-5, x+20, y-5, x, y-30),
        'DoubleUp': (x-20, y, x+20, y, x, y+30, x-20, y-25, x+20, y-25, x, y+10), 
        'SingleUp': (x-20, y-15, x+20, y-15, x, y+25),
        'SingleDown': (x-20, y+15, x+20, y+15, x, y-25)} 
    
    direction = directions[directionStr] 
    
    if not olderThanHour and (directionStr == 'DoubleDown' or directionStr == 'DoubleUp'): 
      backgroundColor=lcd.RED
    elif not olderThanHour and (directionStr == 'SingleUp' or directionStr == 'SingleDown'):
      backgroundColor=lcd.ORANGE
    
    drawDirection(x, y, direction, backgroundColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=180)
    lcd.text(206, 66, sgvStr)

    #ago or date
    lcd.font(lcd.FONT_DejaVu24, rotate=180)
    x = (int)(240-((240-lcd.textWidth(dateStr))/2))
    if x>216: x=216
    lcd.text(x, 110, dateStr)
    
def callBackend():
  global response, INTERVAL, API_ENDPOINT, API_TOKEN, LOCALE, TIMEZONE
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      response = urequests.get(API_ENDPOINT + "/1/api/v1/entries.json?count=1",headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE}).json()
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
  global mode, MODES, emergency, emergencyPause
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + 1800 #30 mins
  else:   
    if mode == 6: mode = 0
    elif mode < 6: mode += 1 
    print('Selected mode ' + MODES[mode])
    printScreen()

def onBtnBPressed():
  global emergency, emergencyPause
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
    batteryLevel = getBatteryLevel();
    if emergency == True or (batteryLevel < 20 and batteryLevel > 0):
      if emergency == True:
        print('Emergency glucose level ' + str(response['sgv']) + '!!!')
      elif batteryLevel < 20:
        print('Low battery level ' + str(batteryLevel) + "%!!!")
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
TIMEZONE = config["timezone"]

MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery"]
mode = 0
response = {}
brightness = 32
emergency = False
emergencyPause = 0
basicModeBackgroudColor = -1

beeper = PWM(Pin(2), freq=1000, duty=50)
beeper.pause()

axp.setLcdBrightness(brightness)
lcd.orient(lcd.LANDSCAPE)
lcd.clear(lcd.WHITE)


nic = network.WLAN(network.STA_IF)
nic.active(True)

printCenteredText("Scanning wifi...", backgroundColor=lcd.DARKGREY)

found = False
while not found:
  try: 
    nets = nic.scan()
    for result in nets:
      ssid = result[0].decode() 
      if ssid in WIFI: found = True; SSID=ssid; WIFI_PASSWORD=WIFI[ssid]; break
  except Exception as e:
      sys.print_exception(e)
      printCenteredText("Saved wifi not found!", backgroundColor=lcd.RED)  
  if not found: time.sleep(1)

printCenteredText("Connecting wifi...", backgroundColor=lcd.OLIVE)
nic.connect(SSID, WIFI_PASSWORD)
print('Connecting wifi ' + SSID)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)

printCenteredText("Setting time...", backgroundColor=lcd.GREENYELLOW)

try: 
  rtc = machine.RTC()
  tm = utime.localtime(currentTime())
  rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
  print("Current time " +  str(rtc.datetime()))

  printCenteredText("Loading data...", backgroundColor=lcd.DARKGREEN)

  _thread.start_new_thread(callBackend, ())
  _thread.start_new_thread(emergencyMonitor, ())

  btnA.wasPressed(onBtnAPressed)
  btnB.wasPressed(onBtnBPressed)
except Exception as e:
  sys.print_exception(e)
  printCenteredText("Restart required!", backgroundColor=lcd.RED)
  