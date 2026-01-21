# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from collections import namedtuple
from time import perf_counter
from datetime import datetime
from csv import DictWriter
import json
import os
import platform
import sys
from pathlib import Path

from core.constants import CONFIG, OUTPUT_BASE_DIR, OPENMATB_ROOT, PATHS, REPLAY_MODE
from core.utils import find_the_first_available_session_number, find_the_last_session_number

class Logger:
    def __init__(self):
        self.datetime = datetime.now()
        self.fields_list = ['logtime', 'scenario_time', 'type', 'module', 'address', 'value']
        self.slot = namedtuple('Row', self.fields_list)
        self.maxfloats = 6  # Time logged at microsecond precision
        self.session_id = None
        self.lsl = None
        self._lsl_ever_enabled = False
        self._finalized = False
        self.manifest_path = None

        self.session_id = find_the_first_available_session_number()
        self.mode = 'w'

        self.scenario_time = 0  # Updated by the scheduler class

        self.file = None
        self.writer = None
        self.queue = list()

        if not REPLAY_MODE:
            self.path = PATHS['SESSIONS'].joinpath(self.datetime.strftime("%Y-%m-%d"),
                                f'{self.session_id}_{self.datetime.strftime("%y%m%d_%H%M%S")}.csv')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.open()
            self._write_manifest()


    def _write_manifest(self):
        if self.path is None:
            raise RuntimeError('Cannot write manifest before session CSV path is set')

        manifest_path = self.path.with_suffix('.manifest.json')
        self.manifest_path = manifest_path

        scenario_path = None
        try:
            scenario_path = CONFIG.get('Openmatb', 'scenario_path', fallback=None)
        except Exception:
            scenario_path = None

        scenario_name = None
        if scenario_path:
            scenario_name = Path(scenario_path).stem

        openmatb_version = None
        try:
            openmatb_version = OPENMATB_ROOT.joinpath('VERSION').read_text(encoding='utf-8').strip()
        except Exception:
            openmatb_version = None

        repo_commit = os.environ.get('OPENMATB_REPO_COMMIT')
        submodule_commit = os.environ.get('OPENMATB_SUBMODULE_COMMIT')
        if not repo_commit or not submodule_commit:
            raise RuntimeError(
                'Missing required git commit identifiers in environment: '
                'OPENMATB_REPO_COMMIT and/or OPENMATB_SUBMODULE_COMMIT'
            )

        output_dir_abs = str(Path(OUTPUT_BASE_DIR).resolve())
        event_log_path_abs = str(Path(self.path).resolve())

        manifest = {
            'manifest_version': 1,
            'created_at_local': self.datetime.isoformat(timespec='seconds'),
            'started_at_local': self.datetime.isoformat(timespec='seconds'),
            'ended_at_local': None,
            'repo_commit': repo_commit,
            'submodule_commit': submodule_commit,
            'scenario_name': scenario_name,
            'participant_id': os.environ.get('OPENMATB_PARTICIPANT') or os.environ.get('OPENMATB_PARTICIPANT_ID'),
            'session_id': os.environ.get('OPENMATB_SESSION') or os.environ.get('OPENMATB_SESSION_ID'),
            'lsl_enabled': False,
            'output_dir': output_dir_abs,
            'event_log_path': event_log_path_abs,
            'logger_session_id': int(self.session_id) if self.session_id is not None else None,
            'openmatb': {
                'version': openmatb_version,
                'scenario_path': scenario_path,
            },
            'paths': {
                'output_base_dir': output_dir_abs,
                'sessions_dir': str(Path(PATHS['SESSIONS']).resolve()),
                'session_csv': event_log_path_abs,
                'scenario_errors_log': str(PATHS['SCENARIO_ERRORS']),
            },
            'environment': {
                'os': os.name,
                'platform': platform.platform(),
                'python_executable': sys.executable,
                'python_version': sys.version,
            },
            'identifiers': {
                'participant': os.environ.get('OPENMATB_PARTICIPANT') or os.environ.get('OPENMATB_PARTICIPANT_ID'),
                'session': os.environ.get('OPENMATB_SESSION') or os.environ.get('OPENMATB_SESSION_ID'),
            },
            'output_env': {
                'OPENMATB_OUTPUT_ROOT': os.environ.get('OPENMATB_OUTPUT_ROOT'),
                'OPENMATB_OUTPUT_SUBDIR': os.environ.get('OPENMATB_OUTPUT_SUBDIR'),
            },
        }

        self._atomic_write_json(manifest_path, manifest)


    def _atomic_write_json(self, path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        with open(tmp_path, 'w', encoding='utf-8', newline='') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)


    def finalize(self):
        if REPLAY_MODE:
            return
        if self._finalized:
            return
        if self.manifest_path is None:
            raise RuntimeError('Manifest path is not set; cannot finalize run manifest')

        self._finalized = True

        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        manifest['ended_at_local'] = datetime.now().isoformat(timespec='seconds')
        manifest['lsl_enabled'] = bool(self._lsl_ever_enabled or (self.lsl is not None))

        self._atomic_write_json(self.manifest_path, manifest)

    # TODO: see if we can/should merge record_* methods into one
    def record_event(self, event):
        if len(event.command) == 1:
            adress = 'self'
            value = event.command[0]
        elif len(event.command) == 2:
            adress = event.command[0]
            value = event.command[1]
        slot = [perf_counter(), self.scenario_time, 'event', event.plugin, adress, value]
        self.write_single_slot(slot)


    def record_input(self, module, key, state):
        slot = [perf_counter(), self.scenario_time, 'input', module, key, state]
        self.write_single_slot(slot)


    def record_aoi(self, container, name):
        plugin = name.split('_')[0]
        widget = '_'.join(name.split('_')[1:])
        slot = [perf_counter(), self.scenario_time, 'aoi', plugin, widget, container.get_x1y1x2y2()]
        self.write_single_slot(slot)


    def record_state(self, graph_name, attribute, value):
        module = graph_name.split('_')[0]
        graph_name = '_'.join(graph_name.split('_')[1:])
        address = f'{graph_name}, {attribute}'
        slot = [perf_counter(), self.scenario_time, 'state', module, address, value]
        self.write_single_slot(slot)


    def record_parameter(self, plugin, address, value):
        slot = [perf_counter(), self.scenario_time, 'parameter', plugin, address, value]
        self.write_single_slot(slot)


    def log_performance(self, module, metric, value):
        slot = [perf_counter(), self.scenario_time, 'performance', module, metric, value]
        self.write_single_slot(slot)


    def record_a_pseudorandom_value(self, module, seed, output):
        slot = [perf_counter(), self.scenario_time, 'seed_value', module, '', seed]
        self.write_single_slot(slot)
        slot = [perf_counter(), self.scenario_time, 'seed_output', module, '', output]
        self.write_single_slot(slot)


    def log_manual_entry(self, entry, key='manual'):
        slot = [perf_counter(), self.scenario_time, key, '', '', entry]
        self.write_single_slot(slot)


    def __enter__(self):
        self.open()
        return self


    def __exit__(self, type, value, traceback):
        self.file.close()


    def open(self):
        create_header = False if self.path.exists() and self.mode == 'a' else True
        self.file = open(str(self.path), self.mode, newline = '')
        self.writer = DictWriter(self.file, fieldnames=self.fields_list)
        if create_header:
            self.writer.writeheader()


    def close(self):
        self.file.close()


    def add_row_to_queue(self, row):
        self.queue.append(row)


    def empty_queue(self):
        self.queue = list()


    def round_row(self, row):
        new_list = list()
        for col in row:
            new_value = round(col, self.maxfloats) if isinstance(col, float) or isinstance(col, int) else col
            new_list.append(new_value)
        return self.slot(*new_list)


    def write_row_queue(self, change_dict=None):
        if not REPLAY_MODE:
            if len(self.queue) == 0:
                print(_('Warning, queue is empty'))
            else:
                for this_row in self.queue:
                    row_dict = self.round_row(this_row)._asdict()
                    if change_dict is not None:
                        for k,v in change_dict.items():
                            row_dict[k] = v
                    self.writer.writerow(row_dict)
                    if self.lsl is not None:
                        self._lsl_ever_enabled = True
                        self.lsl.push(';'.join([str(r) for r in row_dict.values()]))
                self.empty_queue()


    def write_single_slot(self, values):
        row = self.slot(*values)
        self.add_row_to_queue(row)
        self.write_row_queue()


    def set_totaltime(self, totaltime):
        self.totaltime = totaltime


    def set_scenario_time(self, scenario_time):
        self.scenario_time = scenario_time


logger = Logger()