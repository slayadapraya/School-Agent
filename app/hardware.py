"""Read-only Linux telemetry. Missing sensors remain null."""
import re, threading, time
from pathlib import Path
_lock=threading.Lock()
_previous=None

def number(path,scale=1):
    try:return float(Path(path).read_text().strip())/scale
    except (OSError,ValueError):return None

def snapshot():
    global _previous
    cpu=None
    try:
        values=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
        current=(sum(values),values[3]+values[4])
        with _lock:
            if _previous and current[0]>_previous[0]:cpu=round(100*(1-(current[1]-_previous[1])/(current[0]-_previous[0])),1)
            _previous=current
    except (OSError,ValueError,IndexError):pass
    mem={}
    try:mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>=2}
    except (OSError,ValueError):pass
    cards=[]
    for card in Path('/sys/class/drm').glob('card*'):
        if re.fullmatch(r'card\d+',card.name):
            total=number(card/'device/mem_info_vram_total')
            if total:cards.append((total,card))
    gpu=dict.fromkeys(('vram_total','vram_used','utilization','temperature','hotspot','power_watts','fan_rpm','device'))
    if cards:
        total,card=max(cards,key=lambda x:x[0]);device=card/'device'
        gpu.update(vram_total=total,vram_used=number(device/'mem_info_vram_used'),utilization=number(device/'gpu_busy_percent'),device=card.name)
        sensors=list((device/'hwmon').glob('hwmon*'))
        if sensors:
            sensor=sensors[0]
            gpu.update(temperature=number(sensor/'temp1_input',1000),hotspot=number(sensor/'temp2_input',1000),power_watts=number(sensor/'power1_average',1000000) or number(sensor/'power1_input',1000000),fan_rpm=number(sensor/'fan1_input'))
    cpu_temp=None
    for sensor in Path('/sys/class/hwmon').glob('hwmon*'):
        try:
            if (sensor/'name').read_text().strip() in ('k10temp','coretemp'):cpu_temp=number(sensor/'temp1_input',1000);break
        except OSError:pass
    total=mem.get('MemTotal');available=mem.get('MemAvailable')
    return {'timestamp':time.time(),'cpu':{'utilization':cpu,'temperature':cpu_temp},'ram':{'total':total,'used':total-available if total and available is not None else None},'gpu':gpu,'note':'Power is GPU board power reported by its driver. Total PC power and CPU power are unavailable without a supported sensor. Missing readings are shown as unavailable.'}
