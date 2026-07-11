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

# Global variables
global champions_map, client_connected, client_closed, gui, connector, current_region, client_closed
champions_map = {}
champions_id_to_name = {}  # Reverse lookup: champion id -> name, for showing teammate hovers
client_connected = False  # Tracks if the client is connected
lobby_info_task = None  # Handle to the background lobby-info polling task
client_closed = False  # Tracks if the client has been closed
connector = Connector()  # Initialize the connector globally
current_region = "NONE"  # Default region, will be updated on startup
client_closed = False

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
        self.teammate_champions = {}  # cellId -> last known championId (hover/pick tracking)

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
        self.teammate_champions = {}


# Create a global instance of GameState
game_state = GameState()


class LeagueGUI:
    # Color palette (dark theme, League-ish blue/gold accents)
    COLORS = {
        "bg": "#1e2328",
        "bg_alt": "#232a31",
        "panel": "#282f36",
        "border": "#3c4148",
        "text": "#f0e6d2",
        "text_dim": "#a09b8c",
        "accent": "#c8aa6e",
        "accent_dim": "#785a28",
        "good": "#4caf50",
        "bad": "#e05252",
        "warn": "#e0a952",
        "info": "#5bc0de",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("League Client Status")
        self.root.geometry("600x820")
        self.root.minsize(420, 400)
        self.root.configure(bg=self.COLORS["bg"])

        # Apply a modern dark theme
        style = ttk.Style()
        style.theme_use("clam")
        self._configure_style(style)

        # Define roles
        self.roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
        self.role_labels = {
            "TOP": "Top Lane",
            "JUNGLE": "Jungle",
            "MIDDLE": "Mid Lane",
            "BOTTOM": "Bot Lane",
            "UTILITY": "Support"
        }

        # Key used for game modes that don't assign a lane role (Arena, ARAM, URF, etc.)
        self.fallback_role_key = "ANY"
        # All keys whose settings get saved/loaded/refreshed together
        self.all_config_keys = self.roles + [self.fallback_role_key]

        # Variables
        self.summoner_name = tk.StringVar(value="Waiting for connection...")
        self.game_status = tk.StringVar(value="Not Connected")
        self.champ_select_phase = tk.StringVar(value="N/A")
        self.selected_roles = tk.StringVar(value="Roles: N/A")
        self.auto_accept_var = tk.BooleanVar(value=False)

        # Role-specific variables (lane roles + the "ANY" fallback for roleless modes)
        self.role_configs = {
            role: {
                "ban_var": tk.StringVar(value="None"),
                "pick_var": tk.StringVar(value="None"),
                "ban_search_var": tk.StringVar(),
                "pick_search_var": tk.StringVar()
            }
            for role in self.all_config_keys
        }

        # --- Scrollable container -------------------------------------------------
        # Wraps all content in a canvas+scrollbar so nothing (like the button row)
        # can ever be pushed off-screen by DPI scaling or a small window/screen.
        outer = ttk.Frame(root)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=self.COLORS["bg"], highlightthickness=0)
        v_scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=v_scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        v_scroll.pack(side="right", fill="y")

        content = ttk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            # Make the inner frame track the canvas width so children can fill="x" properly
            canvas.itemconfig(content_window, width=event.width)

        content.bind("<Configure>", _on_content_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        root = content  # Everything below is parented to the scrollable content frame

        # Title bar with connection indicator
        title_bar = ttk.Frame(root)
        title_bar.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(title_bar, text="League Client Status", style="Header.TLabel").pack(side="left")

        self.conn_dot = tk.Canvas(title_bar, width=14, height=14, bg=self.COLORS["bg"],
                                   highlightthickness=0)
        self.conn_dot_id = self.conn_dot.create_oval(2, 2, 12, 12, fill=self.COLORS["bad"],
                                                       outline="")
        self.conn_dot.pack(side="right", padx=(0, 4))
        self.conn_text = ttk.Label(title_bar, text="Disconnected", style="Dim.TLabel")
        self.conn_text.pack(side="right", padx=(0, 6))

        # Top frame for summoner info and game status
        info_frame = ttk.LabelFrame(root, text="Game Information", padding=12)
        info_frame.pack(pady=10, padx=10, fill="x")
        info_frame.columnconfigure(1, weight=1)

        def info_row(r, label_text, textvariable=None, text=None):
            ttk.Label(info_frame, text=label_text, style="Dim.TLabel").grid(
                row=r, column=0, sticky="w", padx=5, pady=4)
            if textvariable is not None:
                lbl = ttk.Label(info_frame, textvariable=textvariable, style="Value.TLabel")
            else:
                lbl = ttk.Label(info_frame, text=text, style="Value.TLabel")
            lbl.grid(row=r, column=1, sticky="w", padx=5, pady=4)
            return lbl

        self.summoner_label = info_row(0, "Summoner", self.summoner_name)
        self.status_label = info_row(1, "Game Status", self.game_status)
        self.roles_label = info_row(2, "Selected Roles", self.selected_roles)
        self.phase_label = info_row(3, "Champion Select Phase", self.champ_select_phase)
        self.region_label = info_row(4, "Region", text="N/A")

        ttk.Separator(info_frame, orient="horizontal").grid(row=5, column=0, columnspan=2,
                                                              sticky="ew", pady=8)

        # Auto-Accept Checkbox
        self.auto_accept_button = ttk.Checkbutton(info_frame, text="Auto-Accept Matches",
                                                    variable=self.auto_accept_var,
                                                    command=self.save_configuration)
        self.auto_accept_button.grid(row=6, column=0, columnspan=2, sticky="w", padx=5, pady=2)

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

        # Extra tab for game modes with no assigned lane role (Arena, ARAM, URF, etc.)
        fallback_tab = ttk.Frame(self.notebook, padding=10)
        self.role_tabs[self.fallback_role_key] = fallback_tab
        self.notebook.add(fallback_tab, text="Other Modes")
        self.setup_role_tab(self.fallback_role_key, fallback_tab)

        # Status Log Frame
        c = self.COLORS
        log_frame = ttk.LabelFrame(root, text="Status Log", padding=8)
        log_frame.pack(pady=10, padx=10, fill="both", expand=True)

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill="both", expand=True)

        log_scrollbar = ttk.Scrollbar(log_inner, orient="vertical")
        self.log_text = tk.Text(
            log_inner, height=10, width=60, wrap="word", font=("Consolas", 9),
            bg=c["panel"], fg=c["text"], insertbackground=c["text"],
            relief="flat", borderwidth=0, yscrollcommand=log_scrollbar.set,
        )
        log_scrollbar.config(command=self.log_text.yview)
        self.log_text.pack(side="left", pady=5, padx=(5, 0), fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y", pady=5)

        # Color tags for different message severities
        self.log_text.tag_config("error", foreground=c["bad"])
        self.log_text.tag_config("warn", foreground=c["warn"])
        self.log_text.tag_config("info", foreground=c["info"])
        self.log_text.tag_config("timestamp", foreground=c["text_dim"])
        self.log_text.config(state="disabled")

        ttk.Button(log_frame, text="Clear Log", command=self.clear_log).pack(
            anchor="e", pady=(4, 0))

        # Bottom frame for buttons
        button_frame = ttk.Frame(root)
        button_frame.pack(pady=10, padx=10, fill="x")

        # Open op.gg Button
        self.opgg_button = ttk.Button(button_frame, text="Open op.gg", command=self.open_opgg)
        self.opgg_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # Save Settings Button
        self.save_button = ttk.Button(button_frame, text="Save Settings", command=self.save_configuration,
                                       style="Accent.TButton")
        self.save_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Quit Button
        self.quit_button = ttk.Button(button_frame, text="Quit", command=self.quit_program)
        self.quit_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        # Configure column weights to make buttons expand evenly
        for col in range(3):
            button_frame.columnconfigure(col, weight=1)

        # Load configuration
        self.load_configuration()

        # Start the GUI update loop
        self.update_gui()

    def _configure_style(self, style):
        """Configure ttk widget styles for a cohesive dark theme."""
        c = self.COLORS
        self.root.option_add("*Font", "{Segoe UI} 10")

        style.configure(".", background=c["bg"], foreground=c["text"], font=("Segoe UI", 10))
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Dim.TLabel", background=c["bg"], foreground=c["text_dim"])
        style.configure("Header.TLabel", background=c["bg"], foreground=c["accent"],
                         font=("Segoe UI", 16, "bold"))
        style.configure("Value.TLabel", background=c["bg"], foreground=c["text"],
                         font=("Segoe UI", 10, "bold"))
        style.configure("Current.TLabel", background=c["panel"], foreground=c["accent"],
                         font=("Segoe UI", 10, "bold"))

        style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"],
                         relief="solid")
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["accent"],
                         font=("Segoe UI", 10, "bold"))

        style.configure("TButton", background=c["panel"], foreground=c["text"],
                         bordercolor=c["border"], focusthickness=1, padding=6)
        style.map("TButton", background=[("active", c["accent_dim"]), ("disabled", c["bg_alt"])],
                  foreground=[("disabled", c["text_dim"])])

        style.configure("Accent.TButton", background=c["accent_dim"], foreground=c["text"])
        style.map("Accent.TButton", background=[("active", c["accent"])])

        style.configure("TCheckbutton", background=c["bg"], foreground=c["text"])
        style.map("TCheckbutton", background=[("active", c["bg"])])

        style.configure("TEntry", fieldbackground=c["panel"], foreground=c["text"],
                         bordercolor=c["border"], insertcolor=c["text"])

        style.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
        style.configure("TNotebook.Tab", background=c["bg_alt"], foreground=c["text_dim"],
                         padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", c["panel"])],
                  foreground=[("selected", c["accent"])])

    def _build_champ_picker(self, tab, role, kind, label_text):
        """Build a search + listbox champion picker for either 'ban' or 'pick'."""
        c = self.COLORS
        var_key = f"{kind}_var"
        search_key = f"{kind}_search_var"

        frame = ttk.LabelFrame(tab, text=label_text, padding=8)
        frame.pack(pady=8, padx=10, fill="x")

        # Currently selected champion, shown prominently
        current_row = ttk.Frame(frame)
        current_row.pack(fill="x", pady=(0, 6))
        ttk.Label(current_row, text="Current:", style="Dim.TLabel").pack(side="left")
        current_label = ttk.Label(current_row, textvariable=self.role_configs[role][var_key],
                                   style="Current.TLabel")
        current_label.pack(side="left", padx=6)
        ttk.Button(current_row, text="Clear", width=6,
                   command=lambda: self._clear_selection(role, kind)).pack(side="right")

        # Search entry
        self.role_configs[role][search_key] = tk.StringVar()
        search_entry = ttk.Entry(frame, textvariable=self.role_configs[role][search_key])
        search_entry.pack(pady=2, fill="x")
        search_entry.insert(0, "")

        # Listbox + scrollbar for suggestions
        list_row = ttk.Frame(frame)
        list_row.pack(pady=4, fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_row, orient="vertical")
        suggestion_listbox = tk.Listbox(
            list_row, height=6, yscrollcommand=scrollbar.set,
            bg=c["panel"], fg=c["text"], selectbackground=c["accent_dim"],
            selectforeground=c["text"], highlightbackground=c["border"],
            highlightcolor=c["accent"], relief="flat", borderwidth=0,
        )
        scrollbar.config(command=suggestion_listbox.yview)
        suggestion_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def update_suggestions(event=None):
            search_text = self.role_configs[role][search_key].get().lower()
            suggestion_listbox.delete(0, tk.END)
            suggestion_listbox.insert(tk.END, "None")

            if search_text:
                filtered_champs = sorted(
                    champ for champ in champions_map.keys() if search_text in champ.lower())
            else:
                filtered_champs = sorted(champions_map.keys())

            for champ in filtered_champs:
                suggestion_listbox.insert(tk.END, champ)

        def on_select(event):
            selected_indices = suggestion_listbox.curselection()
            if selected_indices:
                selected_champ = suggestion_listbox.get(selected_indices[0])
                self.role_configs[role][var_key].set(selected_champ)
                self.role_configs[role][search_key].set("")
                update_suggestions()
                self.save_configuration()

        search_entry.bind("<KeyRelease>", update_suggestions)
        suggestion_listbox.bind("<<ListboxSelect>>", on_select)
        update_suggestions()

    def _clear_selection(self, role, kind):
        """Reset a role's ban/pick selection back to 'None'."""
        self.role_configs[role][f"{kind}_var"].set("None")
        self.save_configuration()

    def setup_role_tab(self, role, tab):
        """Set up the widgets for a role tab."""
        if role == self.fallback_role_key:
            ttk.Label(
                tab,
                text="Used for Arena, ARAM, URF, and any other mode without a lane role.",
                style="Dim.TLabel", wraplength=480, justify="left",
            ).pack(fill="x", pady=(0, 6))
        self._build_champ_picker(tab, role, "ban", "Auto-Ban Champion")
        self._build_champ_picker(tab, role, "pick", "Auto-Pick Champion")

    def log_message(self, message):
        """Add a message to the log with timestamp, colored by severity."""
        timestamp = time.strftime("%H:%M:%S", time.localtime())

        lowered = message.lower()
        if "error" in lowered or "failed" in lowered:
            tag = "error"
        elif "warn" in lowered or "no active connection" in lowered:
            tag = "warn"
        else:
            tag = "info"

        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.log_text.insert(tk.END, f"{message}\n", tag)

        # Limit the number of log lines to 1000
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 1000:
            self.log_text.delete("1.0", f"{line_count - 1000}.0")

        self.log_text.see(tk.END)  # Auto-scroll to the end
        self.log_text.config(state="disabled")

    def clear_log(self):
        """Clear all messages from the status log."""
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def set_connection_state(self, connected):
        """Update the connection indicator dot and label."""
        color = self.COLORS["good"] if connected else self.COLORS["bad"]
        self.conn_dot.itemconfig(self.conn_dot_id, fill=color)
        self.conn_text.config(text="Connected" if connected else "Disconnected")

    def load_configuration(self):
        """Load role-specific configuration from file."""
        try:
            if os.path.exists("role_config.json"):
                with open("role_config.json", "r") as file:
                    config = json.load(file)

                    # Load role configurations (lane roles + the roleless "ANY" fallback)
                    for role in self.all_config_keys:
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

            # Save role configurations (lane roles + the roleless "ANY" fallback)
            for role in self.all_config_keys:
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
        # Enable/Disable Open op.gg button based on summoner name
        if self.summoner_name.get() != "Waiting for connection...":
            self.opgg_button.config(state=tk.NORMAL)
        else:
            self.opgg_button.config(state=tk.DISABLED)

        # Schedule the function to run again after 1 second
        self.root.after(1000, self.update_gui)

    def update_champion_dropdowns(self):
        """Update all champion dropdowns with the current champion list."""
        for role in self.all_config_keys:
            # Preserve current selections
            current_ban = self.role_configs[role]["ban_var"].get()
            current_pick = self.role_configs[role]["pick_var"].get()

            # Update the ban and pick search variables
            self.role_configs[role]["ban_search_var"].set(current_ban)
            self.role_configs[role]["pick_search_var"].set(current_pick)

            # If the current selections are not in the champions map, reset them to "None"
            if current_ban not in champions_map and current_ban != "None":
                self.role_configs[role]["ban_var"].set("None")
            if current_pick not in champions_map and current_pick != "None":
                self.role_configs[role]["pick_var"].set("None")

    def open_opgg(self):
        """Open the current game's op.gg page."""
        summoner_name_with_tag = self.summoner_name.get()  # Get the full summoner name with tagline

        if summoner_name_with_tag and current_region:
            # Replace spaces and special characters in the summoner name for the URL
            summoner_name_encoded = summoner_name_with_tag.replace(" ", "%20").replace("#", "-")
            opgg_url = f"https://www.op.gg/summoners/{current_region}/{summoner_name_encoded}"
            webbrowser.open(opgg_url)
            self.log_message(f"Opened op.gg for {summoner_name_with_tag} in region {current_region}")
        else:
            self.log_message("Failed to open op.gg: Summoner name or region not available.")

    def quit_program(self):
        global stop_thread, connector_thread, client_closed, client_connected

        # Save configuration before exiting
        self.save_configuration()

        # Signal the thread to stop
        stop_thread = True
        client_closed = True  # Ensure the client closed flag is set
        client_connected = False  # Let the background polling loop's while-condition exit cleanly

        # Cancel the background lobby-info polling task so it doesn't get
        # destroyed mid-sleep when the loop stops (avoids "Task was destroyed
        # but it is pending!" warnings on exit).
        if loop.is_running() and lobby_info_task is not None and not lobby_info_task.done():
            try:
                async def _cancel_task():
                    lobby_info_task.cancel()
                    try:
                        await lobby_info_task
                    except (asyncio.CancelledError, Exception):
                        pass

                asyncio.run_coroutine_threadsafe(_cancel_task(), loop).result(timeout=2)
            except Exception as e:
                self.log_message(f"Error cancelling background task: {e}")

        # Stop the LCU connector
        if connector.connection:
            try:
                # Stop the connector in a thread-safe manner
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(connector.stop(), loop).result(timeout=2)
            except Exception as e:
                self.log_message(f"Error stopping connector: {e}")

        # Stop the event loop
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)

        # Wait for the connector thread to finish
        if connector_thread.is_alive():
            connector_thread.join(timeout=2)  # Wait up to 2 seconds for the thread to exit

        # Close the GUI
        self.root.destroy()


@connector.ws.register('/lol-gameflow/v1/gameflow-phase', event_types=('UPDATE',))
async def gameflow_phase_changed(connection, event):
    global game_state, gui

    new_phase = event.data
    gui.log_message(f"Game flow phase changed: {new_phase}")

    if new_phase == "None":
        game_state.reset()
        game_state.current_lobby_state = "NONE"
        gui.game_status.set("Not Connected")
        gui.log_message("Game flow phase reset")
    elif new_phase == "Lobby":
        game_state.current_lobby_state = "LOBBY"
        gui.game_status.set("In Lobby")
        gui.log_message("Now in lobby")
    elif new_phase == "Matchmaking":
        game_state.current_lobby_state = "MATCHMAKING"
        gui.game_status.set("In Queue")
        gui.log_message("Searching for a match")

        # Fetch and display the game mode/queue while searching, since the
        # regular lobby-info poller only runs during the LOBBY state.
        try:
            lobby_info = await connection.request('get', '/lol-lobby/v2/lobby')
            if lobby_info.status == 200:
                lobby_info_json = await lobby_info.json()
                game_mode = lobby_info_json.get('gameConfig', {}).get('gameMode', 'Unknown')
                queue_id = lobby_info_json.get('gameConfig', {}).get('queueId', 0)
                gui.game_status.set(f"In Queue - Mode: {game_mode} (Queue ID: {queue_id})")
        except Exception as e:
            gui.log_message(f"Could not fetch queue mode: {e}")
    elif new_phase == "ReadyCheck":
        gui.game_status.set("Ready Check")
        gui.log_message("Match ready check appeared")
    elif new_phase == "ChampSelect":
        game_state.current_lobby_state = "CHAMP_SELECT"
        gui.game_status.set("In Champion Select")
        gui.log_message("Now in champion select")
    elif new_phase == "InProgress":
        game_state.in_game = True
        game_state.current_lobby_state = "IN_GAME"
        gui.game_status.set("In Game")
        gui.log_message("Game detected - now in active game")
        # try:
        #     with open("music.txt", "r") as f:
        #         music_url = f.readline().strip()
        #         if music_url:
        #             webbrowser.open(music_url, new=0, autoraise=True)
        #             gui.log_message("Playing music")
        # except Exception as e:
        #     gui.log_message(f"Error opening music: {e}")
    elif new_phase == "WaitingForStats":
        game_state.in_game = False
        game_state.reset()
        gui.game_status.set("Game Ended")
        gui.log_message("Game has ended")
    gui.update_gui()


@connector.ready
async def connect(connection):
    global client_connected, gui, champions_map, champions_id_to_name, current_region, lobby_info_task
    client_connected = True  # Set flag when connected
    gui.set_connection_state(True)
    gui.game_status.set("Connected to League Client")
    gui.log_message("Connected to League Client")

    # Get the summoner name
    summoner = await connection.request('get', '/lol-summoner/v1/current-summoner')
    summoner_data = await summoner.json()
    gui.summoner_name.set(f"{summoner_data['gameName']}#{summoner_data['tagLine']}")
    gui.log_message(f"Connected as: {summoner_data['gameName']}#{summoner_data['tagLine']}")

    # Fetch the region
    try:
        region_data = await connection.request('get', '/lol-platform-config/v1/namespaces')
        region_json = await region_data.json()
        current_region = region_json.get('active', {}).get('region',
                                                           'euw').lower()  # Default to 'euw' if region is not found
        gui.log_message(f"Region detected: {current_region}")
        gui.region_label.config(text=current_region.upper())  # Update the region label in the GUI
    except Exception as e:
        gui.log_message(f"Error fetching region: {e}")
        current_region = "euw"  # Fallback to default region
        gui.region_label.config(text=current_region.upper())  # Update the region label in the GUI

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
    champions_id_to_name = {cid: name for name, cid in champions_map.items()}
    gui.log_message(f"Champions loaded: {len(champions_map)}")

    # Update the dropdowns with the champions list
    gui.update_champion_dropdowns()

    # Make sure states are reset on startup
    game_state.reset()

    # Start the update loops
    lobby_info_task = asyncio.create_task(update_lobby_info(connection))

    # Update the GUI immediately after connection
    gui.update_gui()


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

            # Best-effort game mode detection so it's clear when Arena/ARAM/URF etc. is active
            try:
                gameflow_resp = await connection.request('get', '/lol-gameflow/v1/session')
                gameflow_json = await gameflow_resp.json()
                mode = gameflow_json.get('gameData', {}).get('queue', {}).get('gameMode', 'Unknown')
                gui.log_message(f"Game mode detected: {mode}")
            except Exception:
                pass  # Non-critical - just skip the mode announcement if unavailable

        # Only proceed if we have a valid localPlayerCellId
        if 'localPlayerCellId' in event.data and event.data['localPlayerCellId'] is not None:
            local_player_cell_id = event.data['localPlayerCellId']

            # Check assigned position
            for teammate in event.data['myTeam']:
                if teammate['cellId'] == local_player_cell_id:
                    # Get the assigned position from the client
                    assigned_position = teammate.get('assignedPosition', '').upper()  # Ensure uppercase for consistency

                    # Convert empty string to 'Unknown' for better logging
                    if not assigned_position:
                        assigned_position = 'UNKNOWN'

                    # Update the assigned position if it's changed
                    if not game_state.am_i_assigned or game_state.current_assigned_position != assigned_position:
                        game_state.am_i_assigned = True
                        game_state.current_assigned_position = assigned_position
                        gui.log_message(f"Assigned position: {assigned_position}")

                        # If valid position, auto-select the corresponding tab.
                        # Otherwise (Arena, ARAM, URF, etc.) fall back to the "Other Modes" tab.
                        if assigned_position in gui.roles:
                            for i, role in enumerate(gui.roles):
                                if role == assigned_position:
                                    gui.notebook.select(i)
                                    gui.log_message(f"Switched to {assigned_position} tab")
                                    break
                        else:
                            gui.notebook.select(len(gui.roles))
                            gui.log_message("No lane role assigned - switched to 'Other Modes' tab")

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
                if not hasattr(champ_select_changed,
                               'last_role_config') or champ_select_changed.last_role_config != game_state.current_assigned_position:
                    gui.log_message(
                        f"Using champion settings for assigned role: {game_state.current_assigned_position}")
                    champ_select_changed.last_role_config = game_state.current_assigned_position  # Track last used role config
            else:
                # No lane role (Arena, ARAM, URF, and other roleless modes) - use the
                # "Other Modes" tab settings instead of skipping auto-ban/pick entirely.
                role_config = gui.role_configs.get(gui.fallback_role_key)
                if not hasattr(champ_select_changed,
                               'last_role_config') or champ_select_changed.last_role_config != gui.fallback_role_key:
                    gui.log_message(
                        f"No lane role assigned ({game_state.current_assigned_position}) - "
                        f"using 'Other Modes' champion settings")
                    champ_select_changed.last_role_config = gui.fallback_role_key  # Track last used role config

            # Auto-ban logic
            if game_state.phase == 'ban' and lobby_phase == 'BAN_PICK' and game_state.am_i_banning and game_state.action_id is not None and role_config:
                selected_ban = role_config["ban_var"].get()
                if selected_ban != "None" and selected_ban in champions_map:
                    try:
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
                        await connection.request('patch',
                                                 f'/lol-champ-select/v1/session/actions/{game_state.action_id}',
                                                 data={"championId": champions_map[selected_pick], "completed": True})
                        gui.log_message(f"Auto-picked {selected_pick}")
                        champ_select_changed.last_pick = selected_pick  # Track last picked champion
                    except Exception as e:
                        gui.log_message(f"Error auto-picking {selected_pick}: {e}")
                game_state.am_i_picking = False

            # Pre-hover our intended pick as early as possible in champ select, so
            # teammates can see our intent before it's actually our turn to pick.
            # (Previously this reused game_state.action_id, which could point at a
            # ban action instead of the pick action - fixed by locating our own
            # pick action directly.)
            own_pick_action = None
            for action_group in event.data['actions']:
                for action in action_group:
                    if action['actorCellId'] == local_player_cell_id and action['type'] == 'pick':
                        own_pick_action = action
                        break
                if own_pick_action:
                    break

            if own_pick_action and not own_pick_action['completed'] and not own_pick_action['isInProgress'] and role_config:
                selected_pick = role_config["pick_var"].get()
                if selected_pick != "None" and selected_pick in champions_map:
                    desired_id = champions_map[selected_pick]
                    if own_pick_action.get('championId') != desired_id:
                        try:
                            await connection.request('patch',
                                                     f"/lol-champ-select/v1/session/actions/{own_pick_action['id']}",
                                                     data={"championId": desired_id, "completed": False})
                            gui.log_message(f"Pre-hovering {selected_pick}")
                        except Exception as e:
                            gui.log_message(f"Error pre-hovering {selected_pick}: {e}")

            # Track what teammates are hovering/picking and log changes.
            # 'championPickIntent' is the hovered (not-yet-locked) champion;
            # 'championId' is populated once they actually lock it in.
            for teammate in event.data['myTeam']:
                cell_id = teammate['cellId']
                if cell_id == local_player_cell_id:
                    continue  # Skip ourselves - our own hover is already logged above

                locked_id = teammate.get('championId', 0)
                hover_id = teammate.get('championPickIntent', 0)
                display_id = locked_id or hover_id
                previous_id = game_state.teammate_champions.get(cell_id)

                if display_id and display_id != previous_id:
                    champ_name = champions_id_to_name.get(display_id, f"Champion {display_id}")
                    position = teammate.get('assignedPosition', '').upper() or "Unknown"
                    verb = "locked in" if locked_id else "hovering"
                    gui.log_message(f"Teammate ({position}) {verb} {champ_name}")

                game_state.teammate_champions[cell_id] = display_id

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
    if not client_closed:  # Only run this logic once
        client_connected = False  # Clear flag when disconnected
        client_closed = True  # Set the flag to indicate the client is closed
        gui.log_message('The League client has been closed!')

        # Stop the connector
        await connector.stop()

        # Update the GUI to reflect the disconnected state
        gui.game_status.set("Not Connected")
        gui.summoner_name.set("Waiting for connection...")
        gui.set_connection_state(False)
        gui.update_gui()


# Function to start the LCU connector in a separate thread
def start_connector():
    global loop, stop_thread, client_closed
    stop_thread = False
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        while not stop_thread and not client_closed:  # Stop if client is closed
            loop.run_until_complete(connector.start())
    except Exception as e:
        gui.log_message(f"Error in connector thread: {e}")
    finally:
        # Clean up the event loop
        if loop.is_running():
            loop.stop()
        loop.close()


# Start the GUI
root = tk.Tk()
gui = LeagueGUI(root)  # Create the GUI object
gui.update_gui()

# Start the LCU connector in a separate thread
connector_thread = threading.Thread(target=start_connector)
connector_thread.daemon = True  # Daemonize thread to exit when the main program exits
connector_thread.start()

# Handle window close event
root.protocol("WM_DELETE_WINDOW", gui.quit_program)

root.mainloop()