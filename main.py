import hashlib, json, meshtastic, meshtastic.tcp_interface, re, requests, sys, threading, time
from packaging.version import Version
from pubsub import pub
import paho.mqtt.client as mqtt

search = re.compile(r"^outages?(\s?(?P<suburb>(\w|\ )+)?)(\s(?P<iid>INCD-[0-9]+-g))?$", re.I)
timestamp = re.compile(r"T(?P<time>\d\d:\d\d)")

channelIndex = 0
waitPeriod = 0

overview = {}
suburbs = {}

unhandledReqs = {}
mqttc = None

def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("meshergex/handled")

def on_mqtt_message(client, userdata, msg):
    # msg.topic
    # msg.payload
    pl = msg.payload.decode()
    if pl in unhandledReqs:
        print(f"Cancel {pl}")
        unhandledReqs[pl].cancel()
        unhandledReqs.pop(pl)

def updateSummary():
    global overview
    r_summ = requests.get("https://www.energex.com.au/api/outages-text/v1.0.ex/summary")
    if r_summ.status_code != 200:
        print(f"Unable to update summary: {r_summ.status_code}")
        return r_summ.status_code
    r_suburbs = requests.get("https://www.energex.com.au/api/outages-text/v1.0.ex/suburb", params={"council": None, "suburb": None})
    if r_suburbs.status_code != 200:
        print(f"Unable to retrieve suburb outages: {r_suburbs.status_code}")
        return r_suburbs.status_code

    overview = {"affected": r_summ.json()['data']['totalCustomersAffected'], "updated": int(r_summ.json()['data']['secondsSinceEpoch']), 
        "suburbs": {i['name']: {'affected': i['customersAffected'], 'outages': i['outagesCount']} for i in r_suburbs.json()['data']}}


def updateSuburb(suburb: str):
    r = requests.get("https://www.energex.com.au/api/outages-text/v1.0.ex/search", params={"suburb": suburb.upper()})
    if r.status_code != 200:
        print(f"Received status {r.status_code}")
        return r.status_code
    suburbs[suburb] = {}
    suburbs[suburb]['timestamp'] = time.monotonic()
    suburbs[suburb]['data'] = r.json()['data']
    return 0

def retrieveSuburb(suburb: str, iid: str):
    suburb = suburb.upper()
    print(f"Suburb: {suburb}, iid: {iid}")

    if len(overview) == 0 or (time.time() - overview['updated']) > 20*60:
        update = True
        updateSummary() 

    if suburb.upper() == "SUMMARY":
        return ((f"Summary: {overview['affected']} affected across {sum(overview['suburbs'][i]['outages'] for i in overview['suburbs'])} outages. "
            f"Last updated {time.strftime('%H:%M', time.localtime(overview['updated']))}"), True)

    if suburb.upper() not in overview['suburbs']:
        return (f"No outage found in {suburb[:40]}. Call 13 62 62 to report outage or 13 19 62 for fallen powerlines or electric shocks.", True)

    if suburb not in suburbs or update:
        if updateSuburb(suburb) != 0:
            return (f"Unable to retrieve data from Energex :(", False)
    
    # If only one outage, show it.
    if len(suburbs[suburb]['data'])  == 1:
        iid = suburbs[suburb]['data'][0]['event']

    if iid is None:
        affected = 0
        for e in suburbs[suburb]['data']:
            affected += int(e['customersAffected'])
        return (f"{suburb} has {len(suburbs[suburb]['data'])} reported outages, with {affected} customers affected.", True)
    else:
        for incident in suburbs[suburb]['data']:
            if incident['event'].upper() == iid.upper():
                nextUpdate = timestamp.search(incident['restoreTime'])
                return (f"{incident['event']}, {incident['suburb']}: {incident['status']} - {incident['cause']}. Affects {incident['customersAffected']}. Next update {nextUpdate.group('time')}", True)
        return (f"{iid}: Not found.", True)

def handleMeshPacket(message, hash, interface):
    if hash in unhandledReqs:
        unhandledReqs.pop(hash)
    # TODO: use sendAlert for WWWarn.
    res = search.match(message)
    if res is None:
        return
    elif res.group("suburb") is None:
        ret = retrieveSuburb("summary", None)
    else:
        ret = retrieveSuburb(res.group("suburb"), res.group("iid"))

    interface.sendText(text = ret[0], wantAck = True, channelIndex = channelIndex)
    if ret[1]:
        # This needs to be delayed to avoid a race condition where we have resolved a request before secondary nodes have even received it.
        t = threading.Timer(10, mqttc.publish, args=("meshergex/handled", hash))
        t.start()

def onMeshReceive(packet, interface):
    message = packet['decoded']['text']
    hash = hashlib.sha256(f"{packet['decoded']['text']}".encode()).hexdigest()
    print(f"Received {hash}")
    if search.match(message) is None:
        return
    
    if waitPeriod == 0:
        handleMeshPacket(message, hash, interface)
    else:
        t = threading.Timer(waitPeriod, handleMeshPacket, kwargs={"message": message, "interface": interface, "hash": hash})
        t.start()
        unhandledReqs[hash] = t

def main():
    global channelIndex
    global waitPeriod
    global mqttc

    pub.subscribe(onMeshReceive, "meshtastic.receive.text")

    with open("config.json") as f:
        config = json.load(f)
        channelIndex = config["mesh_channel_index"]
        waitPeriod = config["response_delay"]

    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.on_connect = on_mqtt_connect
    mqttc.on_message = on_mqtt_message

    mqttc.username_pw_set(config["mqtt_user"], config["mqtt_pass"])

    mqttc.connect(config["mqtt_host"], config["mqtt_port"], 60)
    mqttc.loop_start()

    iface = meshtastic.tcp_interface.TCPInterface(config["mesh_address"])
    print(f"Connected to {iface.getLongName()}")
    if "alert" in config and config['alert']:
        import alerts
        alerts.begin(config, iface)
    while True:
        time.sleep(1000)
    iface.close()
    mqttc.loop_stop()


if __name__ == "__main__":
    main()