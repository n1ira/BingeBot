import time
import os
import schedule
import json
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from tools import check_and_download, seek_missing_episode, seek_newest_episode

# default settings
DEFAULT_SETTINGS = {
    "download_dir": "C:\\Users\\Username\\Downloads\\",
    "torrent_type": ["success", "danger", "default"],
    "series_list_file": "series_list.txt",
    "poll_interval_seconds": 5,
    "will_seek_missing_episodes": False,
    "seek_missing_episodes_interval_seconds": 10,
    "will_seek_newest_episode": True,
    "seek_newest_episode_interval_seconds": 10,
    "torrent_quality": "1080",
    "torrent_providers_whitelist": ["nyaa.si"],
    "torrent_client": {
        "url": "http://localhost:8080/",
        "username": "admin",
        "password": "password"
    }
}

# constant for settings file
SETTINGS_FILE = "settings.json"

def load_or_create_settings():
    """
    Helper function to load or create the settings.
    """
    try:
        with open(SETTINGS_FILE, "r") as file:
            settings = json.load(file)
    except FileNotFoundError:
        with open(SETTINGS_FILE, "w") as file:
            json.dump(DEFAULT_SETTINGS, file, indent=4)
        settings = DEFAULT_SETTINGS

    return settings

def schedule_series_list(settings, scheduled_jobs):
    """
    Helper function to schedule series list.
    """
    # Load the new list of series if it exists
    if not os.path.exists(settings["series_list_file"]):
        # If not, create it and write the sample text
        with open(settings["series_list_file"], 'w') as file:
            file.write("Serial Experiments Lain\n")

    # Load the list of series
    with open(settings["series_list_file"], 'r') as file:
        series_list = file.read().splitlines()

    # Clear previous tasks
    for job in list(schedule.jobs):
        if list(job.tags)[0] not in series_list:
            schedule.cancel_job(job)

    # Schedule the script to run every 5 seconds
    for series_name in series_list:
        if series_name not in scheduled_jobs:  # Check if the job is already scheduled
            scheduled_job = schedule.every(settings["poll_interval_seconds"]).seconds.do(
                check_and_download, series_name, settings["torrent_type"], settings["torrent_quality"], 
                settings["download_dir"], settings["torrent_providers_whitelist"])
            scheduled_job.tag(series_name)  # Tag the job with the series name
            scheduled_jobs.add(series_name)
            
            if settings["will_seek_missing_episodes"]:
                # Schedule seeking for missing episodes
                schedule.every(settings["seek_missing_episodes_interval_seconds"]).seconds.do(
                    seek_missing_episode, series_name, settings["torrent_type"], 
                    settings["torrent_quality"], settings["download_dir"])

            if settings["will_seek_newest_episode"]:
                # Schedule seeking for newest episode
                schedule.every(settings["seek_newest_episode_interval_seconds"]).seconds.do(
                    seek_newest_episode, series_name, settings["torrent_type"], 
                    settings["torrent_quality"], settings["download_dir"])

class MyHandler(FileSystemEventHandler):
    def __init__(self, settings, scheduled_jobs):
        super().__init__()
        self.settings = settings
        self.scheduled_jobs = scheduled_jobs

    def on_modified(self, event):
        # Check if the modified file is series_list.txt
        if os.path.realpath(event.src_path) == os.path.realpath(self.settings["series_list_file"]):
            schedule_series_list(self.settings, self.scheduled_jobs)

    def schedule_series_list(settings, scheduled_jobs):
        """
        Schedules the series list.
        """
        # Load the new list of series
        with open(settings["series_list_file"], 'r') as file:
            series_list = file.read().splitlines()

        # Clear previous tasks
        for job in list(schedule.jobs):
            if list(job.tags)[0] not in series_list:
                schedule.cancel_job(job)

        # Schedule the script to run at the specified intervals
        for series_name in series_list:
            if series_name not in scheduled_jobs:  # Check if the job is already scheduled
                scheduled_job = schedule.every(settings["poll_interval_seconds"]).seconds.do(
                    check_and_download, series_name, settings["torrent_type"], settings["torrent_quality"], 
                    settings["download_dir"], settings["torrent_providers_whitelist"])
                scheduled_job.tag(series_name)  # Tag the job with the series name
                scheduled_jobs.add(series_name)
                
                if settings["will_seek_missing_episodes"]:
                    # Schedule seeking for missing episodes
                    schedule.every(settings["seek_missing_episodes_interval_seconds"]).seconds.do(
                        seek_missing_episode, series_name, settings["torrent_type"], 
                        settings["torrent_quality"], settings["download_dir"])

                if settings["will_seek_newest_episode"]:
                    # Schedule seeking for newest episode
                    schedule.every(settings["seek_newest_episode_interval_seconds"]).seconds.do(
                        seek_newest_episode, series_name, settings["torrent_type"], 
                        settings["torrent_quality"], settings["download_dir"])


if __name__ == "__main__":
    settings = load_or_create_settings()
    scheduled_jobs = set()  # Track scheduled jobs

    # Set up file event handler
    event_handler = MyHandler(settings, scheduled_jobs)

    # Initialize and schedule the series list
    schedule_series_list(settings, scheduled_jobs)

    observer = PollingObserver()  # Use polling instead of default observer to reduce resource usage
    observer.schedule(event_handler, path=settings["download_dir"], recursive=False)

    # Start watching for file changes
    observer.start()

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()