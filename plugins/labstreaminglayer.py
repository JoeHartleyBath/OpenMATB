# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import os
import re
from pathlib import Path

from plugins import Instructions
from core import validation

try:
    import pylsl
except:
    print("unable to import pylsl")

try:
    from pyglet.media import Player, load as pyglet_load
except Exception:
    Player = None
    pyglet_load = None

# Matches STUDY/V0/.../{stress|control}/PLAY|...|asset=<name> markers, as emitted
# by generate_full_study_scenarios.py / generate_adaptive_automation_scenarios.py.
# Playing the matched asset here -- inline, in this plugin's own update(), on
# OpenMATB's own scenario clock -- means the audio fires at the exact same time
# as the marker itself, using the same in-process pyglet engine the
# communications plugin already uses (see communications.py's own Player()),
# instead of an external process trying to resync via LSL/local-clock guessing.
_AUDIO_MARKER_RE = re.compile(r'/(?P<segment>stress|control)/PLAY[^|]*\|.*?asset=(?P<asset>[\w.\-]+)')
_STRESS_AUDIO_DIR = Path(__file__).resolve().parents[1] / 'includes' / 'sounds' / 'stress_pilot'


class Labstreaminglayer(Instructions):
    def __init__(self):
        super().__init__()

        self.validation_dict =  {
            'marker': validation.is_string,
            'streamsession': validation.is_boolean,
            'pauseatstart': validation.is_boolean, 'state': validation.is_string}

        self.parameters.update({'marker':'', 'streamsession':False,
                                'pauseatstart':False})

        self.stream_info = None
        self.stream_outlet = None
        self.stop_on_end = False

        self.lsl_wait_msg = _("Please enable the OpenMATB stream into your LabRecorder.")


    def start(self):
        # If we get there it's because the plugin is used.
        # If pylsl is not available this part should fail.
        # Create a LSL marker outlet.
        super().start()
        self.stream_info = pylsl.StreamInfo('OpenMATB', type='Markers', channel_count=1,
                                             nominal_srate=0, channel_format='string',
                                             source_id='myuidw435368')
        self.stream_outlet = pylsl.StreamOutlet(self.stream_info)

        if self.parameters['pauseatstart'] is True:
            self.slides = [self.get_msg_slide_content(self.lsl_wait_msg)]


    def update(self, dt):
        super().update(dt)

        if self.parameters['streamsession'] is True and self.logger.lsl is None:
            self.logger.lsl = self
        elif self.parameters['streamsession'] is False and self.logger.lsl is not None:
            self.logger.lsl = None

        if self.parameters['marker'] != '':
            # A marker has been set. Push it to the outlet.
            self.push(self.parameters['marker'])
            self._maybe_play_audio(self.parameters['marker'])

            # and reset the marker to empty.
            self.parameters['marker'] = ''


    def push(self, message):
        if self.stream_outlet is None:
            return
        self.stream_outlet.push_sample([message])
#        print(message)


    def _maybe_play_audio(self, marker_text):
        """Play the stress/control stimulus inline if this marker requests it
        and playback is enabled for its segment (OPENMATB_STRESS_AUDIO_ENABLED /
        OPENMATB_CONTROL_AUDIO_ENABLED env vars, set by run_openmatb.py). The
        marker is always pushed to the LSL outlet regardless -- this only
        controls whether the corresponding sound is actually heard.
        """
        if pyglet_load is None or Player is None:
            return

        match = _AUDIO_MARKER_RE.search(marker_text)
        if not match:
            return

        segment = match.group('segment')
        if os.environ.get(f'OPENMATB_{segment.upper()}_AUDIO_ENABLED', '').strip().lower() \
                not in ('1', 'true', 'yes', 'y', 'on'):
            return

        wav_path = _STRESS_AUDIO_DIR / f"{match.group('asset')}.wav"
        if not wav_path.exists():
            return

        try:
            source = pyglet_load(str(wav_path), streaming=False)
            player = Player()
            player.queue(source)
            player.play()
            # Keep a reference so the player isn't garbage-collected mid-playback.
            if not hasattr(self, '_audio_event_players'):
                self._audio_event_players = []
            self._audio_event_players = [p for p in self._audio_event_players if p.source is not None]
            self._audio_event_players.append(player)
        except Exception:
            pass



    def stop(self):
        super().stop()
        self.stream_info = None
        self.stream_outlet = None


    def get_msg_slide_content(self, str_msg):
        return f"<title>Lab streaming layer\n{self.lsl_wait_msg}"

