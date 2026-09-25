import datetime
import os
import json
import urllib.request
import urllib.parse

API_TOKEN = "d9b42867df6f6c7f0805cdce3c65f1ed98743516"

CITIES = {
    "Blue Bell, PA": "geo:40.1448;-75.2688",
    "Philadelphia, PA": "Philadelphia",
    "Bronx, NY": "Bronx",
    "New York City, NY": "New York",
    "Altoona, PA": "geo:40.5186;-78.3947",
    "Chicago, IL": "Chicago",
    "New Delhi, India": "New Delhi",
    "Bengaluru, India": "Bangalore",
    "Chennai, India": "Chennai"
}

def fetch_waqi_data(city_query):
    url = f"https://api.waqi.info/feed/{urllib.parse.quote(city_query)}/?token={API_TOKEN}"
    req = urllib.request.urlopen(url)
    res = json.loads(req.read().decode('utf-8'))
    
    if res.get("status") != "ok":
        raise Exception(f"API Error: {res.get('data')}")
        
    return res["data"]

def process_city_data(api_data):
    time_str = api_data.get("time", {}).get("s", "")
    if time_str:
        dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        date_val = dt.date().isoformat()
        time_val = dt.time().isoformat()
    else:
        now = datetime.datetime.utcnow()
        date_val = now.date().isoformat()
        time_val = now.time().isoformat()

    iaqi = api_data.get("iaqi", {})
    
    def get_val(key):
        return iaqi.get(key, {}).get("v", "")

    temp_c = get_val("t")
    temp_f = round((temp_c * 9/5) + 32, 1) if temp_c != "" else ""

    pri_pollutant = api_data.get("dominentpol", "").upper()
    if pri_pollutant == "PM25":
        pri_pollutant = "PM2.5"
    elif pri_pollutant == "O3":
        pri_pollutant = "Ozone"

    return {
        "Date": date_val,
        "Time": time_val,
        "PM2.5 ug/m3": get_val("pm25"),
        "Temp F": temp_f,
        "Humidity": get_val("h"),
        "Ozone ug/m3": get_val("o3"),
        "NO2 ug/m3": get_val("no2"),
        "SO2 ug/m3": get_val("so2"),
        "CO ug/m3": get_val("co"),
        "AQI+": api_data.get("aqi", ""),
        "Pri. Pollutant": pri_pollutant,
        "PM10 ug/m3": get_val("pm10")
    }

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
        
    all_data[city_name].append(data)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=4)

def main():
    json_file = "data.json"
    
    for city_name, query in CITIES.items():
        try:
            print(f"Fetching {city_name}...")
            raw_data = fetch_waqi_data(query)
            processed_data = process_city_data(raw_data)
            update_json(json_file, city_name, processed_data)
            print(f"Successfully updated {city_name}: AQI={processed_data['AQI+']}, Temp={processed_data['Temp F']}")
        except Exception as e:
            print(f"Error fetching {city_name}: {e}")
            empty = {
                "Date": datetime.datetime.now().date().isoformat(),
                "Time": datetime.datetime.now().time().isoformat(),
                "PM2.5 ug/m3": "", "Temp F": "", "Humidity": "",
                "Ozone ug/m3": "", "NO2 ug/m3": "", "SO2 ug/m3": "",
                "CO ug/m3": "", "AQI+": "", "Pri. Pollutant": "", "PM10 ug/m3": ""
            }
            update_json(json_file, city_name, empty)

if __name__ == "__main__":
    main()
