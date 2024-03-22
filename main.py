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
from machine import Pin, PWM, RTC
from collections import OrderedDict
from imu import IMU
import math

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

def checkBeeper():
  global USE_BEEPER, BEEPER_START_TIME, BEEPER_END_TIME 
  try:   
    if USE_BEEPER == 1:
      d = utime.localtime(0)
      tm = utime.localtime(utime.time())
    
      c = list(d)
      c[3] = tm[3]
      c[4] = tm[4]
      c[5] = tm[5]

      d1 = list(d)
      [HH, MM, SS] = [int(i) for i in BEEPER_START_TIME.split(':')]
      d1[3] = HH
      d1[4] = MM
      d1[5] = SS

      d2 = list(d)
      [HH, MM, SS] = [int(i) for i in BEEPER_END_TIME.split(':')]
      d2[3] = HH
      d2[4] = MM
      d2[5] = SS

      #print("Compare d1: " + str(d1) + ", d2: " + str(d2) + ", c: " + str(c))
      
      if tuple(d1) < tuple(d2):
         return tuple(c) > tuple(d1) and tuple(c) < tuple(d2)
      else:
         return tuple(c) > tuple(d1) or tuple(c) < tuple(d2)
    else:
      return False 
  except Exception as e:
    sys.print_exception(e)
    return True  

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

def printDirection(x, y, xshift=0, yshift=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE):
  lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
  r = drawTriangle(x+xshift, y+yshift, arrowColor, rotateAngle)
  lcd.circle(int(r[0]), int(r[1]), 4, fillcolor=arrowColor, color=arrowColor)

def printDoubleDirection(x, y, ytop=0, ybottom=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE):
  lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
  drawTriangle(x, y+ytop, arrowColor, rotateAngle)
  r = drawTriangle(x, y+ybottom, arrowColor, rotateAngle) 
  #lcd.circle(int(r[0]), int(r[1]), 4, fillcolor=arrowColor, color=arrowColor)

def drawTriangle(centerX, centerY, arrowColor, rotateAngle=90, width=44, height=44):
  angle = math.radians(rotateAngle) # Angle to rotate

  # Vertex's coordinates before rotating
  x1 = centerX + width / 2
  y1 = centerY
  x2 = centerX - width / 2
  y2 = centerY + height / 2
  x3 = centerX - width / 2
  y3 = centerY - height / 2

  # Rotating
  x1r = ((x1 - centerX) * math.cos(angle) - (y1 - centerY) * math.sin(angle) + centerX)
  y1r = ((x1 - centerX) * math.sin(angle) + (y1 - centerY) * math.cos(angle) + centerY)
  x2r = ((x2 - centerX) * math.cos(angle) - (y2 - centerY) * math.sin(angle) + centerX)
  y2r = ((x2 - centerX) * math.sin(angle) + (y2 - centerY) * math.cos(angle) + centerY)
  x3r = ((x3 - centerX) * math.cos(angle) - (y3 - centerY) * math.sin(angle) + centerX)
  y3r = ((x3 - centerX) * math.sin(angle) + (y3 - centerY) * math.cos(angle) + centerY)

  lcd.triangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), fillcolor=arrowColor, color=arrowColor)
  return x1r, y1r, x2r, y2r, x3r, y3r 

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

def printScreen(clear=False, expiredData=False):
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

  tooOld = expiredData
  if tooOld == False:
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
  if (batteryLevel < 20 and batteryLevel > 0 and uptime > 300) and (utime.time() > emergencyPause) and not axp.getChargeState(): 
    emergency=True
    if currentMode < 4 or currentMode == 7: currentMode = 2
    else: currentMode = 6
    clear=True

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
     print("Skip background clearing")
  
  if currentMode in range (0,3):  
    #full mode
    
    #direction
    x=178
    y=48
    
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'SingleUp' and sgv+10>=MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr == 'SingleDown' and sgv-10<=MIN: arrowColor = lcd.ORANGE
    else: arrowColor = backgroundColor  

    if directionStr == 'DoubleUp': printDoubleDirection(x, y, ytop=-10, ybottom=6, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'DoubleDown': printDoubleDirection(x, y, ytop=-10, ybottom=6, rotateAngle=90, arrowColor=arrowColor) 
    elif directionStr == 'SingleUp': printDirection(x, y, xshift=2, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'SingleDown': printDirection(x, y, xshift=2, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'Flat': printDirection(x, y, xshift=2, rotateAngle=0, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveUp': printDirection(x, y, xshift=2, rotateAngle=-45, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveDown': printDirection(x, y, xshift=2, rotateAngle=45, arrowColor=arrowColor)

    #sgv
    lcd.font(lcd.FONT_DejaVu56, rotate=0)
    lcd.textClear(12, 24, "888", backgroundColor)
    lcd.print(sgvStr, 12, 24)
    
    #ago, date or battery
    if batteryLevel < 20 and (currentMode == 2 or currentMode == 6): lcd.setTextColor(lcd.RED)
    lcd.font(lcd.FONT_DejaVu24, rotate=0)
    f=lcd.fontSize()
    lcd.fillRect(0, 100, 240, 100+f[1], backgroundColor)
    lcd.print(dateStr, (int)((240-lcd.textWidth(dateStr))/2), 100)
  elif currentMode in range(4,7):
    #flip full mode

    #direction
    x=58
    y=52
        
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'SingleUp' and sgv+10>=MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr == 'SingleDown' and sgv-10<=MIN: arrowColor = lcd.ORANGE
    else: arrowColor = backgroundColor   
    
    if directionStr == 'DoubleUp': printDoubleDirection(x, y, ytop=-6, ybottom=10, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'DoubleDown': printDoubleDirection(x, y, ytop=-6, ybottom=10, rotateAngle=-90, arrowColor=arrowColor) 
    elif directionStr == 'SingleUp': printDirection(x, y, xshift=-2, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'SingleDown': printDirection(x, y, xshift=-2, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'Flat': printDirection(x, y, xshift=-2, rotateAngle=180, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveUp': printDirection(x, y, xshift=-2, rotateAngle=135, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveDown': printDirection(x, y, xshift=-2, rotateAngle=-135, arrowColor=arrowColor)

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
  print("----------------------------")  
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
  backendRetry = (int)(INTERVAL/4)
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Free memory: ' + str(gc.mem_free()) + ' bytes')
      printTime((utime.time() - startTime), prefix='Uptime is')
      print('Calling backend ...')
      s = utime.time()
      response = urequests.get(API_ENDPOINT + "/entries.json?count=10",headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE}).json()
      printTime((utime.time() - s), prefix='Response received in')
      print('Sgv:', response[0]['sgv'])
      print('Direction:', response[0]['direction'])
      print('Read: ' + response[0]['date'] + ' (' + TIMEZONE + ')')
      
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
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Network error. Retry in ' + str(backendRetry) + ' sec...')
      printScreen(expiredData=True)
      time.sleep(backendRetry)

def emergencyMonitor():
  global emergency, beeper, response
  while True:
    #print('Emergency monitor checking status')
    useBeeper = checkBeeper()
    if emergency == True:
      batteryLevel = getBatteryLevel()
      if batteryLevel < 20:
        print('Low battery level ' + str(batteryLevel) + "%!!!")
      else:
        print('Emergency glucose level ' + str(response[0]['sgv']) + '!!!')
      if useBeeper == True:
        beeper.resume()
      M5Led.on()
      time.sleep(0.5)
      if useBeeper == True:
        beeper.pause()
      M5Led.off()
      time.sleep(0.5)
    else:
      #print('No emergency')
      if useBeeper == True:
        beeper.pause()
      time.sleep(2)

def mpu6050Monitor():
  global mpu6050, mode, response
  while True:
    acceleration = mpu6050.acceleration
    hasResponse = (response != '{}')
    if hasResponse and acceleration[0] > 0.1 and mode in range(0,3): mode += 4; printScreen(clear=True) #change to 'Flip mode' #4,5,6
    elif hasResponse and acceleration[0] < -0.1 and mode in range(4,7): mode -= 4; printScreen(clear=True) #change to 'Normal mode' #0,1,2
    elif hasResponse and acceleration[0] > 0.1 and mode == 7: mode = 8; printScreen(clear=True)
    elif hasResponse and acceleration[0] < -0.1 and mode == 8: mode = 7; printScreen(clear=True)
    #print("Acc:", str(acceleration))
    time.sleep(0.5)
        
########################################    

print('Starting...')
print('APIKEY:', deviceCfg.get_apikey())
macaddr=wifiCfg.wlan_sta.config('mac')
macaddr='{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(*macaddr)
print('MAC address:', macaddr)
print('Free memory: ' + str(gc.mem_free()) + ' bytes')
machine_id = binascii.hexlify(machine.unique_id())
print('Machine unique id:', machine_id.decode())
print('CPU frequency:', machine.freq())

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
  BEEPER_START_TIME = config["beeperStartTime"]
  BEEPER_END_TIME = config["beeperEndTime"]

  if INTERVAL<30: INTERVAL=30
  if MIN<30: MIN=30
  if MAX<100: MAX=100
  if EMERGENCY_MIN<30 or MIN<=EMERGENCY_MIN: EMERGENCY_MIN=MIN-10
  if EMERGENCY_MAX<100 or MAX>=EMERGENCY_MAX: EMERGENCY_MAX=MAX+10  
  if len(API_ENDPOINT)==0: raise Exception("Empty api-endpoint parameter")
  if len(WIFI)==0: raise Exception("Empty wifi parameter")
  if USE_BEEPER != 1 and USE_BEEPER != 0: USE_BEEPER=1

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

#this doesn't work
#machine.freq(20000000)    

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
  rtc = RTC()
  tm = utime.localtime(getNtpTime())
  rtc.datetime((tm[0], tm[1], tm[2], tm[6] + 1, tm[3], tm[4], tm[5], 0))
  print("Current UTC datetime " +  str(rtc.datetime()))
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