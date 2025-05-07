import micropython
import utime
import ujson
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
import framebuf
import network
import urequests as requests
from umqtt.simple import MQTTClient
from fifo import Fifo
from piotimer import Piotimer
from kubios import send_to_kubios, get_kubios_token



button_pressed = False
menu_index = 0
encoder_events = Fifo(30)
last_button_time = 0
x1, y1 = -1, 32  # Starting point (middle horizontal line)
sampling_rate = 250 
fifo = Fifo(2 * sampling_rate)
menu_option = None  # tai sopiva oletusarvo
adc = ADC(26)
clear_height = 50
finger_detected = False     
last_adc_value = 0
run_time_ms = 60000
timer = None
waveform_buffer = []








WIFI_SSID = "KMD652_Group_8"
WIFI_PASSWORD = "KMD652_Group_8"
MQTT_BROKER = "192.168.8.253"
MQTT_PORT =1883
MQTT_USER = "narges8"
MQTT_PASS = "narges8"
MQTT_TOPIC = "medheart/bpm"




# Initialize the OLED näyttö and show "Welcome to MedHeart"

i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)
oled_width = 128
oled_height = 64

# clear screen
oled.fill(0)
oled.show()

def animate_text(text,x,y, delay=0.3):
    oled.fill(0)
    for i in range(len(text)):
        oled.text(text[:i+1],x,y)
        oled.show()
        utime.sleep(delay)


# --- HRV Icon 16x16 pixels ---
hrv_icon = bytearray([
    0x00, 0x00,
    0x0F, 0x80,
    0x1F, 0xC0,
    0x18, 0xC0,
    0x30, 0x60,
    0x30, 0x60,
    0x30, 0x60,
    0x18, 0xC0,
    0x0F, 0x80,
    0x03, 0x00,
    0x03, 0x00,
    0x03, 0x00,
    0x03, 0x00,
    0x03, 0x00,
    0x03, 0x00,
    0x00, 0x00
])

# Create FrameBuffer for HRV icon
hrv_fb = framebuf.FrameBuffer(hrv_icon, 16, 16, framebuf.MONO_HLSB)


# Heart shape definition (16x13 pixels) in hexadecimal format.
# This bytearray contains the pixel data for a heart icon.
# Each pair of hexadecimal values represents one row (16 bits) of the heart image.
# The image is 16 pixels wide and 13 pixels tall.
# It is used with a FrameBuffer to render the shape on an OLED screen.
heart1 = bytearray([
    0x0C, 0x30,
    0x1E, 0x78,
    0x3F, 0xFC,
    0x7F, 0xFE,
    0x7F, 0xFE,
    0x7F, 0xFE,
    0x3F, 0xFC,
    0x1F, 0xF8,
    0x0F, 0xF0,
    0x07, 0xE0,
    0x03, 0xC0,
    0x01, 0x80,
    0x00, 0x00,
])
heart_1 = framebuf.FrameBuffer(heart1, 16, 13, framebuf.MONO_HLSB)

heart_w = 16
heart_h = 13
center_y = (64 - heart_h) // 2


# "Welcome to" text + heart animation together
left_x = 0
right_x = 128 - heart_w

while left_x < 44 and right_x > 68:
    
    oled.fill(0)
    oled.text("Welcome to", 32, 8)

# Two static hearts in the center
    oled.blit(heart_1, 44, center_y)
    oled.blit(heart_1, 68, center_y)
    

# Two moving hearts from the sides
    oled.blit(heart_1, left_x, center_y)
    oled.blit(heart_1, right_x, center_y)

    oled.show()
    utime.sleep(0.05)
    left_x += 2
    right_x -= 2

#Display "MedHeart" + a single heart + heartbeat line

oled.fill(0)
oled.invert(True)


#Display full text
oled.text("Welcome to", 32, 8)
oled.text("MedHeart", 36, 20)

# display heart in bottom
final_x = (128 - heart_w) // 2
final_y = center_y + 14
oled.blit(heart_1, final_x, final_y)


# heart and  ECG line
y = final_y + 6
for x in range(0, 20):
    oled.pixel(x, y, 1)
oled.line(20, y, 22, y - 4, 1)
oled.line(22, y - 4, 24, y, 1)


for x in range(24, 40):
    oled.pixel(x, y, 1)
oled.line(40, y, 43, y - 10, 1)
oled.line(43, y - 10, 46, y, 1)
for x in range(46, 128):
    oled.pixel(x, y, 1)

oled.show()


menu_index = 0


encoder_events = Fifo(30)
class Encoder:
    def __init__(self, pin_a, pin_b, fifo):
        self.a = Pin(pin_a, Pin.IN)
        self.b = Pin(pin_b, Pin.IN)
        self.fifo = fifo
        self.a.irq(handler=self.handler, trigger=Pin.IRQ_RISING, hard=True)

    def handler(self, pin):
        if self.b():
            self.fifo.put(-1)
        else:
            self.fifo.put(1)

rot = Encoder(11, 12, encoder_events)
button = Pin(12, Pin.IN, Pin.PULL_UP)


# Global variable for the menu index

menu_options = ["Measure HR", "HRV Analysis", "History", "Kubios"]
menu_icons = ["HR", "HRV", "HIS", "MQT", "SIG"]

# Function to display the menu (this will update the OLED)
def update_menu(previous, current):
    item_height = 16
    icon_old = menu_icons[previous]
    icon_new = menu_icons[current]
    
   
    y_old = previous * item_height
    oled.fill_rect(2, y_old + 2, 124, 12, 0) 
    oled.text(f"{icon_old} {menu_options[previous]}", 4, y_old + 4, 1) 

    
    y_new = current * item_height
    oled.fill_rect(2, y_new + 2, 124, 12, 1)  
    oled.text(f"{icon_new} {menu_options[current]}", 4, y_new + 4, 0)  

    oled.show()





screen_timeout = 30000
screen_on = True

def on_button(pin):
    global button_pressed, last_button_time
    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_button_time) > 200:  # Debouncing
        button_pressed = True  # Set flag when button is pressed
    last_button_time = now


button.irq(trigger=Pin.IRQ_FALLING, handler=on_button)

def display_menu():
    global menu_index
    items_count = len(menu_options)
    item_height = 16
    screen_height = 64
    visible_items = screen_height // item_height

    oled.fill(0)
    oled.rect(0, 0, 128, 64, 1)  # Keep the nice border

    for i, item in enumerate(menu_options):
        y = i * item_height
        icon = menu_icons[i]
        if i == menu_index:
            oled.fill_rect(2, y + 2, 124, 12, 1)  # Highlight selected item
            oled.text(f"{icon} {item}", 4, y + 4, 0)  # Text in black
        else:
            oled.text(f"{icon} {item}", 4, y + 4, 1)  # Text in white

    oled.show()

# After welcome screen animation
utime.sleep(3)    # Stay on welcome screen for 3 seconds
oled.invert(False)  # Return to normal screen colors
display_menu()     # Show the menu inside a nice frame

def handle_selection():
    if menu_index == 0:
        detect_hr()
    elif menu_index == 1:
        detect_hrv()
    elif menu_index == 2:
        history_menu()
    elif menu_index == 3:
        send_to_kubios()


def wait_for_button_press():
    global button_pressed
    button_pressed = False
    while not button_pressed:
        utime.sleep(0.1)
    button_pressed = False
    


def adc_irq_handler(timer):
    global last_adc_value
    val = adc.read_u16()
    print("ADC:", val)
    
    if val > 25000:  # القيمة 25000 تمثل الحد الأدنى المقبول لوجود إصبع
        last_adc_value = val
        try:
            micropython.schedule(adc_scheduled, 0)
        except RuntimeError:
            pass


def adc_scheduled(dummy):
    try:
        fifo.put(last_adc_value)
    except:
        pass

def draw_heartbeat_waveform(oled, x1, y1, x2, y2, bpm_to_display, remaining):
    oled.fill_rect(0, 10, 128, 40, 0)  # مساحة الرسم
    oled.line(x1, y1, x2, y2, 1)       # خط بين النقاط

    oled.fill_rect(0, 0, 128, 10, 0)   # مساحة BPM
    if bpm_to_display:
        oled.text(f"BPM: {bpm_to_display}", 0, 0, 1)

    oled.fill_rect(0, 54, 128, 10, 0)  # العداد السفلي
    oled.text(f"{remaining}s left", 30, 54, 1)
    oled.show()

def detect_hr():
    global x1, y1, button_pressed, timer

    min_bpm = 30
    max_bpm = 180
    min_interval_ms = 300
    run_time_ms = 60000

    alpha = 0.1
    lp_filtered = 0
    prev_sample = 0
    slope_prev = 0
    last_peak_index = -sampling_rate
    bpm_list = []
    peaks_indexes = []

    x1, y1 = -1, 32
    count = 0
    last_bpm_calc_time = utime.ticks_ms()
    bpm_to_display = None
    recent_max = 0
    recent_min = 65535

    # Wait for finger placement
    oled.fill(0)
    oled.text("Place finger", 10, 20)
    oled.text("on sensor...", 10, 40)
    oled.show()

    finger_detected = False
    while not finger_detected:
        val = adc.read_u16()
        print("Waiting for finger...", val)
        if val > 25000:
            finger_detected = True
        utime.sleep(0.1)

    oled.fill(0)
    oled.text("Finger detected", 10, 30)
    oled.show()
    utime.sleep(1)

    while not fifo.empty():
        fifo.get()

    timer = Piotimer(0, freq=sampling_rate, callback=adc_irq_handler)
    start_time = utime.ticks_ms()

    try:
        while True:
            if button_pressed:
                button_pressed = False
                break

            elapsed = utime.ticks_diff(utime.ticks_ms(), start_time)
            if elapsed >= run_time_ms:
                break

            if not fifo.empty():
                raw = fifo.get()
                count += 1

                lp_filtered = alpha * raw + (1 - alpha) * lp_filtered
                moving_avg = lp_filtered

                recent_max = max(lp_filtered, recent_max * 0.99)
                recent_min = min(lp_filtered, recent_min * 1.01)

                threshold = moving_avg + (recent_max - recent_min) * 0.4

                slope = lp_filtered - prev_sample

                if slope_prev > 0 and slope <= 0 and lp_filtered > threshold:
                    interval = (count - last_peak_index) * 1000 / sampling_rate
                    if interval > min_interval_ms:
                        bpm = 60000 / interval
                        if min_bpm <= bpm <= max_bpm:
                            bpm_list.append(bpm)
                            peaks_indexes.append(count)
                            last_peak_index = count

                slope_prev = slope
                prev_sample = lp_filtered

                if utime.ticks_diff(utime.ticks_ms(), last_bpm_calc_time) >= 5000:
                    valid_bpms = []
                    for i in range(1, len(peaks_indexes)):
                        interval = (peaks_indexes[i] - peaks_indexes[i - 1]) * 4
                        bpm = 60000 / interval
                        if min_bpm <= bpm <= max_bpm:
                            valid_bpms.append(bpm)
                    if valid_bpms:
                        bpm_to_display = int(sum(valid_bpms) / len(valid_bpms))
                    last_bpm_calc_time = utime.ticks_ms()

                if count % 10 == 0:
                    scale = max(1, recent_max - recent_min)
                    y2 = 30 - int(20 * (lp_filtered - recent_min) / scale)
                    y2 = max(10, min(50, y2))
                    x2 = x1 + 1

                    if peaks_indexes and count - peaks_indexes[-1] < 5:
                        y2 = 5

                    remaining = max(0, 60 - elapsed // 1000)

                    draw_heartbeat_waveform(oled, x1, y1, x2, y2, bpm_to_display, remaining)

                    x1, y1 = x2, y2
                    if x1 > 127:
                        x1 = -1

    finally:
        if timer:
            timer.deinit()
        while not fifo.empty():
            fifo.get()

        oled.fill(0)
        valid_bpms = [b for b in bpm_list if min_bpm <= b <= max_bpm]
        if valid_bpms:
            final_bpm = int(sum(valid_bpms) / len(valid_bpms))
            oled.text("Final HR:", 20, 20)
            oled.text(f"{final_bpm} bpm", 30, 40)
        else:
            oled.text("No pulse", 20, 30)

        if len(peaks_indexes) >= 2:
            ppi_in_ms = (peaks_indexes[-1] - peaks_indexes[-2]) * 4
            oled.text(f"PPI: {int(ppi_in_ms)} ms", 10, 54)

        oled.text("Press to exit", 20, 54, 1)
        oled.show()

        while not button_pressed:
            utime.sleep_ms(10)

        button_pressed = False
        
def hrv_analysis_summary(ppi_list):
    if len(ppi_list) < 2:
        display.fill(0)
        display.text("Not enough data", 0, 20)
        display.text("for HRV analysis", 0, 35)
        display.show()
        time.sleep(2)
        return

    mean_ppi = int(sum(ppi_list) / len(ppi_list))
    mean_hr = int(60000 / (sum(ppi_list) / len(ppi_list)))

    sdnn = int(round(
        (sum((x - mean_ppi) ** 2 for x in ppi_list) / (len(ppi_list) - 1)) ** 0.5
    ))

    rmssd = int(round(
        (sum((ppi_list[i+1] - ppi_list[i]) ** 2 for i in range(len(ppi_list) - 1)) / len(ppi_list)) ** 0.5
    ))

    display.fill(0)
    display.text("HRV Summary:", 0, 0)
    display.text(f"Mean PPI: {mean_ppi}", 0, 10)
    display.text(f"Mean HR : {mean_hr}", 0, 20)
    display.text(f"SDNN    : {sdnn}", 0, 30)
    display.text(f"RMSSD   : {rmssd}", 0, 40)
    display.text("Press to return", 0, 56)
    display.show()

    while not button.fifo.has_data():
        utime.sleep_ms(10)
    button.fifo.get()  # Return to menu


    # Loop to keep the menu running and responding to input
previous_index = menu_index  # To track changes in selection

while True:
    if encoder_events.has_data():
        move = encoder_events.get()
        previous_index = menu_index
        menu_index = (menu_index + move) % len(menu_options)
        update_menu(previous_index, menu_index)

    if button_pressed:
        button_pressed = False
        handle_selection()
        display_menu()  # Re-show menu after exiting from selection

    utime.sleep_ms(50)
    
    





        
