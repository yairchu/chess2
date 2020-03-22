import marshal
import random
import select
import socket
import threading
import time
import urllib.request

import stun

import env

def poll(sock):
    return select.select([sock], [], [], 0)[0] != []

def any_actions(actions):
    return any(acts for _, acts in actions)

class NetEngine:
    latency = 5
    replay_max_wait = 30

    def __init__(self, game):
        self.game = game
        self.socket = None
        self.done = False
        self.threads = []
        self.iter_actions = {}
        self.peers = []
        self.address = None
        self.should_start_replay = False

        net_thread = threading.Thread(target=self.net_thread_go)
        self.threads.append(net_thread)
        self.instance_id = random.randrange(2**64)
        if not env.dev_mode:
            net_thread.start()

    def net_thread_go(self):
        self.setup_socket()
        if self.done:
            return
        self.setup_addr_name()
        if self.done:
            return
        self.wait_for_connections()

    def setup_socket(self):
        while True:
            local_port = random.randint(1024, 65535)
            try:
                if self.done:
                    return
                _nat_type, gamehost, gameport = stun.get_ip_info('0.0.0.0', local_port)
                if gameport is None:
                    print('retrying stun connection')
                    continue
                self.my_addr = (gamehost, gameport)
                print('external host %s:%d' % self.my_addr)
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(('', local_port))
                print('listening on port %d' % local_port)
            except socket.error:
                print('retrying establishing server')
                continue
            break
        self.socket = sock

    def setup_addr_name(self):
        url = 'http://game-match.herokuapp.com/register/chess2/%s/%d/' % self.my_addr
        print('registering at %s' % url)
        self.address = urllib.request.urlopen(url).read().decode('utf-8')
        self.game.messages.append('')
        self.game.messages.append('Your address is:')
        self.game.messages.append(self.address.upper())
        self.game.messages.append('')
        self.game.messages.append('Type the address of a friend to play with them')
        self.game.update_label()

    def wait_for_connections(self):
        while not self.peers:
            time.sleep(5)
            if self.done:
                return
            url = 'http://game-match.herokuapp.com/lookup/chess2/%s/' % self.address.replace(' ', '%20')
            print('checking game at %s' % url)
            self.add_peers(urllib.request.urlopen(url).read().decode('utf-8'))

    def connect(self, address):
        connect_thread = threading.Thread(target=self.connect_thread_go, args=(address, ))
        self.threads.append(connect_thread)
        connect_thread.start()

    def connect_thread_go(self, addr):
        while self.address is None:
            # Net thread didn't finish
            time.sleep(1)
        url = 'http://game-match.herokuapp.com/connect/chess2/%s/%s/' % (self.address.replace(' ', '%20'), addr.replace(' ', '%20'))
        print('looking up host at %s' % url)
        self.add_peers(urllib.request.urlopen(url).read().decode('utf-8'))
        self.game.game_model.player = 1

    def add_peers(self, peers_str):
        for x in peers_str.split():
            host, port_str = x.split(':')
            port = int(port_str)
            if (host, port) == self.my_addr:
                continue
            if (host, port) in self.peers:
                continue
            print('established connection with %s:%d' % (host, port))
            self.peers.append((host, port))
            self.game.game_model.started = True
            self.game.messages.clear()
            self.game.messages.append('')
            self.game.messages.append('Connection successful!')
            self.game.messages.append('THE GAME BEGINS!')
            self.game.update_label()

    def active(self):
        return self.peers or env.dev_mode

    def communicate(self):
        if self.socket is None:
            return
        packet = marshal.dumps((
            self.instance_id,
            [(i, self.iter_actions.setdefault(i, {}).setdefault(self.instance_id, []))
                for i in
                range(
                    max(0, self.game.game_model.counter-self.latency),
                    self.game.game_model.counter+self.latency)]))
        for peer in self.peers:
            self.socket.sendto(packet, 0, peer)
        while poll(self.socket):
            packet, peer = self.socket.recvfrom(0x1000)
            peer_id, peer_iter_actions = marshal.loads(packet)
            for i, actions in peer_iter_actions:
                self.iter_actions.setdefault(i, {})[peer_id] = actions

    def get_replay_actions(self):
        return sorted(self.iter_actions.get(self.game.game_model.counter, {}).items())

    def act(self):
        if self.game.game_model.is_replay:
            all_actions = self.get_replay_actions()
            if any_actions(all_actions):
                self.replay_wait = 0
            else:
                self.replay_wait += 1
                if self.replay_wait == self.replay_max_wait:
                    self.replay_wait = 0
                    while not any_actions(all_actions) and self.game.game_model.counter+1 < self.replay_stop:
                        self.game.game_model.counter += 1
                        all_actions = self.get_replay_actions()
        else:
            if not self.peers and not env.dev_mode:
                return
            if self.game.game_model.counter < self.latency:
                self.game.game_model.counter += 1
                return
            if len(self.iter_actions.get(self.game.game_model.counter, {})) <= len(self.peers):
                # We haven't got communications from all peers for this iteration.
                # So we'll wait.
                return
            all_actions = sorted(self.iter_actions[self.game.game_model.counter].items())

        for i, actions in all_actions:
            for action_type, params in actions:
                action_func = getattr(self.game, 'action_'+action_type, None)
                if action_func is None:
                    self.game.messages.append(action_type + ': no such action')
                else:
                    if not hasattr(action_func, 'quiet'):
                        self.game.messages.append(self.game.nick(i) + ' did ' + action_type.upper())
                    if env.dev_mode:
                        action_func(i, *params)
                    else:
                        try:
                            action_func(i, *params)
                        except:
                            self.game.messages.append('action ' + action_type + ' failed')

        self.game.update_label()
        self.game.game_model.counter += 1

        if self.game.game_model.is_replay and self.game.game_model.counter == self.replay_stop:
            self.game.game_model.is_replay = False
            self.game.action_reset(self.instance_id, self.game.game_model.num_boards)

        if self.should_start_replay:
            self.should_start_replay = False
            print('start replay!')
            self.game.game_model.is_replay = True
            self.replay_stop = self.game.game_model.counter
            self.game.game_model.counter = self.game.last_start
            self.replay_wait = 0
            self.game.action_reset(self.instance_id, self.game.game_model.num_boards)

    def iteration(self):
        self.communicate()

        if self.instance_id not in self.iter_actions.setdefault(self.game.game_model.counter+self.latency, {}):
            self.iter_actions[self.game.game_model.counter+self.latency][self.instance_id] = self.game.game_model.cur_actions
            self.game.game_model.cur_actions = []

        self.act()

    def start_replay(self):
        self.should_start_replay = True
