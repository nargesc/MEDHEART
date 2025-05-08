import math
import utime
import ujson
import framebuf
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
import network
import urequests as requests
from umqtt.simple import MQTTClient
from fifo import Fifo
from piotimer import Piotimer

#System Setup and Global Variables

global button_pressed
button_pressed = False
menu_index = 0
encoder_events = Fifo(30)
last_button_time = 0
x1, y1 = -1, 32  
sampling_rate = 250 
fifo = Fifo(2 * sampling_rate)
menu_option = None  
adc = ADC(26)
clear_height = 50
finger_detected = False
global last_adc_value
last_adc_value = 0
run_time_ms = 60000
timer = None
waveform_buffer = []
button_pressed = False
stop_requested = False
ppi_list = []
kubios_client = None  # Global MQTT client


#Wi-Fi and MQTT Configuration

WIFI_SSID = "KMD652_Group_8"
WIFI_PASSWORD = "KMD652_Group_8"
MQTT_BROKER = "192.168.8.253"
MQTT_PORT =21883
MQTT_USER = "narges8"
MQTT_PASS = "narges8"
MQTT_TOPIC = "kubios-request"

def connect_wifi():
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        timeout = 10  
        while not wlan.isconnected() and timeout > 0:
            utime.sleep(1)
            timeout -= 1

    if wlan.isconnected():
        print("Connected, IP:", wlan.ifconfig()[0])
        return True
    else:
        print("Failed to connect.")
        return False



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


"""# --- HRV Icon 16x16 pixels ---
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
"""

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
    global button_pressed, last_button_time, stop_requested
    now = utime.ticks_ms()
    if utime.ticks_diff(now, last_button_time) > 200:
        button_pressed = True
        stop_requested = True  
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
utime.sleep(3)    
oled.invert(False)  
display_menu()


#Heart Rate Measurement and HRV Analysis

def measure_heart_rate(duration=60, show_result=True, allow_button_exit=True):

    global fifo, timer, stop_requested, button_pressed, ppi_list

    sampling_freq = 250
    fifo = Fifo(2 * sampling_freq)
    run_time_in_sec = duration
    baseline_length = 250
    offset = 1100
    min_interval = 60
    sample_window = []
    bpm_list = []
    ppi_list = []

    count = 0
    prev = None
    rising = False
    peak_candidate = None
    candidate_index = None
    last_peak_index = None

    x1, y1 = -1, 32
    last_bpm_update = utime.ticks_ms()
    displayed_bpm = "--"

    stop_requested = False
    button_pressed = False

    # Sampling function
    def adc_read(tim):
        val = adc.read_u16()
        if 25000 < val < 60000:
            try:
                fifo.put(val)
            except:
                pass

    # Start sampling
    timer = Piotimer(freq=sampling_freq, callback=adc_read)
    oled.fill(0)
    oled.text("Start Measuring", 10, 25)
    oled.show()

    start_time = utime.ticks_ms()

    while utime.ticks_diff(utime.ticks_ms(), start_time) < run_time_in_sec * 1000:
        if stop_requested:
            break

        elapsed_ms = utime.ticks_diff(utime.ticks_ms(), start_time)
        time_left = run_time_in_sec - (elapsed_ms // 1000)

        # Process new ADC value
        if not fifo.empty():
            x = fifo.get()
            count += 1
            sample_window.append(x)

            if len(sample_window) > baseline_length:
                sample_window.pop(0)
            if len(sample_window) < baseline_length:
                continue

            baseline = sum(sample_window) / len(sample_window)
            threshold = baseline + offset


            # Graph plotting (optional)
            if count % 2 == 0:
                y2 = int(25 * (baseline - x) / 4000 + 25)
                y2 = max(0, min(50, y2))
                x2 = x1 + 1
                oled.vline(x2, 10, 40, 0)
                if x1 >= 0:
                    oled.line(x1, y1, x2, y2, 1)
                else:
                    oled.pixel(x2, y2, 1)
                x1 = x2 if x2 <= 127 else -1
                y1 = y2

            # Peak detection
            if prev is None:
                prev = x
                continue

            diff = x - prev
            if diff > 0:
                rising = True
                if peak_candidate is None or x > peak_candidate:
                    peak_candidate = x
                    candidate_index = count
            elif rising:
                if peak_candidate and peak_candidate > threshold:
                    if last_peak_index is None or (candidate_index - last_peak_index) >= min_interval:
                        if last_peak_index is not None:
                            interval = candidate_index - last_peak_index
                            bpm = (60 * sampling_freq) / interval
                            if 30 < bpm < 180:
                                bpm_list.append(bpm)
                                ppi_list.append(interval * 4)
                        last_peak_index = candidate_index
                rising = False
                peak_candidate = None
                candidate_index = None
            prev = x

        # === Update displayed BPM every 5 seconds ===
        if utime.ticks_diff(utime.ticks_ms(), last_bpm_update) >= 5000 and len(bpm_list) >= 2:
            recent_bpm = sum(bpm_list[-5:]) / min(5, len(bpm_list))
            displayed_bpm = str(int(recent_bpm))
            last_bpm_update = utime.ticks_ms()

        # === Display update ===
        oled.fill_rect(0, 0, 128, 10, 0)
        oled.text(f"BPM: {displayed_bpm}", 0, 0)
        oled.fill_rect(0, 54, 128, 10, 0)
        oled.text(f"Time left: {time_left}s", 10, 54)
        oled.show()

    timer.deinit()
    fifo.empty()

    if show_result:
     oled.fill(0)
    if bpm_list:
        avg_bpm = sum(bpm_list) / len(bpm_list)
        oled.text("BPM:", 10, 25)
        oled.text(f"{int(avg_bpm)}", 55, 25)
        save_history(int(avg_bpm))
    else:
        oled.text("No signal", 25, 30)
    oled.show()

    if allow_button_exit:
        while True:
            if button_pressed:
                button_pressed = False
                break
            utime.sleep(0.1)


    display_menu()


    
def avg_ppi(ppi_list):
    return int(sum(ppi_list) / len(ppi_list)) if ppi_list else 0

def avg_bpm(ppi_list):
    return int(60000 / (sum(ppi_list) / len(ppi_list))) if ppi_list else 0

def calculate_sdnn(ppi_list, mean_ppi):
    if len(ppi_list) < 2:
        return 0
    variance = sum((x - mean_ppi) ** 2 for x in ppi_list) / (len(ppi_list) - 1)
    return int(round(variance ** 0.5))

def calculate_rmssd(ppi_list):
    if len(ppi_list) < 2:
        return 0
    diffs = [(ppi_list[i+1] - ppi_list[i]) ** 2 for i in range(len(ppi_list) - 1)]
    return int(round((sum(diffs) / len(diffs)) ** 0.5))

def analys_hrv(ppi_list):
    global button_pressed, oled
   
    filtered_ppis = [ppi for ppi in ppi_list if 300 < ppi < 2000]

    if len(filtered_ppis) < 2:
        oled.fill(0)
        oled.text("Not enough data", 10, 25)
        oled.show()
        utime.sleep(2)
        return

  
    clean_ppis = [filtered_ppis[0]]
    for i in range(1, len(filtered_ppis)):
        if abs(filtered_ppis[i] - filtered_ppis[i - 1]) < 400:
            clean_ppis.append(filtered_ppis[i])

    if len(clean_ppis) < 2:
        oled.fill(0)
        oled.text("Filtered too much", 10, 25)
        oled.show()
        utime.sleep(2)
        return

    mean_ppi_val = avg_ppi(clean_ppis)
    mean_hr_val = avg_bpm(clean_ppis)
    sdnn_val = calculate_sdnn(clean_ppis, mean_ppi_val)
    rmssd_val = calculate_rmssd(clean_ppis)

    oled.fill(0)
    oled.text("HRV Results", 25, 0)
    oled.text(f"PPI   : {mean_ppi_val}", 0, 15)
    oled.text(f"HR    : {mean_hr_val}", 0, 25)
    oled.text(f"SDNN  : {sdnn_val} ms", 0, 35)
    oled.text(f"RMSSD : {rmssd_val} ms", 0, 45)
    oled.show()
    utime.sleep(6)
    
    send_hrv_mqtt(mean_ppi_val, mean_hr_val, rmssd_val, sdnn_val)
    oled.fill_rect(0, 56, 128, 8, 0)
    oled.text("Press to return", 10, 56)
    oled.show()

    while not button_pressed:
        utime.sleep_ms(10)

    return mean_ppi_val, mean_hr_val, sdnn_val, rmssd_val
    button_pressed = False
    display_menu()

    
# send data to mqtt


def send_hrv_mqtt(mean_ppi, mean_hr, rmssd, sdnn):
    if not wifi_connected:
        print("Wi-Fi not connected, skipping MQTT send.")
        return

    msg = {
        "mean_ppi": mean_ppi,
        "mean_hr": mean_hr,
        "rmssd": rmssd,
        "sdnn": sdnn
    }

    try:
        client = MQTTClient("medheart_client", MQTT_BROKER, port=MQTT_PORT,
                            user=MQTT_USER, password=MQTT_PASS)
        client.connect()
        client.publish(MQTT_TOPIC.encode(), ujson.dumps(msg).encode())
        client.disconnect()
        print(" MQTT data sent:", msg)
    except Exception as e:
        print("MQTT send failed:", e)


def wait_for_kubios_response(timeout=10):
    client = MQTTClient("pico", MQTT_BROKER, port=MQTT_PORT)
    client.set_callback(on_kubios_response)
    client.connect()
    client.subscribe("kubios-response")

    start = utime.ticks_ms()
    while utime.ticks_diff(utime.ticks_ms(), start) < timeout * 1000:
        client.check_msg()
        utime.sleep_ms(200)
    client.disconnect()


def send_kubios_mqtt(ppi_list, duration_sec):
    if not wifi_connected:
        print("Wi-Fi not connected, skipping Kubios MQTT send.")
        return

    # Check if PPI data is valid
    if not ppi_list or len(ppi_list) < 2:
        print("Not enough PPI data.")
        return

    data = {
        "id": utime.ticks_ms(),  # Unique message ID
        "type": "RRI",           # Data type (RRI = RR intervals in ms)
        "data": ppi_list,        # The list of PPI values (in ms)
        "analysis": {
            "type": "readiness"  # Analysis type: can be "readiness", "stress", "recovery", etc.
        }
    }

    try:
        client = MQTTClient("kubios_sender", MQTT_BROKER, port=MQTT_PORT,
                            user=MQTT_USER, password=MQTT_PASS)
        client.connect()
        client.publish("kubios-request", ujson.dumps(data))
        client.disconnect()
        print("Sent HRV data to Kubios proxy:", data)
    except Exception as e:
        print("Error sending data to Kubios:", e)

def on_kubios_response(topic, msg):
    global button_pressed

    try:
        result = ujson.loads(msg)
        analysis = result.get("data", {}).get("analysis", {})
        freq = analysis.get("freq_domain", {})
        artefact = result.get("data", {}).get("artefact_level", "N/A")
        timestamp = result.get("data", {}).get("create_timestamp", None)

        HF = int(freq.get("HF_power", 0))
        LF = int(freq.get("LF_power", 0))
        VLF = int(freq.get("VLF_power", 0))

        oled.fill(0)
        oled.text("Kubios Result:", 0, 0)
        oled.text(f"HF : {HF}", 0, 12)
        oled.text(f"LF : {LF}", 0, 24)
        oled.text(f"VLF: {VLF}", 0, 36)
        oled.text(f"Artfct: {artefact}", 0, 48)
        oled.show()

       
        kubios_summary = f"HF:{HF}, LF:{LF}, VLF:{VLF}"
        save_history(kubios_summary, timestamp=timestamp, source="Kubios")

        while not button_pressed:
            utime.sleep_ms(100)
        button_pressed = False
        display_menu()

    except Exception as e:
        print("Error parsing Kubios response:", e)
        oled.fill(0)
        oled.text("Parse Error", 20, 30)
        oled.show()
        utime.sleep(2)
        display_menu()

    except Exception as e:
        print("Error parsing Kubios response:", e)
        oled.fill(0)
        oled.text("Parse Error", 20, 30)
        oled.show()
        utime.sleep(2)
        display_menu()


        oled.show()
        utime.sleep(6)

    except Exception as e:
        print("Error parsing Kubios response:", e)
        

def kubios_workflow():
    global ppi_list, button_pressed

    ppi_list.clear()

    
    measure_heart_rate(duration=30, show_result=False, allow_button_exit=False)

    oled.fill(0)
    oled.text("Sending to", 20, 20)
    oled.text("Kubios...", 35, 35)
    oled.show()
    send_kubios_mqtt(ppi_list, 30)

    oled.fill(0)
    oled.text("Waiting result", 10, 20)
    oled.show()

    
    try:
        client = MQTTClient("kubios_listener", MQTT_BROKER, port=MQTT_PORT,
                            user=MQTT_USER, password=MQTT_PASS)
        client.set_callback(on_kubios_response)  
        client.connect()
        client.subscribe("kubios-response")

        start = utime.ticks_ms()
        while True:
            client.check_msg()  
            if utime.ticks_diff(utime.ticks_ms(), start) > 10000:
                oled.fill(0)
                oled.text("Timeout waiting", 5, 20)
                oled.text("Kubios result", 5, 35)
                oled.show()
                utime.sleep(2)
                break
            if button_pressed:
                button_pressed = False
                break
            utime.sleep_ms(200)

        client.disconnect()

    except Exception as e:
        print("MQTT error:", e)
        oled.fill(0)
        oled.text("MQTT error", 10, 25)
        oled.show()
        utime.sleep(2)

    display_menu()



history = []

def save_history(bpm, timestamp=None, source="HR"):
    if timestamp is None:
        timestamp = utime.localtime()
    formatted_time = "{:02d}-{:02d} {:02d}:{:02d}".format(timestamp[1], timestamp[2], timestamp[3], timestamp[4])
    history.append({
        "bpm": bpm if source == "HR" else f"{source}",  
        "time": formatted_time
    })



# Connect to Wi-Fi once at startup

wifi_connected = connect_wifi()


# Main loop
while True:
    # Handle rotary encoder movement
    if not encoder_events.empty():
        move = encoder_events.get()
        previous_index = menu_index
        menu_index = (menu_index + move) % len(menu_options)
        update_menu(previous_index, menu_index)

    # Handle button press and menu selection
    if button_pressed:
        button_pressed = False
        selected_option = menu_options[menu_index]

        if selected_option == "Measure HR":
            measure_heart_rate()
            display_menu()

        elif selected_option == "HRV Analysis":
            analys_hrv(ppi_list)
            display_menu()

        elif selected_option == "Kubios":
            kubios_workflow()
            display_menu()
        elif selected_option == "History":
                        oled.fill(0)
                        if history:
                            for i, record in enumerate(history[-3:]):
                                
                                if 'bpm' in record:
                                    bpm_value = record['bpm']
                                    text_line = bpm_value if isinstance(bpm_value, str) else f"{bpm_value} BPM"
                                else:
                                    text_line = "Kubios"  

                                time_str = record.get('time', 'No Time')
                                oled.text(text_line, 0, i * 16)
                                oled.text(time_str, 64, i * 16)
                        else:
                            oled.text("No history", 10, 30)
                        oled.show()
                        utime.sleep(4)
                        display_menu()




        
                    