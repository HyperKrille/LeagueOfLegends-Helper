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
global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, summoner_name, game_mode, champions_map
am_i_assigned = False
am_i_banning = False
am_i_picking = False
in_game = False
phase = ''
summoner_name = "Waiting for connection..."  # Initialize with a default value
game_mode = "Not Connected"  # Initialize with a default value
champions_map = {}  # Initialize the champions map


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

        # Bind the dropdowns to save the last selection when changed
        self.auto_ban_dropdown.bind("<<ComboboxSelected>>", self.save_last_selection)
        self.auto_pick_dropdown.bind("<<ComboboxSelected>>", self.save_last_selection)

        # Load last selected ban and pick
        self.load_last_selection()

        # Quit Button
        self.quit_button = ttk.Button(root, text="Quit", command=self.quit_program)
        self.quit_button.pack(pady=20)

        # Start the GUI update loop
        self.update_gui()

    def load_last_selection(self):
        try:
            with open("last_selection.txt", "r") as file:
                lines = file.read().splitlines()
                if len(lines) >= 2:  # Ensure there are at least two lines
                    last_ban, last_pick = lines[:2]  # Only take the first two lines
                    self.auto_ban_var.set(last_ban)
                    self.auto_pick_var.set(last_pick)
                else:
                    print("last_selection.txt is empty or incomplete. Starting with default selections.")
        except FileNotFoundError:
            print("last_selection.txt not found. Starting with default selections.")

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


async def update_lobby_info(connection):
    global gui, in_game
    while not in_game:  # Stop updating once the game is found
        try:
            # Get the current lobby information
            lobby_info = await connection.request('get', '/lol-lobby/v2/lobby')
            lobby_info_json = await lobby_info.json()
            print("Lobby Info:", lobby_info_json)  # Debug: Print the entire lobby info

            game_mode = lobby_info_json.get('gameConfig', {}).get('gameMode', 'Unknown')
            gui.game_status.set(f"Connected - Game Mode: {game_mode}")  # Update game status with game mode

            # Fetch the player's selected roles from the localMember section
            local_player_roles = "N/A"  # Default value

            local_member = lobby_info_json.get('localMember', {})
            first_role = local_member.get('firstPositionPreference', '')
            second_role = local_member.get('secondPositionPreference', '')

            if first_role or second_role:
                local_player_roles = f"{first_role}, {second_role}"


            # Update the roles label in the GUI
            gui.selected_roles.set(f"Roles: {local_player_roles}")

            print(f"Current game mode: {game_mode}, Roles: {local_player_roles}")  # Debug print
        except Exception as e:
            print(f"Error retrieving lobby info: {e}")
            gui.game_status.set("Connected - Game Mode: Unknown")  # Fallback if lobby info retrieval fails
            gui.selected_roles.set("Roles: N/A")  # Fallback for roles

        # Wait for 5 seconds before fetching again
        await asyncio.sleep(5)



@connector.ready
async def connect(connection):
    global gui, champions_map
    gui.game_status.set("Connected to League Client")  # Update game status in GUI

    # Get the summoner name
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    gui.summoner_name.set(summoner_data['gameName'])  # Update summoner name in GUI
    print(f"Summoner name retrieved: {summoner_data['gameName']}")  # Debug print

    # Get the summoner ID and champion list
    summoner_id = summoner_data['summonerId']
    print(f"Summoner ID: {summoner_id}")  # Debug print

    # Get the list of champions
    champion_list = await connection.request('get', f'/lol-champions/v1/inventories/{summoner_id}/champions-minimal')
    champion_list_to_json = await champion_list.json()

    # Populate the champions_map
    temp_champions_map = {}
    for champion in champion_list_to_json:
        temp_champions_map.update({champion['name']: champion['id']})
    champions_map = temp_champions_map
    print(f"Champions map populated with {len(champions_map)} champions.")  # Debug print

    # Update the dropdowns with the champions list
    gui.auto_ban_dropdown['values'] = ["None"] + list(champions_map.keys())
    gui.auto_pick_dropdown['values'] = ["None"] + list(champions_map.keys())

    # Start the lobby info update loop
    await asyncio.create_task(update_lobby_info(connection))


@connector.ws.register('/lol-matchmaking/v1/ready-check', event_types=('UPDATE',))
async def ready_check_changed(connection, event):
    if event.data['state'] == 'InProgress' and event.data['playerResponse'] == 'None':
        if gui.auto_accept_var.get():  # Check if auto-accept is enabled
            await connection.request('post', '/lol-matchmaking/v1/ready-check/accept', data={})
            print("Match accepted!")  # Debug print
        else:
            print("Match ready check appeared, but auto-accept is off.")  # Debug print


@connector.ws.register('/lol-champ-select/v1/session', event_types=('CREATE', 'UPDATE',))
async def champ_select_changed(connection, event):
    global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, action_id
    have_i_prepicked = False
    lobby_phase = event.data['timer']['phase']

    # Update the champion select phase in the GUI
    gui.champ_select_phase.set(lobby_phase)

    local_player_cell_id = event.data['localPlayerCellId']
    for teammate in event.data['myTeam']:
        if teammate['cellId'] == local_player_cell_id:
            assigned_position = teammate['assignedPosition']
            am_i_assigned = True

    for action in event.data['actions']:
        for actionArr in action:
            if actionArr['actorCellId'] == local_player_cell_id and actionArr['isInProgress'] == True:
                phase = actionArr['type']
                action_id = actionArr['id']
                if phase == 'ban':
                    am_i_banning = actionArr['isInProgress']
                if phase == 'pick':
                    am_i_picking = actionArr['isInProgress']

    if phase == 'ban' and lobby_phase == 'BAN_PICK' and am_i_banning:
        selected_ban = gui.auto_ban_var.get()  # Get the auto-ban champion
        if selected_ban != "None":  # Skip if "None" is selected
            try:
                # Attempt to ban the selected champion
                await connection.request('patch', '/lol-champ-select/v1/session/actions/%d' % action_id,
                                         data={"championId": champions_map[selected_ban], "completed": True})
                print(f"Auto-banned {selected_ban}")  # Debug print
            except Exception as e:
                print(f"Error auto-banning {selected_ban}: {e}")
        am_i_banning = False  # Stop the ban loop

    if phase == 'pick' and lobby_phase == 'BAN_PICK' and am_i_picking:
        selected_pick = gui.auto_pick_var.get()  # Get the auto-pick champion
        if selected_pick != "None":  # Skip if "None" is selected
            try:
                # Attempt to pick the selected champion
                await connection.request('patch', '/lol-champ-select/v1/session/actions/%d' % action_id,
                                       data={"championId": champions_map[selected_pick], "completed": True})
                print(f"Auto-picked {selected_pick}")  # Debug print
            except Exception as e:
                print(f"Error auto-picking {selected_pick}: {e}")
        am_i_picking = False  # Stop the pick loop

    if lobby_phase == 'PLANNING' and not have_i_prepicked:
        selected_pick = gui.auto_pick_var.get()  # Get the auto-pick champion
        if selected_pick != "None":  # Skip if "None" is selected
            try:
                # Pre-pick the selected champion
                await connection.request('patch', '/lol-champ-select/v1/session/actions/%d' % action_id,
                                         data={"championId": champions_map[selected_pick], "completed": False})
                have_i_prepicked = True  # Mark that pre-picking is done
                print(f"Pre-picked {selected_pick}")  # Debug print
            except Exception as e:
                print(f"Error pre-picking {selected_pick}: {e}")

    if lobby_phase == 'FINALIZATION':
        while not in_game:
            try:
                # Check if the game has started
                request_game_data = requests.get('https://127.0.0.1:2999/liveclientdata/allgamedata', verify=False)
                game_data = request_game_data.json()['gameData']['gameTime']
                if game_data > 0 and not in_game:
                    print("Game found!")
                    in_game = True
                    music_url = open("music.txt", "r").readline()  # Read the music URL from music.txt
                    webbrowser.open(music_url, new=0, autoraise=True)  # Open the music URL
                time.sleep(2)
            except (Exception,):
                print('Waiting for game to start...')
                time.sleep(2)


@connector.close
async def disconnect(_):
    print('The client has been closed!')
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