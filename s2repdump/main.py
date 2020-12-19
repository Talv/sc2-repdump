#!/usr/bin/python3

import sys
import os
import re
from typing import List
from collections import OrderedDict, Iterable
import argparse
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from more_itertools import peekable
from tabulate import tabulate
from colorlog import ColoredFormatter
import mpyq
from s2protocol import versions
from s2repdump.types import S2REPDUMP_VERSION, enum, resource


@enum
class EPlayerControl:
    OPEN     = 0
    CLOSED   = 1
    HUMAN    = 2
    COMPUTER = 3


@enum
class EObserve:
    NONE      = 0
    SPECTATOR = 1
    REFEREE   = 2


@enum
class EGameSpeed:
    SLOWER = 0
    SLOW   = 1
    NORMAL = 2
    FAST   = 3
    FASTER = 4


@enum
class EMessageRecipient:
    ALL        = 0
    ALLIES     = 1
    INDIVIDUAL = 2
    BATTLENET  = 3
    OBSERVERS  = 4


@enum
class EBankValueKind:
    FIXED  = 0
    FLAG   = 1
    INT    = 2
    STRING = 3
    POINT  = 4
    UNIT   = 5
    TEXT   = 6
    SKIP   = 7


COLOR_CODES = {
    "B4141E": "Red",
    "0042FF": "Blue",
    "1CA7EA": "Teal",
    "EBE129": "Yellow",
    "540081": "Purple",
    "FE8A0E": "Orange",
    "168000": "Green",
    "CCA6FC": "Light Pink",
    "1F01C9": "Violet",
    "525494": "Light Grey",
    "106246": "Dark Green",
    "4E2A04": "Brown",
    "96FF91": "Light Green",
    "232323": "Dark Grey",
    "E55BB0": "Pink",
    "FFFFFF": "White",
    "000000": "Black",
}


@resource
class PlayerColor:
    def __init__(self, *components):
        self.r = components[0]
        self.g = components[1]
        self.b = components[2]
        self.a = components[3]

    def hex(self):
        return f'{self.r:02X}{self.g:02X}{self.b:02X}'

    def __str__(self):
        return COLOR_CODES.get(self.hex(), f'#{self.hex()}')


@resource
class GameParticipant:
    idx: int = None
    pid: int = None
    uid: int = None
    name: str = None
    clan: str = None
    ctrl: int = None
    toon: str = None
    working_slot: int = None
    color: PlayerColor = None

    def __init__(self):
        pass


@resource
class GameBank:
    name: str
    net_size: int = 0
    content_size: int = 0
    sections_count: int = 0
    keys_count: int = 0
    signed: bool = False

    def __init__(self, name, player: GameParticipant):
        self.name = name
        self.player = player
        self.events = []

    def append_event(self, ev):
        self.events.append(ev)

        if ev['_event'] == 'NNet.Game.SBankSectionEvent':
            self.sections_count += 1
        elif ev['_event'] == 'NNet.Game.SBankKeyEvent':
            self.keys_count += 1
            self.content_size += len(ev['m_name'])
            if ev['m_type'] != 7:
                self.content_size += len(ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankValueEvent':
            self.content_size += len(ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankSignatureEvent' and ev['m_signature']:
            self.signed = True

        self.net_size += ev['_bits'] / 8


@resource
class ProtoFeatures:
    user_id_driven: bool
    working_slots: bool
    tracker_present: bool
    tracker_player_pid: bool

    def puid_from_ev(self, ev):
        return ev['_userid']['m_userId'] if self.user_id_driven else ev['_playerid']['m_playerId']


@resource
class GameParticipantsList(list):
    def __init__(self, features: ProtoFeatures):
        super().__init__(self)
        self.features = features

    def get_player(self, puid=None, uid=None, pid=None, slot_id=None):
        if puid is not None:
            if self.features.user_id_driven:
                uid = puid
            else:
                pid = puid

        if uid is not None:
            return next(filter(lambda x: x.uid == uid, self))
        elif pid is not None:
            return next(filter(lambda x: x.pid == pid, self))
        elif slot_id is not None:
            return next(filter(lambda x: x.working_slot == slot_id, self))
        else:
            raise Exception()

    def get_player_by_uid(self, uid):
        return next(filter(lambda x: x.uid == uid, self))

    def get_player_by_pid(self, pid):
        return next(filter(lambda x: x.pid == pid, self))


@resource
class S2Replay:
    proto_build: int
    protocol: __module__
    features: ProtoFeatures = ProtoFeatures()

    header: dict
    details: dict
    init_data: dict

    participants: GameParticipantsList
    banks: List[GameBank]

    def __init__(self, filename, strict_mode=False):
        def read_archive_contents(name):
            content = self.archive.read_file(name)
            if not content:
                logging.warning('MPQ missing file: "%s"' % name)
            return content

        def must_read_archive_contents(name):
            content = read_archive_contents(name)
            if not content:
                logging.critical('MPQ missing required file: "%s"' % name)
                sys.exit(1)
            return content

        self.archive = mpyq.MPQArchive(filename)

        content = self.archive.header['user_data_header']['content']
        self.header = versions.latest().decode_replay_header(content)

        self.proto_build = self.header['m_version']['m_baseBuild']
        logging.info('Protocol build %d' % (self.proto_build))

        # >= 24764 (after HotS came out)
        # in WoL observers weren't seperated from players and working slot concept didn't exist
        self.features.user_id_driven = self.proto_build >= 24764
        self.features.working_slots = self.proto_build >= 24764

        # https://liquipedia.net/starcraft2/Patch_2.0.4
        # tracker section should be present in replays from build 24944
        self.features.tracker_present = self.proto_build >= 25604

        # https://liquipedia.net/starcraft2/Patch_2.0.8
        # SPlayerSetupEvent should be included in the tracker from build 25604
        self.features.tracker_player_pid = self.proto_build >= 25604

        try:
            self.protocol = versions.build(self.proto_build)
        except ImportError as e:
            logging.warning('Unsupported protocol: (%s)' % (str(e)))
            if strict_mode:
                logging.critical('Aborting, because of strict mode.')
                sys.exit(1)

            proto_mods = [int(re.sub(r'^protocol([0-9]+)\.py$', '\\1', x)) for x in versions.list_all()]
            tmp = [abs(i - self.proto_build) for i in proto_mods]
            idx = tmp.index(min(tmp))
            # always favorize newer protos in case of up to date replays
            if self.proto_build > 70000 and len(proto_mods) >= (idx + 2):
                idx += 1
            fallbackBuild = proto_mods[idx]
            self.protocol = versions.build(fallbackBuild)
            logging.warning('Attempting to use %s instead' % self.protocol.__name__)

        # read files
        self.details = self.protocol.decode_replay_details(must_read_archive_contents('replay.details'))
        self.init_data = self.protocol.decode_replay_initdata(must_read_archive_contents('replay.initData'))
        self.gameevents = peekable(self.protocol.decode_replay_game_events(must_read_archive_contents('replay.game.events')))
        content = read_archive_contents('replay.message.events')
        self.messageevents = peekable(self.protocol.decode_replay_message_events(content) if content else None)
        content = read_archive_contents('replay.tracker.events')
        self.features.tracker_present = bool(content)
        self.trackerevents = peekable(self.protocol.decode_replay_tracker_events(content) if content else None)

        # setup
        self.participants = setup_participants(self)
        self.banks = setup_banks(self)


def setup_participants(s2rep: S2Replay):
    plist = GameParticipantsList(s2rep.features)

    for key, dp_entry in enumerate(s2rep.details['m_playerList']):
        if dp_entry['m_control'] in [EPlayerControl.OPEN]: continue

        pinfo = GameParticipant()
        plist.append(pinfo)

        pinfo.idx = key + 1

        if dp_entry['m_control'] == EPlayerControl.HUMAN:
            pinfo.toon = '%d-S2-%d-%d' % (dp_entry['m_toon']['m_region'], dp_entry['m_toon']['m_realm'], dp_entry['m_toon']['m_id'])
        pinfo.ctrl = EPlayerControl[dp_entry['m_control']]

        if dp_entry['m_name']:
            tmp = dp_entry['m_name'].decode('utf8').split('<sp/>')
            if len(tmp) > 1:
                pinfo.name = tmp[1]
                pinfo.clan = tmp[0].replace('&lt;', '<').replace('&gt;', '>')
            else:
                pinfo.name = tmp[0]

        mcol = dp_entry['m_color']
        pinfo.color = PlayerColor(mcol['m_r'], mcol['m_g'], mcol['m_b'], mcol['m_a'])

        if s2rep.features.working_slots:
            if dp_entry['m_workingSetSlotId'] is None:
                # entry without a "working" slot in the lobby might indicate:
                # - game recovered from replay - where particuplar player was either replaced or excluded
                # - a referee or an observer ??
                # - player that dropped from the game before it has even started ??
                logging.warning('"%s" has no working slot assigned' % (pinfo.name))
                pinfo.uid = plist[-2].uid + 1 if len(plist) > 1 else 0
                continue

            for slot_index, sl_slot in enumerate(s2rep.init_data['m_syncLobbyState']['m_lobbyState']['m_slots']):
                if dp_entry['m_workingSetSlotId'] != sl_slot['m_workingSetSlotId']: continue

                pinfo.working_slot = slot_index
                pinfo.uid = sl_slot['m_userId']
                break
        else:
            next_slot = plist[-2].working_slot + 1 if len(plist) > 1 else 0
            sl_slot = s2rep.init_data['m_syncLobbyState']['m_lobbyState']['m_slots'][next_slot]
            pinfo.working_slot = next_slot
            pinfo.uid = sl_slot['m_userId']

        if dp_entry['m_observe'] == EObserve.NONE or not s2rep.features.working_slots:
            # attempt to determine the player_id
            # in newer protos we'll relay on `SPlayerSetupEvent` event from the tracker that will be fetched later
            pinfo.pid = pinfo.working_slot + 1

        if dp_entry['m_control'] == EPlayerControl.COMPUTER:
            assert pinfo.working_slot is not None

        if dp_entry['m_control'] == EPlayerControl.HUMAN:
            assert pinfo.uid is not None

    if s2rep.features.tracker_player_pid:
        while True:
            ev = s2rep.trackerevents.peek()
            if ev['_event'] != 'NNet.Replay.Tracker.SPlayerSetupEvent': break
            ev = next(s2rep.trackerevents)
            if ev['m_slotId'] is None: continue
            plist.get_player(slot_id=ev['m_slotId']).pid = ev['m_playerId']

    return plist


def setup_banks(s2rep: S2Replay) -> List[GameBank]:
    BANK_EVENTS = [
        'NNet.Game.SBankFileEvent',
        'NNet.Game.SBankSectionEvent',
        'NNet.Game.SBankKeyEvent',
        'NNet.Game.SBankValueEvent',
        'NNet.Game.SBankSignatureEvent',
    ]

    banks = OrderedDict()

    for x in s2rep.participants:
        if s2rep.features.user_id_driven:
            if x.uid is None: continue
            banks[x.uid] = []
        else:
            if x.pid is None: continue
            banks[x.pid] = []

    for ev in s2rep.gameevents:
        if ev['_event'] in BANK_EVENTS:
            puid = s2rep.features.puid_from_ev(ev)

            if ev['_event'] == 'NNet.Game.SBankFileEvent':
                player = s2rep.participants.get_player(puid)
                banks[puid].append(GameBank(ev['m_name'].decode('ascii'), player))

            banks[puid][-1].append_event(ev)
        else:
            if ev['_gameloop'] > 0:
                break
            else:
                continue

    tmpl = []
    for x in banks.values():
        for y in x:
            tmpl.append(y)
    return tmpl


def rebuild_bank(gbank: GameBank, target_dir):
    dkinds = [
        'fixed',
        'flag',
        'int',
        'string',
        None, # TODO: point
        None, # TODO: unit
        'text',
        None, # skip
    ]

    def enter_section(name):
        sc_curr = ET.Element('Section')
        sc_curr.set('name', name)
        return sc_curr

    def enter_key(sc_curr, name, kind=None, value=None):
        key_curr = ET.Element('Key')
        key_curr.set('name', name)
        sc_curr.append(key_curr)
        if kind != None:
            enter_value(key_curr, kind, value)
        return key_curr

    def enter_value(key_curr, kind, value):
        el = ET.Element('Value')
        if kind == 7:
            # skip - value will be in the next message
            return
        attr = dkinds[kind]
        el.set(attr, value.decode('utf8'))
        key_curr.append(el)

    def enter_signature(signature):
        el = ET.Element('Signature', {'value': ''.join('{:02X}'.format(x) for x in signature)})
        return el

    sc_curr = None # type: ET.Element
    key_curr = None # type: ET.Element
    root = ET.Element('Bank')
    root.set('version', '1')

    # process events
    for ev in gbank.events:
        if ev['_event'] == 'NNet.Game.SBankSectionEvent':
            sc_curr = enter_section(ev['m_name'].decode('utf8'))
            root.append(sc_curr)
        elif ev['_event'] == 'NNet.Game.SBankKeyEvent':
            key_curr = enter_key(sc_curr, ev['m_name'].decode('utf8'), ev['m_type'], ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankValueEvent':
            enter_value(key_curr, ev['m_type'], ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankSignatureEvent':
            sig_el = enter_signature(ev['m_signature'])
            root.append(sig_el)

    # write to disk
    target_dir = os.path.abspath(os.path.join(target_dir, gbank.player.toon))
    try:
        os.makedirs(target_dir)
    except OSError:
        if not os.path.isdir(target_dir):
            raise
    filename = '%s.SC2Bank' % os.path.join(target_dir, gbank.name)
    btree = ET.ElementTree(root)
    btree.write(filename, encoding='utf-8', xml_declaration=True)

    # beautify the content by rewriting it through minidom
    pxml = minidom.parse(filename).toprettyxml(encoding='utf-8', indent=" " * 4, newl="\r\n")
    with open(filename, 'wb') as f:
        f.write(pxml)

    return filename


def main(args):
    s2rep = S2Replay(args.replay_file, strict_mode=args.strict_mode)

    if args.players:
        hdkeys = GameParticipant.props

        data = []
        for x in s2rep.participants:
            data.append([x[key] for key in hdkeys])

        print("\n## PLAYERS\n")
        print(tabulate(data, headers=hdkeys, tablefmt='github'))
        print()


    if args.chat and s2rep.messageevents:
        print("\n## CHATLOG\n")
        for ev in s2rep.messageevents:
            if ev['_event'] != 'NNet.Game.SChatMessage': continue

            if '_userid' in ev:
                name = s2rep.participants.get_player_by_uid(ev['_userid']['m_userId']).name
            elif '_playerid' in ev:
                name = s2rep.participants.get_player_by_pid(ev['_playerid']['m_playerId']).name
            else:
                raise Exception('couldn\'t determine user')

            secs = ev['_gameloop'] / 16

            print('%s | %06s | %-s: %s' % (
                '%d:%02d:%02d' % (secs / 3600, secs % 3600 / 60, secs % 60),
                EMessageRecipient[ev['m_recipient']],
                name,
                ev['m_string'].decode('utf8', 'replace')
            ))
        print()


    if args.bank_list:
        hdkeys = ['idx', 'uid', 'player'] + GameBank.props
        data = []
        for i, cbank in enumerate(s2rep.banks):
            data.append([
                i,
                cbank.player.uid,
                cbank.player.name,
            ] + [cbank[key] for key in GameBank.props])
        print("\n## BANKS\n")
        print(tabulate(data, headers=hdkeys, tablefmt='github'))
        print()


    if args.bank_rebuild:
        for currb in s2rep.banks:
            pname = currb.player.name
            logging.info(f'Rebuilding "{currb.name}.SC2Bank" for player "{pname}" ..')
            filename = rebuild_bank(currb, args.out)
            logging.debug(f'File saved at "{filename}"')


def setup_logger():
    logFormatter = ColoredFormatter(
        "%(asctime)s,%(msecs)-3d %(log_color)s%(levelname)-8s%(reset)s %(blue)s%(funcName)s/%(filename)s:%(lineno)s%(reset)s %(message)s",
        datefmt='%H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bg_red,fg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    consoleHandler = logging.StreamHandler(sys.stderr)
    consoleHandler.setFormatter(logFormatter)
    logging.getLogger().addHandler(consoleHandler)


def cli():
    parser = argparse.ArgumentParser(
        prog='s2repdump',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('replay_file', help='.SC2Replay file to load')
    parser.add_argument('-v', '--verbose', help='verbose logging; stacks up to 3', action='count', default=0)
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('--version', action='version', version='%(prog)s ' +
                        ('%s (s2protocol %s)' % (S2REPDUMP_VERSION, versions.latest().__name__[8:])))
    # parser.add_argument('--json', help='json', action='store_true')
    parser.add_argument('--players', help='print info about players', action='store_true')
    parser.add_argument('--chat', help='chat messages', action='store_true')
    parser.add_argument('--bank-list', help='list SC2Bank\'s', action='store_true')
    parser.add_argument('--bank-rebuild', help='rebuild SC2Bank files', action='store_true')
    parser.add_argument('--out', help='output directory', type=str, default='./out')
    parser.add_argument('--strict-mode', help='do not try to decode replays if there\'s not matching protocol', action='store_true')
    args = parser.parse_args()
    args.verbose = min(args.verbose, 3)

    setup_logger()
    logging.getLogger().setLevel(
        [logging.WARN, logging.INFO, logging.DEBUG, logging.NOTSET][args.verbose]
    )
    if args.quiet:
        logging.getLogger().setLevel(logging.CRITICAL)

    main(args)


if __name__ == '__main__':
    cli()
