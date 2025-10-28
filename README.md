# Meshergex

Interviewing Energex outages for Meshtastic participants.

## Setup
Set up a python venv and install dependencies:

```sh
python3 -m venv venv
. venv/bin/activate
pip3 install -r requirements.txt
```

Copy the example config file and then fill it out:

```sh
cp config.json.example config.json
```

You will need to fill out each of the blank fields. Most fields should be self-explanatory, except:

- The `response_delay` field determines how long the script will wait before deciding to reply; this is used for the fail-over and should only be left at 0 for the primary bot.
- The `mesh_channel_index` field specifies in which channel slot to reply. This is 0-indexed, so your primary channel is 0, the first secondary channel is in 1, and so on.
- The `mesh_address` field specifies where to find the Meshtastic node. This should be `localhost` for Femtofox devices or the IP address otherwise.

Whilst the script should not crash, you may wish to use pm2 to ensure it is restarted after a crash and after a reboot:

```sh
pm2 start --name meshergex --interpreter $(pwd)/venv/bin/python3 $(pwd)/main.py
```

Otherwise, you may set it up as a systemd service or simply run it manually.