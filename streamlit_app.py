"""
🎮 Smash Tournament Season Rankings
A Streamlit app for tracking and analyzing tournament results
Version 2.0 - With player ID tracking and profiles
"""

import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import io

# Page config
st.set_page_config(
    page_title="Season Rankings",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# DATA STORAGE
# =============================================================================

DATA_FILE = Path("data/tournaments.json")

def load_data():
    """Load tournament data from file"""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "tournaments": [],
        "settings": get_default_settings(),
        "player_aliases": {}  # Manual alias overrides: {"display_name": ["alt_name1", "alt_name2"]}
    }

def save_data(data):
    """Save tournament data to file"""
    DATA_FILE.parent.mkdir(exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

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
        "min_tournaments": 1
    }

# =============================================================================
# PLAYER IDENTITY TRACKING
# =============================================================================

def build_player_registry(tournaments: list, manual_aliases: dict) -> dict:
    """
    Build a registry mapping user_ids and names to canonical player identities.
    
    Returns: {
        "by_user_id": {user_id: canonical_name},
        "by_name": {any_name: canonical_name},
        "profiles": {canonical_name: {user_id, all_tags, ...}}
    }
    """
    registry = {
        "by_user_id": {},
        "by_name": {},
        "profiles": {}
    }
    
    # First pass: collect all user_ids and their associated names
    user_id_to_names = {}  # {user_id: set of names}
    name_to_user_ids = {}  # {name: set of user_ids}
    
    for tourney in tournaments:
        for event in tourney.get("events", []):
            # From standings
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
            
            # From entrants (if available)
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
    
    # Build canonical names (use most recent or most common tag)
    for user_id, names in user_id_to_names.items():
        # Pick the longest name as canonical (usually includes prefix)
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
    
    # Apply manual aliases (overrides)
    for display_name, aliases in manual_aliases.items():
        for alias in aliases:
            registry["by_name"][alias] = display_name
        
        # Also add the display_name itself
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
    
    # Add any names not yet in registry (no user_id found)
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
        """Extract tournament slug from Start.gg URL"""
        import re
        url = url.rstrip('/')
        match = re.search(r'start\.gg/tournament/([^/]+)', url)
        if not match:
            raise ValueError(f"Could not extract tournament slug from URL: {url}")
        return match.group(1)
    
    def export_tournament(self, url: str, progress_callback=None) -> dict:
        """Export tournament data from Start.gg"""
        tournament_slug = self.extract_tournament_slug(url)
        
        if progress_callback:
            progress_callback("Fetching tournament info...")
        
        # Get tournament and events
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
        
        # Find Singles event
        singles_event = None
        for event in events:
            if event["name"].lower() == "singles":
                singles_event = event
                break
        
        if not singles_event:
            # If no "Singles" event, take the first one
            if events:
                singles_event = events[0]
            else:
                raise Exception("No events found in this tournament")
        
        event_id = singles_event["id"]
        
        if progress_callback:
            progress_callback(f"Processing event: {singles_event['name']}...")
        
        # Get entrants (with user IDs!)
        entrants = self._get_entrants(event_id, progress_callback)
        
        # Get standings
        standings = self._get_standings(event_id, progress_callback)
        
        # Get phases and sets
        phases = self._get_phases(event_id)
        all_sets = []
        
        for phase in phases:
            phase_sets = self._get_phase_sets(phase["id"], phase["name"], progress_callback)
            all_sets.extend(phase_sets)
        
        # Build export data
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
        """Get event entrants with user IDs"""
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
                      user {
                        id
                        name
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
        """Get event standings with user IDs"""
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
                        user {
                          id
                          name
                        }
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
        """Get event phases"""
        query = """
        query EventPhases($eventId: ID!) {
          event(id: $eventId) {
            phases {
              id
              name
              state
            }
          }
        }
        """
        
        result = self._make_request(query, {"eventId": event_id})
        return result.get("data", {}).get("event", {}).get("phases", [])
    
    def _get_phase_sets(self, phase_id: int, phase_name: str, progress_callback=None) -> list:
        """Get sets from a phase via phase groups"""
        if progress_callback:
            progress_callback(f"Fetching matches from {phase_name}...")
        
        # First get phase groups
        pg_query = """
        query PhaseGroups($phaseId: ID!) {
          phase(id: $phaseId) {
            phaseGroups {
              nodes { id displayIdentifier }
            }
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
                    result = self._make_request(sets_query, {
                        "pgId": pg_id,
                        "page": page
                    })
                    
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

def calculate_rankings(tournaments: list, settings: dict, registry: dict) -> pd.DataFrame:
    """Calculate season rankings from tournament data with player identity merging"""
    if not tournaments:
        return pd.DataFrame()
    
    points_map = settings["points"]
    player_data = {}
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        tourney_date = tourney["tournament"].get("startAt", 0)
        
        for event in tourney.get("events", []):
            # Only process Singles
            if event.get("name", "").lower() != "singles":
                continue
            
            num_entrants = event.get("numEntrants", 0)
            
            for standing in event.get("standings", []):
                placement = standing.get("placement")
                entrant = standing.get("entrant") or {}
                
                if not entrant:
                    continue
                
                # Get canonical player name using registry
                raw_name = entrant.get("name", "Unknown")
                player_name = get_canonical_name(raw_name, registry)
                
                # Initialize player data
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
                
                # Calculate points for this placement
                base_points = 0
                for place_str, pts in sorted(points_map.items(), key=lambda x: int(x[0])):
                    place = int(place_str)
                    if placement <= place:
                        base_points = pts
                        break
                
                # Apply attendance scaling if enabled
                if settings.get("attendance_scaling") and num_entrants > 0:
                    scaling_base = settings.get("scaling_base", 32)
                    scale_factor = num_entrants / scaling_base
                    base_points = int(base_points * scale_factor)
                
                # Store result
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
        
        # Apply "best N" if enabled
        if settings.get("best_n_enabled"):
            best_n = settings.get("best_n", 6)
            results = results[:best_n]
        
        # Apply "drop worst" if enabled
        if settings.get("drop_worst") and len(results) > 1:
            results = results[:-1]
        
        data["total_points"] = sum(r["points"] for r in results)
    
    # Filter by minimum tournaments
    min_tournaments = settings.get("min_tournaments", 1)
    player_data = {k: v for k, v in player_data.items() if v["tournaments_played"] >= min_tournaments}
    
    # Convert to DataFrame
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

def get_player_details(tournaments: list, player_name: str, registry: dict) -> dict:
    """Get detailed stats for a single player"""
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
        "notable_wins": [],  # Wins against top players
        "recent_sets": []
    }
    
    placements = []
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        tourney_date = tourney["tournament"].get("startAt", 0)
        
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            # Find this player's standing
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
            
            # Find sets involving this player
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
    
    # Sort results by date
    details["results"] = sorted(details["results"], key=lambda x: x.get("date", 0), reverse=True)
    details["recent_sets"] = details["recent_sets"][:20]  # Last 20 sets
    
    return details

def get_head_to_head(tournaments: list, player1: str, player2: str, registry: dict) -> dict:
    """Get head-to-head record between two players"""
    h2h = {
        "player1": player1,
        "player2": player2,
        "p1_wins": 0,
        "p2_wins": 0,
        "sets": []
    }
    
    for tourney in tournaments:
        tourney_name = tourney["tournament"]["name"]
        
        for event in tourney.get("events", []):
            if event.get("name", "").lower() != "singles":
                continue
            
            for set_data in event.get("sets", []):
                slots = set_data.get("slots") or []
                
                if len(slots) != 2:
                    continue
                
                # Safely get names with null handling
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
    # Load data
    data = load_data()
    
    # Build player registry
    registry = build_player_registry(
        data["tournaments"],
        data.get("player_aliases", {})
    )
    
    # Sidebar
    with st.sidebar:
        st.title("🎮 Season Rankings")
        st.markdown("---")
        
        # Navigation
        page = st.radio(
            "Navigation",
            ["🏆 Rankings", "➕ Add Tournament", "👤 Players", "🥊 Head-to-Head", "📋 Tournaments", "⚙️ Settings", "🔗 Manage Aliases"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        st.caption(f"📊 {len(data['tournaments'])} tournaments")
        st.caption(f"👥 {len(registry['profiles'])} players")
    
    # Main content
    if page == "🏆 Rankings":
        show_rankings_page(data, registry)
    elif page == "➕ Add Tournament":
        show_add_tournament_page(data)
    elif page == "👤 Players":
        show_players_page(data, registry)
    elif page == "🥊 Head-to-Head":
        show_head_to_head_page(data, registry)
    elif page == "📋 Tournaments":
        show_tournaments_page(data)
    elif page == "⚙️ Settings":
        show_settings_page(data)
    elif page == "🔗 Manage Aliases":
        show_aliases_page(data, registry)

def show_rankings_page(data, registry):
    """Display the main rankings page"""
    st.title("🏆 Season Rankings")
    
    if not data["tournaments"]:
        st.info("No tournaments added yet. Go to '➕ Add Tournament' to get started!")
        return
    
    # Calculate rankings
    settings = data.get("settings", get_default_settings())
    df = calculate_rankings(data["tournaments"], settings, registry)
    
    if df.empty:
        st.warning("No ranking data available.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tournaments", len(data["tournaments"]))
    with col2:
        st.metric("Players", len(df))
    with col3:
        total_sets = sum(
            len(event.get("sets", []))
            for t in data["tournaments"]
            for event in t.get("events", [])
        )
        st.metric("Total Sets", total_sets)
    with col4:
        if len(df) > 0:
            st.metric("Leader", df.iloc[0]["Player"])
    
    st.markdown("---")
    
    # Rankings table
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
    
    # Export buttons
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Excel export
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Rankings', index=False)
            
            # Tournament summary sheet
            tourney_df = pd.DataFrame([
                {
                    "Tournament": t["tournament"]["name"],
                    "Date": datetime.fromtimestamp(t["tournament"].get("startAt", 0)).strftime("%Y-%m-%d") if t["tournament"].get("startAt") else "N/A",
                    "Entrants": t["events"][0].get("numEntrants", 0) if t.get("events") else 0,
                    "Winner": get_canonical_name(
                        next((s["entrant"]["name"] for s in t["events"][0].get("standings", []) if s.get("placement") == 1 and s.get("entrant")), "N/A"),
                        registry
                    ) if t.get("events") else "N/A"
                }
                for t in data["tournaments"]
            ])
            tourney_df.to_excel(writer, sheet_name='Tournaments', index=False)
        
        st.download_button(
            "📥 Export Excel",
            excel_buffer.getvalue(),
            file_name="season_rankings.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col2:
        # CSV export
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Export CSV",
            csv,
            file_name="season_rankings.csv",
            mime="text/csv"
        )

def show_add_tournament_page(data):
    """Page for adding new tournaments"""
    st.title("➕ Add Tournament")
    
    # Check for API key
    api_key = st.secrets.get("STARTGG_API_KEY", "")
    
    if not api_key:
        st.error("⚠️ Start.gg API key not configured!")
        st.markdown("""
        To add tournaments, you need to:
        1. Get your API key from [start.gg/admin/profile/developer](https://start.gg/admin/profile/developer)
        2. Add it to your Streamlit secrets (Settings → Secrets):
        ```toml
        STARTGG_API_KEY = "your_api_key_here"
        ```
        """)
        return
    
    st.markdown("Paste a Start.gg tournament URL to import it:")
    
    url = st.text_input(
        "Tournament URL",
        placeholder="https://www.start.gg/tournament/your-tournament/events",
        label_visibility="collapsed"
    )
    
    if st.button("➕ Add Tournament", type="primary", disabled=not url):
        with st.spinner("Importing tournament..."):
            try:
                progress = st.empty()
                
                def update_progress(msg):
                    progress.text(msg)
                
                exporter = StartGGExporter(api_key)
                tournament_data = exporter.export_tournament(url, update_progress)
                
                # Check if already exists
                existing_ids = [t["tournament"]["id"] for t in data["tournaments"]]
                if tournament_data["tournament"]["id"] in existing_ids:
                    st.warning(f"Tournament '{tournament_data['tournament']['name']}' is already added!")
                else:
                    data["tournaments"].append(tournament_data)
                    save_data(data)
                    
                    st.success(f"✅ Added: {tournament_data['tournament']['name']}")
                    
                    # Show summary
                    event = tournament_data["events"][0]
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Entrants", event.get("numEntrants", 0))
                    col2.metric("Sets", len(event.get("sets", [])))
                    col3.metric("Standings", len(event.get("standings", [])))
                    
                    st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Show existing tournaments
    if data["tournaments"]:
        st.markdown("---")
        st.subheader("📋 Loaded Tournaments")
        
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

def show_players_page(data, registry):
    """Page showing player profiles"""
    st.title("👤 Players")
    
    if not data["tournaments"]:
        st.info("No tournaments added yet.")
        return
    
    # Get all players
    all_players = sorted(registry.get("profiles", {}).keys())
    
    if not all_players:
        st.warning("No players found.")
        return
    
    # Player selector
    selected_player = st.selectbox(
        "Select a player:",
        all_players,
        index=0
    )
    
    if selected_player:
        details = get_player_details(data["tournaments"], selected_player, registry)
        profile = details.get("profile", {})
        
        st.markdown("---")
        
        # Player header
        st.header(selected_player)
        
        # Show aliases if any
        all_tags = profile.get("all_tags", [])
        if len(all_tags) > 1:
            other_tags = [t for t in all_tags if t != selected_player]
            st.caption(f"Also known as: {', '.join(other_tags)}")
        
        # Stats overview
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Events", details["tournaments_played"])
        col2.metric("Wins", details["total_wins"])
        col3.metric("Losses", details["total_losses"])
        win_rate = round(details["total_wins"] / (details["total_wins"] + details["total_losses"]) * 100, 1) if (details["total_wins"] + details["total_losses"]) > 0 else 0
        col4.metric("Win Rate", f"{win_rate}%")
        col5.metric("Best", f"#{details['best_placement']}" if details["best_placement"] < 999 else "N/A")
        
        st.markdown("---")
        
        # Tournament results
        st.subheader("📊 Tournament Results")
        
        if details["results"]:
            results_df = pd.DataFrame(details["results"])
            results_df["Date"] = results_df["date"].apply(
                lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d") if x else "N/A"
            )
            results_df["Placement"] = results_df["placement"].apply(lambda x: f"#{x}")
            
            st.dataframe(
                results_df[["tournament", "Date", "Placement", "entrants", "tag_used"]].rename(columns={
                    "tournament": "Tournament",
                    "entrants": "Entrants",
                    "tag_used": "Tag Used"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No tournament results found.")
        
        # Recent sets
        st.markdown("---")
        st.subheader("🎮 Recent Sets")
        
        if details["recent_sets"]:
            for set_info in details["recent_sets"][:10]:
                result_emoji = "✅" if set_info["won"] else "❌"
                st.write(f"{result_emoji} vs **{set_info['opponent']}** - {set_info['score']} ({set_info['round']} @ {set_info['tournament']})")
        else:
            st.info("No set data found.")

def show_head_to_head_page(data, registry):
    """Page for head-to-head lookup"""
    st.title("🥊 Head-to-Head")
    
    if not data["tournaments"]:
        st.info("No tournaments added yet.")
        return
    
    # Get all players
    all_players = sorted(registry.get("profiles", {}).keys())
    
    if len(all_players) < 2:
        st.warning("Need at least 2 players for head-to-head.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        player1 = st.selectbox("Player 1", all_players, key="p1")
    
    with col2:
        remaining_players = [p for p in all_players if p != player1]
        player2 = st.selectbox("Player 2", remaining_players, key="p2")
    
    if player1 and player2:
        h2h = get_head_to_head(data["tournaments"], player1, player2, registry)
        
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
                winner_emoji = "🏆"
                st.write(f"**{match['tournament']}** - {match['round']}")
                st.write(f"  {match['score']} → {winner_emoji} {match['winner']}")
        else:
            st.info("These players haven't faced each other yet.")

def show_tournaments_page(data):
    """Page showing all tournaments"""
    st.title("📋 Tournament History")
    
    if not data["tournaments"]:
        st.info("No tournaments added yet.")
        return
    
    # Sort by date
    tournaments = sorted(
        data["tournaments"],
        key=lambda t: t["tournament"].get("startAt", 0),
        reverse=True
    )
    
    for t in tournaments:
        tourney = t["tournament"]
        event = t["events"][0] if t.get("events") else {}
        
        date_str = ""
        if tourney.get("startAt"):
            date_str = datetime.fromtimestamp(tourney["startAt"]).strftime("%b %d, %Y")
        
        with st.expander(f"**{tourney['name']}** {('- ' + date_str) if date_str else ''}"):
            col1, col2, col3 = st.columns(3)
            col1.metric("Entrants", event.get("numEntrants", "N/A"))
            col2.metric("Sets", len(event.get("sets", [])))
            
            # Get winner
            winner = "N/A"
            for standing in event.get("standings", []):
                if standing.get("placement") == 1 and standing.get("entrant"):
                    winner = standing["entrant"]["name"]
                    break
            col3.metric("Winner", winner)
            
            # Top 8
            st.markdown("**Top 8:**")
            top8 = sorted(
                [s for s in event.get("standings", []) if s.get("placement", 99) <= 8],
                key=lambda s: s.get("placement", 99)
            )
            
            for s in top8:
                place = s.get("placement", "?")
                name = s.get("entrant", {}).get("name", "Unknown")
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
                st.write(f"{medal} {name}")

def show_settings_page(data):
    """Page for ranking settings"""
    st.title("⚙️ Ranking Settings")
    
    settings = data.get("settings", get_default_settings())
    
    st.subheader("🎯 Points System")
    st.caption("Adjust points awarded for each placement")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        settings["points"]["1"] = st.number_input("🥇 1st Place", value=settings["points"].get("1", 100), step=5)
        settings["points"]["2"] = st.number_input("🥈 2nd Place", value=settings["points"].get("2", 70), step=5)
        settings["points"]["3"] = st.number_input("🥉 3rd Place", value=settings["points"].get("3", 50), step=5)
    
    with col2:
        settings["points"]["4"] = st.number_input("4th Place", value=settings["points"].get("4", 40), step=5)
        settings["points"]["5"] = st.number_input("5th-6th Place", value=settings["points"].get("5", 30), step=5)
        settings["points"]["7"] = st.number_input("7th-8th Place", value=settings["points"].get("7", 20), step=5)
    
    with col3:
        settings["points"]["9"] = st.number_input("9th-12th Place", value=settings["points"].get("9", 10), step=5)
        settings["points"]["13"] = st.number_input("13th-16th Place", value=settings["points"].get("13", 5), step=5)
        settings["points"]["17"] = st.number_input("17th+ Place", value=settings["points"].get("17", 2), step=1)
    
    st.markdown("---")
    st.subheader("📊 Ranking Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        settings["attendance_scaling"] = st.checkbox(
            "📈 Scale points by attendance",
            value=settings.get("attendance_scaling", False),
            help="Larger tournaments award more points"
        )
        
        if settings["attendance_scaling"]:
            settings["scaling_base"] = st.slider(
                "Base attendance for 100% points",
                min_value=8, max_value=128, value=settings.get("scaling_base", 32),
                help="A tournament with this many entrants gives full points"
            )
        
        settings["drop_worst"] = st.checkbox(
            "🗑️ Drop worst result",
            value=settings.get("drop_worst", False),
            help="Exclude each player's worst tournament"
        )
    
    with col2:
        settings["best_n_enabled"] = st.checkbox(
            "🏅 Count best N tournaments only",
            value=settings.get("best_n_enabled", False),
            help="Only count top results"
        )
        
        if settings["best_n_enabled"]:
            settings["best_n"] = st.slider(
                "Number of tournaments to count",
                min_value=1, max_value=20, value=settings.get("best_n", 6)
            )
        
        settings["min_tournaments"] = st.slider(
            "Minimum tournaments to qualify",
            min_value=1, max_value=10, value=settings.get("min_tournaments", 1),
            help="Players must attend at least this many events"
        )
    
    st.markdown("---")
    
    if st.button("💾 Save Settings", type="primary"):
        data["settings"] = settings
        save_data(data)
        st.success("✅ Settings saved!")
        st.rerun()

def show_aliases_page(data, registry):
    """Page for managing player aliases"""
    st.title("🔗 Manage Player Aliases")
    
    st.markdown("""
    Use this page to manually link player tags that belong to the same person.
    
    The app automatically detects players using Start.gg user IDs, but sometimes 
    players create new accounts or the ID isn't tracked. Use this to fix those cases.
    """)
    
    st.markdown("---")
    
    # Show current aliases
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
    
    # Add new alias
    st.subheader("➕ Add Alias")
    
    # Get all known names
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
        primary_name = st.selectbox(
            "Primary name (to display):",
            [""] + all_names,
            help="This is the name that will be shown in rankings"
        )
    
    with col2:
        # Filter out the primary name
        available_aliases = [n for n in all_names if n != primary_name]
        alias_names = st.multiselect(
            "Aliases (same person):",
            available_aliases,
            help="Select all other tags this player uses"
        )
    
    if st.button("➕ Add Alias", disabled=not primary_name or not alias_names):
        if "player_aliases" not in data:
            data["player_aliases"] = {}
        
        # Merge with existing aliases if any
        existing = data["player_aliases"].get(primary_name, [])
        data["player_aliases"][primary_name] = list(set(existing + alias_names))
        save_data(data)
        st.success(f"✅ Linked {', '.join(alias_names)} to {primary_name}")
        st.rerun()
    
    st.markdown("---")
    
    # Show auto-detected groups
    st.subheader("🔍 Auto-Detected Player Groups")
    st.caption("These are players automatically linked by Start.gg user ID")
    
    for canonical, profile in registry.get("profiles", {}).items():
        tags = profile.get("all_tags", [])
        if len(tags) > 1 and canonical not in current_aliases:
            st.write(f"**{canonical}**: {', '.join(tags)}")

if __name__ == "__main__":
    main()
