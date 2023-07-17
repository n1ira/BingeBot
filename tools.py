# import necessary modules
import requests
from bs4 import BeautifulSoup
import re
import os
import json
from urllib.parse import quote
from qbittorrent import Client
import threading
import colorlog
import logging

# Create a logger
logger = colorlog.getLogger()
logger.setLevel(logging.DEBUG)

# Create a console handler
handler = colorlog.StreamHandler()

# Set a format for the handler
handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)-8s%(reset)s %(message)s"))

# Add the handler to the logger
logger.addHandler(handler)



# constant for torrent site URL
NYAA_URL = "https://nyaa.si/?f=0&c=0_0&q="
NYAA_URL_NO_EPISODE = "https://nyaa.si/?f=0&c=1_2&q="


# lock for downloads
download_lock = threading.Lock()

def get_url(series_name, episode_number=None):
    """
    Helper function to generate the URL for the torrent site.
    """
    if episode_number is not None:
        return NYAA_URL + quote(series_name + ' ' + str(episode_number)) + "&s=seeders&o=desc"
    else:
        return NYAA_URL_NO_EPISODE + quote(series_name) + "&s=seeders&o=desc"


from requests.exceptions import ConnectionError
from halo import Halo

def get_torrents(url, torrent_type):
    """
    Helper function to get a list of torrents from the torrent site.
    """
    spinner = Halo(text='Loading', spinner='dots')
    spinner.start()

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except (requests.Timeout, ConnectionError):
        spinner.stop()
        logger.error(f"Error occurred while fetching data from {url}")
        return []
    
    spinner.stop()

    soup = BeautifulSoup(response.text, 'html.parser')
    torrents = soup.find_all('tr', class_=torrent_type)
    return torrents



def get_episode_data(torrent, torrent_quality):
    """
    Helper function to extract episode data from a torrent.
    """
    # Find title and magnet link
    title_element = torrent.find_all('td')[1].find('a', href=lambda href: href and "#comments" not in href)
    magnet_link = torrent.find('a', href=lambda href: href and 'magnet:' in href)['href']

    if title_element is not None:
        title = title_element.text
        episode_number = extract_episode_number(title, torrent_quality)
        return (episode_number, title, magnet_link)
    else:
        return None


def extract_episode_number(title, torrent_quality):
    """
    Helper function to extract the episode number from a title.
    """
    episode_number = None

    # Check if episode title is in format 'S01E01'
    episode_match_1 = re.search(r'S\d+E(\d+)', title)
    # Look for episode number that comes after a hyphen
    episode_match_2 = re.search(r' - (\d+)', title)

    is_bd = re.search(r'\[BD\]', title, re.IGNORECASE)
    is_movie = re.search(r'movie', title, re.IGNORECASE)

    if is_movie or is_bd:
        return 1
    elif episode_match_1:
        temp_episode_number = int(episode_match_1.group(1))
        if temp_episode_number == int(torrent_quality):
            episode_number = 1
        else:
            episode_number = temp_episode_number
    elif episode_match_2:
        temp_episode_number = int(episode_match_2.group(1))
        if temp_episode_number == int(torrent_quality):
            episode_number = 1
        else:
            episode_number = temp_episode_number

    return episode_number

def get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, download_dir, episode_number=None):
    """
    Fetches the newest episodes from the torrent site.
    """
    url = get_url(series_name, episode_number)
    torrents = get_torrents(url, torrent_type)

    # Extract episode numbers and links
    episodes = {}
    for torrent in torrents:
        episode_data = get_episode_data(torrent, torrent_quality)
        if episode_data is not None:
            episode_number, title, magnet_link = episode_data
            if episode_number and torrent_quality in title and not is_episode_downloaded(series_name, episode_number, download_dir):
                if episode_number > episodes_after and episode_number is not torrent_quality:
                    logger.info(f"Found episode {episode_number} of {series_name}")
                    # Keep only the highest-seeded version of each episode
                    if episode_number not in episodes:
                        episodes[episode_number] = magnet_link

    # Sort by episode number and convert to list
    episodes = sorted(episodes.items(), key=lambda x: x[0], reverse=True)

    return episodes

def load_downloaded_episodes(download_dir):
    """
    Helper function to load downloaded episodes from a JSON file.
    """
    try:
        with open(os.path.join(download_dir, "downloaded_episodes.json"), "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def get_missing_episodes(base_series_name, starting_episode, downloaded_episodes):
    """
    Helper function to get missing episodes.
    """
    max_episode_number = max(downloaded_episodes[base_series_name]) if downloaded_episodes[base_series_name] else 0

    # Adjust the range of episodes considering the starting episode
    complete_episodes = list(range(starting_episode, max_episode_number + 1))

    missing_episodes = list(set(complete_episodes) - set(downloaded_episodes[base_series_name]))

    if not missing_episodes:
        logger.info(f"No missing episodes found for {base_series_name}")

    return missing_episodes

def seek_missing_episode(series_name, torrent_type, torrent_quality, download_dir):
    """
    Seeks for missing episodes and download them.
    """
    # Extract the base series name and starting episode
    base_series_name, starting_episode = split_series_name(series_name)
    starting_episode = int(starting_episode) + 1

    downloaded_episodes = load_downloaded_episodes(download_dir)

    if base_series_name not in downloaded_episodes:
        logger.error(f"{base_series_name} not found in downloaded_episodes")
        # create empty list for series and update downloaded_episodes.json
        downloaded_episodes[base_series_name] = []
        with open(os.path.join(download_dir, "downloaded_episodes.json"), "w") as file:
            json.dump(downloaded_episodes, file, sort_keys=True, indent=4)
        logger.info(f"Created entry in downloaded_episodes for {base_series_name}")
        return

    missing_episodes = get_missing_episodes(base_series_name, starting_episode, downloaded_episodes)

    if missing_episodes:
        logger.info(f"Missing episodes for {base_series_name} are: {missing_episodes}")

        for missing_episode in missing_episodes:
            logger.info(f"Looking for episode {missing_episode} of {base_series_name}")

            newest_episodes = get_newest_episodes_nyaa(base_series_name, torrent_type, missing_episode, torrent_quality, download_dir, missing_episode)

            if newest_episodes:
                logger.info(f"Found episode {missing_episode} of {base_series_name}")

                series_dir = os.path.join(download_dir, base_series_name)
                create_dir_if_not_exists(series_dir)

                magnet_links = [episode[1] for episode in newest_episodes]
                add_torrent_to_qbittorrent(magnet_links, series_dir)

                for episode in newest_episodes:
                    mark_episode_as_downloaded(base_series_name, episode[0], download_dir)
            else:
                logger.debug(f"Episode {missing_episode} of {base_series_name} not found on nyaa.si")


def seek_newest_episode(series_name, torrent_type, torrent_quality, download_dir):
    """
    Seeks and downloads the newest episode.
    """
    # Extract the base series name and starting episode
    base_series_name, starting_episode = split_series_name(series_name)
    starting_episode = int(starting_episode) + 1

    downloaded_episodes = load_downloaded_episodes(download_dir)

    if base_series_name not in downloaded_episodes:
        logger.error(f"{base_series_name} not found in downloaded_episodes")
        # create empty list for series and update downloaded_episodes.json
        downloaded_episodes[base_series_name] = []
        with open(os.path.join(download_dir, "downloaded_episodes.json"), "w") as file:
            json.dump(downloaded_episodes, file, sort_keys=True, indent=4)
        logger.info(f"Created entry in downloaded_episodes for {base_series_name}")
        return

    # Get the max episode number, skip if no episodes have been downloaded
    max_episode_number = max(downloaded_episodes[base_series_name]) if downloaded_episodes[base_series_name] else 0

    # Seek for the next episode considering the starting episode
    next_episode = max(max_episode_number + 1, starting_episode)

    logger.info(f"Seeking episode {next_episode} of {base_series_name}")

    newest_episodes = get_newest_episodes_nyaa(base_series_name, torrent_type, next_episode, torrent_quality, download_dir, next_episode)

    if newest_episodes:
        logger.info(f"Found episode {next_episode} of {base_series_name}")

        series_dir = os.path.join(download_dir, base_series_name)
        create_dir_if_not_exists(series_dir)

        magnet_links = [episode[1] for episode in newest_episodes]
        add_torrent_to_qbittorrent(magnet_links, series_dir)

        for episode in newest_episodes:
            mark_episode_as_downloaded(base_series_name, episode[0], download_dir)
    else:
        logger.debug(f"Episode {next_episode} of {base_series_name} not found on nyaa.si")


def check_and_download(series_name_and_episodes_after, torrent_type, torrent_quality, download_dir, torrent_providers_whitelist):
    """
    Checks and downloads the new episodes.
    """
    series_name, episodes_after = split_series_name(series_name_and_episodes_after)

    series_name = series_name.strip()

    with download_lock:
        logger.info(f"Checking for new episodes of {series_name}")

        if "nyaa.si" in torrent_providers_whitelist:
            newest_episodes = get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, download_dir)
        else:
            logger.error(f"Nyaa.si not in whitelist, skipping {series_name}")

        if newest_episodes:
            series_dir = os.path.join(download_dir, series_name)
            create_dir_if_not_exists(series_dir)

            magnet_links = [episode[1] for episode in newest_episodes]
            add_torrent_to_qbittorrent(magnet_links, series_dir)

            for episode in newest_episodes:
                mark_episode_as_downloaded(series_name, episode[0], download_dir)


def mark_episode_as_downloaded(series_name, episode_number, download_dir):
    print("Marking episode " + str(episode_number) + " of " + series_name + " as downloaded")

    downloaded_episodes = load_downloaded_episodes(download_dir)

    # If series not in dictionary, add an empty list
    if series_name not in downloaded_episodes:
        downloaded_episodes[series_name] = []

    # Add the episode to the series list
    downloaded_episodes[series_name].append(episode_number)

    # Write the dictionary back to the file
    with open(download_dir + "downloaded_episodes.json", "w") as file:
        json.dump(downloaded_episodes, file, sort_keys=True, indent=4)

def add_torrent_to_qbittorrent(magnet_links, savepath):
    print("Adding torrents to qBittorrent")

    qb = Client('http://localhost:8080/')
    # getting the credentials from the settings file
    with open("settings.json", "r") as file:
        settings = json.load(file)
    qb_username = settings["torrent_client"]["username"]
    qb_password = settings["torrent_client"]["password"]
    qb.login(qb_username, qb_password)
    qb.download_from_link(magnet_links, savepath=savepath)


def create_dir_if_not_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)

def split_series_name(series_name):
    """
    Splits the series_name into base_series_name and starting_episode
    """
    if ":" in series_name:
        base_series_name, starting_episode = series_name.split(":")
        return base_series_name, int(starting_episode)
    else:
        return series_name, 0

def is_episode_downloaded(series_name, episode_number, download_dir):
    downloaded_episodes = load_downloaded_episodes(download_dir)

    if series_name in downloaded_episodes:
        # Return True if the episode has been downloaded before
        return episode_number in downloaded_episodes[series_name]
    else:
        return False