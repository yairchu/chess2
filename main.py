'''
A networked real-time strategy game based on Chess
'''

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput

import env
from board_view import BoardView
from game_model import GameModel
from net_engine import NetEngine
from widgets import WrappedLabel, WrappedButton

num_msg_lines = 3 if env.is_mobile else 8

def quiet_action(func):
    func.quiet = True
    return func

class Game(BoxLayout):
    game_title = 'Chess 2: No turns, no sight!'

    def __init__(self, **kwargs):
        super(Game, self).__init__(**kwargs)
        self.game_model = GameModel()
        self.game_model.king_captured = self.king_captured
        self.game_model.on_message.append(self.update_label)
        self.net_engine = NetEngine(self.game_model, self.get_action)

        self.score = [0, 0]

        self.board_view = BoardView(self.game_model)
        self.add_widget(self.board_view)
        self.game_model.on_init.append(self.board_view.reset)

        self.info_pane = BoxLayout(orientation='vertical', size_hint_min_y=500)
        self.add_widget(self.info_pane)

        row_args = {'size_hint': (1, 0), 'size_hint_min_y': 70}

        if not env.is_mobile:
            self.info_pane.add_widget(WrappedLabel(halign='center', text=self.game_title, **row_args))

        self.button_pane = BoxLayout(orientation='vertical', size_hint=(1, .4))
        self.info_pane.add_widget(self.button_pane)

        self.button_pane.add_widget(WrappedButton(
            halign='center',
            text='Tutorial: How to play',
            on_press=self.start_tutorial))
        self.button_pane.add_widget(WrappedButton(
            halign='center',
            text='Start Game' if env.is_mobile else 'Start Game: Play with friends',
            on_press=self.start_game))

        self.score_label = WrappedLabel(
            halign='center',
            **row_args)
        self.info_pane.add_widget(self.score_label)

        self.label = WrappedLabel(halign='center', valign='bottom')
        self.info_pane.add_widget(self.label)

        self.text_input = TextInput(
            multiline=False,
            text_validate_unfocus=env.is_mobile,
            **row_args)
        self.text_input.bind(on_text_validate=self.handle_text_input)
        if not env.is_mobile:
            def steal_focus(*args):
                if not self.text_input.focus:
                    self.text_input.focus = True
            self.text_input.bind(focus=steal_focus)
        self.info_pane.add_widget(self.text_input)

        self.game_model.add_message('')
        self.game_model.add_message(self.game_title if env.is_mobile else 'Welcome to Chess 2!')

        self.bind(size=self.resized)
        Clock.schedule_interval(self.on_clock, 1/30)

    def stop_net_engine(self):
        if not self.net_engine:
            return
        self.net_engine.should_stop = True

    def start_game(self, _):
        self.game_model.mode = 'connect'
        self.score = [0, 0]
        self.stop_net_engine()
        self.net_engine = NetEngine(self.game_model, self.get_action)
        self.game_model.messages.clear()
        self.game_model.add_message('Establishing server connection...')
        self.action_reset()
        self.net_engine.start()

    def start_tutorial(self, i):
        self.game_model.mode = 'tutorial'
        self.stop_net_engine()
        self.net_engine = NetEngine(self.game_model, self.get_action)
        self.game_model.messages.clear()
        self.game_model.add_message('Move the chess pieces and see what happens!')
        self.tutorial_messages = [
            'Keep moving the pieces at your own pace.',
            'Each piece has its own color, and the board is painted to show where it can move.',
            'You only see where your pieces can move',
            'You will also see any piece that threatens the king.',
            'Note that unlike classic chess, the king can move to a threatened position!',
            'There are no turns!',
            'There are cool-downs (rate limits) instead.',
            'You win the game by capturing the opponent king',
            'The game is played with friends over the internet.',
            'To start a game both you and your friend need to click "Start Game".',
            'Then either you or the friend should type the game identifier that the other was given.',
            'This concludes our tutorial!',
            ]
        self.game_model.init()
        self.net_engine.new_game()

    def update_label(self):
        self.score_label.text = 'White: %d   Black: %d' % tuple(self.score)
        self.label.text = '\n'.join(self.game_model.messages[-num_msg_lines:])

    def resized(self, _widget, size):
        self.orientation = 'horizontal' if size[0] > size[1] else 'vertical'
        if self.orientation == 'horizontal':
            self.button_pane.orientation = 'vertical'
            self.button_pane.size_hint = (1, .4)
            self.button_pane.size_hint_min_y = 140
        else:
            self.button_pane.orientation = 'horizontal'
            self.button_pane.size_hint = (1, .4)
            self.button_pane.size_hint_min_y = 70
        p = 1/3
        self.info_pane.size_hint = (p, 1) if self.orientation == 'horizontal' else (1, p)

    def nick(self, i):
        if i == self.net_engine.instance_id:
            return self.player_str(self.game_model.player)
        return 'friend'

    def handle_text_input(self, entry):
        command = entry.text
        entry.text = ''
        if not command:
            return
        if command[:1] == '/':
            self.game_model.add_action(*command[1:].split())
            return
        if self.game_model.active():
            # Chat
            self.game_model.add_action('msg', command)
            return
        self.net_engine.connect(command)

    def get_action(self, action_type):
        return getattr(self, 'action_'+action_type, None)

    @quiet_action
    def action_msg(self, i, *txt):
        self.game_model.add_message('%s: %s' % (self.nick(i), ' '.join(txt)))

    @quiet_action
    def action_move(self, _id, src, dst):
        if src not in self.game_model.board:
            return
        piece = self.game_model.board[src]
        if piece.move(dst):
            self.game_model.add_message('%s %s moved' % (self.player_str(piece.player), type(piece).__name__.lower()))
            if self.game_model.mode == 'tutorial' and self.tutorial_messages:
                self.game_model.add_message('')
                self.game_model.add_message(self.tutorial_messages.pop(0))

    def action_reset(self, _id=None, num_boards=1):
        self.net_engine.new_game()
        self.game_model.init(int(num_boards))

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
            self.board_view.reset()
        self.game_model.add_message(self.nick(i) + ' becomes ' + self.player_str(player))

    def action_credits(self, _id):
        self.game_model.add_message('''Credits:
        Programming: Yair Chuchem
        Chess sets/Graphics: Armondo H. Marroquin and Eric Bentzen (http://www.enpassant.dk/chess/fonteng.htm)
        Logic/Concept: Ancient People, Yair Chuchem, and fellow Play-Testers
        Programming Infrastructure: Python (Guido van Rossum and friends), Pygame/SDL (Pete Shinners and friends)
        ''')

    def action_help(self, _id):
        self.game_model.add_message('commands: /help | /reset | /credits')

    def king_captured(self, who):
        if self.game_model.mode == 'replay':
            return
        winner = 1 - who%2
        self.score[winner] += 1
        self.game_model.add_message('')
        self.game_model.add_message('%s King Captured!' % self.player_str(who))
        self.game_model.add_message('%s wins!' % self.player_str(winner))
        self.net_engine.start_replay()

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
        self.game.stop_net_engine()

if __name__ == '__main__':
    Window.softinput_mode = 'pan'
    Chess2App().run()
