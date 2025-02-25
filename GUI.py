import time
import requests
import urllib3
from lcu_driver import Connector
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import asyncio

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

connector = Connector()
global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, summoner_name, game_mode, champions_map, action_id, current_lobby_state
am_i_assigned = False
am_i_banning = False
am_i_picking = False
in_game = False
phase = ''
action_id = None
summoner_name = "Waiting for connection..."  # Initialize with a default value
game_mode = "Not Connected"  # Initialize with a default value
champions_map = {}  # Initialize the champions map
current_lobby_state = "NONE"  # Track current lobby state


class LeagueGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("League Client Status")
        self.root.geometry("500x500")

        # Variables
        self.summoner_name = tk.StringVar(value="Waiting for connection...")
        self.game_status = tk.StringVar(value="Not Connected")
        self.champ_select_phase = tk.StringVar(value="N/A")
        self.selected_roles = tk.StringVar(value="Roles: N/A")  # New variable for roles
        self.auto_accept_var = tk.BooleanVar(value=False)
        self.auto_ban_var = tk.StringVar(value="None")
        self.auto_pick_var = tk.StringVar(value="None")
        self.ban_search_var = tk.StringVar()
        self.pick_search_var = tk.StringVar()

        # Summoner Name Label
        ttk.Label(root, text="Summoner:").pack(pady=5)
        self.summoner_label = ttk.Label(root, textvariable=self.summoner_name, font=("Arial", 12, "bold"))
        self.summoner_label.pack()

        # Game Status Label
        ttk.Label(root, text="Game Status:").pack(pady=5)
        self.status_label = ttk.Label(root, textvariable=self.game_status, font=("Arial", 10))
        self.status_label.pack()

        # Selected Roles Label
        ttk.Label(root, text="Selected Roles:").pack(pady=5)  # New label for roles
        self.roles_label = ttk.Label(root, textvariable=self.selected_roles, font=("Arial", 10))
        self.roles_label.pack()

        # Champion Select Phase Label
        ttk.Label(root, text="Champion Select Phase:").pack(pady=5)
        self.phase_label = ttk.Label(root, textvariable=self.champ_select_phase, font=("Arial", 10))
        self.phase_label.pack()

        # Auto-Accept Matches Toggle
        self.auto_accept_button = ttk.Checkbutton(root, text="Auto-Accept Matches", variable=self.auto_accept_var)
        self.auto_accept_button.pack(pady=10)

        # Create a frame for auto-ban and auto-pick (side by side layout)
        ban_pick_frame = ttk.Frame(root)
        ban_pick_frame.pack(pady=5, fill="x")

        # Auto-Ban Section
        auto_ban_frame = ttk.Frame(ban_pick_frame)
        auto_ban_frame.pack(side="left", padx=10, expand=True)

        ttk.Label(auto_ban_frame, text="Auto-Ban Champion:").pack(pady=2)
        self.auto_ban_dropdown = ttk.Combobox(auto_ban_frame, textvariable=self.auto_ban_var)
        self.auto_ban_dropdown['values'] = ["None"] + list(champions_map.keys())
        self.auto_ban_dropdown.pack(pady=2)

        ttk.Label(auto_ban_frame, text="Search:").pack(pady=2)
        self.ban_search_entry = ttk.Entry(auto_ban_frame, textvariable=self.ban_search_var)
        self.ban_search_entry.pack(pady=2)
        self.ban_search_entry.bind('<KeyRelease>', self.filter_auto_ban_dropdown)

        # Auto-Pick Section
        auto_pick_frame = ttk.Frame(ban_pick_frame)
        auto_pick_frame.pack(side="right", padx=10, expand=True)

        ttk.Label(auto_pick_frame, text="Auto-Pick Champion:").pack(pady=2)
        self.auto_pick_dropdown = ttk.Combobox(auto_pick_frame, textvariable=self.auto_pick_var)
        self.auto_pick_dropdown['values'] = ["None"] + list(champions_map.keys())
        self.auto_pick_dropdown.pack(pady=2)

        ttk.Label(auto_pick_frame, text="Search:").pack(pady=2)
        self.pick_search_entry = ttk.Entry(auto_pick_frame, textvariable=self.pick_search_var)
        self.pick_search_entry.pack(pady=2)
        self.pick_search_entry.bind('<KeyRelease>', self.filter_auto_pick_dropdown)

        # Status log Frame
        log_frame = ttk.LabelFrame(root, text="Status Log")
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=8, width=50)
        self.log_text.pack(pady=5, padx=5, fill="both", expand=True)

        # Scrollbar for log
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Bind the dropdowns to save the last selection when changed
        self.auto_ban_dropdown.bind("<<ComboboxSelected>>", self.save_last_selection)
        self.auto_pick_dropdown.bind("<<ComboboxSelected>>", self.save_last_selection)

        # Load last selected ban and pick
        self.load_last_selection()

        # Quit Button
        self.quit_button = ttk.Button(root, text="Quit", command=self.quit_program)
        self.quit_button.pack(pady=10)

        # Start the GUI update loop
        self.update_gui()

    def log_message(self, message):
        """Add a message to the log with timestamp"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)  # Auto-scroll to the end

    def load_last_selection(self):
        try:
            with open("last_selection.txt", "r") as file:
                lines = file.read().splitlines()
                if len(lines) >= 2:  # Ensure there are at least two lines
                    last_ban, last_pick = lines[:2]  # Only take the first two lines
                    self.auto_ban_var.set(last_ban)
                    self.auto_pick_var.set(last_pick)
                else:
                    self.log_message("last_selection.txt is empty or incomplete. Starting with default selections.")
        except FileNotFoundError:
            self.log_message("last_selection.txt not found. Starting with default selections.")

    def reset_states(self):
        global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, action_id, current_lobby_state
        am_i_assigned = False
        am_i_banning = False
        am_i_picking = False
        phase = ''
        in_game = False
        action_id = None
        current_lobby_state = "NONE"
        self.champ_select_phase.set("N/A")  # Reset the phase in the GUI
        self.game_status.set("Connected - Waiting for Queue")  # Update game status
        self.log_message("States reset: ready for a new game")

    def save_last_selection(self, event=None):
        with open("last_selection.txt", "w") as file:
            file.write(f"{self.auto_ban_var.get()}\n{self.auto_pick_var.get()}")

    def filter_auto_ban_dropdown(self, event=None):
        search_text = self.ban_search_var.get().lower()
        filtered_champs = [champ for champ in champions_map.keys() if search_text in champ.lower()]
        self.auto_ban_dropdown['values'] = ["None"] + filtered_champs

    def filter_auto_pick_dropdown(self, event=None):
        search_text = self.pick_search_var.get().lower()
        filtered_champs = [champ for champ in champions_map.keys() if search_text in champ.lower()]
        self.auto_pick_dropdown['values'] = ["None"] + filtered_champs

    def update_gui(self):
        # Schedule the function to run again after 1 second
        self.root.after(1000, self.update_gui)

    def quit_program(self):
        # Stop the LCU connector
        asyncio.run_coroutine_threadsafe(connector.stop(), loop)
        # Close the GUI
        self.root.destroy()


async def check_game_phase(connection):
    """Continuously checks for the current game phase"""
    global gui, in_game, current_lobby_state

    while True:
        try:
            # Check if in champion select
            champ_select = await connection.request('get', '/lol-champ-select/v1/session')
            champ_select_status = champ_select.status

            # Check if in matchmaking queue
            matchmaking = await connection.request('get', '/lol-matchmaking/v1/search')
            matchmaking_status = matchmaking.status

            # Check if in game
            try:
                game_check = requests.get('https://127.0.0.1:2999/liveclientdata/activeplayer', verify=False, timeout=1)
                game_running = game_check.status_code == 200
            except:
                game_running = False

            # Update game state based on checks
            if game_running and not in_game:
                in_game = True
                current_lobby_state = "IN_GAME"
                gui.game_status.set("In Game")
                gui.log_message("Game detected - now in active game")

                # Play music if configured
                try:
                    with open("music.txt", "r") as f:
                        music_url = f.readline().strip()
                        if music_url:
                            webbrowser.open(music_url, new=0, autoraise=True)
                            gui.log_message("Playing music")
                        else:
                            gui.log_message("No music URL found in music.txt")
                except Exception as e:
                    gui.log_message(f"Error opening music: {e}")

            elif champ_select_status == 200 and current_lobby_state != "CHAMP_SELECT":
                current_lobby_state = "CHAMP_SELECT"
                gui.game_status.set("In Champion Select")
                gui.log_message("Now in champion select")

            elif matchmaking_status == 200 and current_lobby_state != "MATCHMAKING":
                current_lobby_state = "MATCHMAKING"
                gui.game_status.set("In Queue")
                gui.log_message("Searching for a match")

            elif in_game and not game_running:
                # Game has ended
                in_game = False
                gui.reset_states()
                gui.log_message("Game has ended")

            elif not in_game and not game_running and champ_select_status != 200 and matchmaking_status != 200 and current_lobby_state != "LOBBY":
                current_lobby_state = "LOBBY"
                gui.game_status.set("In Lobby")
                gui.log_message("Now in lobby")

        except Exception as e:
            if str(e) != "":  # Only log non-empty errors
                gui.log_message(f"Error checking game phase: {e}")

        # Check less frequently to reduce API load
        await asyncio.sleep(3)


async def update_lobby_info(connection):
    global gui, in_game, current_lobby_state

    while True:
        try:
            # Skip checking if in game to reduce unnecessary API calls
            if in_game or current_lobby_state == "NONE":
                await asyncio.sleep(5)
                continue

            # Get the current lobby information
            lobby_info = await connection.request('get', '/lol-lobby/v2/lobby')

            if lobby_info.status == 200:
                lobby_info_json = await lobby_info.json()

                # Check for valid lobby data
                if 'gameConfig' in lobby_info_json:
                    # We have an active lobby
                    game_mode = lobby_info_json.get('gameConfig', {}).get('gameMode', 'Unknown')
                    queue_id = lobby_info_json.get('gameConfig', {}).get('queueId', 0)

                    # Only update if this is new information
                    if current_lobby_state != "MATCHMAKING":
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
            if str(e) != "":  # Only log non-empty errors
                gui.log_message(f"Error updating lobby info: {e}")

        # Wait before fetching again
        await asyncio.sleep(5)


@connector.ready
async def connect(connection):
    global gui, champions_map
    gui.game_status.set("Connected to League Client")  # Update game status in GUI
    gui.log_message("Connected to League Client")

    # Get the summoner name
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    gui.summoner_name.set(f"{summoner_data['gameName']}#{summoner_data['tagLine']}")  # Update with Riot ID format
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
    gui.auto_ban_dropdown['values'] = ["None"] + list(champions_map.keys())
    gui.auto_pick_dropdown['values'] = ["None"] + list(champions_map.keys())

    # Make sure states are reset on startup
    gui.reset_states()

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
    global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, action_id, current_lobby_state

    # Check if the session is deleted (queue dodged)
    if event.type == 'DELETE':
        gui.log_message("Champion select ended - session deleted")
        gui.reset_states()
        return

    # Handle champion select
    try:
        lobby_phase = event.data['timer']['phase']
        gui.champ_select_phase.set(lobby_phase)

        # Update the current state if it changed
        if current_lobby_state != "CHAMP_SELECT":
            current_lobby_state = "CHAMP_SELECT"
            gui.game_status.set(f"Champion Select - {lobby_phase}")
            gui.log_message(f"Champion select phase: {lobby_phase}")

        # Only proceed if we have a valid localPlayerCellId
        if 'localPlayerCellId' in event.data and event.data['localPlayerCellId'] is not None:
            local_player_cell_id = event.data['localPlayerCellId']

            # Check assigned position
            for teammate in event.data['myTeam']:
                if teammate['cellId'] == local_player_cell_id:
                    assigned_position = teammate.get('assignedPosition', 'Unknown')
                    if not am_i_assigned:
                        am_i_assigned = True
                        gui.log_message(f"Assigned position: {assigned_position}")

            # Find our current action
            for action_group in event.data['actions']:
                for action in action_group:
                    if action['actorCellId'] == local_player_cell_id and action['isInProgress'] == True:
                        # Only log if this is a new phase
                        if phase != action['type']:
                            phase = action['type']
                            gui.log_message(f"Your turn to {phase.upper()}")

                        action_id = action['id']

                        if phase == 'ban':
                            am_i_banning = action['isInProgress']
                        if phase == 'pick':
                            am_i_picking = action['isInProgress']

            # Auto-ban logic
            if phase == 'ban' and lobby_phase == 'BAN_PICK' and am_i_banning and action_id is not None:
                selected_ban = gui.auto_ban_var.get()
                if selected_ban != "None" and selected_ban in champions_map:
                    try:
                        await connection.request('patch', f'/lol-champ-select/v1/session/actions/{action_id}',
                                                 data={"championId": champions_map[selected_ban], "completed": True})
                        gui.log_message(f"Auto-banned {selected_ban}")
                    except Exception as e:
                        gui.log_message(f"Error auto-banning {selected_ban}: {e}")
                am_i_banning = False

            # Auto-pick logic
            if phase == 'pick' and lobby_phase == 'BAN_PICK' and am_i_picking and action_id is not None:
                selected_pick = gui.auto_pick_var.get()
                if selected_pick != "None" and selected_pick in champions_map:
                    try:
                        await connection.request('patch', f'/lol-champ-select/v1/session/actions/{action_id}',
                                                 data={"championId": champions_map[selected_pick], "completed": True})
                        gui.log_message(f"Auto-picked {selected_pick}")
                    except Exception as e:
                        gui.log_message(f"Error auto-picking {selected_pick}: {e}")
                am_i_picking = False

            # Pre-pick in PLANNING phase
            if lobby_phase == 'PLANNING' and action_id is not None:
                selected_pick = gui.auto_pick_var.get()
                if selected_pick != "None" and selected_pick in champions_map:
                    try:
                        await connection.request('patch', f'/lol-champ-select/v1/session/actions/{action_id}',
                                                 data={"championId": champions_map[selected_pick], "completed": False})
                        gui.log_message(f"Pre-picked {selected_pick}")
                    except Exception as e:
                        gui.log_message(f"Error pre-picking {selected_pick}: {e}")

        # Set up game start detection for finalization phase
        if lobby_phase == 'FINALIZATION' and current_lobby_state != "GAME_STARTING":
            current_lobby_state = "GAME_STARTING"
            gui.game_status.set("Game Starting...")
            gui.log_message("Game is about to start")

    except Exception as e:
        gui.log_message(f"Error in champ select: {e}")


@connector.close
async def disconnect(_):
    gui.log_message('The League client has been closed!')
    await connector.stop()


# Function to start the LCU connector in a separate thread
def start_connector():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connector.start())


# Start the LCU connector in a separate thread
connector_thread = threading.Thread(target=start_connector)
connector_thread.daemon = True  # Daemonize thread to exit when the main program exits
connector_thread.start()

# Start the GUI
root = tk.Tk()
gui = LeagueGUI(root)  # Create the GUI object

# Handle window close event
root.protocol("WM_DELETE_WINDOW", gui.quit_program)

root.mainloop()