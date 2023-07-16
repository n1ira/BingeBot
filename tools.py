import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
from qbittorrent import Client
import os
import json


def get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, anime_dir):
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
            
            # Look for episode number that comes after a hyphen 
            episode_number = re.search(r'(?<=-)\s*\d+', title)
            # Check if episode number is the quality (e.g. 1080p)
            if episode_number and episode_number.group().strip() == torrent_quality:
                episode_number = None
            # Check if episode title is in format 'S01E01'
            if not episode_number:
                episode_number = re.search(r'(?<=S)\d+(?=E)', title)
            
            # Check for torrent quality and if episode has not been downloaded before
            if episode_number and torrent_quality in title and not is_episode_downloaded(series_name, int(episode_number.group().strip()), anime_dir):
                episode_number = int(episode_number.group().strip())
                if episode_number > episodes_after:
                    print("Found episode " + str(episode_number) + " of " + series_name)

                    # Keep only the highest-seeded version of each episode
                    if episode_number not in episodes:
                        episodes[episode_number] = magnet_link

    # Sort by episode number and convert to list
    episodes = sorted(episodes.items(), key=lambda x: x[0], reverse=True)

    return episodes


def load_downloaded_episodes(anime_dir):
    try:
        with open(anime_dir + "downloaded_episodes.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def is_episode_downloaded(series_name, episode_number, anime_dir):
    downloaded_episodes = load_downloaded_episodes(anime_dir)

    if series_name in downloaded_episodes:
        # Return True if the episode has been downloaded before
        return episode_number in downloaded_episodes[series_name]
    else:
        return False

def mark_episode_as_downloaded(series_name, episode_number, anime_dir):
    print("Marking episode " + str(episode_number) + " of " + series_name + " as downloaded")

    downloaded_episodes = load_downloaded_episodes(anime_dir)

    # If series not in dictionary, add an empty list
    if series_name not in downloaded_episodes:
        downloaded_episodes[series_name] = []

    # Add the episode to the series list
    downloaded_episodes[series_name].append(episode_number)

    # Write the dictionary back to the file
    with open(anime_dir + "downloaded_episodes.json", "w") as file:
        json.dump(downloaded_episodes, file, sort_keys=True, indent=4)


def add_torrent_to_qbittorrent(magnet_links, savepath):
    print("Adding torrents to qBittorrent")

    qb = Client('http://localhost:8080/')
    qb.login('admin', 'grant123')
    qb.download_from_link(magnet_links, savepath=savepath)


def create_dir_if_not_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)

import threading
download_lock = threading.Lock()
def check_and_download(series_name_and_episodes_after, torrent_type, torrent_quality, anime_dir, torrent_providers_whitelist):
    if ":" in series_name_and_episodes_after:
        series_name, episodes_after = series_name_and_episodes_after.split(":")
        episodes_after = int(episodes_after.strip())
    else:
        series_name = series_name_and_episodes_after
        episodes_after = 0

    series_name = series_name.strip()

    with download_lock:
        print("Checking for new episodes of " + series_name)

        if "nyaa.si" in torrent_providers_whitelist:
            newest_episodes = get_newest_episodes_nyaa(series_name, torrent_type, episodes_after, torrent_quality, anime_dir)
        else:
            print("Nyaa.si not in whitelist, skipping " + series_name)

        if newest_episodes:
            series_dir = os.path.join(anime_dir, series_name)
            create_dir_if_not_exists(series_dir)

            magnet_links = [episode[1] for episode in newest_episodes]
            add_torrent_to_qbittorrent(magnet_links, series_dir)

            for episode in newest_episodes:
                mark_episode_as_downloaded(series_name, episode[0], anime_dir)
