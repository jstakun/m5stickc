import network
import urequests
import time
import ujson
import sys
import _thread
import utime
import machine 
import usocket as socket
import ustruct as struct
import gc
import deviceCfg
import wifiCfg
import ubinascii
from machine import Pin, PWM
from collections import OrderedDict
from imu import IMU

EMERGENCY_PAUSE_INTERVAL = 1800  #sec = 30 mins
MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery", "chart", "flip_chart"]

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

def saveSgvFile(sgvdict):
  sgvfile = open('sgvdict.txt', 'w')
  for key in sgvdict:
    sgvfile.write(str(key) + ':' + str(sgvdict[key]) + '\n')
  sgvfile.close()  

def readSgvFile():
  d = OrderedDict()
  try: 
    sgvfile = open('sgvdict.txt', 'r')
    entries = sgvfile.read().split('\n')
    for entry in entries:
      if ":" in entry:
        [s, v] = [int(i) for i in entry.split(':')]
        d.update({s: v})
  except Exception as e:
    sys.print_exception(e)
  return d  

def resetMachine(seconds=5):
  if seconds<1: seconds=1
  for i in range(seconds, 0, -1):
     printCenteredText('Reset in ' + str(i) + ' sec', backgroundColor=lcd.RED, clear=True)
     time.sleep(1)
  machine.reset()    

def printTime(seconds, prefix='', suffix=''):
  m, s = divmod(seconds, 60)
  h, m = divmod(m, 60)
  print(prefix + ' {:02d}:{:02d}:{:02d} '.format(h, m, s) + suffix)  

def printCenteredText(msg, font=lcd.FONT_DejaVu24, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=False):
  global mpu6050
  rotateAngle = 0
  if mpu6050.acceleration[0] > 0: rotateAngle = 180
  
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

def printChart(zoom=1):
  global sgvDict, MIN, MAX

  #horizontal glucose level lines nand fills
  if mode == 8:
    maxy = 136-(int)(136-(MAX/2))
    miny = 136-(int)(136-(MIN/2))
    lcd.fillRect(0, 0, 240, miny, lcd.RED) #70
    lcd.fillRect(0, miny, 240, maxy, lcd.LIGHTGREY)
    lcd.fillRect(0, maxy, 240, 136, lcd.ORANGE) #172
    lcd.line(0, maxy, 240, maxy, color=lcd.BLACK)
    lcd.line(0, miny, 240, miny, color=lcd.BLACK)
  else:   
    maxy = (int)(136-(MAX/2))
    miny = (int)(136-(MIN/2))
    lcd.fillRect(0, 0, 240, maxy, lcd.ORANGE) #172
    lcd.fillRect(0, maxy, 240, miny, lcd.LIGHTGREY)
    lcd.fillRect(0, miny, 240, 136, lcd.RED) #70
    lcd.line(0, maxy, 240, maxy, color=lcd.BLACK)
    lcd.line(0, miny, 240, miny, color=lcd.BLACK)
  
  #hours vertical lines
  tm = utime.localtime(utime.time())
  if mode == 8:
    x=(tm[4]*zoom)
    while x<=240:
      lcd.line(x, 0, x, 136, color=lcd.BLACK)
      x+=(60*zoom)
  else:  
    x=240-(tm[4]*zoom)
    while x>=0:
      lcd.line(x, 0, x, 136, color=lcd.BLACK)
      x-=(60*zoom)
  
  #sgv values
  points = []
  for key in sgvDict:
    the_date = utime.localtime(key)
    hourDiff = tm[3]+1-the_date[3]
    minutes = the_date[4]
    if mode == 8:
      x = 240-(240-(hourDiff*zoom*60)-(tm[4]*zoom)+(minutes*zoom))
      y = (int)(sgvDict[key]/2)
    else:   
      x = 240-(hourDiff*zoom*60)-(tm[4]*zoom)+(minutes*zoom)
      y = (int)(136-sgvDict[key]/2)
    fillcolor = lcd.BLACK
    if sgvDict[key]<=MIN: fillcolor=lcd.LIGHTGREY
    elif sgvDict[key]>=MAX: fillcolor=lcd.LIGHTGREY 
    points.append((x,y,fillcolor))

  n = len(points)-1
  while(n >= 0):
    p = points[n]
    lcd.circle(p[0], p[1], zoom+2, fillcolor=p[2], color=lcd.BLACK) 
    if n>0 and abs(p[0]-points[n-1][0])<=60:
      lcd.line(p[0], p[1],points[n-1][0],points[n-1][1], color=lcd.BLACK) 
    n -= 1

def printScreen(clear=False):
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, currentBackgroudColor, screenDrawing, startTime
  
  print('Printing screen in ' + MODES[mode] + ' mode')
  waitTime = 0.0
  while screenDrawing == True:
    time.sleep(0.1)
    waitTime += 0.1
    print(".", end="")

  if waitTime > 0: 
    print('Finished in ' + str(waitTime) + ' seconds')
  screenDrawing = True   

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

  if tooOld: backgroundColor=lcd.DARKGREY; M5Led.on(); emergency=False
  elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=(utime.time() > emergencyPause and not tooOld)  
  elif sgv >= (MIN-10) and sgv < MIN and directionStr.endswith("Up"): backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off()
  elif sgv > EMERGENCY_MIN and sgv <= MIN: backgroundColor=lcd.RED; M5Led.on(); emergency=False
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off() 
  elif sgv > MAX and sgv <= (MAX+10) and directionStr.endswith("Down"): backgroundColor=lcd.DARKGREEN; emergency=False; M5Led.off()
  elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=False
  elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; M5Led.on(); emergency=(utime.time() > emergencyPause and not tooOld)  

  #if emergency change to one of full modes 
  currentMode = mode
  if emergency==True and (mode==3 or mode==7): currentMode = 0
  
  #battery level emergency
  batteryLevel = getBatteryLevel()
  uptime = utime.time() - startTime  
  if (batteryLevel < 20 and batteryLevel > 0 and uptime > 300) and (utime.time() > emergencyPause) and not axp.getChargeState(): emergency=True; currentMode=2; clear=True

  if "ago" in newest and (currentMode == 0 or currentMode == 4): 
    dateStr = newest['ago']
  elif currentMode == 2 or currentMode == 6:
    batteryLevel = getBatteryLevel()
    if batteryLevel >= 0:
       dateStr = "Battery: " + str(getBatteryLevel()) + "%"
    else: 
       dateStr = "Battery level unknown"
  else:   
    dateStr = newest['date'].replace("T", " ")[:-3] #remove seconds to fit screen

  lcd.setTextColor(lcd.WHITE)

  #in skip background clearing if color doesn't change  
  if clear or currentBackgroudColor != backgroundColor:
     lcd.clear(backgroundColor)
     currentBackgroudColor = backgroundColor
  else:
     print("Skipping background clearing")
  
  if currentMode in range (0,3):  
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
    
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'SingleUp' and sgv+10>=MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr == 'SingleDown' and sgv-10<=MIN: arrowColor = lcd.ORANGE
    else: arrowColor = backgroundColor  
        
    printDirection(x, y, direction, arrowColor=arrowColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=0)
    lcd.textClear(12, 24, "888", backgroundColor)
    lcd.print(sgvStr, 12, 24)
    
    #ago, date or battery
    if batteryLevel < 20 and currentMode == 2: lcd.setTextColor(lcd.RED)
    lcd.font(lcd.FONT_DejaVu24, rotate=0)
    f=lcd.fontSize()
    lcd.fillRect(0, 100, 240, 100+f[1], backgroundColor)
    lcd.print(dateStr, (int)((240-lcd.textWidth(dateStr))/2), 100)
  elif currentMode in range(4,7):
    #flip full mode

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
    
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'SingleUp' and sgv+10>=MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr == 'SingleDown' and sgv-10<=MIN: arrowColor = lcd.ORANGE
    else: arrowColor = backgroundColor   
    
    printDirection(x, y, direction, arrowColor=arrowColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=180)
    x = 206
    y = 78
    lcd.textClear(x-lcd.textWidth("888"), y-lcd.fontSize()[1], "888", backgroundColor)
    lcd.print(sgvStr, x, y)

    #ago, date or battery
    if batteryLevel < 20 and currentMode == 6: lcd.setTextColor(lcd.RED)
    lcd.font(lcd.FONT_DejaVu18, rotate=180)
    x = (int)(240-((240-lcd.textWidth(dateStr))/2))
    if x>216: x=216
    y = 118
    lcd.fillRect(0, y-lcd.fontSize()[1], 240, y, backgroundColor)
    lcd.print(dateStr, x, y)
  elif currentMode in range(7,9):
    #chart
    printChart()
    currentBackgroudColor = -1
  screenDrawing = False  

def onBtnAPressed():
  global mode, emergency, emergencyPause, currentBackgroudColor, mpu6050
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + EMERGENCY_PAUSE_INTERVAL 
  else:   
    if mode == 7 and mpu6050.acceleration[0] < 0: mode = 0
    elif mode == 6 and mpu6050.acceleration[0] > 0: mode = 8
    elif mode == 3 and mpu6050.acceleration[0] < 0: mode = 7
    elif mode == 8: mode = 3
    else: mode += 1 
    currentBackgroudColor = -1
    print('Selected mode ' + MODES[mode])
    printScreen()

def onBtnBPressed():
  global emergency, emergencyPause
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + EMERGENCY_PAUSE_INTERVAL
  else:   
    global brightness
    brightness += 16
    if brightness > 96: brightness = 32
    axp.setLcdBrightness(brightness)

def backendMonitor():
  global response, INTERVAL, API_ENDPOINT, API_TOKEN, LOCALE, TIMEZONE, startTime, sgvDict
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Free memory: ' + str(gc.mem_free()) + ' bytes')
      printTime((utime.time() - startTime), prefix='Uptime is')
      response = urequests.get(API_ENDPOINT + "/entries.json?count=10",headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE}).json()
      print('Sgv:', response[0]['sgv'])
      print('Read:', response[0]['date'])
      print('Direction:', response[0]['direction'])

      d = OrderedDict()
      seconds = -1
      for index, entry in enumerate(response):
        the_date = getDateTuple(entry['date'])  
        seconds = utime.mktime(the_date)
        d.update({seconds: entry['sgv']})

      dictLen = len(d)  
      for key in sgvDict:
        if key < seconds and dictLen < 50:
          d.update({key: sgvDict[key]})
        elif dictLen >= 50:
          break  
        dictLen = len(d)

      sgvDict = d
      saveSgvFile(d)
      print('Cached ' + str(dictLen) + " sgv entries")
      #print(sgvDict)  
      
      printScreen()
      time.sleep(INTERVAL)
    except Exception as e:
      sys.print_exception(e)
      retry = (int)(INTERVAL/4)
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Network error. Retry in ' + str(retry) + ' sec...')
      time.sleep(retry)

def emergencyMonitor():
  global emergency, beeper, response, USE_BEEPER
  while True:
    if emergency == True:
      batteryLevel = getBatteryLevel()
      if batteryLevel < 20:
        print('Low battery level ' + str(batteryLevel) + "%!!!")
      else:
        print('Emergency glucose level ' + str(response[0]['sgv']) + '!!!')
      if USE_BEEPER == 1:
        beeper.resume()
      M5Led.on()
      time.sleep(0.5)
      if USE_BEEPER == 1:
        beeper.pause()
      M5Led.off()
      time.sleep(0.5)
    else:
      #print('No emergency')
      if USE_BEEPER == 1:
        beeper.pause()
      time.sleep(1)

def mpu6050Monitor():
  global mpu6050, mode, response
  while True:
    acceleration = mpu6050.acceleration
    hasResponse = (response != '{}')
    if hasResponse and acceleration[0] > 0 and mode in range(0,3): mode += 4; printScreen(clear=True) #change to 'Flip mode' #4,5,6
    elif hasResponse and acceleration[0] < 0 and mode in range(4,7): mode -= 4; printScreen(clear=True) #change to 'Normal mode' #0,1,2
    elif hasResponse and acceleration[0] > 0 and mode == 7: mode = 8; printScreen(clear=True)
    elif hasResponse and acceleration[0] < 0 and mode == 8: mode = 7; printScreen(clear=True)
    time.sleep(0.5)
        
########################################    

print('Starting...')
print('APIKEY: ' + deviceCfg.get_apikey())
macaddr=wifiCfg.wlan_sta.config('mac')
macaddr='{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(*macaddr)
print('MAC Adddress: ' + macaddr)
print('Free memory: ' + str(gc.mem_free()) + ' bytes')
machine_id = binascii.hexlify(machine.unique_id())
print('Machine unique id: ' + machine_id.decode())

response = '{}'
brightness = 32
emergency = False
emergencyPause = 0
currentBackgroudColor = -1
screenDrawing = False

axp.setLcdBrightness(brightness)
lcd.orient(lcd.LANDSCAPE)

try:
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
  USE_BEEPER = config["beeper"]

  if INTERVAL<30: INTERVAL=30
  if MIN<30: MIN=30
  if MAX<100: MAX=100
  if EMERGENCY_MIN<30 or MIN<=EMERGENCY_MIN: EMERGENCY_MIN=MIN-10
  if EMERGENCY_MAX<100 or MAX>=EMERGENCY_MAX: EMERGENCY_MAX=MAX+10  
  if len(API_ENDPOINT)==0: raise Exception("Empty api-endpoint parameter")
  if len(WIFI)==0: raise Exception("Empty wifi parameter")
  if USE_BEEPER > 1 or USE_BEEPER < 0: USE_BEEPER=1

  beeper = PWM(Pin(2), freq=1000, duty=50)
  beeper.pause()

  mpu6050 = IMU()
  mode = 0
  if mpu6050.acceleration[0] > 0: mode = 4 #flip

  lcd.clear(lcd.DARKGREY)
except Exception as e:
  sys.print_exception(e)
  while True:
    printCenteredText("Fix config.json!", backgroundColor=lcd.RED, clear=True)
    time.sleep(2)
    printCenteredText("Restart required!", backgroundColor=lcd.RED, clear=True)
    time.sleep(2)

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
      printCenteredText("Wifi not found!", backgroundColor=lcd.RED, clear=True)  
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
  print("Current datetime " +  str(rtc.datetime()))
  startTime = utime.time()

  printCenteredText("Loading data...", backgroundColor=lcd.DARKGREY) #lcd.DARKGREEN)

  sgvDict = readSgvFile()
  dictLen = len(sgvDict)
  print('Loaded ' + str(dictLen) + " sgv entries")

  _thread.start_new_thread(backendMonitor, ())
  _thread.start_new_thread(emergencyMonitor, ())
  _thread.start_new_thread(mpu6050Monitor, ())

  btnA.wasPressed(onBtnAPressed)
  btnB.wasPressed(onBtnBPressed)
except Exception as e:
  sys.print_exception(e)
  printCenteredText("Restart required!", backgroundColor=lcd.RED, clear=True)
  time.sleep(1)
  resetMachine()