#!/usr/bin/python
"""
This file is my shitty attempt at making a parser for valhim server logs to find
relevent data IE: steamid, player names, deaths, events
"""

import re
import sys
import datetime as dt
from collections import defaultdict
import requests
from prettytable import PrettyTable

# Optional colors to use
R = '\033[91m'
G = '\033[92m'
Y = '\033[93m'
B = '\033[94m'
P = '\033[95m'
W = '\033[97m'
E = '\033[0m'

def get_player_details(steam64id):
    """Given a steam64id use the Steam API to look up player details"""
    # Set up the API endpoint and the API key
    endpoint = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    # You'll need an API key from here https://steamcommunity.com/dev/apikey
    api_key = "EXAMPLEAPIKEYEXAMPLEAPIKEY123456"
    # Set up the parameters for the API request
    params = { "key": api_key, "steamids": steam64id }
    # Make the API request
    response = requests.get(endpoint, params=params, timeout=10)
    # Check the status code of the response
    if response.status_code == 200:
        # If the request was successful, get the player details from the response
        player_details = response.json()["response"]["players"][0]
        return player_details
    # If the request was not successful, return an error message
    return f"Error retrieving player details: {response.status_code}"

def extract_steamid(line):
    """Given a valheim server log line, extract the SteamID"""
    # Use a regular expression to extract the SteamID from the log line
    match = re.search(r"(Got connection SteamID|Closing socket) (\d{17})", line)
    if match:
        return match.group(2)
    return None

def extract_timestamp(line):
    """Given a valheim server log line, extract the timestamp"""
    # Use a regular expression to extract the timestamp from the log line
    match = re.search(r"(\d+/\d+/\d+ \d+:\d+:\d+)", line)
    if match:
        return match.group(1)
    return None

def extract_status(line):
    """Given a valheim server log line, extract a status we're looking for"""
    # Use a regular expression to extract the status from the log line
    match = re.search(r"(Got connection|Closing socket)", line)
    if match:
        return match.group(1)
    return None

def get_login_count(steamid, logins):
    """ Given a steamid, and a dict of logins, find how many times they logged in """
    # Return the number of logins for the given SteamID
    return len(logins[steamid]['login'])

def get_total_minutes_logged_in(steamid, logins):
    """ Given a steamid, and a dict of logins, find total mins of logged time """
    # Calculate the total number of minutes that the SteamID has been logged in
    total_minutes = 0
    login_times = logins[steamid]['login']
    logout_times = logins[steamid]['logout']
    # If the number of logins and logouts is not equal, we can't accurately calculate
    # the total minutes logged in; so we'll assume the player is still connected
    # and update the the last logout entry as the current time
    if len(login_times) > len(logout_times):
        # In this case, the user is still logged in, so we use the current time
        # as the logout time for their latest login
        logout_times.append(dt.datetime.now().strftime("%m/%d/%Y %H:%M:%S"))
    for login_time, logout_time in zip(login_times, logout_times):
        login_dt = dt.datetime.strptime(login_time, "%m/%d/%Y %H:%M:%S")
        logout_dt = dt.datetime.strptime(logout_time, "%m/%d/%Y %H:%M:%S")
        elapsed_time = logout_dt - login_dt
        total_minutes += elapsed_time.total_seconds() / 60
    return total_minutes

def death_finder(line):
    """Given a valheim server log line, find player deaths"""
    # Use a regular expression to find deaths from the log line
    match = re.search(r"(Got character ZDOID from (\w+) : 0:0)", line)
    if match:
        return match.group(1).split()[4]
    return None

def event_finder(line):
    """Given a valheim server log line, find events"""
    # Use a regular expression to find events from the log line
    match = re.search(r"(Random event set:(\w+))", line)
    if match:
        return match.group(1)
    return None

# Below here is horrible program logic, but w/e i r newbz and not a real dev
# Open the log file and read the lines into a list
with open(sys.argv[1], "r", encoding="utf-8") as f:
    log_lines = f.readlines()

# Initialize a dictionary to store the login and logout times for each SteamID
steam_logins = defaultdict(lambda: {'login': [], 'logout': []})
# Initialize death and event dicts
death_log = {}
event_log = {}
total_server_time = 0 # pylint: disable=invalid-name

# Parse the log file lines and extract the relevant information
# For each log line try and find pieces of info we're looking for
for log_line in log_lines:
    # Extract the SteamID, timestamp, status, death, and events from the log line
    player_steamid = extract_steamid(log_line)
    timestamp = extract_timestamp(log_line)
    if timestamp:
        # if the timestamp is valid, also get it without the time for key values
        timestamp_without_time = str(timestamp.split()[0]) # pylint: disable=invalid-name
    status = extract_status(log_line)
    death = death_finder(log_line)
    event = event_finder(log_line)
    # If we find an event, we need to store it in a dict for tracking
    if event:
        event = event.split(':')[1]
        # If we've never seen the timestamp before create it
        if timestamp_without_time not in event_log:
            event_log[timestamp_without_time] = {}
            # If we've never seen that type of event for that day create it
            if event not in event_log[timestamp_without_time]:
                event_log[timestamp_without_time][event] = 1
            # If we have seen this event for that day incriment the counter
            elif event in event_log[timestamp_without_time]:
                event_log[timestamp_without_time][event]+=1
        # If we have the date already continue on and check for events
        elif timestamp_without_time in event_log:
            # If we've never seen that type of event for that day create it
            if event not in event_log[timestamp_without_time]:
                event_log[timestamp_without_time][event] = 1
            # If we have seen this event for that day incriment the counter
            elif event in event_log[timestamp_without_time]:
                event_log[timestamp_without_time][event]+=1
    # If we've found a death on the log line, lets store it for tracking
    if death:
        # If the player hasn't been tracked before add them to the dict
        if death not in death_log:
            death_log[death]=[timestamp]
        # if they have been added before, append the new death time
        elif death in death_log:
            death_log[death].append(timestamp)
    # Add the login or logout time to the appropriate field in the logins dictionary
    if status == "Got connection":
        steam_logins[player_steamid]["login"].append(timestamp)
    elif status == "Closing socket":
        # Handle case of duplicate entries of logouts(stupid server logs)
        if timestamp not in steam_logins[player_steamid]["logout"]:
            steam_logins[player_steamid]["logout"].append(timestamp)


# Print section for the various pieces of data that we've extracted and collected
# from parsing the valheim server logs

# Print server events
events_table = PrettyTable()
events_table.field_names = ["Date", "Server Event(s)"]
events_table.align = 'l'
for k, v in event_log.items():
    event_string = "" # pylint: disable=invalid-name
    for event, count in v.items():
        event_string += f"{event}: {count}, "
    events_table.add_row([G+k+E, R+str(event_string[:-2])+E])
# Print death statistics
death_table = PrettyTable()
death_table.align = 'l'
death_table.field_names = ["Player", "Deaths"]
for player in sorted(death_log, key=lambda k: len(death_log[k]), reverse=False):
    death_table.add_row([G+player+E, R+str(len(death_log[player]))+E])
# Store the output of each table as a string
events_table_str = str(events_table) # pylint: disable=invalid-name
death_table_str = str(death_table) # pylint: disable=invalid-name

# Split each table into a list of strings, representing each row
events_table_rows = events_table_str.split('\n')
death_table_rows = death_table_str.split('\n')

# Find the maximum number of rows in both tables
max_rows = max(len(events_table_rows), len(death_table_rows))

# Iterate through the rows and print the rows side by side
for i in range(max_rows):
    # Get the current row for each table
    events_row = events_table_rows[i] if i < len(events_table_rows) else ''
    death_row = death_table_rows[i] if i < len(death_table_rows) else ''

    # Print the rows side by side
    print(f"{events_row:<30} {death_row}")

# Print all players that have logged in, their details from steam and some basic stats
player_table = PrettyTable()
player_table.align = 'l'
player_table.field_names = ["SteamID", "Name", "Real Name", "Login(s)", "Hrs Played", "First Login",
                     "Last Login", "Profile URL", "Ctry", "ST"]
for user_steamid in steam_logins:
    player_info = get_player_details(user_steamid)
    player_table.add_row([G+user_steamid+E, Y+player_info['personaname']+E,
                   R+player_info.get('realname', 'N/A')+E,
                   get_login_count(user_steamid, steam_logins),
                   round(get_total_minutes_logged_in(user_steamid, steam_logins)/60, 2),
                   steam_logins[user_steamid]['login'][0], steam_logins[user_steamid]['login'][-1],
                   B+player_info['profileurl']+E, player_info.get('loccountrycode', 'N/A'),
                   player_info.get('locstatecode', 'N/A')])
    total_server_time += (get_total_minutes_logged_in(user_steamid, steam_logins)/60)
print(player_table)
print("\nTotal server time played in days: " + str(round(total_server_time/24,2)))
