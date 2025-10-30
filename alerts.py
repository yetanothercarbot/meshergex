import requests, threading, time

alertChannelIndex = 0
bom_warnings = []
current_fires = {}

def get_bom_warnings():
    pass

def get_fires():
    print("get")
    r = requests.get("https://publiccontent-gis-psba-qld-gov-au.s3.amazonaws.com/content/Feeds/BushfireCurrentIncidents/bushfireAlert.json")
    if r.status_code != 200:
        print(f"Unable to get fires: {r.status_code}")
        return r.status_code
    ret = {i['OBJECTID']: {"title": i['WarningTitle'], "detail": i['Header'], "lat": i['Latitude'], "lon": i['Longitude']} for i in [n['properties'] for n in r.json()['features']]}
    return ret

def update_fires(iface):
    global current_fires
    new_fires = get_fires()
    additions = []
    deletions = []

    for fire_id in current_fires:
        if fire_id not in new_fires:
            # Remove fire no longer relevant
            deletions.append(fire_id)
    
    for fire_id in new_fires:
        if fire_id not in current_fires:
            # TODO: Filter for SEQ!
            # Add new waypoint
            additions.append(fire_id)

    current_fires = new_fires
    update_individual_fire(iface, current_fires, additions, deletions)

def update_individual_fire(iface, fires, additions, deletions):
    if len(deletions) > 0:
        iface.deleteWaypoint(waypoint_id = deletions[0], wantAck = True, channelIndex = alertChannelIndex)
        deletions.pop(0)
        t = threading.Timer(2, update_individual_fire, kwargs={"iface": iface, "fires": fires, "additions": additions, "deletions": deletions})
        t.start()
        return

    if len(additions) > 0:
        # icon 128293
        fire = fires[additions[0]]
        expiry = int(time.time() + 24*60*60)
        print(f"{fire['title'][:30]}: {fire['detail'][:100]}")
        iface.sendWaypoint(name = fire['title'][:30], description = fire['detail'][:100], expire = expiry, waypoint_id = additions[0], latitude = fire['lat'], longitude = fire['lon'], channelIndex = alertChannelIndex)
        additions.pop(0)
        t = threading.Timer(2, update_individual_fire, kwargs={"iface": iface, "fires": fires, "additions": additions, "deletions": deletions})
        t.start()
        return

    threading.Timer(30*60, update_fires)

def begin(config, iface):
    global alertChannelIndex
    alertChannelIndex = config['alert_channel_index']
    update_fires(iface)
