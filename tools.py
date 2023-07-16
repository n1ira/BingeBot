import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
from qbittorrent import Client
import os
import json


def get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, download_dir, episode_number=None):
    # Add episode_number to the url if it is specified
    if episode_number is not None:
        url = "https://nyaa.si/?f=0&c=0_0&q=" + quote(series_name + ' ' + str(episode_number)) + "&s=seeders&o=desc"
    else:
        url = "https://nyaa.si/?f=0&c=1_2&q=" + quote(series_name) + "&s=seeders&o=desc"

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all torrents
    torrents = soup.find_all('tr', class_=torrent_type)

    # Extract episode numbers and links
    episodes = {}
    for torrent in torrents:
        title_element = torrent.find_all('td')[1].find('a', href=lambda href: href and "#comments" not in href)
        if title_element is not None:
            title = title_element.text
            magnet_link = torrent.find('a', href=lambda href: href and 'magnet:' in href)['href']
            
            # Initialize episode_number to None
            episode_number = None

            # Check if episode title is in format 'S01E01'
            episode_match = re.search(r'S\d+E(\d+)', title)
            if episode_match:
                episode_number = int(episode_match.group(1))
                # print("Looking for format S01E01, found " + str(episode_number) + " in " + title)

            # Look for episode number that comes after a hyphen 
            elif not episode_match:
                episode_match = re.search(r' - (\d+)', title)
                episode_number = int(episode_match.group(1)) if episode_match else None
                if episode_number == torrent_quality:
                    episode_number = None
                    print("Episode number is the quality, skipping " + title)
            
            # Check for torrent quality and if episode has not been downloaded before
            if episode_number and torrent_quality in title:
                if not is_episode_downloaded(series_name, episode_number, download_dir):
                    if episode_number > episodes_after:
                        print("Found episode " + str(episode_number) + " of " + series_name)

                        # Keep only the highest-seeded version of each episode
                        if episode_number not in episodes:
                            episodes[episode_number] = magnet_link

    # Sort by episode number and convert to list
    episodes = sorted(episodes.items(), key=lambda x: x[0], reverse=True)

    return episodes


################### SEEKERS #####################

def seek_missing_episode(series_name, torrent_type, torrent_quality, download_dir):
    # Extract the base series name and starting episode
    base_series_name, starting_episode = split_series_name(series_name)
    starting_episode = int(starting_episode) + 1

    downloaded_episodes = load_downloaded_episodes(download_dir)

    if base_series_name not in downloaded_episodes:
        print(base_series_name + " not found in downloaded_episodes")
        return

    max_episode_number = max(downloaded_episodes[base_series_name])
    
    # Adjust the range of episodes considering the starting episode
    complete_episodes = list(range(starting_episode, max_episode_number + 1))

    missing_episodes = list(set(complete_episodes) - set(downloaded_episodes[base_series_name]))

    if not missing_episodes:
        print("No missing episodes found for " + base_series_name)
        return

    print("Missing episodes for " + base_series_name + " are: " + str(missing_episodes))

    for missing_episode in missing_episodes:
        print("Looking for episode " + str(missing_episode) + " of " + base_series_name)

        newest_episodes = get_newest_episodes_nyaa(base_series_name, torrent_type, missing_episode, torrent_quality, download_dir, missing_episode)

        if newest_episodes:
            print("Found episode " + str(missing_episode) + " of " + base_series_name)

            series_dir = os.path.join(download_dir, base_series_name)
            create_dir_if_not_exists(series_dir)

            magnet_links = [episode[1] for episode in newest_episodes]
            add_torrent_to_qbittorrent(magnet_links, series_dir)

            for episode in newest_episodes:
                mark_episode_as_downloaded(base_series_name, episode[0], download_dir)
        else:
            print("Episode " + str(missing_episode) + " of " + base_series_name + " not found on nyaa.si")

def seek_newest_episode(series_name, torrent_type, torrent_quality, download_dir):
    # Extract the base series name and starting episode
    base_series_name, starting_episode = split_series_name(series_name)
    starting_episode = int(starting_episode) + 1

    downloaded_episodes = load_downloaded_episodes(download_dir)

    if base_series_name not in downloaded_episodes:
        print(base_series_name + " not found in downloaded_episodes")
        return

    max_episode_number = max(downloaded_episodes[base_series_name])

    # Seek for the next episode considering the starting episode
    next_episode = max(max_episode_number + 1, starting_episode)

    print("Seeking episode " + str(next_episode) + " of " + base_series_name)

    newest_episodes = get_newest_episodes_nyaa(base_series_name, torrent_type, next_episode, torrent_quality, download_dir, next_episode)

    if newest_episodes:
        print("Found episode " + str(next_episode) + " of " + base_series_name)

        series_dir = os.path.join(download_dir, base_series_name)
        create_dir_if_not_exists(series_dir)

        magnet_links = [episode[1] for episode in newest_episodes]
        add_torrent_to_qbittorrent(magnet_links, series_dir)

        for episode in newest_episodes:
            mark_episode_as_downloaded(base_series_name, episode[0], download_dir)
    else:
        print("Episode " + str(next_episode) + " of " + base_series_name + " not found on nyaa.si")


################### DOWNLOADS HANDLING #####################
def load_downloaded_episodes(download_dir):
    try:
        with open(download_dir + "downloaded_episodes.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def is_episode_downloaded(series_name, episode_number, download_dir):
    downloaded_episodes = load_downloaded_episodes(download_dir)

    if series_name in downloaded_episodes:
        # Return True if the episode has been downloaded before
        return episode_number in downloaded_episodes[series_name]
    else:
        return False

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
    qb.login('admin', 'grant123')
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

import threading
download_lock = threading.Lock()
def check_and_download(series_name_and_episodes_after, torrent_type, torrent_quality, download_dir, torrent_providers_whitelist):
    series_name, episodes_after = split_series_name(series_name_and_episodes_after)

    series_name = series_name.strip()

    with download_lock:
        print("Checking for new episodes of " + series_name)

        if "nyaa.si" in torrent_providers_whitelist:
            newest_episodes = get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, download_dir)
        else:
            print("Nyaa.si not in whitelist, skipping " + series_name)

        if newest_episodes:
            series_dir = os.path.join(download_dir, series_name)
            create_dir_if_not_exists(series_dir)

            magnet_links = [episode[1] for episode in newest_episodes]
            add_torrent_to_qbittorrent(magnet_links, series_dir)

            for episode in newest_episodes:
                mark_episode_as_downloaded(series_name, episode[0], download_dir)