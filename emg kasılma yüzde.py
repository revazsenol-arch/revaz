import serial
import matplotlib.pyplot as plt
import numpy as np
import collections
import time

# --- 1. AYARLAR ---
SERIAL_PORT = 'COM4'
BAUD_RATE = 115200     
MAX_SAMPLES = 200      
OFFSET = 512.0
MVC_VALUE = 1.0  

smooth_buffer = collections.deque(maxlen=30) 
data_queue = collections.deque([0]*MAX_SAMPLES, maxlen=MAX_SAMPLES)
last_3_reps = collections.deque(["--", "--", "--"], maxlen=3)

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.001)
    ser.flushInput()
except Exception as e:
    print(f"Bağlantı hatası: {e}"); exit()

# --- 2. GÜÇLENDİRİLMİŞ KALİBRASYON ---
def calibrate():
    global OFFSET, MVC_VALUE
    
    # ADIM 1: SIFIRLAMA (Gevşek Bırak)
    print("\n--- ADIM 1: SIFIRLAMA ---")
    print("Kasınızı tamamen serbest bırakın...")
    time.sleep(2)
    ser.reset_input_buffer()
    offsets = []
    st = time.time()
    while time.time() - st < 2: # 2 saniye boyunca veri topla
        l = ser.readline().decode('utf-8', errors='ignore').strip()
        if l:
            try: offsets.append(float(l))
            except: pass
    
    OFFSET = np.mean(offsets) if offsets else 512.0
    print(f"Sıfır Noktası Sabitlendi: {OFFSET:.2f}")

    # ADIM 2: MAKSİMUM GÜÇ (Gerçekçi MVC)
    print("\n--- ADIM 2: MAKSİMUM GÜÇ ---")
    print("Sıkabildiğin kadar sık ve 3 saniye tut!")
    time.sleep(0.5)
    samples = []
    st = time.time()
    while time.time() - st < 3:
        l = ser.readline().decode('utf-8', errors='ignore').strip()
        if l:
            try:
                # Sinyali doğrult (Rectify)
                val = abs(float(l) - OFFSET)
                samples.append(val)
            except: pass
            
    if samples:
        # En yüksek %20'lik dilimin ortalamasını alıyoruz (Zıplamaları eliyoruz)
        sorted_samples = np.sort(samples)
        top_20_percent = sorted_samples[int(len(sorted_samples)*0.8):]
        MVC_VALUE = np.mean(top_20_percent)
        
        # Eğer MVC çok düşükse (hiç sıkılmadıysa) hata vermemesi için
        if MVC_VALUE < 1: MVC_VALUE = 1
    else:
        MVC_VALUE = 100.0 # Varsayılan değer
        
    print(f"Maksimum Kapasite Ayarlandı. Sistem Hazır!")

calibrate()

# --- 3. GRAFİK TASARIMI ---
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(12, 7))
line, = ax.plot(np.arange(MAX_SAMPLES), data_queue, color='#00FF00', lw=1.5, animated=True)
ax.set_ylim(0, 115)
ax.set_title("EMG Kas Aktivite Takibi", color='white', fontsize=14, pad=25)

live_text = ax.text(0.5, 0.85, '% 0', transform=ax.transAxes, ha='center', 
                    fontsize=60, color='#00FF00', fontweight='bold', animated=True)

history_text = ax.text(0.98, 0.95, 'SON 3 TEKRAR:\n1. --\n2. --\n3. --', transform=ax.transAxes, 
                       ha='right', va='top', fontsize=14, color='orange', family='monospace', 
                       bbox=dict(boxstyle='round', facecolor='black', alpha=1.0, edgecolor='#444444'), animated=True)

fig.canvas.draw()
background = fig.canvas.copy_from_bbox(ax.bbox)
plt.show(block=False)

# --- 4. ANA DÖNGÜ ---
current_rep_max = 0.0
is_active = False

while True:
    if ser.in_waiting > 50:
        for _ in range(ser.in_waiting // 10): ser.readline()

    line_str = ser.readline().decode('utf-8', errors='ignore').strip()
    
    if line_str:
        try:
            raw_val = float(line_str)
            rectified = abs(raw_val - OFFSET)
            
            # Filtreleme
            smooth_buffer.append(rectified)
            smoothed = np.mean(smooth_buffer)
            
            # Yüzde Hesapla
            percentage = (smoothed / MVC_VALUE) * 100
            
            # --- NOISE GATE (Gürültü Kapısı) ---
            # Eğer değer %3'ten küçükse tam 0 yap (Serbestte sıfır görünmesi için)
            if percentage < 3.0: percentage = 0.0
            if percentage > 110: percentage = 110 # Sınırla

            # --- TEKRAR YAKALAMA ---
            if percentage > 15.0: 
                is_active = True
                if percentage > current_rep_max: current_rep_max = percentage
                live_text.set_text(f"% {int(percentage)}")
                live_text.set_color("#FF3333") 
            else:
                if is_active:
                    last_3_reps.append(f"% {int(current_rep_max)}")
                    h_list = list(last_3_reps)
                    h_list.reverse()
                    new_history = "SON 3 TEKRAR:\n"
                    for i, val in enumerate(h_list):
                        new_history += f"{i+1}. {val}\n"
                    history_text.set_text(new_history.strip())
                    current_rep_max = 0.0
                    is_active = False
                
                live_text.set_text(f"% {int(percentage)}")
                live_text.set_color("#00FF00") 

            data_queue.append(percentage)
            line.set_ydata(data_queue)

            fig.canvas.restore_region(background)
            ax.draw_artist(line)
            ax.draw_artist(live_text)
            ax.draw_artist(history_text)
            fig.canvas.blit(ax.bbox)
            fig.canvas.flush_events()
            
        except: continue