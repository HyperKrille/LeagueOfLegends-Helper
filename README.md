# League of Legends Helper

![League of Legends Logo](https://upload.wikimedia.org/wikipedia/commons/2/2a/LoL_icon.png)  
*Script to auto-accept, auto-pick, and auto-ban in League of Legends.*

---

## **Overview**

This project is a Python-based GUI tool designed to enhance your League of Legends experience by automating repetitive tasks during the matchmaking and champion selection phases. It interacts with the League of Legends client using the `lcu_driver` library to communicate with the League Client API (LCU). The tool is lightweight, easy to use, and helps you focus on your game strategy rather than manual inputs.

---

## **Features**

- **Summoner Name Display**: Displays the currently logged-in summoner's name and tagline.
- **Game Status Tracking**: Tracks the current game status (e.g., in lobby, in queue, in champion select, in game).
- **Auto-Accept Matches**: Automatically accepts match queue when enabled.
- **Auto-Ban Champion**: Allows users to pre-select a champion to be banned automatically during champion select.
- **Auto-Pick Champion**: Allows users to pre-select a champion to be picked automatically during champion select.
- **Role-Specific Configurations**: Set different auto-ban and auto-pick champions for each role (Top, Jungle, Mid, Bottom, Support).
- **Searchable Champion Dropdowns**: Easily search and filter champions for banning and picking.
- **Pre-Hover Champions**: Hovers over the selected champion during the PLANNING phase for a smoother experience.
- **Persistent Settings**: Saves your last selected auto-ban and auto-pick choices for future games.
- **Real-Time Logs**: Provides real-time logs of actions and events for transparency.

---

## **Installation**

### Prerequisites
- **Python 3.8 or higher**: Download and install Python from [python.org](https://www.python.org/).
- **League of Legends Client**: The tool requires the League of Legends client to be running.
### Steps
1. Clone the Repository:

```bash
git clone https://github.com/your-username/LeagueOfLegends-Helper.git
cd LeagueOfLegends-Helper
```
2. Install Dependencies:
Install the required Python libraries using `pip`:
```bash
pip install -r requirements.txt
```

3. Run the Script:
Launch the tool by running:
```bash
python GUI.py
```

## Creating a .exe File

To distribute the tool as a standalone executable, you can use `PyInstaller`. Follow these steps:

1. **Install PyInstaller:**

```bash
pip install pyinstaller
```
2. **Create the Executable:**
Navigate to the project directory and run:

```bash
pyinstaller --onefile --windowed --add-data "music.txt;." GUI.py
```
* The `--onefile` flag bundles everything into a single executable.

* The `--windowed` flag prevents a terminal window from appearing when running the tool.

* The `--add-data` flag will include the `.txt` file with the executable.

3. **Locate the Executable:**

* The `.exe` file will be created in the `dist` folder inside your project directory.

## Configuration File

The tool saves your settings in a `role_config.json` file. This file stores:

* Auto-ban and auto-pick selections for each role.
* Auto-accept match preference.

You can manually edit this file if needed, but changes made in the GUI will automatically update it.



