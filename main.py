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
import gc
import deviceCfg
import wifiCfg

def getNtpTime():
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

def getDateTuple(date_str):
  [yyyy, mm, dd] = [int(i) for i in date_str.split('T')[0].split('-')]
  [HH, MM, SS] = [int(i) for i in date_str.split('T')[1].split(':')]
  return (yyyy, mm, dd, HH, MM, SS, 0, 0, 0)

def isOlderThan(date_str, mins): 
  global rtc
  the_date = getDateTuple(date_str)
  seconds = utime.mktime(the_date) #UTC+1
  now = utime.time() #UTC
  diff = (now - seconds + 3600)
  printTime(diff, prefix='Entry read', suffix='ago')
  return diff > (60 * mins) 

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

def printTime(seconds, prefix='', suffix=''):
  m, s = divmod(seconds, 60)
  h, m = divmod(m, 60)
  print(prefix + ' {:02d}:{:02d}:{:02d} '.format(h, m, s) + suffix)  

def printCenteredText(msg, font=lcd.FONT_DejaVu24, rotateAngle=0, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=False):
  lcd.font(font, rotate=rotateAngle)
  if clear == True:
     lcd.clear(backgroundColor)
  lcd.setTextColor(textColor)
  w = lcd.textWidth(msg)
  f = lcd.fontSize()
  lcd.fillRect(0, 80-f[1], 240, f[1], backgroundColor)
  if rotateAngle==180:
    lcd.print(msg, (int)(w+((240-w)/2)), 80)
  else:
    lcd.print(msg, (int)((240-w)/2), (int)(80-f[1]))

def printDirection(x, y, direction, arrowColor, fillColor=lcd.WHITE):
  lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
  lcd.triangle(direction[0], direction[1], direction[2], direction[3], direction[4], direction[5], fillcolor=arrowColor, color=arrowColor)
  if len(direction) == 12:
    lcd.triangle(direction[6], direction[7], direction[8], direction[9], direction[10], direction[11], fillcolor=arrowColor, color=arrowColor)
  lcd.circle(direction[0], direction[1], 4, fillcolor=arrowColor, color=arrowColor)

def printChart():
  global response

  #background
  lcd.fillRect(0, 0, 240, 50, lcd.ORANGE)
  lcd.fillRect(0, 50, 240, 101, lcd.LIGHTGREY)
  lcd.fillRect(0, 101, 240, 136, lcd.RED)

  #hour lines
  tm = utime.localtime(utime.time())
  
  x=120+(tm[4]*2)
  lcd.line(x, 0, x, 136, color=lcd.BLACK)
  x=(tm[4]*2)
  lcd.line(x, 0, x, 136, color=lcd.BLACK)
  
  #sgv values
  prevx=-1
  prevy=-1

  for idv, entry in enumerate(response):
    the_date = getDateTuple(entry["date"])
    hourDiff = tm[3]-the_date[3]
    minutes = the_date[4]
    x=240-(hourDiff*120)-(60-minutes)*2
    y=(int)(136-entry["sgv"]/2)
    lcd.circle(x, y, 4, fillcolor=lcd.BLACK, color=lcd.BLACK)
    if prevx>-1 and prevy>-1:
      lcd.line(prevx, prevy, x, y, color=lcd.BLACK)
    prevx=x
    prevy=y  

def printScreen():
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, currentBackgroudColor
  
  newest = response[0]
  sgv = newest['sgv']
  sgvStr = str(newest['sgv'])
  if sgv < 100: sgvStr = " " + sgvStr

  directionStr = newest['direction']

  tooOld = False
  try:
    tooOld = isOlderThan(newest['date'], 30)
  except Exception as e:
    sys.print_exception(e)

  if not tooOld and "ago" in newest and (mode == 0 or mode == 4): 
    dateStr = newest['ago']
  elif mode == 2 or mode == 6:
    dateStr = "Battery: " + str(getBatteryLevel()) + "%"
  else:   
    dateStr = newest['date'].replace("T", " ")[:-3] #remove seconds to fit screen

  if tooOld: backgroundColor=lcd.DARKGREY; M5Led.on(); emergency=False
  elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=(utime.time() > emergencyPause)  
  elif sgv >= (MIN-10) and sgv < MIN and directionStr.endswith("Up"): backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off()
  elif sgv > EMERGENCY_MIN and sgv <= MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=False
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off() 
  elif sgv > MAX and sgv <= (MAX+10) and directionStr.endswith("Down"): backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off()
  elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=False
  elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=(utime.time() > emergencyPause)  

  #if emergency change to one of full modes 
  if emergency==True and (mode==3 or mode==7) : mode=0

  lcd.setTextColor(lcd.WHITE)

  #in skip background clearing if color doesn't change  
  if (currentBackgroudColor != backgroundColor):
     lcd.clear(backgroundColor)
     currentBackgroudColor = backgroundColor
  else:
     print("Skipping background clearing")
  
  if mode in range (0,3):  
    #full mode
    
    #direction
    x=178
    y=48
    
    directions = {'Flat': (x+25, y, x-15, y-20, x-15, y+20), 
        'FortyFiveDown': (x+15, y+20, x+15, y-20, x-25, y),
        'FortyFiveUp': (x+15, y-20, x+15, y+20, x-25, y), 
        'DoubleDown': (x, y+10, x-20, y-25, x+20, y-25, x, y+30, x-20, y, x+20, y),
        'DoubleUp': (x, y-30, x-20, y-5, x+20, y-5, x, y-7, x-20, y+18, x+20, y+18), 
        'SingleUp': (x, y-25, x-20, y+15, x+20, y+15),
        'SingleDown': (x, y+25, x-20, y-15, x+20, y-15)} 
    
    direction = directions[directionStr] 
    
    if not tooOld and (directionStr == 'DoubleDown' or directionStr == 'DoubleUp'): 
      arrowColor = lcd.RED
    elif not tooOld and (directionStr == 'SingleUp' or directionStr == 'SingleDown'):
      arrowColor = lcd.ORANGE
    else:
      arrowColor = backgroundColor  
    
    printDirection(x, y, direction, arrowColor=arrowColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=0)
    lcd.textClear(12, 24, "888", backgroundColor)
    lcd.print(sgvStr, 12, 24)
    
    #ago or date
    lcd.font(lcd.FONT_DejaVu24, rotate=0)
    f=lcd.fontSize()
    lcd.fillRect(0, 100, 240, 100+f[1], backgroundColor)
    lcd.print(dateStr, (int)((240-lcd.textWidth(dateStr))/2), 100)
  elif mode in range(4,7):
    #flip mode

    #direction
    x=58
    y=52
    
    directions = {'Flat': (x-25, y, x+15, y-20, x+15, y+20), 
        'FortyFiveDown': (x-15, y-20, x-15, y+20, x+25, y),
        'FortyFiveUp': (x-15, y+20, x-15, y-20, x+25, y), 
        'DoubleDown': (x, y-30, x-20, y-5, x+20, y-5, x, y-7, x-20, y+18, x+20, y+18),
        'DoubleUp': (x, y+30, x-20, y, x+20, y, x, y+10, x-20, y-25, x+20, y-25), 
        'SingleUp': (x, y+25, x-20, y-15, x+20, y-15),
        'SingleDown': (x, y-25, x-20, y+15, x+20, y+15)} 
    
    direction = directions[directionStr] 
    
    if not tooOld and (directionStr == 'DoubleDown' or directionStr == 'DoubleUp'): 
      arrowColor = lcd.RED
    elif not tooOld and (directionStr == 'SingleUp' or directionStr == 'SingleDown'):
      arrowColor = lcd.ORANGE
    else:
      arrowColor = backgroundColor  
    
    printDirection(x, y, direction, arrowColor=arrowColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=180)
    x = 206
    y = 78
    lcd.textClear(x-lcd.textWidth("888"), y-lcd.fontSize()[1], "888", backgroundColor)
    lcd.print(sgvStr, x, y)

    #ago or date
    lcd.font(lcd.FONT_DejaVu18, rotate=180)
    x = (int)(240-((240-lcd.textWidth(dateStr))/2))
    if x>216: x=216
    y = 118
    lcd.fillRect(0, y-lcd.fontSize()[1], 240, y, backgroundColor)
    lcd.print(dateStr, x, y)
  elif mode == 7:
    #chart
    printChart()
    currentBackgroudColor = -1

def backendMonitor():
  global response, INTERVAL, API_ENDPOINT, API_TOKEN, LOCALE, TIMEZONE, startTime
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Free memory: ' + str(gc.mem_free()) + ' bytes')
      printTime((utime.time() - startTime), prefix='Uptime is')
      response = urequests.get(API_ENDPOINT + "/entries.json?count=10",headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE}).json()
      print('Sgv:', response[0]['sgv'])
      print('Read:', response[0]['date'])
      print('Direction:', response[0]['direction'])
      printScreen()
      time.sleep(INTERVAL)
    except Exception as e:
      sys.print_exception(e)
      retry = (int)(INTERVAL/4)
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Network error. Retry in ' + str(retry) + ' sec...')
      time.sleep(retry)

def onBtnAPressed():
  global mode, MODES, emergency, emergencyPause, currentBackgroudColor
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + 1800 #30 mins
  else:   
    if mode == (len(MODES)-1): mode = 0
    else: mode += 1 
    currentBackgroudColor = -1
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
        print('Emergency glucose level ' + str(response[0]['sgv']) + '!!!')
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

print('Starting...')
print("APIKEY: " + deviceCfg.get_apikey())
macaddr=wifiCfg.wlan_sta.config('mac')
macaddr='{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(*macaddr)
print('MAC Adddress: ' + macaddr)
print('Free memory: ' + str(gc.mem_free()) + ' bytes')

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

MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery", "chart"]
mode = 0
response = {}
brightness = 32
emergency = False
emergencyPause = 0
currentBackgroudColor = -1

beeper = PWM(Pin(2), freq=1000, duty=50)
beeper.pause()

axp.setLcdBrightness(brightness)
lcd.orient(lcd.LANDSCAPE)
lcd.clear(lcd.DARKGREY)

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
      printCenteredText("Saved wifi not found!", backgroundColor=lcd.RED, clear=True)  
  if not found: time.sleep(1)

printCenteredText("Connecting wifi...", backgroundColor=lcd.DARKGREY) #lcd.OLIVE)
nic.connect(SSID, WIFI_PASSWORD)
print('Connecting wifi ' + SSID)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)
print("")  

printCenteredText("Setting time...", backgroundColor=lcd.DARKGREY) #lcd.GREENYELLOW)

try: 
  rtc = machine.RTC()
  tm = utime.localtime(getNtpTime())
  rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
  print("Current time " +  str(rtc.datetime()))
  startTime = utime.time()

  printCenteredText("Loading data...", backgroundColor=lcd.DARKGREY) #lcd.DARKGREEN)

  _thread.start_new_thread(backendMonitor, ())
  _thread.start_new_thread(emergencyMonitor, ())

  btnA.wasPressed(onBtnAPressed)
  btnB.wasPressed(onBtnBPressed)
except Exception as e:
  sys.print_exception(e)
  printCenteredText("Restart required!", backgroundColor=lcd.RED, clear=True)
  