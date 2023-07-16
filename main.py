import time
import os
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import schedule
import json

from tools import check_and_download


scheduled_jobs = set()  # Track scheduled jobs


################### SETTINGS #####################
# Path to the settings file
settings_file = "settings.json"

def load_or_create_settings():
    try:
        with open(settings_file, "r") as file:
            settings = json.load(file)
    except FileNotFoundError:
        default_settings = {
            "download_dir": "C:\\Users\\Username\\Downloads\\",
            "torrent_type": ["success", "danger", "default"],
            "series_list_file": "series_list.txt",
            "poll_interval_seconds": 5,
            "torrent_quality": "1080",
            "torrent_providers_whitelist": ["nyaa.si"],
            "torrent_client": {
                "url": "http://localhost:8080/",
                "username": "admin",
                "password": "password"
            }
        }
        with open(settings_file, "w") as file:
            json.dump(default_settings, file, indent=4)
        settings = default_settings

    return settings

# Load settings
settings = load_or_create_settings()

# Now you can access the settings in your code, e.g.
download_dir = settings["download_dir"]
torrent_type = settings["torrent_type"]
series_list_file = settings["series_list_file"]
poll_interval_seconds = settings["poll_interval_seconds"]
torrent_quality = settings["torrent_quality"]
torrent_providers_whitelist = settings["torrent_providers_whitelist"]


class MyHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        print("Watching for changes to " + series_list_file)

    def on_modified(self, event):
        # Check if the modified file is anime_list.txt
        if os.path.realpath(event.src_path) == os.path.realpath(series_list_file):
            self.schedule_anime_list()

    def schedule_anime_list(self):
        # Load the new list of series
        with open(series_list_file, 'r') as file:
            series_list = file.read().splitlines()

        # Clear previous tasks
        for job in list(schedule.jobs):
            if list(job.tags)[0] not in series_list:
                schedule.cancel_job(job)


        # Schedule the script to run every 5 seconds
        for series_name in series_list:
            if series_name not in scheduled_jobs:  # Check if the job is already scheduled
                print("Scheduling " + series_name)
                scheduled_job = schedule.every(poll_interval_seconds).seconds.do(check_and_download, series_name, torrent_type, torrent_quality, download_dir, torrent_providers_whitelist)
                scheduled_job.tag(series_name)  # Tag the job with the series name
                scheduled_jobs.add(series_name)


if __name__ == "__main__":
    # Set up file event handler
    event_handler = MyHandler()

    # Initialize and schedule the anime list
    event_handler.schedule_anime_list()

    observer = PollingObserver()  # Use polling instead of default observer to reduce resource usage
    observer.schedule(event_handler, path=download_dir, recursive=False)

    # Start watching for file changes
    observer.start()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()