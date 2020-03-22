'''
A networked real-time strategy game based on Chess
'''

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

import env
from board_view import BoardView
from game_model import GameModel
from net_engine import NetEngine
from widgets import WrappedLabel

num_msg_lines = 6

def quiet_action(func):
    func.quiet = True
    return func

class Game(BoxLayout):
    def __init__(self, **kwargs):
        super(Game, self).__init__(**kwargs)
        self.game_model = GameModel()
        self.game_model.king_captured = self.king_captured
        self.net_engine = NetEngine(self)
        self.nicknames = {}
        self.messages = []
        self.last_start = 0
        self.last_selected_at_dst = {}
        self.score = [0, 0]

        self.board_view = BoardView(self.game_model)
        self.add_widget(self.board_view)

        self.info_pane = BoxLayout(orientation='vertical')
        self.add_widget(self.info_pane)

        row = 60
        self.score_label = WrappedLabel(
            halign='center',
            size_hint=(1, 0),
            size_hint_min_y=row)
        self.info_pane.add_widget(self.score_label)

        self.label = WrappedLabel(halign='center', valign='bottom')
        self.info_pane.add_widget(self.label)

        self.text_input = TextInput(
            multiline=False,
            text_validate_unfocus=env.is_mobile,
            size_hint=(1, 0),
            size_hint_min_y=row)
        self.text_input.bind(on_text_validate=self.handle_text_input)
        if not env.is_mobile:
            def steal_focus(*args):
                if not self.text_input.focus:
                    self.text_input.focus = True
            self.text_input.bind(focus=steal_focus)
        self.info_pane.add_widget(self.text_input)

        self.action_reset(self.net_engine.instance_id)

        self.messages.append('')
        self.messages.append('Welcome to Chess 2!')
        self.messages.append('Developer Mode' if env.dev_mode else 'Establishing server connection...')
        self.update_label()

        self.bind(size=self.resized)
        Clock.schedule_interval(self.on_clock, 1/30)

    def update_label(self):
        self.score_label.text = 'White: %d   Black: %d' % tuple(self.score)
        self.label.text = '\n'.join(self.messages[-num_msg_lines:])

    def resized(self, _widget, size):
        self.orientation = 'horizontal' if size[0] > size[1] else 'vertical'
        p = 1/3
        self.info_pane.size_hint = (p, 1) if self.orientation == 'horizontal' else (1, p)

    def nick(self, i):
        return self.nicknames.get(i, 'anonymouse')

    def handle_text_input(self, entry):
        command = entry.text
        entry.text = ''
        if not command:
            return
        if command[:1] == '/':
            self.game_model.add_action(*command[1:].split())
            return
        if self.net_engine.active():
            # Chat
            self.game_model.add_action('msg', command)
            return
        self.net_engine.connect(command)

    @quiet_action
    def action_nick(self, i, *words):
        name = '-'.join(words)
        if not name:
            name = 'null-boy'
        self.messages.append(self.nick(i) + ' is now ' + name)
        self.nicknames[i] = name

    @quiet_action
    def action_msg(self, i, *txt):
        self.messages.append('%s: %s' % (self.nick(i), ' '.join(txt)))

    @quiet_action
    def action_move(self, _id, src, dst):
        if src not in self.game_model.board:
            return
        self.game_model.board[src].move(dst)

    def action_reset(self, _id, num_boards=1):
        self.game_model.init(int(num_boards))
        self.board_view.reset()
        self.potential_pieces = []

    def action_replay(self, i):
        self.iter_actions[self.game_model.counter][i] = [('endreplay', ())]
        self.replay_counter = self.last_start
        self.action_reset(i, self.num_boards)
        self.is_replay = True

    def action_endreplay(self, _id):
        self.is_replay = False

    def player_str(self, player):
        if player is None:
            return 'spectator'
        r = ['White', 'Black'][player%2]
        if self.game_model.num_boards > 1:
            r += '#'+str(player//2)
        return r

    @quiet_action
    def action_become(self, i, player):
        player = int(player)
        if i == self.net_engine.instance_id:
            self.game_model.player = player
        self.messages.append(self.nick(i) + ' becomes ' + self.player_str(player))

    def action_credits(self, _id):
        self.messages.extend('''Credits:
        Programming: Yair Chuchem
        Chess sets/Graphics: Armondo H. Marroquin and Eric Bentzen (http://www.enpassant.dk/chess/fonteng.htm)
        Logic/Concept: Ancient People, Yair Chuchem, and fellow Play-Testers
        Programming Infrastructure: Python (Guido van Rossum and friends), Pygame/SDL (Pete Shinners and friends)
        '''.split('\n'))

    def action_help(self, _id):
        self.messages.append('commands: /help | /reset | /nick <nickname> | /replay | /credits')

    def king_captured(self, who):
        winner = 1 - who%2
        self.score[winner] += 1
        self.game_model.init(self.game_model.num_boards)
        self.board_view.reset()
        self.messages.append('')
        self.messages.append('%s King Captured!' % self.player_str(who))
        self.messages.append('%s wins!' % self.player_str(winner))
        self.update_label()

    def on_clock(self, _interval):
        self.net_engine.iteration()
        self.board_view.update_dst()
        self.board_view.show_board()

class Chess2App(App):
    def build(self):
        self.game = Game()
        self.game.text_input.focus = True
        return self.game
    def stop(self):
        self.game.done = True

if __name__ == '__main__':
    Window.softinput_mode = 'pan'
    Chess2App().run()
