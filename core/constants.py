# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import sys
from pyglet.graphics import OrderedGroup as Group
from pathlib import Path
import os
import configparser

REPLAY_MODE = len(sys.argv) > 1 and sys.argv[1] == '-r'
REPLAY_STRIP_PROPORTION = 0.08

C = COLORS = dict(WHITE=(255, 255, 255, 255),
                  WHITE_TRANSLUCENT=(255, 255, 255, 235),
                  BLACK=(50, 50, 50, 255),
                  GREEN=(142, 219, 176, 255),
                  RED=(241, 100, 100, 255),
                  BACKGROUND=(240, 240, 240, 255),
                  LIGHTGREY=(220, 220, 220, 255),
                  DARKGREY=(50, 50, 50, 255),
                  GREY=(200, 200, 200, 255),
                  BLUE=(153, 204, 255, 255))

F = FONT_SIZES = dict(SMALL=12,
                      MEDIUM=16,
                      LARGE=20,
                      XLARGE=30)

# Proportion of the plugin title into its container
PLUGIN_TITLE_HEIGHT_PROPORTION = 0.1

# Limit between the background and the foreground in relation with draw order
BFLIM = 15

# Ignore these plugins arguments
DEPRECATED = ['pumpstatus', 'end', 'cutofffrequency', 'equalproportions']

OPENMATB_ROOT = Path(__file__).resolve().parents[1]


def _default_output_root() -> Path:
    if os.name == 'nt':
        return Path(r"C:\\data\\adaptive_matb")
    return Path.home() / 'data' / 'adaptive_matb'


def _resolve_output_base_dir() -> Path:
    output_root_raw = os.environ.get('OPENMATB_OUTPUT_ROOT')
    output_subdir_raw = os.environ.get('OPENMATB_OUTPUT_SUBDIR')

    output_root = Path(output_root_raw) if output_root_raw else _default_output_root()
    output_subdir = Path(output_subdir_raw) if output_subdir_raw else Path('openmatb')

    if output_subdir.is_absolute():
        return output_subdir
    return output_root / output_subdir


OUTPUT_BASE_DIR = _resolve_output_base_dir()
OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

PATHS = {
    'PLUGINS': OPENMATB_ROOT / 'plugins',
    'SESSIONS': OUTPUT_BASE_DIR / 'sessions',
}
PATHS.update({k.upper(): OPENMATB_ROOT / 'includes' / k
              for k in ['img', 'instructions', 'scenarios', 'sounds', 'questionnaires']})

PATHS['SESSIONS'].mkdir(parents=True, exist_ok=True)
PATHS['SCENARIO_ERRORS'] = OUTPUT_BASE_DIR / 'last_scenario_errors.log'

# Read the configuration file
CONFIG = configparser.ConfigParser()
CONFIG.read(OPENMATB_ROOT.joinpath('config.ini'))
