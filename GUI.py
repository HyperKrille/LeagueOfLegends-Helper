import time
import requests
import urllib3
from lcu_driver import Connector
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

connector = Connector()

# Global variables
global champions_map, client_connected, client_closed, gui
champions_map = {}
client_connected = False  # Tracks if the client is connected
client_closed = False  # Tracks if the client has been closed


class GameState:
    """Class to manage game-related states."""
    def __init__(self):
        self.am_i_assigned = False
        self.am_i_banning = False
        self.am_i_picking = False
        self.phase = ''
        self.in_game = False
        self.action_id = None
        self.current_lobby_state = "NONE"
        self.current_assigned_position = "NONE"

    def reset(self):
        """Reset all states to default values."""
        self.am_i_assigned = False
        self.am_i_banning = False
        self.am_i_picking = False
        self.phase = ''
        self.in_game = False
        self.action_id = None
        self.current_lobby_state = "NONE"
        self.current_assigned_position = "NONE"


# Create a global instance of GameState
game_state = GameState()


class LeagueGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("League Client Status")
        self.root.geometry("650x900")

        # Apply a modern theme
        style = ttk.Style()
        style.theme_use("clam")

        # Define roles
        self.roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
        self.role_labels = {
            "TOP": "Top Lane",
            "JUNGLE": "Jungle",
            "MIDDLE": "Mid Lane",
            "BOTTOM": "Bot Lane",
            "UTILITY": "Support"
        }

        # Variables
        self.summoner_name = tk.StringVar(value="Waiting for connection...")
        self.game_status = tk.StringVar(value="Not Connected")
        self.champ_select_phase = tk.StringVar(value="N/A")
        self.selected_roles = tk.StringVar(value="Roles: N/A")
        self.auto_accept_var = tk.BooleanVar(value=False)

        # Role-specific variables
        self.role_configs = {
            role: {
                "ban_var": tk.StringVar(value="None"),
                "pick_var": tk.StringVar(value="None"),
                "ban_search_var": tk.StringVar(),
                "pick_search_var": tk.StringVar()
            }
            for role in self.roles
        }

        # Top frame for summoner info and game status
        info_frame = ttk.LabelFrame(root, text="Game Information", padding=10)
        info_frame.pack(pady=10, padx=10, fill="x")

        # Summoner Info
        ttk.Label(info_frame, text="Summoner:", font=("Arial", 11, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.summoner_label = ttk.Label(info_frame, textvariable=self.summoner_name, font=("Arial", 11))
        self.summoner_label.grid(row=0, column=1, sticky="w", padx=5)

        # Game Status
        ttk.Label(info_frame, text="Game Status:", font=("Arial", 10)).grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.status_label = ttk.Label(info_frame, textvariable=self.game_status, font=("Arial", 10, "bold"))
        self.status_label.grid(row=1, column=1, sticky="w", padx=5)

        # Selected Roles
        ttk.Label(info_frame, text="Selected Roles:", font=("Arial", 10)).grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.roles_label = ttk.Label(info_frame, textvariable=self.selected_roles, font=("Arial", 10))
        self.roles_label.grid(row=2, column=1, sticky="w", padx=5)

        # Champion Select Phase
        ttk.Label(info_frame, text="Champion Select Phase:", font=("Arial", 10)).grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.phase_label = ttk.Label(info_frame, textvariable=self.champ_select_phase, font=("Arial", 10))
        self.phase_label.grid(row=3, column=1, sticky="w", padx=5)

        # Auto-Accept Checkbox
        self.auto_accept_button = ttk.Checkbutton(info_frame, text="Auto-Accept Matches", variable=self.auto_accept_var)
        self.auto_accept_button.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        # Notebook (Tabbed View for Roles)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, padx=10, fill="both", expand=True)

        # Create a tab for each role
        self.role_tabs = {}
        for role in self.roles:
            tab = ttk.Frame(self.notebook, padding=10)
            self.role_tabs[role] = tab
            self.notebook.add(tab, text=self.role_labels[role])
            self.setup_role_tab(role, tab)

        # Status Log Frame
        log_frame = ttk.LabelFrame(root, text="Status Log", padding=10)
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=10, width=60, wrap="word", font=("Arial", 10))
        self.log_text.pack(pady=5, padx=5, fill="both", expand=True)

        # # Scrollbar for log
        # scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        # scrollbar.pack(side="right", fill="y")
        # self.log_text.config(yscrollcommand=scrollbar.set)

        # Quit Button
        self.quit_button = ttk.Button(root, text="Quit", command=self.quit_program, style="TButton")
        self.quit_button.pack(pady=10)

        # Load configuration
        self.load_configuration()

        # Start the GUI update loop
        self.update_gui()

    def setup_role_tab(self, role, tab):
        """Set up the widgets for a role tab."""
        # Auto-Ban Section
        auto_ban_frame = ttk.LabelFrame(tab, text="Auto-Ban Champion")
        auto_ban_frame.pack(pady=10, padx=10, fill="x")

        ttk.Label(auto_ban_frame, text="Search:").pack(pady=2)
        ban_search_entry = ttk.Entry(auto_ban_frame, textvariable=self.role_configs[role]["ban_search_var"])
        ban_search_entry.pack(pady=2, fill="x")

        auto_ban_dropdown = ttk.Combobox(auto_ban_frame, textvariable=self.role_configs[role]["ban_var"])
        auto_ban_dropdown['values'] = ["None"] + list(champions_map.keys())
        auto_ban_dropdown.pack(pady=5, fill="x")

        # Auto-Pick Section
        auto_pick_frame = ttk.LabelFrame(tab, text="Auto-Pick Champion")
        auto_pick_frame.pack(pady=10, padx=10, fill="x")

        ttk.Label(auto_pick_frame, text="Search:").pack(pady=2)
        pick_search_entry = ttk.Entry(auto_pick_frame, textvariable=self.role_configs[role]["pick_search_var"])
        pick_search_entry.pack(pady=2, fill="x")

        auto_pick_dropdown = ttk.Combobox(auto_pick_frame, textvariable=self.role_configs[role]["pick_var"])
        auto_pick_dropdown['values'] = ["None"] + list(champions_map.keys())
        auto_pick_dropdown.pack(pady=5, fill="x")

        # Store references to the dropdowns
        self.role_configs[role]["ban_dropdown"] = auto_ban_dropdown
        self.role_configs[role]["pick_dropdown"] = auto_pick_dropdown

        # Bind search boxes to filter functions
        ban_search_entry.bind('<KeyRelease>', lambda event, r=role: self.filter_dropdown(r, "ban"))
        pick_search_entry.bind('<KeyRelease>', lambda event, r=role: self.filter_dropdown(r, "pick"))

        # Bind dropdowns to save config when changed
        auto_ban_dropdown.bind("<<ComboboxSelected>>", lambda event: self.save_configuration())
        auto_pick_dropdown.bind("<<ComboboxSelected>>", lambda event: self.save_configuration())

    def filter_dropdown(self, role, dropdown_type):
        """Filter the champion dropdown based on search text."""
        if dropdown_type == "ban":
            search_text = self.role_configs[role]["ban_search_var"].get().lower()
            dropdown = self.role_configs[role]["ban_dropdown"]
        else:  # pick
            search_text = self.role_configs[role]["pick_search_var"].get().lower()
            dropdown = self.role_configs[role]["pick_dropdown"]

        filtered_champs = [champ for champ in champions_map.keys() if search_text in champ.lower()]
        dropdown['values'] = ["None"] + filtered_champs

    def log_message(self, message):
        """Add a message to the log with timestamp."""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)  # Auto-scroll to the end

    def load_configuration(self):
        """Load role-specific configuration from file."""
        try:
            if os.path.exists("role_config.json"):
                with open("role_config.json", "r") as file:
                    config = json.load(file)

                    # Load role configurations
                    for role in self.roles:
                        if role in config:
                            if "ban" in config[role]:
                                self.role_configs[role]["ban_var"].set(config[role]["ban"])
                            if "pick" in config[role]:
                                self.role_configs[role]["pick_var"].set(config[role]["pick"])

                    # Load auto accept setting
                    if "auto_accept" in config:
                        self.auto_accept_var.set(config["auto_accept"])

                self.log_message("Configuration loaded successfully")
            else:
                self.log_message("No configuration file found. Using default settings.")
        except Exception as e:
            self.log_message(f"Error loading configuration: {e}")

    def save_configuration(self):
        """Save role-specific configuration to file."""
        try:
            config = {"auto_accept": self.auto_accept_var.get()}

            # Save role configurations
            for role in self.roles:
                config[role] = {
                    "ban": self.role_configs[role]["ban_var"].get(),
                    "pick": self.role_configs[role]["pick_var"].get()
                }

            with open("role_config.json", "w") as file:
                json.dump(config, file, indent=4)

            self.log_message("Configuration saved")
        except Exception as e:
            self.log_message(f"Error saving configuration: {e}")

    def update_gui(self):
        """Update the GUI periodically."""
        # Update notebook selection based on assigned role
        if game_state.current_assigned_position in self.roles:
            # Find the index of the tab that corresponds to the current role
            for i, role in enumerate(self.roles):
                if role == game_state.current_assigned_position:
                    self.notebook.select(i)
                    break

        # Schedule the function to run again after 1 second
        self.root.after(1000, self.update_gui)

    def update_champion_dropdowns(self):
        """Update all champion dropdowns with the current champion list."""
        for role in self.roles:
            ban_dropdown = self.role_configs[role]["ban_dropdown"]
            pick_dropdown = self.role_configs[role]["pick_dropdown"]

            # Preserve current selections
            current_ban = self.role_configs[role]["ban_var"].get()
            current_pick = self.role_configs[role]["pick_var"].get()

            # Update the dropdown values
            ban_dropdown['values'] = ["None"] + list(champions_map.keys())
            pick_dropdown['values'] = ["None"] + list(champions_map.keys())

            # Restore selections if they still exist in the new champion list
            if current_ban in champions_map or current_ban == "None":
                self.role_configs[role]["ban_var"].set(current_ban)
            else:
                self.role_configs[role]["ban_var"].set("None")

            if current_pick in champions_map or current_pick == "None":
                self.role_configs[role]["pick_var"].set(current_pick)
            else:
                self.role_configs[role]["pick_var"].set("None")

    def quit_program(self):
        """Handle program exit."""
        # Save configuration before exiting
        self.save_configuration()
        # Stop the LCU connector
        asyncio.run_coroutine_threadsafe(connector.stop(), loop)
        # Close the GUI
        self.root.destroy()


async def check_game_phase(connection):
    """Continuously checks for the current game phase with reduced API calls."""
    global gui, game_state, client_connected

    # Track last known states to avoid redundant API calls
    last_champ_select_status = 0
    last_matchmaking_status = 0
    last_game_check_time = 0

    while client_connected:  # Only run while client is connected
        try:
            current_time = time.time()
            game_running = False

            # Only check if in game every 5 seconds
            if not game_state.in_game and current_time - last_game_check_time >= 5:
                last_game_check_time = current_time
                try:
                    game_check = requests.get('https://127.0.0.1:2999/liveclientdata/activeplayer',
                                              verify=False, timeout=1)
                    game_running = game_check.status_code == 200
                except:
                    game_running = False

            # If we're in a game, only check game status, not the other endpoints
            if game_running and not game_state.in_game:
                game_state.in_game = True
                game_state.current_lobby_state = "IN_GAME"
                gui.game_status.set("In Game")
                gui.log_message("Game detected - now in active game")

                # Play music if configured (only check once when entering game)
                try:
                    with open("music.txt", "r") as f:
                        music_url = f.readline().strip()
                        if music_url:
                            webbrowser.open(music_url, new=0, autoraise=True)
                            gui.log_message("Playing music")
                except Exception as e:
                    gui.log_message(f"Error opening music: {e}")

                # In game - sleep longer and only check game status
                await asyncio.sleep(5)
                continue

            # If already in game, only check if game has ended
            if game_state.in_game:
                try:
                    game_check = requests.get('https://127.0.0.1:2999/liveclientdata/activeplayer',
                                              verify=False, timeout=1)
                    if game_check.status_code != 200:
                        game_state.in_game = False
                        game_state.reset()  # Reset states when the game ends
                        gui.log_message("Game has ended")
                except:
                    game_state.in_game = False
                    game_state.reset()  # Reset states when the game ends
                    gui.log_message("Game has ended")

                # Check less frequently while in game
                await asyncio.sleep(5)
                continue

            # If not in game, check other states with reduced frequency

            # Only check champ select if we're not known to be in it
            if game_state.current_lobby_state != "CHAMP_SELECT":
                champ_select = await connection.request('get', '/lol-champ-select/v1/session')
                last_champ_select_status = champ_select.status

                if last_champ_select_status == 200 and game_state.current_lobby_state != "CHAMP_SELECT":
                    game_state.current_lobby_state = "CHAMP_SELECT"
                    gui.game_status.set("In Champion Select")
                    gui.log_message("Now in champion select")

                    # Champion select detected - no need to check matchmaking
                    await asyncio.sleep(3)
                    continue

            # Only check matchmaking if we're not known to be in queue
            if game_state.current_lobby_state != "MATCHMAKING" and game_state.current_lobby_state != "CHAMP_SELECT":
                matchmaking = await connection.request('get', '/lol-matchmaking/v1/search')
                last_matchmaking_status = matchmaking.status

                if last_matchmaking_status == 200 and game_state.current_lobby_state != "MATCHMAKING":
                    game_state.current_lobby_state = "MATCHMAKING"
                    gui.game_status.set("In Queue")
                    gui.log_message("Searching for a match")

                    # In queue - check more frequently for ready check
                    await asyncio.sleep(2)
                    continue

            # If we're not in any of the above states, assume lobby
            if game_state.current_lobby_state != "LOBBY" and last_champ_select_status != 200 and last_matchmaking_status != 200:
                game_state.current_lobby_state = "LOBBY"
                gui.game_status.set("In Lobby")
                gui.log_message("Now in lobby")

        except Exception as e:
            if str(e) != "" and client_connected:  # Only log if client is connected
                gui.log_message(f"Error checking game phase: {e}")
            await asyncio.sleep(5)  # Add delay after errors

        # Adaptive sleep time based on current state
        if game_state.current_lobby_state == "MATCHMAKING":
            await asyncio.sleep(2)  # Check more frequently in queue for ready check
        elif game_state.current_lobby_state == "CHAMP_SELECT":
            await asyncio.sleep(3)  # Moderate frequency in champ select
        else:
            await asyncio.sleep(5)  # Longer delay in lobby or other states


async def update_lobby_info(connection):
    """Updates lobby info with reduced API calls."""
    global gui, game_state, client_connected

    # Track the last time we updated lobby info
    last_update_time = 0

    while client_connected:  # Only run while client is connected
        try:
            current_time = time.time()

            # Skip checking if in game or if recently checked
            if game_state.in_game or game_state.current_lobby_state == "NONE" or current_time - last_update_time < 5:
                await asyncio.sleep(3)
                continue

            # Only update lobby info when in LOBBY state to reduce API calls
            if game_state.current_lobby_state == "LOBBY":
                # Get the current lobby information
                lobby_info = await connection.request('get', '/lol-lobby/v2/lobby')
                last_update_time = current_time

                if lobby_info.status == 200:
                    lobby_info_json = await lobby_info.json()

                    # Check for valid lobby data
                    if 'gameConfig' in lobby_info_json:
                        # We have an active lobby
                        game_mode = lobby_info_json.get('gameConfig', {}).get('gameMode', 'Unknown')
                        queue_id = lobby_info_json.get('gameConfig', {}).get('queueId', 0)

                        gui.game_status.set(f"In Lobby - Mode: {game_mode} (Queue ID: {queue_id})")

                        # Fetch the player's selected roles from the localMember section
                        local_player_roles = "N/A"  # Default value
                        local_member = lobby_info_json.get('localMember', {})
                        first_role = local_member.get('firstPositionPreference', '')
                        second_role = local_member.get('secondPositionPreference', '')

                        if first_role or second_role:
                            local_player_roles = f"{first_role}, {second_role}"

                        # Update the roles label in the GUI
                        gui.selected_roles.set(f"Roles: {local_player_roles}")

        except Exception as e:
            if str(e) != "" and client_connected:  # Only log if client is connected
                gui.log_message(f"Error updating lobby info: {e}")
            await asyncio.sleep(5)  # Add delay after errors

        # Wait before fetching again - longer delay for this function
        await asyncio.sleep(5)


@connector.ws.register('/lol-gameflow/v1/gameflow-phase', event_types=('UPDATE',))
async def gameflow_changed(connection, event):
    global game_state, gui

    new_phase = event.data
    gui.log_message(f"Game flow phase changed: {new_phase}")

    # Reset tracking variables when leaving champion select
    if new_phase != "ChampSelect" and game_state.current_lobby_state == "CHAMP_SELECT":
        gui.log_message("Champion select ended - possible dodge or cancelled queue")
        game_state.reset()
        # Clear last ban/pick tracking to ensure they work in next champ select
        if hasattr(champ_select_changed, 'last_ban'):
            delattr(champ_select_changed, 'last_ban')
        if hasattr(champ_select_changed, 'last_pick'):
            delattr(champ_select_changed, 'last_pick')
        if hasattr(champ_select_changed, 'last_prepick'):
            delattr(champ_select_changed, 'last_prepick')
        if hasattr(champ_select_changed, 'last_role_config'):
            delattr(champ_select_changed, 'last_role_config')

@connector.ready
async def connect(connection):
    global client_connected, gui, champions_map
    client_connected = True  # Set flag when connected
    gui.game_status.set("Connected to League Client")
    gui.log_message("Connected to League Client")

    # Get the summoner name
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    gui.summoner_name.set(f"{summoner_data['gameName']}#{summoner_data['tagLine']}")
    gui.log_message(f"Connected as: {summoner_data['gameName']}#{summoner_data['tagLine']}")

    # Get the summoner ID and champion list
    summoner_id = summoner_data['summonerId']

    # Get the list of champions
    champion_list = await connection.request('get', f'/lol-champions/v1/inventories/{summoner_id}/champions-minimal')
    champion_list_to_json = await champion_list.json()

    # Populate the champions_map
    temp_champions_map = {}
    for champion in champion_list_to_json:
        temp_champions_map.update({champion['name']: champion['id']})
    champions_map = temp_champions_map
    gui.log_message(f"Champions loaded: {len(champions_map)}")

    # Update the dropdowns with the champions list
    gui.update_champion_dropdowns()

    # Make sure states are reset on startup
    game_state.reset()

    # Start the update loops
    asyncio.create_task(update_lobby_info(connection))
    asyncio.create_task(check_game_phase(connection))


@connector.ws.register('/lol-matchmaking/v1/ready-check', event_types=('UPDATE',))
async def ready_check_changed(connection, event):
    if event.data['state'] == 'InProgress' and event.data['playerResponse'] == 'None':
        if gui.auto_accept_var.get():  # Check if auto-accept is enabled
            await connection.request('post', '/lol-matchmaking/v1/ready-check/accept', data={})
            gui.log_message("Match auto-accepted!")
        else:
            gui.log_message("Match ready check appeared, but auto-accept is off.")


@connector.ws.register('/lol-champ-select/v1/session', event_types=('CREATE', 'UPDATE', 'DELETE'))
async def champ_select_changed(connection, event):
    global game_state, gui

    # Check if the session is deleted (queue dodged)
    if event.type == 'DELETE':
        gui.log_message("Champion select ended - session deleted")
        game_state.reset()  # Reset states when champion select ends
        return

    # Handle champion select
    try:
        lobby_phase = event.data['timer']['phase']
        gui.champ_select_phase.set(lobby_phase)

        # Update the current state if it changed
        if game_state.current_lobby_state != "CHAMP_SELECT":
            game_state.current_lobby_state = "CHAMP_SELECT"
            gui.game_status.set(f"Champion Select - {lobby_phase}")
            gui.log_message(f"Champion select phase: {lobby_phase}")

        # Only proceed if we have a valid localPlayerCellId
        if 'localPlayerCellId' in event.data and event.data['localPlayerCellId'] is not None:
            local_player_cell_id = event.data['localPlayerCellId']

            # Check assigned position
            for teammate in event.data['myTeam']:
                if teammate['cellId'] == local_player_cell_id:
                    # Get the assigned position from the client
                    #teammate['assignedPosition'] = 'jungle' #for testing
                    assigned_position = teammate.get('assignedPosition', '').upper()  # Ensure uppercase for consistency

                    # Convert empty string to 'Unknown' for better logging
                    if not assigned_position:
                        assigned_position = 'UNKNOWN'

                    # Update the assigned position if it's changed
                    if not game_state.am_i_assigned or game_state.current_assigned_position != assigned_position:
                        game_state.am_i_assigned = True
                        game_state.current_assigned_position = assigned_position
                        gui.log_message(f"Assigned position: {assigned_position}")

                        # If valid position, auto-select the corresponding tab
                        if assigned_position in gui.roles:
                            for i, role in enumerate(gui.roles):
                                if role == assigned_position:
                                    gui.notebook.select(i)
                                    gui.log_message(f"Switched to {assigned_position} tab")
                                    break

            # Find our current action
            for action_group in event.data['actions']:
                for action in action_group:
                    if action['actorCellId'] == local_player_cell_id and action['isInProgress'] == True:
                        # Only log if this is a new phase
                        if game_state.phase != action['type']:
                            game_state.phase = action['type']
                            gui.log_message(f"Your turn to {game_state.phase.upper()}")

                        game_state.action_id = action['id']

                        if game_state.phase == 'ban':
                            game_state.am_i_banning = action['isInProgress']
                        if game_state.phase == 'pick':
                            game_state.am_i_picking = action['isInProgress']

            # Get the role-specific champions based on assigned position
            role_config = None

            # First try to use the assigned position from the client
            if game_state.current_assigned_position in gui.roles:
                role_config = gui.role_configs[game_state.current_assigned_position]
                if not hasattr(champ_select_changed, 'last_role_config') or champ_select_changed.last_role_config != game_state.current_assigned_position:
                    gui.log_message(f"Using champion settings for assigned role: {game_state.current_assigned_position}")
                    champ_select_changed.last_role_config = game_state.current_assigned_position  # Track last used role config
            else:
                # If no valid assigned position, log a warning but don't fall back to another role
                if not hasattr(champ_select_changed, 'last_role_config') or champ_select_changed.last_role_config != 'UNKNOWN':
                    gui.log_message(f"No valid assigned role detected. Assigned position: {game_state.current_assigned_position}")
                    champ_select_changed.last_role_config = 'UNKNOWN'  # Track last used role config

            # Auto-ban logic
            if game_state.phase == 'ban' and lobby_phase == 'BAN_PICK' and game_state.am_i_banning and game_state.action_id is not None and role_config:
                selected_ban = role_config["ban_var"].get()
                if selected_ban != "None" and selected_ban in champions_map:
                    try:
                        # Don't check for last_ban to ensure it always attempts to ban
                        await connection.request('patch',
                                                 f'/lol-champ-select/v1/session/actions/{game_state.action_id}',
                                                 data={"championId": champions_map[selected_ban], "completed": True})
                        gui.log_message(f"Auto-banned {selected_ban}")
                        champ_select_changed.last_ban = selected_ban  # Track last banned champion
                    except Exception as e:
                        gui.log_message(f"Error auto-banning {selected_ban}: {e}")
                game_state.am_i_banning = False

            # Auto-pick logic
            if game_state.phase == 'pick' and lobby_phase == 'BAN_PICK' and game_state.am_i_picking and game_state.action_id is not None and role_config:
                selected_pick = role_config["pick_var"].get()
                if selected_pick != "None" and selected_pick in champions_map:
                    try:
                        # Don't check for last_pick to ensure it always attempts to pick
                        await connection.request('patch',
                                                 f'/lol-champ-select/v1/session/actions/{game_state.action_id}',
                                                 data={"championId": champions_map[selected_pick], "completed": True})
                        gui.log_message(f"Auto-picked {selected_pick}")
                        champ_select_changed.last_pick = selected_pick  # Track last picked champion
                    except Exception as e:
                        gui.log_message(f"Error auto-picking {selected_pick}: {e}")
                game_state.am_i_picking = False

            # Pre-pick in PLANNING phase
            if lobby_phase == 'PLANNING' and game_state.action_id is not None and role_config:
                selected_pick = role_config["pick_var"].get()
                if selected_pick != "None" and selected_pick in champions_map:
                    if not hasattr(champ_select_changed, 'last_prepick') or champ_select_changed.last_prepick != selected_pick:
                        try:
                            await connection.request('patch', f'/lol-champ-select/v1/session/actions/{game_state.action_id}',
                                                     data={"championId": champions_map[selected_pick], "completed": False})
                            gui.log_message(f"Pre-picked {selected_pick}")
                            champ_select_changed.last_prepick = selected_pick  # Track last pre-picked champion
                        except Exception as e:
                            gui.log_message(f"Error pre-picking {selected_pick}: {e}")

        # Set up game start detection for finalization phase
        if lobby_phase == 'FINALIZATION' and game_state.current_lobby_state != "GAME_STARTING":
            game_state.current_lobby_state = "GAME_STARTING"
            gui.game_status.set("Game Starting...")
            gui.log_message("Game is about to start")

    except Exception as e:
        gui.log_message(f"Error in champ select: {e}")


@connector.close
async def disconnect(_):
    global client_connected, client_closed
    client_connected = False  # Clear flag when disconnected
    if not client_closed:
        gui.log_message('The League client has been closed!')
        client_closed = True
    await connector.stop()


# Function to start the LCU connector in a separate thread
def start_connector():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connector.start())

# Start the GUI
root = tk.Tk()
gui = LeagueGUI(root)  # Create the GUI object

# Start the LCU connector in a separate thread
connector_thread = threading.Thread(target=start_connector)
connector_thread.daemon = True  # Daemonize thread to exit when the main program exits
connector_thread.start()


# Handle window close event
root.protocol("WM_DELETE_WINDOW", gui.quit_program)

root.mainloop()