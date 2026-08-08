# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from plugins.abstractplugin import BlockingPlugin
from core.widgets import Simpletext, Slider, Frame
from core.constants import FONT_SIZES as F, PATHS as P, COLORS as C, REPLAY_MODE
from re import match as regex_match

#: Horizontal centre of a Slider's groove, as a proportion of the row width.
#:
#: Slider.set_sub_containers lays a row out as
#:     [min 0.133w][groove 0.6w][max 0.133w][value 0.133w]
#: -- one gutter to the left of the groove, two to the right -- so the groove's
#: centre sits at 0.4333w, not 0.5w. A question container built at full width
#: centres its text at 0.5w, which put every question 6.7% of the row width to
#: the RIGHT of the slider it labels. This is derived from the same expression
#: the slider uses rather than hard-coded, so the two cannot drift apart.
#:
#: Keep in step with Slider.set_sub_containers' slider_width default.
_SLIDER_WIDTH = 0.6
_GROOVE_CENTRE = (1 - _SLIDER_WIDTH) / 3 + _SLIDER_WIDTH / 2


class Genericscales(BlockingPlugin):
    def __init__(self):
        super().__init__()

        self.folder = P['QUESTIONNAIRES']
        new_par = dict(filename=None, pointsize=0, maxdurationsec=0,
                       response=dict(text=_('Set every slider, then press SPACE to validate'),
                                     key='SPACE'),
                       allowkeypress=True)
        self.sliders = dict()
        self.parameters.update(new_par)

        self.ignore_empty_lines = True

        # Values field accepts an optional 4th entry, the response step:
        #   min/max/default        -> continuous slider (NASA-TLX)
        #   min/max/default/step   -> snapped slider    (IMI, 1/7/4/1)
        self.regex_scale_pattern = r'(.*);(.*)/(.*);(\d*)/(\d*)/(\d*)'
        self.question_height_ratio = 0.1  # question + response slider
        self.question_interspace = 0.05  # Space to leave between two questions
        self.top_to_top = self.question_interspace + self.question_height_ratio

        self.untouched_message = _('Please respond to every item before continuing.')


    def drop_scale_widgets(self):
        """Discard the previous screen's questions and sliders.

        Widgets are keyed by rank (label_1, slider_1, ...), so a screen with fewer
        items than its predecessor would otherwise leave the surplus question and
        slider of the previous screen on display, and stop() would log their values
        as if they belonged to this screen.
        """
        for slider in self.sliders.values():
            slider.detach()
        self.sliders = dict()

        stale = [name for name in self.widgets
                 if name.startswith(self.get_widget_fullname('label_'))
                 or name.startswith(self.get_widget_fullname('slider_'))]
        for name in stale:
            self.widgets[name].hide()
            del self.widgets[name]


    def make_slide_graphs(self):
        self.drop_scale_widgets()
        super().make_slide_graphs()

        scales = self.current_slide.split('\n')
        scale_list = [s.strip() for s in scales if len(s.strip()) > 0]
        if len(scale_list) == 0:
            return

        all_scales_container = self.container.get_reduced(1, self.top_to_top*(len(scale_list)))

        height_in_prop = (self.question_height_ratio * self.container.h)/all_scales_container.h
        for l, scale in enumerate(scale_list):

            # Define the scale main container (question + response slider)
            scale_container = all_scales_container.reduce_and_translate(
                height=height_in_prop, y=1-(1/(len(scale_list)))*l)

            # Width 2 x _GROOVE_CENTRE, flush left (x=0), so the container spans
            # [0, 2*0.4333] and its centre lands on the groove's centre. Simpletext
            # anchors at x=0.5 of its container, so the question now sits directly
            # over the slider it labels. Hit-boxes and recorded values are
            # untouched -- only the label container moves. Applies to TLX, IMI and
            # the post-block checks together, since all three use this plugin.
            text_container = scale_container.reduce_and_translate(
                2 * _GROOVE_CENTRE, 0.4, 0, 1)
            slider_container = scale_container.reduce_and_translate(1, 0.6, 0, 0)

            if regex_match(self.regex_scale_pattern, scale):
                title, label, limit_labels, values = scale.strip().split(';')
                label_min, label_max = limit_labels.split('/')
                value_list = [int(v) for v in values.split('/')]
                value_min, value_max, value_default = value_list[:3]
                value_step = value_list[3] if len(value_list) > 3 else None

                self.add_widget(f'label_{l+1}', Simpletext, container=text_container,
                                text=label, wrap_width=0.8, font_size=F['MEDIUM'],
                                draw_order=self.m_draw)

                self.sliders[f'slider_{l+1}'] = self.add_widget(f'slider_{l+1}', Slider,
                                container=slider_container,
                                title=title, label_min=label_min, label_max=label_max,
                                value_min=value_min, value_max=value_max,
                                value_default=value_default, value_step=value_step,
                                rank=l, draw_order=self.m_draw+3)

        self.add_widget('untouched', Simpletext, container=self.container, text=str(),
                        color=C['RED'], font_size=F['MEDIUM'], x=0.5, y=0.04,
                        wrap_width=0.8, draw_order=self.m_draw+1)


    def refresh_widgets(self):
        # Useful for replay mode (refresh groove positions)
        if not super().refresh_widgets():
            return

        for slider_name, slider in self.sliders.items():
            slider.update()


    def get_untouched_sliders(self):
        return [s for s in self.sliders.values() if not s.is_touched()]


    def set_untouched_message(self, text):
        widget = self.get_widget('untouched')
        if widget is not None:
            widget.set_text(text)


    def do_on_key(self, keystr, state, emulate=False):
        # A questionnaire screen is validated with SPACE, and the vendor default
        # accepts that press whether or not the participant has answered anything --
        # every slider would then be logged at its default value. Refuse the press
        # while any slider is untouched. Replay is exempt: touch state is not part
        # of the log, so a replayed session could not advance.
        if state == 'release' and self.filter_key(keystr) == 'SPACE' and not REPLAY_MODE:
            if len(self.get_untouched_sliders()) > 0:
                self.set_untouched_message(self.untouched_message)
                return
            # Clear it only on a press that validates, so the key-down half of the
            # same press does not blank the warning and log the change.
            self.set_untouched_message(str())
        return super().do_on_key(keystr, state, emulate)


    def stop(self):
        for slider_name, slider_widget in self.sliders.items():
            self.log_performance(slider_widget.get_title(), slider_widget.get_value())
        super().stop()
