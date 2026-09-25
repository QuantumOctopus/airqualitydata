import datetime
import os
import openpyxl
import re
import json
import pytz
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

CITIES = {
    "Blue Bell, PA": {"url": "https://www.iqair.com/usa/pennsylvania/blue-bell", "tz": "America/New_York"},
    "Philadelphia, PA": {"url": "https://www.iqair.com/usa/pennsylvania/philadelphia", "tz": "America/New_York"},
    "Bronx, NY": {"url": "https://www.iqair.com/us/usa/new-york/bronx", "tz": "America/New_York"},
    "New York City, NY": {"url": "https://www.iqair.com/us/usa/new-york/new-york-city", "tz": "America/New_York"},
    "Altoona, PA": {"url": "https://www.iqair.com/us/usa/pennsylvania/altoona", "tz": "America/New_York"},
    "Chicago, IL": {"url": "https://www.iqair.com/us/usa/illinois/chicago", "tz": "America/Chicago"},
    "New Delhi, India": {"url": "https://www.iqair.com/in-en/india/delhi/new-delhi", "tz": "Asia/Kolkata"},
    "Bengaluru, India": {"url": "https://www.iqair.com/in-en/india/karnataka/bengaluru", "tz": "Asia/Kolkata"},
    "Chennai, India": {"url": "https://www.iqair.com/in-en/india/tamil-nadu/chennai", "tz": "Asia/Kolkata"}
}

def extract_metric(lines, label, offset=1):
    """Finds a label in the lines and returns the line at the given offset."""
    for i, line in enumerate(lines):
        if label.lower() in line.lower():
            if i + offset < len(lines):
                return lines[i + offset].strip()
    return ""

def set_pollutant_value(data, pri_pollutant, val):
    if pri_pollutant == "PM2.5":
        data["PM2.5 ug/m3"] = val
    elif pri_pollutant == "PM10":
        data["PM10 ug/m3"] = val
    elif pri_pollutant in ("O3", "O₃") or "ozone" in pri_pollutant.lower():
        data["Ozone ug/m3"] = val
    elif pri_pollutant in ("NO2", "NO₂"):
        data["NO2 ug/m3"] = val
    elif pri_pollutant in ("SO2", "SO₂"):
        data["SO2 ug/m3"] = val
    elif pri_pollutant == "CO":
        data["CO ug/m3"] = val

def scrape_city_data(page, url, tz_name):
    print(f"Scraping {url}...")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    
    # Scroll down to ensure lazy-loaded "Air pollutants" section renders
    page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
    page.wait_for_timeout(1000)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(3000)
    
    text = page.locator("body").inner_text()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    local_tz = pytz.timezone(tz_name)
    now = datetime.datetime.now(local_tz)
    # Initialize with empty strings
    data = {
        "Date": now.date(),
        "Time": datetime.time(now.hour, now.minute),
        "PM2.5 ug/m3": "",
        "Temp F": "",
        "Humidity": "",
        "Ozone ug/m3": "",
        "NO2 ug/m3": "",
        "SO2 ug/m3": "",
        "CO ug/m3": "",
        "AQI+": "",
        "Pri. Pollutant": "",
        "PM10 ug/m3": ""
    }
    
    # AQI is usually just before "US AQI" or on the same line
    for i, line in enumerate(lines):
        if "US AQI" in line:
            tokens = line.replace("*", "").split()
            if tokens and tokens[0].isdigit():
                data["AQI+"] = tokens[0]
            elif i > 0:
                aqi = lines[i-1].replace("*", "").strip()
                if aqi.isdigit():
                    data["AQI+"] = aqi
            break
            
    # Primary Pollutant Name and Top-Box Value
    pri_pollutant = ""
    for i, line in enumerate(lines):
        if "main pollutant:" in line.lower():
            parts = line.split(":", 1)
            
            if len(parts) > 1 and parts[1].strip():
                rest = parts[1].strip()
                if "µg/m³" in rest:
                    clean_rest = rest.replace("µg/m³", "").strip()
                    tokens = clean_rest.split()
                    if len(tokens) >= 2:
                        pri_pollutant = " ".join(tokens[:-1])
                        val = tokens[-1]
                        set_pollutant_value(data, pri_pollutant, val)
                else:
                    pri_pollutant = rest
            elif i + 1 < len(lines):
                pri_pollutant = lines[i+1].strip()
                
            # If value wasn't inline, look ahead up to 4 lines for µg/m³
            if pri_pollutant and not (len(parts) > 1 and "µg/m³" in parts[1]):
                for j in range(i, min(i+5, len(lines))):
                    if "µg/m³" in lines[j]:
                        val = lines[j].replace("µg/m³", "").strip()
                        val_tokens = val.split()
                        if val_tokens:
                            set_pollutant_value(data, pri_pollutant, val_tokens[-1])
                        break
            break
            
    if pri_pollutant.strip().upper() in ["O3", "O₃"]:
        pri_pollutant = "Ozone"
            
    data["Pri. Pollutant"] = pri_pollutant

    # Temperature and Humidity usually follow the AQI block
    # Looking for a line with '°' for temp
    for i, line in enumerate(lines):
        if '°' in line and len(line) < 10:
            temp_c = line.replace('°', '').strip()
            try:
                temp_c_float = float(temp_c)
                temp_f = round((temp_c_float * 9/5) + 32, 1)
                data["Temp F"] = str(temp_f)
            except ValueError:
                pass
                
            # Usually humidity is 2 lines down (e.g. 13 km/h then 57 %)
            if i + 2 < len(lines) and '%' in lines[i+2]:
                data["Humidity"] = lines[i+2].replace('%', '').strip()
            break

    # Find Pollutant Values (From the "Air pollutants" box)
    air_pollutants_idx = 0
    for i, line in enumerate(lines):
        if line.lower() == "air pollutants":
            air_pollutants_idx = i
            break

    pollutant_keys = {
        "PM2.5": "PM2.5 ug/m3",
        "PM10": "PM10 ug/m3",
        "Ozone": "Ozone ug/m3",
        "O3": "Ozone ug/m3",
        "O₃": "Ozone ug/m3",
        "Nitrogen dioxide": "NO2 ug/m3",
        "NO2": "NO2 ug/m3",
        "NO₂": "NO2 ug/m3",
        "Sulfur dioxide": "SO2 ug/m3",
        "SO2": "SO2 ug/m3",
        "SO₂": "SO2 ug/m3",
        "Carbon monoxide": "CO ug/m3",
        "CO": "CO ug/m3"
    }

    for i in range(air_pollutants_idx, len(lines)):
        line = lines[i].strip()
        for p_name, p_key in pollutant_keys.items():
            if data[p_key] == "" and line.upper() == p_name.upper():
                # The value should be in the next few lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    val_line = lines[j]
                    if "µg/m³" in val_line:
                        val = val_line.replace("µg/m³", "").strip()
                        if not val and j > 0:
                            val = lines[j-1].strip()
                        val_tokens = val.split()
                        if val_tokens:
                            data[p_key] = val_tokens[-1]
                        break
                break
                
    return data

def update_json(file_path, city_name, data):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                all_data = json.load(f)
            except json.JSONDecodeError:
                all_data = {}
    else:
        all_data = {}
        
    if city_name not in all_data:
        all_data[city_name] = []
        
    row_data = {}
    for key, val in data.items():
        if isinstance(val, (datetime.date, datetime.time)):
            row_data[key] = str(val)
        else:
            if isinstance(val, str) and val != "":
                if val.lstrip('-').isdigit():
                    row_data[key] = int(val)
                else:
                    try:
                        row_data[key] = float(val)
                    except ValueError:
                        row_data[key] = val
            else:
                row_data[key] = val
                
    all_data[city_name].append(row_data)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=4)

def main():
    json_file = "data.json"
    with sync_playwright() as p:
        # We use standard chromium
        browser = p.chromium.launch(headless=True)
        # Create a context with a standard user agent to avoid basic blocks
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)
        
        for city, info in CITIES.items():
            try:
                data = scrape_city_data(page, info["url"], info["tz"])
                update_json(json_file, city, data)
                print(f"Successfully updated {city}: AQI={data['AQI+']}, Temp={data['Temp F']}")
            except Exception as e:
                print(f"Error scraping {city}: {e}")
                
        browser.close()

if __name__ == "__main__":
    main()
