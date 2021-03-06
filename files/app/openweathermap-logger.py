from pyowm import OWM
from pyowm.utils import config
from pyowm.utils import timestamps

import os
import socket
import binascii
import time
import sys
import configparser
import init_db
from influxdb import InfluxDBClient

eConfig = configparser.RawConfigParser(allow_no_value=True)
eConfig.read("config.ini")

log_path = eConfig.get('Logging', 'log_path', fallback='/var/log/solar/')
do_raw_log = eConfig.getboolean('Logging', 'do_raw_log')
apikey = os.getenv('apikey', '')

country = eConfig.get('Weather', 'country')
language = eConfig.get('Weather', 'language')

influx_server = eConfig.get('InfluxDB', 'influx_server')
influx_port = int(eConfig.get('InfluxDB', 'influx_port'))
influx_database = eConfig.get('InfluxDB', 'database')
influx_measurement = eConfig.get('InfluxDB', 'measurement')

if __debug__:
    print("running with debug")
    print(influx_server)
    print(influx_port)
    print(influx_database)
    print(influx_measurement)
    print(log_path)
    print(do_raw_log)
else:
    print("running without debug")

# if the db is not found, then try to create it
try:
    dbclient = InfluxDBClient(host=influx_server, port=influx_port)
    dblist = dbclient.get_list_database()
    db_found = False
    for db in dblist:
        if db['name'] == influx_database:
            db_found = True
    if not(db_found):
        print('Database ' + influx_database + ' not found, trying to create it')        

#select_clause = 'SELECT mean("value") INTO "cpu_mean" ' \
#                'FROM "weather" GROUP BY time(1m)'
#client.create_continuous_query(
#     'cpu_mean', select_clause, 'influx_database', 'EVERY 10s FOR 2m'

#CREATE CONTINUOUS QUERY "cq_30m" ON "food_data" BEGIN
# SELECT mean("website") AS "mean_website",mean("phone") AS "mean_phone"
#  INTO "a_year"."downsampled_orders"
#  FROM "orders"
#  GROUP BY time(30m)
#END

except Exception as e:
    print('Error querying open database: ' )
    print(e)

config_dict = config.get_default_config()
config_dict['language'] = language
        
try:
    while True:
        owm = OWM(apikey, config_dict)
        mgr = owm.weather_manager()

        # Here put your city and Country ISO 3166 country codes
        observation = mgr.weather_at_place(country)

        w = observation.weather
        # Weather details from INTERNET

        values = dict()
        values['status'] = w.status         # short version of status (eg. 'Rain')
        values['detailed_status']  = w.detailed_status  # detailed version of status (eg. 'light rain')

        wind  = w.wind()


        values['wind_speed']  = wind ["speed"]
        values['wind_direction_deg']  = wind ["deg"]
        values['humidity']  = w.humidity

        temperature  = w.temperature('celsius')
        values['temp']  = temperature["temp"]
        values['pressure'] = w.pressure['press']

        values['clouds'] = w.clouds #Cloud coverage
        values["sunrise"] = w.sunrise_time()*1000 #Sunrise time (GMT UNIXtime or ISO 8601)
        values["sunset"] = w.sunset_time() #Sunset time (GMT UNIXtime or ISO 8601)
        values["weather_code"] =  w.weather_code
        values["weather_icon"] = w.weather_icon_name
        values["visibility_distance"] = w.visibility_distance

        location = observation.location.name
        values["location"] = location

        rain = w.rain
        #If there is no data recorded from rain then return 0, otherwise #return the actual data
        if len(rain) == 0:
            values['lastrain'] = float("0")
        else:
            if "3h" in rain:
               values['lastrain'] = rain["3h"]
            if "1h" in rain:
               values['lastrain'] = rain["1h"]

        snow = w.snow
        #If there is no data recorded from rain then return 0, otherwise #return the actual data
        if len(snow) == 0:
            values['lastsnow'] = float("0")
        else:
            if "3h" in snow:
               values['lastsnow'] = snow["3h"]
            if "1h" in snow:
               values['lastsnow'] = snow["1h"]

#       UV index
        s = country.split(",")
        reg = owm.city_id_registry()
        list_of_locations = reg.locations_for(s[0], country=s[1])
        myLocation = list_of_locations[0]

        uvimgr = owm.uvindex_manager()

        uvi = uvimgr.uvindex_around_coords(myLocation.lat, myLocation.lon )
        values['uvi'] = uvi.value

        # Print the data
        if __debug__:
            print(values)
        
        json_body = {'points': [{
                                 'tags': {'location':  location },
                                 'fields': {k: v for k, v in values.items()}
                                        }],
                            'measurement': influx_measurement
                            }

        client = InfluxDBClient(host=influx_server,
                                port=influx_port)
        success = client.write(json_body,
                            # params isneeded, otherwise error 'database is required' happens
                            params={'db': influx_database})

        if not success:
            print('error writing to database')

        client.close()

        time.sleep( 300 )
except Exception as e:
    print(e)
    print("Unexpected error:", sys.exc_info()[0])
#        raise
finally:
    if __debug__:
        print("Finally")