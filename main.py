import time
import requests
import urllib3
from lcu_driver import Connector
import webbrowser
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

# Configuration for auto-accept, auto-ban, and auto-pick
auto_accept = False  # Set to True to enable auto-accept
auto_ban_champion = "None"  # Set to a champion name to enable auto-ban
auto_pick_champion = "None"  # Set to a champion name to enable auto-pick


async def update_lobby_info(connection):
    global in_game
    while not in_game:  # Stop updating once the game is found
        try:
            # Get the current lobby information
            lobby_info = await connection.request('get', '/lol-lobby/v2/lobby')
            lobby_info_json = await lobby_info.json()
            game_mode = lobby_info_json.get('gameConfig', {}).get('gameMode', 'Unknown')
            print(f"Current game mode: {game_mode}")  # Debug print
        except Exception as e:
            print(f"Error retrieving lobby info: {e}")

        # Wait for 5 seconds before fetching again
        await asyncio.sleep(5)


@connector.ready
async def connect(connection):
    global champions_map
    print("Connected to League Client")

    # Get the summoner name
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    summoner_name = summoner_data['gameName']
    print(f"Summoner name retrieved: {summoner_name}")  # Debug print

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

    # Start the lobby info update loop
    await asyncio.create_task(update_lobby_info(connection))


@connector.ws.register('/lol-matchmaking/v1/ready-check', event_types=('UPDATE',))
async def ready_check_changed(connection, event):
    if event.data['state'] == 'InProgress' and event.data['playerResponse'] == 'None':
        if auto_accept:  # Check if auto-accept is enabled
            await connection.request('post', '/lol-matchmaking/v1/ready-check/accept', data={})
            print("Match accepted!")  # Debug print
        else:
            print("Match ready check appeared, but auto-accept is off.")  # Debug print


@connector.ws.register('/lol-champ-select/v1/session', event_types=('CREATE', 'UPDATE',))
async def champ_select_changed(connection, event):
    global am_i_assigned, am_i_banning, am_i_picking, phase, in_game, action_id
    have_i_prepicked = False
    lobby_phase = event.data['timer']['phase']

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
        selected_ban = auto_ban_champion  # Get the auto-ban champion
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
        selected_pick = auto_pick_champion  # Get the auto-pick champion
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
        selected_pick = auto_pick_champion  # Get the auto-pick champion
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
    connector.start()


# Start the LCU connector in a separate thread
connector_thread = threading.Thread(target=start_connector)
connector_thread.daemon = True  # Daemonize thread to exit when the main program exits
connector_thread.start()

# Keep the script running
while True:
    time.sleep(1)