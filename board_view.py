import itertools
import operator
import random

from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.widget import Widget

import env

class BoardView(Widget):
    def __init__(self, game, **kwargs):
        super(BoardView, self).__init__(**kwargs)
        self.game = game
        Window.bind(mouse_pos=self.mouse_motion)
        self.bind(size=self.resized)
        self.mouse_pos = None
        self.reset()

    def resized(self, a, b):
        self.square_size = min(self.size) / 8

    def reset(self):
        self.selected = None
        self.is_dragging = False
        self.shuffle_sets()

    def shuffle_sets(self):
        'Randomly change which chess piece images sets are used'
        a = [0, 2, 4]
        b = [1, 3, 5]
        random.shuffle(a)
        random.shuffle(b)
        self.chess_sets_perm = [[a, b][i%2][i//2] for i in range(6)]

    def show_board(self):
        cols, see = self.board_info()

        self.canvas.clear()
        sq = (self.square_size-1, self.square_size-1)
        with self.canvas:
            for (x, y), col in cols.items():
                sx, sy = self.screen_pos((x, y))
                Color(*[x/255 for x in col])
                Rectangle(pos=(sx, sy), size=sq)
                if (x, y) in self.game.board:
                    piece = self.game.board[x, y]
                    if self.game.board[x, y].freeze_until > self.game.counter:
                        freeze_ratio = (piece.freeze_until - self.game.counter) / piece.freeze_time
                        Color(.7, .7, .7)
                        Rectangle(pos=(sx, sy), size=(self.square_size * freeze_ratio, self.square_size))

            for pos, piece in self.game.board.items():
                if pos not in see:
                    continue
                transparent = False
                if piece.last_move_time is not None:
                    move_time = (self.game.counter - piece.last_move_time)*0.1
                    if move_time < 1:
                        pos_between = move_time
                        if piece.last_pos is not None:
                            last_screen_pos = self.screen_pos(piece.last_pos)
                            new_screen_pos = self.screen_pos(pos)
                            Rectangle(
                                texture=piece.image(self.chess_sets_perm),
                                pos=[int(last_screen_pos[i]+(new_screen_pos[i]-last_screen_pos[i])*pos_between) for i in range(2)],
                                size=sq)
                if piece is self.selected and self.game.active():
                    transparent = True
                Color(1, 1, 1, .5 if transparent else 1)
                Rectangle(
                    texture=piece.image(self.chess_sets_perm),
                    pos=self.screen_pos(pos),
                    size=sq)

            if self.selected is not None and self.dst_pos is not None and self.game.active():
                Color(1, 1, 1, .5)
                Rectangle(
                    texture=self.selected.image(self.chess_sets_perm),
                    pos=self.screen_pos(self.dst_pos),
                    size=sq)

            if self.is_dragging:
                x, y = self.raw_mouse_pos
                Color(1, 1, 1, .5)
                Rectangle(
                    texture=self.selected.image(self.chess_sets_perm),
                    pos=(x-self.square_size//2, y-self.square_size//2),
                    size=sq)

    def board_info(self):
        player = None if self.game.mode == 'replay' else self.game.player
        flash = {}
        if not env.is_mobile and not self.is_dragging:
            flashy = self.game.board.get(self.mouse_pos)
            if flashy is not None and flashy.player == player:
                for pos in flashy.moves():
                    flash[pos] = flashy.sight_color

        movesee = {}
        see = set()
        for piece in self.game.board.values():
            if player is not None and piece.side() != player%2:
                continue
            see.add(piece.pos)
            if piece.player == player:
                moves = set(piece.moves())
                if self.mouse_pos in moves and not self.is_dragging and piece == self.selected:
                    flash[piece.pos] = piece.sight_color
                else:
                    movesee[piece.pos] = piece.sight_color
            for dst in itertools.chain(piece.sight()):
                see.add(dst)
                if piece.player == player and dst in moves:
                    movesee[dst] = list(map(operator.add, movesee.get(dst, [0]*3), piece.sight_color))

        cols = {}
        for pos in see:
            cols[pos] = (240, 240, 240)
        for pos, col in movesee.items():
            cols[pos] = [128+a*127./max(col) for a in col]
        for pos, col in flash.items():
            cols[pos] = [255*x for x in col]

        return cols, see

    def on_touch_down(self, event):
        if not self.game.active():
            return
        self.calc_mouse_pos(event.pos)
        if event.is_mouse_scrolling:
            if [] == self.potential_pieces:
                return
            d = 1 if event.button == 'scrolldown' else -1
            self.selected = self.potential_pieces[
                (self.potential_pieces.index(self.selected)+d)%len(self.potential_pieces)]
            return
        if self.mouse_pos in self.game.board and self.game.board[self.mouse_pos].player == self.game.player:
            self.is_dragging = True
            self.selected = self.game.board[self.mouse_pos]
            self.dst_pos = None

    def mouse_motion(self, _win, pos):
        if not self.game.active():
            return
        self.raw_mouse_pos = pos
        self.calc_mouse_pos(pos)

    def on_touch_up(self, event):
        if not self.game.active():
            return
        if event.is_mouse_scrolling:
            return
        self.calc_mouse_pos(event.pos)
        self.is_dragging = False
        if self.selected is None or self.dst_pos is None:
            return
        self.game.add_action('move', self.selected.pos, self.dst_pos)
        self.selected = None

    def calc_mouse_pos(self, pos):
        board_pos = [int((x - sx) // self.square_size) for x, sx in zip(pos, self.pos)]
        if self.game.player%2 == 1:
            board_pos = [s-1-x for x, s in zip(board_pos, self.game.board_size)]
        self.mouse_pos = tuple(board_pos)

    def screen_pos(self, pos):
        if self.game.player%2 == 1:
            pos = [s-1-x for x, s in zip(pos, self.game.board_size)]
        return tuple(sx+self.square_size*x for x, sx in zip(pos, self.pos))

    last_pos = None
    def update_dst(self):
        if self.selected is not None and self.game.board.get(self.selected.pos) is not self.selected:
            self.selected = None
        if self.is_dragging and self.selected is not None:
            self.dst_pos = None
            if self.mouse_pos in self.selected.moves():
                self.dst_pos = self.mouse_pos
            return
        self.is_dragging = False
        self.potential_pieces = []
        for piece in self.game.board.values():
            if piece.player == self.game.player and self.mouse_pos in piece.moves():
                self.potential_pieces.append(piece)
        self.potential_pieces.sort(key = lambda x: x.move_preference)
        if [] == self.potential_pieces:
            self.selected = None
        else:
            self.dst_pos = self.mouse_pos
            if self.last_pos != self.dst_pos or self.selected not in self.potential_pieces:
                self.selected = self.potential_pieces[0]
            self.last_pos = self.dst_pos
