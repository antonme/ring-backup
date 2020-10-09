import getpass
import json
import os
import time
from datetime import timezone
from pathlib import Path

from oauthlib.oauth2 import MissingTokenError
from ring_doorbell import Ring, Auth

cache_file = Path("token.cache")
videos_path = "Videos"


def token_updated(token):
    cache_file.write_text(json.dumps(token))


def otp_callback():
    auth_code = input("2FA code: ")
    return auth_code


if cache_file.is_file():
    auth = Auth("MyProject/1.0", json.loads(cache_file.read_text()), token_updated)
else:
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    auth = Auth("MyProject/1.0", None, token_updated)
    try:
        auth.fetch_token(username, password)
    except MissingTokenError:
        auth.fetch_token(username, password, otp_callback())

ring = Ring(auth)
ring.update_data()

devices = ring.devices()
file_dict = {}

for dirpath, dirnames, filenames in os.walk("Videos"):
    for filename in filenames:
        fp = dirpath + "/" + filename
        if not os.path.getmtime(fp) in file_dict and filename[len(filename) - 4:] == ".mp4":
            file_dict[os.path.getmtime(fp)] = fp

devices = ring.devices()
bell_time = 0
event_id = 0
enough = True
for doorbell in devices['doorbots']:
    # listing the last 15 events of any kind
    while True:
        if not event_id:
            events = doorbell.history(limit=30)
        else:
            events = doorbell.history(limit=30, older_than=event_id)

        for event in events:
            bell_time_orig = event['created_at']
            bell_time_orig_int = time.mktime(bell_time_orig.timetuple())

            bell_time = bell_time_orig.replace(tzinfo=timezone.utc).astimezone(tz=None)
            bell_time_str = bell_time.strftime('%Y-%m-%d %H.%M.%S')
            bell_time_log = bell_time.strftime('%Y.%m.%d %H:%M:%S')

            bell_time_int = time.mktime(bell_time.timetuple())

            subfolder = "/" + bell_time.strftime('%B %Y') + "/"

            if not os.path.exists(videos_path + subfolder):
                os.makedirs(videos_path + subfolder)

            event_id = event['id']
            vision = event['cv_properties']

            kinds = {'on_demand': 'On-demand video ',
                     'motion': 'Person video ' if vision['person_detected'] else 'Motion video ',
                     'ding': 'Ring video ' + ("(answered) " if event['answered'] else "(unanswered) ")}

            kind_str = kinds.get(event['kind'], event['kind'] + " video")

            duration = int(event['duration'])

            filename = videos_path + subfolder + kind_str + str(duration) + "s " + bell_time_str + ".mp4"

            if bell_time_int in file_dict:
                cur_name = file_dict[bell_time_int]
                if cur_name != filename:
                    enough = False
                    print(f'[{bell_time_log}] Wrong name: [{filename}]  Renaming.')
                    os.rename(cur_name, filename)
            elif not Path(filename).is_file():
                enough = False
                print(f'[{bell_time_log}]  New video: [{filename}]  Downloading...', end='')
                doorbell.recording_download(event_id, filename)
                print("done.")

            if Path(filename).is_file():
                os.utime(filename, (bell_time_int, bell_time_int))

            time.sleep(0.05)

        if len(events) == 0 or enough:
            print(f"[{bell_time_log}]  Seems like all videos are already loaded. Nothing to do here.")
            exit(0)

        time.sleep(0.2)
