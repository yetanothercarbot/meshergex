import ftplib, requests, threading, time
import lxml.etree as ET

alertChannelIndex = 0
bom_warnings = []
current_fires = {}

class BomWarning():
    title = ""
    area = ""
    phenomena = ""
    issued = ""
    def __init__(self, el):
        self.title = el.xpath("//text[@type='warning_title']/p")[0].text.replace(" - Southeast Queensland", "")
        self.area = el.xpath("//text[@type='warning_area_summary']/p")[0].text
        self.phenomena = el.xpath("//text[@type='warning_phenomena_summary']/p")[0].text
        self.issued = el.xpath("//text[@type='issued_at']/p")[0].text
    def __eq__(self, value):
        return self.title == value.title == self.area == value.area and self.issued == value.issued
    def messages(self):
        return (f"{self.title} {self.phenomena}", f"{self.area} {self.issued} by BOM.")

def get_bom_warnings():
    bom_data = ""
    def append_str(dat):
        nonlocal bom_data
        bom_data += dat.decode()

    with ftplib.FTP('ftp.bom.gov.au') as ftp:
        ftp.login()
        ftp.cwd('anon/gen/fwo/')
        ftp.retrbinary("RETR IDQ21035.xml", append_str)
        ftp.quit()

    root = ET.fromstring(bytes(bom_data, encoding='utf8'))
    warnings = []

    for warn in root.xpath("//warning"):
        warnings.append(BomWarning(warn))
    
    return warnings


def push_bom_messages(iface, messages):
    iface.sendText(text = messages[0], wantAck = True, channelIndex = alertChannelIndex)
    messages.pop(0)
    if len(messages) > 0:
        t = threading.Timer(4, push_bom_messages, kwargs={"iface": iface, "messages": messages})
        t.start()
    else:
        t = threading.Timer(30*60, update_bom_warnings)
        t.start()


def update_bom_warnings(iface):
    new_warnings = get_bom_warnings()
    queued_messages = []
    for new_warning in new_warnings:
        if new_warning not in bom_warnings:
            queued_messages.append(new_warning.messages()[0])
            queued_messages.append(new_warning.messages()[1])
    
    bom_warnings = new_warnings
    push_bom_messages(iface, queued_messages)

def get_fires():
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
            if new_fires[fire_id]['lat'] < -25.81525557379747 and new_fires[fire_id]['lon'] > 151.92023048912603:
                # Add new waypoint
                additions.append(fire_id)

    current_fires = new_fires
    update_individual_fire(iface, current_fires, additions, deletions)

def update_individual_fire(iface, fires, additions, deletions):
    if len(deletions) > 0:
        iface.deleteWaypoint(waypoint_id = deletions[0], wantAck = True, channelIndex = alertChannelIndex)
        deletions.pop(0)
        t = threading.Timer(4, update_individual_fire, kwargs={"iface": iface, "fires": fires, "additions": additions, "deletions": deletions})
        t.start()
        return

    if len(additions) > 0:
        # icon 128293
        fire = fires[additions[0]]
        expiry = int(time.time() + 24*60*60)
        iface.sendWaypoint(name = fire['title'][:30], description = fire['detail'][:100], expire = expiry, waypoint_id = additions[0], latitude = fire['lat'], longitude = fire['lon'], channelIndex = alertChannelIndex)
        additions.pop(0)
        t = threading.Timer(4, update_individual_fire, kwargs={"iface": iface, "fires": fires, "additions": additions, "deletions": deletions})
        t.start()
        return

    t = threading.Timer(30*60, update_fires)
    t.start()

def begin(config, iface):
    global alertChannelIndex
    alertChannelIndex = config['alert_channel_index']
    update_bom_warnings(iface)
    update_fires(iface)
