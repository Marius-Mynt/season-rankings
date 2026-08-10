"""
🎮 Smash Tournament Season Rankings
A Streamlit app for tracking and analyzing tournament results
Version 4.0 - With character tracking and seasons management
"""

import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import io
import base64
from collections import defaultdict

# Page config
st.set_page_config(
    page_title="Season Rankings",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# GITHUB STORAGE
# =============================================================================

DATA_FILE_PATH = "data/tournaments.json"

def get_github_config():
    """Get GitHub configuration from secrets"""
    return {
        "token": st.secrets.get("GITHUB_TOKEN", ""),
        "repo": st.secrets.get("GITHUB_REPO", ""),
    }

def load_data_from_github():
    """Load tournament data from GitHub repository"""
    config = get_github_config()
    
    if not config["repo"]:
        st.warning("⚠️ GitHub repo not configured. Data will not persist!")
        return get_empty_data()
    
    # For public repos, try reading WITHOUT authentication first (more reliable)
    # Use raw.githubusercontent.com which doesn't need API auth
    raw_url = f"https://raw.githubusercontent.com/{config['repo']}/main/{DATA_FILE_PATH}"
    
    try:
        # First, try the raw URL (works for public repos, no auth needed)
        response = requests.get(raw_url, timeout=10)
        
        if response.status_code == 200:
            try:
                data = json.loads(response.text)
                st.session_state["github_load_status"] = "success (raw)"
                # We still need the SHA for updates, so fetch it separately
                _fetch_sha_only(config)
                # Ensure new fields exist
                if "seasons" not in data:
                    data["seasons"] = []
                if "active_season" not in data:
                    data["active_season"] = None
                if "character_names" not in data:
                    data["character_names"] = {}
                return data
            except json.JSONDecodeError as e:
                st.session_state["github_load_status"] = f"json_error: {str(e)}"
        elif response.status_code == 404:
            # File doesn't exist yet
            st.session_state["github_load_status"] = "new"
            return get_empty_data()
        else:
            # Raw URL failed, try API method as fallback
            st.session_state["github_load_status"] = f"raw_failed_{response.status_code}, trying API..."
    except Exception as e:
        st.session_state["github_load_status"] = f"raw_exception: {str(e)}"
    
    # Fallback: try the GitHub API with authentication
    if config.get("token"):
        return _load_data_via_api(config)
    
    st.error("Could not load data from GitHub.")
    return get_empty_data()

def _fetch_sha_only(config):
    """Fetch just the SHA for the file (needed for updates)"""
    if not config.get("token"):
        return
    
    url = f"https://api.github.com/repos/{config['repo']}/contents/{DATA_FILE_PATH}"
    headers = {
        "Authorization": f"token {config['token']}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            content = response.json()
            st.session_state["github_sha"] = content.get("sha")
    except:
        pass  # SHA fetch failed, will get it on next save

def _load_data_via_api(config):
    """Load data via GitHub API (fallback method)"""
    url = f"https://api.github.com/repos/{config['repo']}/contents/{DATA_FILE_PATH}"
    headers = {
        "Authorization": f"token {config['token']}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        rate_limit_remaining = response.headers.get('X-RateLimit-Remaining', 'unknown')
        
        if response.status_code == 200:
            if not response.text or response.text.strip() == "":
                st.session_state["github_load_status"] = "api_empty_response"
                return get_empty_data()
            
            try:
                content = response.json()
            except json.JSONDecodeError as e:
                st.session_state["github_load_status"] = f"api_json_error: {str(e)}"
                return get_empty_data()
            
            file_content = base64.b64decode(content["content"]).decode("utf-8")
            data = json.loads(file_content)
            st.session_state["github_sha"] = content["sha"]
            st.session_state["github_load_status"] = "success (api)"
            st.session_state["github_rate_limit"] = rate_limit_remaining
            
            if "seasons" not in data:
                data["seasons"] = []
            if "active_season" not in data:
                data["active_season"] = None
            if "character_names" not in data:
                data["character_names"] = {}
            return data
        elif response.status_code == 404:
            st.session_state["github_load_status"] = "new"
            return get_empty_data()
        else:
            st.session_state["github_load_status"] = f"api_error_{response.status_code}"
            return get_empty_data()
    except Exception as e:
        st.session_state["github_load_status"] = f"api_exception: {str(e)}"
        return get_empty_data()
        return get_empty_data()

def save_data_to_github(data):
    """Save tournament data to GitHub repository"""
    config = get_github_config()
    
    if not config["token"] or not config["repo"]:
        st.warning("⚠️ GitHub storage not configured. Data will not persist!")
        return False
    
    url = f"https://api.github.com/repos/{config['repo']}/contents/{DATA_FILE_PATH}"
    headers = {
        "Authorization": f"token {config['token']}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    content = json.dumps(data, indent=2, ensure_ascii=False)
    content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    
    body = {
        "message": f"Update rankings data - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_base64,
    }
    
    if "github_sha" in st.session_state:
        body["sha"] = st.session_state["github_sha"]
    
    try:
        response = requests.put(url, headers=headers, json=body)
        
        if response.status_code in [200, 201]:
            st.session_state["github_sha"] = response.json()["content"]["sha"]
            return True
        else:
            st.error(f"GitHub save error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        st.error(f"Error saving to GitHub: {str(e)}")
        return False

def get_empty_data():
    """Return empty data structure"""
    return {
        "tournaments": [],
        "settings": get_default_settings(),
        "player_aliases": {},
        "seasons": [],
        "active_season": None,
        "character_names": {}  # {character_id: "Character Name"}
    }

def get_default_settings():
    """Default ranking settings"""
    return {
        "points": {
            "1": 100, "2": 70, "3": 50, "4": 40,
            "5": 30, "7": 20, "9": 10, "13": 5, "17": 2
        },
        "attendance_scaling": False,
        "scaling_base": 32,
        "best_n_enabled": False,
        "best_n": 6,
        "drop_worst": False,
        "min_tournaments": 1,
        "characters_enabled": True  # Toggle for character features
    }

def load_data():
    """Load data, using session state if available"""
    if "app_data" not in st.session_state:
        st.session_state["app_data"] = load_data_from_github()
    return st.session_state["app_data"]

def save_data(data):
    """Save data and update session state"""
    st.session_state["app_data"] = data
    return save_data_to_github(data)

def refresh_data():
    """Force refresh data from GitHub"""
    st.session_state["app_data"] = load_data_from_github()
    return st.session_state["app_data"]

# =============================================================================
# SEASON MANAGEMENT
# =============================================================================

def get_active_tournaments(data):
    """Get tournaments for the active season, or all if no season active"""
    active_season_id = data.get("active_season")
    
    if not active_season_id:
        return data["tournaments"]
    
    # Find the active season
    for season in data.get("seasons", []):
        if season["id"] == active_season_id:
            tournament_ids = season.get("tournament_ids", [])
            return [t for t in data["tournaments"] if t["tournament"]["id"] in tournament_ids]
    
    return data["tournaments"]

def create_season(data, name: str, tournament_ids: list) -> dict:
    """Create a new season"""
    season = {
        "id": f"season_{int(datetime.now().timestamp())}",
        "name": name,
        "created_at": datetime.now().isoformat(),
        "tournament_ids": tournament_ids,
        "archived": False,
        "final_rankings": None  # Will be populated when archived
    }
    
    if "seasons" not in data:
        data["seasons"] = []
    
    data["seasons"].append(season)
    return season

def archive_season(data, season_id: str, registry: dict):
    """Archive a season with final rankings"""
    for season in data.get("seasons", []):
        if season["id"] == season_id:
            # Calculate final rankings
            season_tournaments = [
                t for t in data["tournaments"]
                if t["tournament"]["id"] in season.get("tournament_ids", [])
            ]
            
            settings = data.get("settings", get_default_settings())
            df = calculate_rankings(season_tournaments, settings, registry, data.get("character_names", {}))
            
            # Store as list of dicts
            season["final_rankings"] = df.to_dict('records') if not df.empty else []
            season["archived"] = True
            season["archived_at"] = datetime.now().isoformat()
            
            # If this was the active season, clear it
            if data.get("active_season") == season_id:
                data["active_season"] = None
            
            return True
    return False

# =============================================================================
# CHARACTER TRACKING
# =============================================================================

# Built-in SSBU character list as fallback (if API doesn't provide it)
# Based on Start.gg's known character IDs for Super Smash Bros. Ultimate
SSBU_CHARACTERS_BUILTIN = {
    "1271": "Mario",
    "1272": "Donkey Kong",
    "1273": "Link",
    "1274": "Samus",
    "1275": "Dark Samus",
    "1276": "Yoshi",
    "1277": "Kirby",
    "1278": "Fox",
    "1279": "Pikachu",
    "1280": "Luigi",
    "1281": "Ness",
    "1282": "Captain Falcon",
    "1283": "Jigglypuff",
    "1284": "Peach",
    "1285": "Daisy",
    "1286": "Bowser",
    "1287": "Ice Climbers",
    "1288": "Sheik",
    "1289": "Zelda",
    "1290": "Dr. Mario",
    "1291": "Pichu",
    "1292": "Falco",
    "1293": "Marth",
    "1294": "Lucina",
    "1295": "Young Link",
    "1296": "Ganondorf",
    "1297": "Mewtwo",
    "1298": "Roy",
    "1299": "Chrom",
    "1300": "Mr. Game & Watch",
    "1301": "Meta Knight",
    "1302": "Pit",
    "1303": "Dark Pit",
    "1304": "Zero Suit Samus",
    "1305": "Wario",
    "1306": "Snake",
    "1307": "Ike",
    "1308": "Pokemon Trainer",
    "1309": "Diddy Kong",
    "1310": "Lucas",
    "1311": "Sonic",
    "1312": "King Dedede",
    "1313": "Olimar",
    "1314": "Lucario",
    "1315": "R.O.B.",
    "1316": "Toon Link",
    "1317": "Wolf",
    "1318": "Villager",
    "1319": "Mega Man",
    "1320": "Wii Fit Trainer",
    "1321": "Rosalina & Luma",
    "1322": "Little Mac",
    "1323": "Greninja",
    "1324": "Mii Brawler",
    "1325": "Mii Swordfighter",
    "1326": "Mii Gunner",
    "1327": "Palutena",
    "1328": "Pac-Man",
    "1329": "Robin",
    "1330": "Shulk",
    "1331": "Bowser Jr.",
    "1332": "Duck Hunt",
    "1333": "Ryu",
    "1334": "Ken",
    "1335": "Cloud",
    "1336": "Corrin",
    "1337": "Bayonetta",
    "1338": "Inkling",
    "1339": "Ridley",
    "1340": "Simon",
    "1341": "Richter",
    "1342": "King K. Rool",
    "1343": "Isabelle",
    "1344": "Incineroar",
    "1345": "Piranha Plant",
    "1346": "Joker",
    "1347": "Hero",
    "1348": "Banjo & Kazooie",
    "1349": "Terry",
    "1350": "Byleth",
    "1351": "Min Min",
    "1352": "Steve",
    "1353": "Sephiroth",
    "1354": "Pyra/Mythra",
    "1355": "Kazuya",
    "1356": "Sora",
    # Alternative IDs that might be used
    "1405": "Random",
}

def fetch_character_list_from_startgg(api_token: str, videogame_id: int = 1386) -> tuple:
    """
    Fetch character names from Start.gg API for a specific videogame.
    Default videogame_id 1386 = Super Smash Bros. Ultimate
    
    Returns: (character_dict, error_message)
    """
    url = "https://api.start.gg/gql/alpha"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # Try multiple query formats
    queries = [
        # Format 1: Standard query
        """
        query VideogameCharacters($videogameId: ID!) {
          videogame(id: $videogameId) {
            id
            name
            characters {
              id
              name
            }
          }
        }
        """,
        # Format 2: Without variable
        f"""
        query {{
          videogame(id: {videogame_id}) {{
            id
            name
            characters {{
              id
              name
            }}
          }}
        }}
        """,
        # Format 3: Using slug
        """
        query {
          videogame(slug: "ultimate") {
            id
            name
            characters {
              id
              name
            }
          }
        }
        """
    ]
    
    last_error = ""
    
    for i, query in enumerate(queries):
        try:
            if i == 0:
                payload = {"query": query, "variables": {"videogameId": videogame_id}}
            else:
                payload = {"query": query}
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                continue
            
            result = response.json()
            
            if "errors" in result:
                last_error = f"GraphQL error: {result['errors'][0].get('message', 'Unknown error')}"
                continue
            
            videogame = result.get("data", {}).get("videogame")
            
            if not videogame:
                last_error = f"No videogame data returned. Response: {str(result)[:200]}"
                continue
            
            characters = videogame.get("characters", [])
            
            if not characters:
                last_error = f"Videogame found ({videogame.get('name', 'Unknown')}) but no characters field. This API endpoint may not support character data."
                continue
            
            char_map = {}
            for char in characters:
                if char and char.get("id") and char.get("name"):
                    char_map[str(char["id"])] = char["name"]
            
            if char_map:
                return (char_map, None)
            else:
                last_error = "Characters list was empty"
                
        except Exception as e:
            last_error = f"Exception: {str(e)}"
            continue
    
    return ({}, last_error)

def extract_character_data(tournaments: list, registry: dict, character_names: dict) -> dict:
    """
    Extract character usage data from tournament sets.
    
    Returns: {
        player_name: {
            character_id: {
                "name": character_name,
                "games_played": int,
                "games_won": int,
                "win_rate": float
            }
        }
    }
    """
    player_characters = defaultdict(lambda: defaultdict(lambda: {
        "games_played": 0,
        "games_won": 0
    }))
    
    for tourney in tournaments:
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            for set_data in event.get("sets", []):
                games = set_data.get("games") or []
                winner_id = set_data.get("winnerId")
                
                for game in games:
                    if not game:
                        continue
                    
                    game_winner_id = game.get("winnerId")
                    selections = game.get("selections") or []
                    
                    for selection in selections:
                        if not selection:
                            continue
                        
                        entrant = selection.get("entrant") or {}
                        entrant_name = entrant.get("name", "")
                        entrant_id = entrant.get("id")
                        
                        if not entrant_name:
                            continue
                        
                        # Get canonical player name
                        player_name = get_canonical_name(entrant_name, registry)
                        
                        # Get character
                        selection_type = selection.get("selectionType")
                        character_id = selection.get("selectionValue")
                        
                        if selection_type == "CHARACTER" and character_id:
                            char_id_str = str(character_id)
                            player_characters[player_name][char_id_str]["games_played"] += 1
                            
                            # Check if this player won this game
                            if entrant_id == game_winner_id:
                                player_characters[player_name][char_id_str]["games_won"] += 1
    
    # Calculate win rates and add character names
    result = {}
    for player_name, characters in player_characters.items():
        result[player_name] = {}
        for char_id, stats in characters.items():
            games_played = stats["games_played"]
            games_won = stats["games_won"]
            win_rate = round(games_won / games_played * 100, 1) if games_played > 0 else 0
            
            result[player_name][char_id] = {
                "id": char_id,
                "name": character_names.get(char_id, f"Character #{char_id}"),
                "games_played": games_played,
                "games_won": games_won,
                "win_rate": win_rate
            }
    
    return result

def get_player_characters(player_name: str, tournaments: list, registry: dict, character_names: dict) -> list:
    """Get character stats for a specific player, sorted by games played"""
    all_char_data = extract_character_data(tournaments, registry, character_names)
    player_chars = all_char_data.get(player_name, {})
    
    # Convert to list and sort by games played
    char_list = list(player_chars.values())
    char_list.sort(key=lambda x: x["games_played"], reverse=True)
    
    return char_list

def get_all_character_ids(tournaments: list) -> set:
    """Get all unique character IDs from tournament data"""
    char_ids = set()
    
    for tourney in tournaments:
        for event in tourney.get("events", []):
            for set_data in event.get("sets", []):
                games = set_data.get("games") or []
                for game in games:
                    if not game:
                        continue
                    selections = game.get("selections") or []
                    for selection in selections:
                        if selection and selection.get("selectionType") == "CHARACTER":
                            char_id = selection.get("selectionValue")
                            if char_id:
                                char_ids.add(str(char_id))
    
    return char_ids

# =============================================================================
# PLAYER IDENTITY TRACKING
# =============================================================================

def build_player_registry(tournaments: list, manual_aliases: dict) -> dict:
    """Build a registry mapping user_ids and names to canonical player identities."""
    registry = {
        "by_user_id": {},
        "by_name": {},
        "profiles": {}
    }
    
    user_id_to_names = {}
    name_to_user_ids = {}
    
    for tourney in tournaments:
        for event in tourney.get("events", []):
            for standing in event.get("standings", []):
                entrant = standing.get("entrant") or {}
                entrant_name = entrant.get("name", "")
                
                for participant in entrant.get("participants", []):
                    user = participant.get("user") or {}
                    user_id = user.get("id")
                    gamer_tag = participant.get("gamerTag", "")
                    
                    if user_id:
                        if user_id not in user_id_to_names:
                            user_id_to_names[user_id] = set()
                        user_id_to_names[user_id].add(entrant_name)
                        if gamer_tag:
                            user_id_to_names[user_id].add(gamer_tag)
                        
                        if entrant_name:
                            if entrant_name not in name_to_user_ids:
                                name_to_user_ids[entrant_name] = set()
                            name_to_user_ids[entrant_name].add(user_id)
            
            for entrant in event.get("entrants", []):
                entrant_name = entrant.get("name", "")
                
                for participant in entrant.get("participants", []):
                    user = participant.get("user") or {}
                    user_id = user.get("id")
                    gamer_tag = participant.get("gamerTag", "")
                    
                    if user_id:
                        if user_id not in user_id_to_names:
                            user_id_to_names[user_id] = set()
                        user_id_to_names[user_id].add(entrant_name)
                        if gamer_tag:
                            user_id_to_names[user_id].add(gamer_tag)
                        
                        if entrant_name:
                            if entrant_name not in name_to_user_ids:
                                name_to_user_ids[entrant_name] = set()
                            name_to_user_ids[entrant_name].add(user_id)
    
    for user_id, names in user_id_to_names.items():
        canonical = max(names, key=len) if names else f"Player_{user_id}"
        registry["by_user_id"][user_id] = canonical
        
        for name in names:
            registry["by_name"][name] = canonical
        
        if canonical not in registry["profiles"]:
            registry["profiles"][canonical] = {
                "user_id": user_id,
                "all_tags": list(names),
                "canonical_name": canonical
            }
    
    for display_name, aliases in manual_aliases.items():
        for alias in aliases:
            registry["by_name"][alias] = display_name
        registry["by_name"][display_name] = display_name
        
        if display_name not in registry["profiles"]:
            registry["profiles"][display_name] = {
                "user_id": None,
                "all_tags": [display_name] + aliases,
                "canonical_name": display_name
            }
        else:
            registry["profiles"][display_name]["all_tags"] = list(
                set(registry["profiles"][display_name]["all_tags"] + aliases)
            )
    
    for tourney in tournaments:
        for event in tourney.get("events", []):
            for standing in event.get("standings", []):
                entrant = standing.get("entrant") or {}
                name = entrant.get("name", "")
                if name and name not in registry["by_name"]:
                    registry["by_name"][name] = name
                    registry["profiles"][name] = {
                        "user_id": None,
                        "all_tags": [name],
                        "canonical_name": name
                    }
    
    return registry

def get_canonical_name(name: str, registry: dict) -> str:
    """Get the canonical name for a player"""
    return registry.get("by_name", {}).get(name, name)

# =============================================================================
# START.GG API
# =============================================================================

class StartGGExporter:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.api_url = "https://api.start.gg/gql/alpha"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, query: str, variables: dict) -> dict:
        response = requests.post(
            self.api_url,
            headers=self.headers,
            json={"query": query, "variables": variables}
        )
        return response.json()
    
    def extract_tournament_slug(self, url: str) -> str:
        import re
        url = url.rstrip('/')
        match = re.search(r'start\.gg/tournament/([^/]+)', url)
        if not match:
            raise ValueError(f"Could not extract tournament slug from URL: {url}")
        return match.group(1)
    
    def export_tournament(self, url: str, progress_callback=None) -> dict:
        tournament_slug = self.extract_tournament_slug(url)
        
        if progress_callback:
            progress_callback("Fetching tournament info...")
        
        query = """
        query TournamentEvents($slug: String!) {
          tournament(slug: $slug) {
            id
            name
            startAt
            endAt
            events {
              id
              name
              slug
              numEntrants
              state
              videogame { id name }
            }
          }
        }
        """
        
        result = self._make_request(query, {"slug": tournament_slug})
        
        if "errors" in result:
            raise Exception(result["errors"][0]["message"])
        
        tournament = result["data"]["tournament"]
        events = tournament.get("events", [])
        
        singles_event = None
        for event in events:
            if event["name"].lower() == "singles":
                singles_event = event
                break
        
        if not singles_event:
            if events:
                singles_event = events[0]
            else:
                raise Exception("No events found in this tournament")
        
        event_id = singles_event["id"]
        
        if progress_callback:
            progress_callback(f"Processing event: {singles_event['name']}...")
        
        entrants = self._get_entrants(event_id, progress_callback)
        standings = self._get_standings(event_id, progress_callback)
        phases = self._get_phases(event_id)
        all_sets = []
        
        for phase in phases:
            phase_sets = self._get_phase_sets(phase["id"], phase["name"], progress_callback)
            all_sets.extend(phase_sets)
        
        export_data = {
            "tournament": {
                "id": tournament["id"],
                "name": tournament["name"],
                "slug": tournament_slug,
                "startAt": tournament.get("startAt"),
                "endAt": tournament.get("endAt")
            },
            "events": [{
                "id": singles_event["id"],
                "name": singles_event["name"],
                "numEntrants": singles_event["numEntrants"],
                "videogame": singles_event.get("videogame"),
                "entrants": entrants,
                "standings": standings,
                "sets": all_sets
            }]
        }
        
        return export_data
    
    def _get_entrants(self, event_id: int, progress_callback=None) -> list:
        if progress_callback:
            progress_callback("Fetching entrants...")
        
        entrants = []
        page = 1
        
        while True:
            query = """
            query EventEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
              event(id: $eventId) {
                entrants(query: { page: $page, perPage: $perPage }) {
                  pageInfo { totalPages }
                  nodes {
                    id
                    name
                    participants {
                      id
                      gamerTag
                      prefix
                      user { id name }
                    }
                  }
                }
              }
            }
            """
            
            result = self._make_request(query, {
                "eventId": event_id,
                "page": page,
                "perPage": 50
            })
            
            if "errors" in result:
                break
            
            nodes = result.get("data", {}).get("event", {}).get("entrants", {}).get("nodes", [])
            if not nodes:
                break
            
            entrants.extend(nodes)
            
            total_pages = result.get("data", {}).get("event", {}).get("entrants", {}).get("pageInfo", {}).get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
        
        return entrants
    
    def _get_standings(self, event_id: int, progress_callback=None) -> list:
        if progress_callback:
            progress_callback("Fetching standings...")
        
        standings = []
        page = 1
        
        while True:
            query = """
            query EventStandings($eventId: ID!, $page: Int!, $perPage: Int!) {
              event(id: $eventId) {
                standings(query: { page: $page, perPage: $perPage }) {
                  pageInfo { totalPages }
                  nodes {
                    placement
                    entrant {
                      id
                      name
                      participants {
                        gamerTag
                        prefix
                        user { id name }
                      }
                    }
                  }
                }
              }
            }
            """
            
            result = self._make_request(query, {
                "eventId": event_id,
                "page": page,
                "perPage": 50
            })
            
            if "errors" in result:
                break
            
            nodes = result.get("data", {}).get("event", {}).get("standings", {}).get("nodes", [])
            if not nodes:
                break
            
            standings.extend(nodes)
            
            total_pages = result.get("data", {}).get("event", {}).get("standings", {}).get("pageInfo", {}).get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
        
        return standings
    
    def _get_phases(self, event_id: int) -> list:
        query = """
        query EventPhases($eventId: ID!) {
          event(id: $eventId) {
            phases { id name state }
          }
        }
        """
        result = self._make_request(query, {"eventId": event_id})
        return result.get("data", {}).get("event", {}).get("phases", [])
    
    def _get_phase_sets(self, phase_id: int, phase_name: str, progress_callback=None) -> list:
        if progress_callback:
            progress_callback(f"Fetching matches from {phase_name}...")
        
        pg_query = """
        query PhaseGroups($phaseId: ID!) {
          phase(id: $phaseId) {
            phaseGroups { nodes { id displayIdentifier } }
          }
        }
        """
        
        pg_result = self._make_request(pg_query, {"phaseId": phase_id})
        phase_groups = pg_result.get("data", {}).get("phase", {}).get("phaseGroups", {}).get("nodes", [])
        
        all_sets = []
        
        for pg in phase_groups:
            pg_id = pg["id"]
            pg_name = pg.get("displayIdentifier", "Unknown")
            page = 1
            
            while True:
                # Include game data with character selections
                sets_query = """
                query PhaseGroupSets($pgId: ID!, $page: Int!) {
                  phaseGroup(id: $pgId) {
                    sets(page: $page, perPage: 20, sortType: STANDARD) {
                      pageInfo { total totalPages }
                      nodes {
                        id
                        fullRoundText
                        round
                        completedAt
                        winnerId
                        displayScore
                        games {
                          id
                          orderNum
                          winnerId
                          selections {
                            entrant { id name }
                            selectionType
                            selectionValue
                          }
                        }
                        slots {
                          id
                          entrant {
                            id
                            name
                            participants {
                              gamerTag
                              prefix
                              user { id }
                            }
                          }
                          standing {
                            placement
                            stats { score { value } }
                          }
                        }
                      }
                    }
                  }
                }
                """
                
                try:
                    result = self._make_request(sets_query, {"pgId": pg_id, "page": page})
                    
                    if "errors" in result:
                        break
                    
                    pg_data = result.get("data", {}).get("phaseGroup", {})
                    sets_data = pg_data.get("sets", {})
                    nodes = sets_data.get("nodes", [])
                    
                    if not nodes:
                        break
                    
                    for s in nodes:
                        s["phaseName"] = phase_name
                        s["phaseGroupName"] = pg_name
                    
                    all_sets.extend(nodes)
                    
                    total_pages = sets_data.get("pageInfo", {}).get("totalPages", 1)
                    if page >= total_pages:
                        break
                    page += 1
                except Exception:
                    break
        
        return all_sets

# =============================================================================
# RANKING CALCULATIONS
# =============================================================================

def calculate_rankings(tournaments: list, settings: dict, registry: dict, character_names: dict = None) -> pd.DataFrame:
    if not tournaments:
        return pd.DataFrame()
    
    if character_names is None:
        character_names = {}
    
    points_map = settings["points"]
    player_data = {}
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        tourney_date = tourney["tournament"].get("startAt", 0)
        
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            num_entrants = event.get("numEntrants", 0)
            
            for standing in event.get("standings", []):
                placement = standing.get("placement")
                entrant = standing.get("entrant") or {}
                
                if not entrant:
                    continue
                
                raw_name = entrant.get("name", "Unknown")
                player_name = get_canonical_name(raw_name, registry)
                
                if player_name not in player_data:
                    profile = registry.get("profiles", {}).get(player_name, {})
                    player_data[player_name] = {
                        "name": player_name,
                        "user_id": profile.get("user_id"),
                        "all_tags": profile.get("all_tags", [player_name]),
                        "total_points": 0,
                        "results": [],
                        "wins": 0,
                        "losses": 0,
                        "tournaments_played": 0,
                        "first_places": 0,
                        "second_places": 0,
                        "third_places": 0,
                        "best_placement": 999
                    }
                
                base_points = 0
                for place_str, pts in sorted(points_map.items(), key=lambda x: int(x[0])):
                    place = int(place_str)
                    if placement <= place:
                        base_points = pts
                        break
                
                if settings.get("attendance_scaling") and num_entrants > 0:
                    scaling_base = settings.get("scaling_base", 32)
                    scale_factor = num_entrants / scaling_base
                    base_points = int(base_points * scale_factor)
                
                player_data[player_name]["results"].append({
                    "tournament": tourney_name,
                    "date": tourney_date,
                    "placement": placement,
                    "points": base_points,
                    "entrants": num_entrants,
                    "tag_used": raw_name
                })
                
                player_data[player_name]["tournaments_played"] += 1
                
                if placement == 1:
                    player_data[player_name]["first_places"] += 1
                elif placement == 2:
                    player_data[player_name]["second_places"] += 1
                elif placement == 3:
                    player_data[player_name]["third_places"] += 1
                
                if placement < player_data[player_name]["best_placement"]:
                    player_data[player_name]["best_placement"] = placement
    
    # Calculate wins/losses from sets
    for tourney in tournaments:
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            for set_data in event.get("sets", []):
                winner_id = set_data.get("winnerId")
                slots = set_data.get("slots") or []
                
                for slot in slots:
                    if not slot:
                        continue
                    entrant = slot.get("entrant")
                    if not entrant:
                        continue
                    
                    raw_name = entrant.get("name", "Unknown")
                    player_name = get_canonical_name(raw_name, registry)
                    
                    if player_name not in player_data:
                        continue
                    
                    if entrant.get("id") == winner_id:
                        player_data[player_name]["wins"] += 1
                    else:
                        player_data[player_name]["losses"] += 1
    
    # Calculate total points
    for player_name, data in player_data.items():
        results = sorted(data["results"], key=lambda x: x["points"], reverse=True)
        
        if settings.get("best_n_enabled"):
            best_n = settings.get("best_n", 6)
            results = results[:best_n]
        
        if settings.get("drop_worst") and len(results) > 1:
            results = results[:-1]
        
        data["total_points"] = sum(r["points"] for r in results)
    
    min_tournaments = settings.get("min_tournaments", 1)
    player_data = {k: v for k, v in player_data.items() if v["tournaments_played"] >= min_tournaments}
    
    df = pd.DataFrame([
        {
            "Rank": 0,
            "Player": data["name"],
            "Points": data["total_points"],
            "W": data["wins"],
            "L": data["losses"],
            "Win%": round(data["wins"] / (data["wins"] + data["losses"]) * 100, 1) if (data["wins"] + data["losses"]) > 0 else 0,
            "🥇": data["first_places"],
            "🥈": data["second_places"],
            "🥉": data["third_places"],
            "Best": data["best_placement"],
            "Events": data["tournaments_played"]
        }
        for data in player_data.values()
    ])
    
    if len(df) > 0:
        df = df.sort_values("Points", ascending=False).reset_index(drop=True)
        df["Rank"] = range(1, len(df) + 1)
    
    return df

def get_player_details(tournaments: list, player_name: str, registry: dict, character_names: dict) -> dict:
    details = {
        "name": player_name,
        "profile": registry.get("profiles", {}).get(player_name, {}),
        "results": [],
        "total_wins": 0,
        "total_losses": 0,
        "tournaments_played": 0,
        "best_placement": 999,
        "worst_placement": 0,
        "avg_placement": 0,
        "recent_sets": [],
        "characters": []
    }
    
    placements = []
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        tourney_date = tourney["tournament"].get("startAt", 0)
        
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            for standing in event.get("standings", []):
                entrant = standing.get("entrant") or {}
                raw_name = entrant.get("name", "")
                canonical = get_canonical_name(raw_name, registry)
                
                if canonical == player_name:
                    placement = standing.get("placement", 0)
                    placements.append(placement)
                    
                    details["results"].append({
                        "tournament": tourney_name,
                        "date": tourney_date,
                        "placement": placement,
                        "entrants": event.get("numEntrants", 0),
                        "tag_used": raw_name
                    })
                    
                    if placement < details["best_placement"]:
                        details["best_placement"] = placement
                    if placement > details["worst_placement"]:
                        details["worst_placement"] = placement
                    
                    details["tournaments_played"] += 1
                    break
            
            for set_data in event.get("sets", []):
                slots = set_data.get("slots") or []
                if len(slots) != 2:
                    continue
                
                player_in_set = False
                player_slot = None
                opponent_slot = None
                
                for slot in slots:
                    if not slot:
                        continue
                    entrant = slot.get("entrant") or {}
                    raw_name = entrant.get("name", "")
                    canonical = get_canonical_name(raw_name, registry)
                    
                    if canonical == player_name:
                        player_in_set = True
                        player_slot = slot
                    else:
                        opponent_slot = slot
                
                if player_in_set and player_slot and opponent_slot:
                    winner_id = set_data.get("winnerId")
                    player_entrant = player_slot.get("entrant") or {}
                    opponent_entrant = opponent_slot.get("entrant") or {}
                    
                    won = player_entrant.get("id") == winner_id
                    
                    if won:
                        details["total_wins"] += 1
                    else:
                        details["total_losses"] += 1
                    
                    opponent_name = get_canonical_name(
                        opponent_entrant.get("name", "Unknown"),
                        registry
                    )
                    
                    details["recent_sets"].append({
                        "tournament": tourney_name,
                        "round": set_data.get("fullRoundText", "Unknown"),
                        "opponent": opponent_name,
                        "score": set_data.get("displayScore", "N/A"),
                        "won": won
                    })
    
    if placements:
        details["avg_placement"] = round(sum(placements) / len(placements), 1)
    
    details["results"] = sorted(details["results"], key=lambda x: x.get("date", 0), reverse=True)
    details["recent_sets"] = details["recent_sets"][:20]
    
    # Get character data
    details["characters"] = get_player_characters(player_name, tournaments, registry, character_names)
    
    return details

def get_head_to_head(tournaments: list, player1: str, player2: str, registry: dict) -> dict:
    h2h = {"player1": player1, "player2": player2, "p1_wins": 0, "p2_wins": 0, "sets": []}
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            for set_data in event.get("sets", []):
                slots = set_data.get("slots") or []
                if len(slots) != 2:
                    continue
                
                slot_names = []
                for slot in slots:
                    if slot and slot.get("entrant"):
                        raw_name = slot["entrant"].get("name", "")
                        canonical = get_canonical_name(raw_name, registry)
                        slot_names.append((canonical, slot))
                    else:
                        slot_names.append(("", None))
                
                if len(slot_names) != 2:
                    continue
                
                names = [sn[0] for sn in slot_names]
                
                if player1 in names and player2 in names:
                    winner_id = set_data.get("winnerId")
                    winner_name = None
                    
                    for canonical, slot in slot_names:
                        if slot and slot.get("entrant", {}).get("id") == winner_id:
                            winner_name = canonical
                            break
                    
                    if winner_name == player1:
                        h2h["p1_wins"] += 1
                    elif winner_name == player2:
                        h2h["p2_wins"] += 1
                    
                    h2h["sets"].append({
                        "tournament": tourney_name,
                        "round": set_data.get("fullRoundText", "Unknown"),
                        "score": set_data.get("displayScore", "N/A"),
                        "winner": winner_name
                    })
    
    return h2h

# =============================================================================
# STREAMLIT UI
# =============================================================================

def main():
    data = load_data()
    
    # Get active tournaments based on season
    active_tournaments = get_active_tournaments(data)
    
    registry = build_player_registry(
        active_tournaments,
        data.get("player_aliases", {})
    )
    
    with st.sidebar:
        st.title("🎮 Season Rankings")
        
        # Season selector
        seasons = data.get("seasons", [])
        active_season = data.get("active_season")
        
        season_options = ["All Tournaments"] + [s["name"] for s in seasons if not s.get("archived")]
        current_idx = 0
        
        if active_season:
            for i, s in enumerate(seasons):
                if s["id"] == active_season and not s.get("archived"):
                    current_idx = i + 1
                    break
        
        selected_season = st.selectbox(
            "📅 Season",
            season_options,
            index=current_idx
        )
        
        # Update active season
        if selected_season == "All Tournaments":
            if data.get("active_season") is not None:
                data["active_season"] = None
                save_data(data)
                st.rerun()
        else:
            for s in seasons:
                if s["name"] == selected_season:
                    if data.get("active_season") != s["id"]:
                        data["active_season"] = s["id"]
                        save_data(data)
                        st.rerun()
                    break
        
        st.markdown("---")
        
        # Build navigation options based on settings
        nav_options = ["🏆 Rankings", "➕ Add Tournament", "👤 Players", "🥊 Head-to-Head", 
                       "📋 Tournaments", "📅 Seasons"]
        
        # Only show Characters page if enabled
        settings = data.get("settings", get_default_settings())
        if settings.get("characters_enabled", True):
            nav_options.append("🎮 Characters")
        
        nav_options.extend(["⚙️ Settings", "🔗 Manage Aliases"])
        
        page = st.radio(
            "Navigation",
            nav_options,
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.caption(f"📊 {len(active_tournaments)} tournaments")
        st.caption(f"👥 {len(registry['profiles'])} players")
        
        # Show GitHub connection status
        load_status = st.session_state.get("github_load_status", "unknown")
        if load_status == "success":
            st.caption("☁️ Synced with GitHub")
        elif load_status == "new":
            st.caption("☁️ New data file")
        elif load_status == "unknown":
            st.caption("⏳ Loading...")
        else:
            st.caption(f"⚠️ GitHub: {load_status}")
        
        st.markdown("---")
        if st.button("🔄 Refresh Data"):
            refresh_data()
            st.rerun()
    
    if page == "🏆 Rankings":
        show_rankings_page(data, registry, active_tournaments)
    elif page == "➕ Add Tournament":
        show_add_tournament_page(data)
    elif page == "👤 Players":
        show_players_page(data, registry, active_tournaments)
    elif page == "🥊 Head-to-Head":
        show_head_to_head_page(data, registry, active_tournaments)
    elif page == "📋 Tournaments":
        show_tournaments_page(data, active_tournaments)
    elif page == "📅 Seasons":
        show_seasons_page(data, registry)
    elif page == "🎮 Characters":
        show_characters_page(data, active_tournaments)
    elif page == "⚙️ Settings":
        show_settings_page(data)
    elif page == "🔗 Manage Aliases":
        show_aliases_page(data, registry)

def show_rankings_page(data, registry, tournaments):
    st.title("🏆 Season Rankings")
    
    if not tournaments:
        st.info("No tournaments in this season. Go to '➕ Add Tournament' or '📅 Seasons' to get started!")
        return
    
    settings = data.get("settings", get_default_settings())
    character_names = data.get("character_names", {})
    df = calculate_rankings(tournaments, settings, registry, character_names)
    
    if df.empty:
        st.warning("No ranking data available.")
        return
    
    # Better layout: Leader first, then stats
    leader_name = df.iloc[0]["Player"] if len(df) > 0 else "N/A"
    
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    with col1:
        st.metric("👑 Leader", leader_name)
    with col2:
        st.metric("Tournaments", len(tournaments))
    with col3:
        st.metric("Players", len(df))
    with col4:
        total_sets = sum(len(event.get("sets", [])) for t in tournaments for event in t.get("events", []))
        st.metric("Total Sets", total_sets)
    
    st.markdown("---")
    
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn("Rank", width="small"),
            "Player": st.column_config.TextColumn("Player", width="medium"),
            "Points": st.column_config.NumberColumn("Points", width="small"),
            "W": st.column_config.NumberColumn("W", width="small"),
            "L": st.column_config.NumberColumn("L", width="small"),
            "Win%": st.column_config.NumberColumn("Win%", format="%.1f%%", width="small"),
            "🥇": st.column_config.NumberColumn("🥇", width="small"),
            "🥈": st.column_config.NumberColumn("🥈", width="small"),
            "🥉": st.column_config.NumberColumn("🥉", width="small"),
            "Best": st.column_config.NumberColumn("Best", width="small"),
            "Events": st.column_config.NumberColumn("Events", width="small"),
        }
    )
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Rankings', index=False)
        
        st.download_button(
            "📥 Export Excel",
            excel_buffer.getvalue(),
            file_name="season_rankings.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col2:
        csv = df.to_csv(index=False)
        st.download_button("📥 Export CSV", csv, file_name="season_rankings.csv", mime="text/csv")

def show_add_tournament_page(data):
    st.title("➕ Add Tournament")
    
    api_key = st.secrets.get("STARTGG_API_KEY", "")
    
    if not api_key:
        st.error("⚠️ Start.gg API key not configured!")
        return
    
    st.markdown("Paste a Start.gg tournament URL to import it:")
    
    url = st.text_input("Tournament URL", placeholder="https://www.start.gg/tournament/your-tournament/events", label_visibility="collapsed")
    
    if st.button("➕ Add Tournament", type="primary", disabled=not url):
        with st.spinner("Importing tournament..."):
            try:
                progress = st.empty()
                exporter = StartGGExporter(api_key)
                tournament_data = exporter.export_tournament(url, lambda msg: progress.text(msg))
                
                existing_ids = [t["tournament"]["id"] for t in data["tournaments"]]
                if tournament_data["tournament"]["id"] in existing_ids:
                    st.warning(f"Tournament '{tournament_data['tournament']['name']}' is already added!")
                else:
                    data["tournaments"].append(tournament_data)
                    
                    if save_data(data):
                        st.success(f"✅ Added: {tournament_data['tournament']['name']}")
                        event = tournament_data["events"][0]
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Entrants", event.get("numEntrants", 0))
                        col2.metric("Sets", len(event.get("sets", [])))
                        col3.metric("Standings", len(event.get("standings", [])))
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    if data["tournaments"]:
        st.markdown("---")
        st.subheader("📋 All Tournaments")
        
        for i, t in enumerate(data["tournaments"]):
            col1, col2 = st.columns([4, 1])
            with col1:
                date_str = ""
                if t["tournament"].get("startAt"):
                    date_str = datetime.fromtimestamp(t["tournament"]["startAt"]).strftime(" (%b %d, %Y)")
                st.write(f"**{t['tournament']['name']}**{date_str}")
            with col2:
                if st.button("🗑️", key=f"delete_{i}"):
                    data["tournaments"].pop(i)
                    save_data(data)
                    st.rerun()

def show_players_page(data, registry, tournaments):
    st.title("👤 Players")
    
    if not tournaments:
        st.info("No tournaments added yet.")
        return
    
    all_players = sorted(registry.get("profiles", {}).keys())
    
    if not all_players:
        st.warning("No players found.")
        return
    
    selected_player = st.selectbox("Select a player:", all_players)
    
    if selected_player:
        character_names = data.get("character_names", {})
        details = get_player_details(tournaments, selected_player, registry, character_names)
        profile = details.get("profile", {})
        
        st.markdown("---")
        st.header(selected_player)
        
        all_tags = profile.get("all_tags", [])
        if len(all_tags) > 1:
            other_tags = [t for t in all_tags if t != selected_player]
            st.caption(f"Also known as: {', '.join(other_tags)}")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Events", details["tournaments_played"])
        col2.metric("Wins", details["total_wins"])
        col3.metric("Losses", details["total_losses"])
        win_rate = round(details["total_wins"] / (details["total_wins"] + details["total_losses"]) * 100, 1) if (details["total_wins"] + details["total_losses"]) > 0 else 0
        col4.metric("Win Rate", f"{win_rate}%")
        col5.metric("Best", f"#{details['best_placement']}" if details["best_placement"] < 999 else "N/A")
        
        # Character section (only if enabled)
        settings = data.get("settings", get_default_settings())
        if settings.get("characters_enabled", True):
            st.markdown("---")
            st.subheader("🎮 Characters")
            
            if details["characters"]:
                for i, char in enumerate(details["characters"]):
                    char_name = char["name"]
                    games = char["games_played"]
                    wins = char["games_won"]
                    wr = char["win_rate"]
                    
                    # Main / Secondary badges
                    badge = ""
                    if i == 0:
                        badge = "🎯 **Main** - "
                    elif i == 1 and games >= 5:
                        badge = "2️⃣ **Secondary** - "
                    
                    st.write(f"{badge}**{char_name}**: {games} games ({wins}W - {games-wins}L) - {wr}% win rate")
            else:
                st.info("No character data available for this player.")
        
        # Tournament results
        st.markdown("---")
        st.subheader("📊 Tournament Results")
        
        if details["results"]:
            results_df = pd.DataFrame(details["results"])
            results_df["Date"] = results_df["date"].apply(lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d") if x else "N/A")
            results_df["Placement"] = results_df["placement"].apply(lambda x: f"#{x}")
            
            st.dataframe(
                results_df[["tournament", "Date", "Placement", "entrants"]].rename(columns={
                    "tournament": "Tournament", "entrants": "Entrants"
                }),
                use_container_width=True,
                hide_index=True
            )
        
        # Recent sets
        st.markdown("---")
        st.subheader("🎮 Recent Sets")
        
        if details["recent_sets"]:
            for set_info in details["recent_sets"][:10]:
                result_emoji = "✅" if set_info["won"] else "❌"
                st.write(f"{result_emoji} vs **{set_info['opponent']}** - {set_info['score']} ({set_info['round']} @ {set_info['tournament']})")

def show_head_to_head_page(data, registry, tournaments):
    st.title("🥊 Head-to-Head")
    
    if not tournaments:
        st.info("No tournaments added yet.")
        return
    
    all_players = sorted(registry.get("profiles", {}).keys())
    
    if len(all_players) < 2:
        st.warning("Need at least 2 players for head-to-head.")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        player1 = st.selectbox("Player 1", all_players, key="p1")
    with col2:
        remaining = [p for p in all_players if p != player1]
        player2 = st.selectbox("Player 2", remaining, key="p2")
    
    if player1 and player2:
        h2h = get_head_to_head(tournaments, player1, player2, registry)
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            st.markdown(f"### {player1}")
            st.metric("Wins", h2h["p1_wins"])
        with col2:
            st.markdown("### vs")
        with col3:
            st.markdown(f"### {player2}")
            st.metric("Wins", h2h["p2_wins"])
        
        if h2h["sets"]:
            st.markdown("---")
            st.subheader("Match History")
            for match in h2h["sets"]:
                st.write(f"**{match['tournament']}** - {match['round']}")
                st.write(f"  {match['score']} → 🏆 {match['winner']}")
        else:
            st.info("These players haven't faced each other yet.")

def show_tournaments_page(data, tournaments):
    st.title("📋 Tournament History")
    
    if not tournaments:
        st.info("No tournaments in this view.")
        return
    
    sorted_tournaments = sorted(tournaments, key=lambda t: t["tournament"].get("startAt", 0), reverse=True)
    
    for t in sorted_tournaments:
        tourney = t["tournament"]
        event = t["events"][0] if t.get("events") else {}
        
        date_str = datetime.fromtimestamp(tourney["startAt"]).strftime("%b %d, %Y") if tourney.get("startAt") else ""
        
        with st.expander(f"**{tourney['name']}** {('- ' + date_str) if date_str else ''}"):
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrants", event.get("numEntrants", "N/A"))
            col2.metric("Sets", len(event.get("sets", [])))
            
            winner = "N/A"
            for standing in event.get("standings", []):
                if standing.get("placement") == 1 and standing.get("entrant"):
                    winner = standing["entrant"]["name"]
                    break
            col3.metric("Winner", winner)
            
            st.markdown("**Top 8:**")
            top8 = sorted([s for s in event.get("standings", []) if s.get("placement", 99) <= 8], key=lambda s: s.get("placement", 99))
            
            for s in top8:
                place = s.get("placement", "?")
                name = s.get("entrant", {}).get("name", "Unknown")
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
                st.write(f"{medal} {name}")

def show_seasons_page(data, registry):
    st.title("📅 Seasons")
    
    st.markdown("""
    Create seasons to organize tournaments into ranking periods. 
    Archive seasons to save final standings and start fresh.
    """)
    
    st.markdown("---")
    
    # Create new season
    st.subheader("➕ Create New Season")
    
    col1, col2 = st.columns(2)
    
    with col1:
        season_name = st.text_input("Season Name", placeholder="e.g., Spring 2024")
    
    with col2:
        # Tournament selector
        all_tournaments = data.get("tournaments", [])
        tournament_options = {
            f"{t['tournament']['name']} ({datetime.fromtimestamp(t['tournament'].get('startAt', 0)).strftime('%b %Y') if t['tournament'].get('startAt') else 'No date'})": t["tournament"]["id"]
            for t in all_tournaments
        }
        
        selected_tournaments = st.multiselect(
            "Select Tournaments",
            options=list(tournament_options.keys())
        )
    
    if st.button("➕ Create Season", disabled=not season_name or not selected_tournaments):
        tournament_ids = [tournament_options[name] for name in selected_tournaments]
        create_season(data, season_name, tournament_ids)
        if save_data(data):
            st.success(f"✅ Created season: {season_name}")
            st.rerun()
    
    st.markdown("---")
    
    # Active seasons
    st.subheader("📋 Active Seasons")
    
    active_seasons = [s for s in data.get("seasons", []) if not s.get("archived")]
    
    if active_seasons:
        for season in active_seasons:
            with st.expander(f"**{season['name']}** - {len(season.get('tournament_ids', []))} tournaments"):
                st.write(f"Created: {season.get('created_at', 'N/A')[:10]}")
                
                # List tournaments in this season
                tournament_ids = season.get("tournament_ids", [])
                for t in data["tournaments"]:
                    if t["tournament"]["id"] in tournament_ids:
                        st.write(f"  • {t['tournament']['name']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🏁 Archive Season", key=f"archive_{season['id']}"):
                        if archive_season(data, season["id"], registry):
                            save_data(data)
                            st.success(f"Archived {season['name']} with final rankings!")
                            st.rerun()
                with col2:
                    if st.button("🗑️ Delete", key=f"delete_season_{season['id']}"):
                        data["seasons"] = [s for s in data["seasons"] if s["id"] != season["id"]]
                        if data.get("active_season") == season["id"]:
                            data["active_season"] = None
                        save_data(data)
                        st.rerun()
    else:
        st.info("No active seasons. Create one above!")
    
    st.markdown("---")
    
    # Archived seasons
    st.subheader("🏆 Archived Seasons")
    
    archived_seasons = [s for s in data.get("seasons", []) if s.get("archived")]
    
    if archived_seasons:
        for season in archived_seasons:
            with st.expander(f"**{season['name']}** - Archived {season.get('archived_at', 'N/A')[:10]}"):
                rankings = season.get("final_rankings", [])
                
                if rankings:
                    st.markdown("**Final Top 10:**")
                    for r in rankings[:10]:
                        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r.get("Rank"), f"#{r.get('Rank')}")
                        st.write(f"{medal} {r.get('Player')} - {r.get('Points')} pts")
                    
                    # Download full rankings
                    df = pd.DataFrame(rankings)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        f"📥 Download Full Rankings",
                        csv,
                        file_name=f"{season['name'].replace(' ', '_')}_rankings.csv",
                        mime="text/csv",
                        key=f"download_{season['id']}"
                    )
    else:
        st.info("No archived seasons yet.")

def show_characters_page(data, tournaments):
    st.title("🎮 Character Management")
    
    st.markdown("""
    Map character IDs from Start.gg to readable names.
    Use the auto-fetch button to get official character names from Start.gg!
    """)
    
    # Get all character IDs
    char_ids = get_all_character_ids(tournaments)
    character_names = data.get("character_names", {})
    
    if not char_ids:
        st.info("No character data found in tournaments. Make sure tournaments have game-by-game reporting enabled.")
        return
    
    # Auto-fetch section
    st.markdown("---")
    st.subheader("🔄 Auto-Fetch Character Names")
    
    api_key = st.secrets.get("STARTGG_API_KEY", "")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.caption("Get character names automatically")
    
    with col2:
        if st.button("🔄 Fetch from API", type="secondary", disabled=not api_key):
            with st.spinner("Fetching character names..."):
                # Fetch for SSBU (videogame ID 1386)
                fetched_names, error = fetch_character_list_from_startgg(api_key, 1386)
                
                if fetched_names:
                    # Merge with existing (fetched takes priority for matching IDs)
                    for char_id, name in fetched_names.items():
                        if char_id in char_ids:  # Only save IDs we actually use
                            character_names[char_id] = name
                    
                    data["character_names"] = character_names
                    if save_data(data):
                        st.success(f"✅ Fetched {len(fetched_names)} character names!")
                        st.rerun()
                else:
                    st.error(f"Failed to fetch character names.")
                    if error:
                        st.code(error, language=None)
    
    with col3:
        if st.button("📦 Use Built-in List", type="primary"):
            # Use the built-in SSBU character list
            mapped_count = 0
            for char_id in char_ids:
                if char_id in SSBU_CHARACTERS_BUILTIN:
                    character_names[char_id] = SSBU_CHARACTERS_BUILTIN[char_id]
                    mapped_count += 1
            
            data["character_names"] = character_names
            if save_data(data):
                unmapped = len(char_ids) - mapped_count
                if unmapped > 0:
                    st.warning(f"✅ Mapped {mapped_count} characters. {unmapped} IDs not in built-in list (may need manual entry).")
                else:
                    st.success(f"✅ Mapped all {mapped_count} characters!")
                st.rerun()
    
    # Show how many are mapped vs unmapped
    mapped_count = sum(1 for cid in char_ids if cid in character_names and character_names[cid])
    unmapped_count = len(char_ids) - mapped_count
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Characters Used", len(char_ids))
    col2.metric("Mapped", mapped_count)
    col3.metric("Unmapped", unmapped_count, delta=f"-{unmapped_count}" if unmapped_count > 0 else None, delta_color="inverse")
    
    st.markdown("---")
    st.subheader("📋 Character ID Mapping")
    
    # Show unmapped first, then mapped
    unmapped_ids = [cid for cid in char_ids if cid not in character_names or not character_names[cid]]
    mapped_ids = [cid for cid in char_ids if cid in character_names and character_names[cid]]
    
    if unmapped_ids:
        st.markdown("**⚠️ Unmapped Characters:**")
        for char_id in sorted(unmapped_ids, key=lambda x: int(x) if x.isdigit() else 0):
            col1, col2 = st.columns([1, 3])
            with col1:
                st.write(f"**ID: {char_id}**")
            with col2:
                new_name = st.text_input(
                    f"Name for {char_id}",
                    value="",
                    key=f"char_{char_id}",
                    placeholder="Enter character name..."
                )
                if new_name:
                    character_names[char_id] = new_name
        st.markdown("---")
    
    if mapped_ids:
        st.markdown("**✅ Mapped Characters:**")
        for char_id in sorted(mapped_ids, key=lambda x: int(x) if x.isdigit() else 0):
            col1, col2 = st.columns([1, 3])
            with col1:
                st.write(f"**ID: {char_id}**")
            with col2:
                current_name = character_names.get(char_id, "")
                new_name = st.text_input(
                    f"Name for {char_id}",
                    value=current_name,
                    key=f"char_{char_id}",
                    placeholder="Enter character name..."
                )
                if new_name != current_name:
                    character_names[char_id] = new_name
    
    st.markdown("---")
    
    if st.button("💾 Save Character Names", type="primary"):
        data["character_names"] = character_names
        if save_data(data):
            st.success("✅ Character names saved!")
            st.rerun()

def show_settings_page(data):
    st.title("⚙️ Ranking Settings")
    
    settings = data.get("settings", get_default_settings())
    
    st.subheader("🎯 Points System")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        settings["points"]["1"] = st.number_input("🥇 1st", value=settings["points"].get("1", 100), step=5)
        settings["points"]["2"] = st.number_input("🥈 2nd", value=settings["points"].get("2", 70), step=5)
        settings["points"]["3"] = st.number_input("🥉 3rd", value=settings["points"].get("3", 50), step=5)
    
    with col2:
        settings["points"]["4"] = st.number_input("4th", value=settings["points"].get("4", 40), step=5)
        settings["points"]["5"] = st.number_input("5th-6th", value=settings["points"].get("5", 30), step=5)
        settings["points"]["7"] = st.number_input("7th-8th", value=settings["points"].get("7", 20), step=5)
    
    with col3:
        settings["points"]["9"] = st.number_input("9th-12th", value=settings["points"].get("9", 10), step=5)
        settings["points"]["13"] = st.number_input("13th-16th", value=settings["points"].get("13", 5), step=5)
        settings["points"]["17"] = st.number_input("17th+", value=settings["points"].get("17", 2), step=1)
    
    st.markdown("---")
    st.subheader("📊 Ranking Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        settings["attendance_scaling"] = st.checkbox("📈 Scale by attendance", value=settings.get("attendance_scaling", False))
        if settings["attendance_scaling"]:
            settings["scaling_base"] = st.slider("Base attendance", 8, 128, settings.get("scaling_base", 32))
        
        settings["drop_worst"] = st.checkbox("🗑️ Drop worst result", value=settings.get("drop_worst", False))
    
    with col2:
        settings["best_n_enabled"] = st.checkbox("🏅 Count best N only", value=settings.get("best_n_enabled", False))
        if settings["best_n_enabled"]:
            settings["best_n"] = st.slider("N tournaments", 1, 20, settings.get("best_n", 6))
        
        settings["min_tournaments"] = st.slider("Min. tournaments to qualify", 1, 10, settings.get("min_tournaments", 1))
    
    st.markdown("---")
    st.subheader("🎮 Feature Toggles")
    
    settings["characters_enabled"] = st.checkbox(
        "Enable character tracking",
        value=settings.get("characters_enabled", True),
        help="Show character usage stats on player profiles. Disable if character data is not working correctly."
    )
    
    st.markdown("---")
    
    if st.button("💾 Save Settings", type="primary"):
        data["settings"] = settings
        if save_data(data):
            st.success("✅ Settings saved!")
            st.rerun()
    
    # Advanced / Dev Settings (collapsible)
    st.markdown("---")
    with st.expander("🔧 Advanced / Dev Settings"):
        st.warning("⚠️ These options are for advanced users and developers.")
        
        st.markdown("### 🔄 Re-fetch Tournament Data")
        st.caption("Re-download all tournament data from Start.gg. Useful if data structure changed or to get updated character data.")
        
        api_key = st.secrets.get("STARTGG_API_KEY", "")
        
        if not api_key:
            st.error("API key not configured. Cannot re-fetch.")
        else:
            if st.button("🔄 Re-fetch All Tournaments", type="secondary"):
                with st.spinner("Re-fetching all tournaments... This may take a while."):
                    exporter = StartGGExporter(api_key)
                    success_count = 0
                    error_count = 0
                    
                    new_tournaments = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, t in enumerate(data["tournaments"]):
                        slug = t["tournament"].get("slug", "")
                        name = t["tournament"].get("name", "Unknown")
                        
                        status_text.text(f"Re-fetching: {name}...")
                        
                        try:
                            url = f"https://start.gg/tournament/{slug}"
                            new_data = exporter.export_tournament(url)
                            new_tournaments.append(new_data)
                            success_count += 1
                        except Exception as e:
                            st.error(f"Failed to re-fetch {name}: {str(e)}")
                            # Keep old data on failure
                            new_tournaments.append(t)
                            error_count += 1
                        
                        progress_bar.progress((i + 1) / len(data["tournaments"]))
                    
                    data["tournaments"] = new_tournaments
                    
                    if save_data(data):
                        st.success(f"✅ Re-fetched {success_count} tournaments ({error_count} errors)")
                        st.rerun()
                    else:
                        st.error("Failed to save re-fetched data.")
        
        st.markdown("---")
        st.markdown("### 🗑️ Danger Zone")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Clear All Character Names", type="secondary"):
                data["character_names"] = {}
                if save_data(data):
                    st.success("Character names cleared.")
                    st.rerun()
        
        with col2:
            if st.button("🗑️ Clear All Player Aliases", type="secondary"):
                data["player_aliases"] = {}
                if save_data(data):
                    st.success("Player aliases cleared.")
                    st.rerun()
        
        st.markdown("---")
        
        # Show raw data stats
        st.markdown("### 📊 Data Statistics")
        st.write(f"- **Tournaments:** {len(data.get('tournaments', []))}")
        st.write(f"- **Seasons:** {len(data.get('seasons', []))}")
        st.write(f"- **Player Aliases:** {len(data.get('player_aliases', {}))}")
        st.write(f"- **Character Mappings:** {len(data.get('character_names', {}))}")
        
        st.markdown("### ☁️ GitHub Connection")
        config = get_github_config()
        st.write(f"- **Repo:** {config.get('repo', 'Not set')}")
        st.write(f"- **Token:** {'✅ Set' if config.get('token') else '❌ Not set'}")
        st.write(f"- **Load Status:** {st.session_state.get('github_load_status', 'unknown')}")
        st.write(f"- **File SHA:** {st.session_state.get('github_sha', 'None')[:12] if st.session_state.get('github_sha') else 'None'}...")
        st.write(f"- **Rate Limit Remaining:** {st.session_state.get('github_rate_limit', 'unknown')}")

def show_aliases_page(data, registry):
    st.title("🔗 Manage Player Aliases")
    
    current_aliases = data.get("player_aliases", {})
    
    st.subheader("📋 Current Aliases")
    
    if current_aliases:
        for display_name, aliases in current_aliases.items():
            col1, col2, col3 = st.columns([2, 3, 1])
            with col1:
                st.write(f"**{display_name}**")
            with col2:
                st.write(f"= {', '.join(aliases)}")
            with col3:
                if st.button("🗑️", key=f"del_alias_{display_name}"):
                    del data["player_aliases"][display_name]
                    save_data(data)
                    st.rerun()
    else:
        st.info("No manual aliases configured.")
    
    st.markdown("---")
    st.subheader("➕ Add Alias")
    
    all_names = set()
    for tourney in data["tournaments"]:
        for event in tourney.get("events", []):
            for standing in event.get("standings", []):
                entrant = standing.get("entrant") or {}
                if entrant.get("name"):
                    all_names.add(entrant["name"])
    
    all_names = sorted(list(all_names))
    
    col1, col2 = st.columns(2)
    
    with col1:
        primary_name = st.selectbox("Primary name:", [""] + all_names)
    with col2:
        available = [n for n in all_names if n != primary_name]
        alias_names = st.multiselect("Aliases:", available)
    
    if st.button("➕ Add Alias", disabled=not primary_name or not alias_names):
        if "player_aliases" not in data:
            data["player_aliases"] = {}
        existing = data["player_aliases"].get(primary_name, [])
        data["player_aliases"][primary_name] = list(set(existing + alias_names))
        if save_data(data):
            st.success(f"✅ Linked aliases to {primary_name}")
            st.rerun()

if __name__ == "__main__":
    main()
