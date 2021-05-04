#!/usr/bin/python3

import sys
import os
import re
import json
from binascii import b2a_hex
from typing import List
import argparse
import logging
from more_itertools import peekable
from tabulate import tabulate
from colorlog import ColoredFormatter
import mpyq
from s2protocol import versions
from s2repdump.meta import S2REPDUMP_VERSION
from s2repdump.utils import resource
from s2repdump.types import *
from s2repdump.bank import GameBankStorage


PROTO_VERSION_MAPPINGS = {
    # 4.12.X
    80188: 79998,
}


@resource
class S2Replay:
    proto_build: int
    protocol: __module__
    features: ProtoFeatures = ProtoFeatures()

    header: dict
    details: dict
    init_data: dict

    info: ReplayInfo
    participants: GameParticipantsList
    banks: List[GameBankMeta]

    def __init__(self, filename, strict=False):
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
            if strict:
                logging.critical('Aborting, because of strict mode.')
                sys.exit(1)

            try:
                fallbackBuild = PROTO_VERSION_MAPPINGS[self.proto_build]
            except KeyError:
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
        self.info = setup_info(self)
        self.participants = setup_participants(self)
        self.banks = setup_banks(self)


def setup_info(s2rep: S2Replay):
    info = ReplayInfo()
    info.title = s2rep.details['m_title'].decode('utf8')
    info.client_version = '.'.join([
        str(s2rep.header['m_version']['m_major']),
        str(s2rep.header['m_version']['m_minor']),
        str(s2rep.header['m_version']['m_revision']),
        str(s2rep.header['m_version']['m_build']),
    ])
    info.region = None
    info.timestamp = int((s2rep.details['m_timeUTC'] / 10000000) - 11644473600)
    info.elapsed_game_loops = s2rep.header['m_elapsedGameLoops']

    info.map_info = MapInfo()
    info.map_info.cache_handles = [*map(
        # lambda x: '%s.%s' % (b2a_hex(x[16:]).decode(), x[0:4].decode('ascii')),
        lambda x: '%s' % (b2a_hex(x[16:]).decode()),
        s2rep.details['m_cacheHandles']
    )]
    info.map_info.author_handle = s2rep.init_data['m_syncLobbyState']['m_gameDescription']['m_mapAuthorName'].decode() or None
    if info.map_info.author_handle:
        info.region = int(info.map_info.author_handle[0])

    return info


def setup_participants(s2rep: S2Replay):
    plist = GameParticipantsList(s2rep.features)

    for key, dp_entry in enumerate(s2rep.details['m_playerList']):
        if dp_entry['m_control'] in [EPlayerControl.OPEN]: continue

        pinfo = GameParticipant()
        plist.append(pinfo)

        pinfo.idx = key + 1

        if dp_entry['m_control'] == EPlayerControl.HUMAN:
            if dp_entry['m_toon']['m_region']:
                pinfo.handle = '%d-S2-%d-%d' % (dp_entry['m_toon']['m_region'], dp_entry['m_toon']['m_realm'], dp_entry['m_toon']['m_id'])
            else:
                pinfo.handle = None
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
                # - game started without lobby (test document mode etc.)
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
            p = plist.get_player(slot_id=ev['m_slotId'])
            if p is None:
                logging.warning('Failed to match a slot_id of %d with a pid of %d' % (ev['m_slotId'], ev['m_playerId']))
                continue
            p.pid = ev['m_playerId']

    return plist


def setup_banks(s2rep: S2Replay) -> List[GameBankMeta]:
    BANK_EVENTS = [
        'NNet.Game.SBankFileEvent',
        'NNet.Game.SBankSectionEvent',
        'NNet.Game.SBankKeyEvent',
        'NNet.Game.SBankValueEvent',
        'NNet.Game.SBankSignatureEvent',
    ]

    banks = {}

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
                banks[puid].append(GameBankMeta(ev['m_name'].decode('ascii'), player))

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


def main(args):
    s2rep = S2Replay(args.replay_file, strict=args.strict)
    sections = {}

    if 'info' in args.decode:
        if args.json:
            sections['info'] = s2rep.info
        else:
            data = []
            def append_prop(val, key_path: str = ''):
                if hasattr(val, 'props'):
                    for sub_key in val.props:
                        append_prop(val[sub_key], f'{key_path}.{sub_key}'.lstrip('.'))
                elif isinstance(val, list):
                    if len(val) == 0:
                        append_prop(None, f'{key_path}[]')
                    for i, x in enumerate(val):
                        append_prop(x, f'{key_path}[{i}]')
                else:
                    r = None
                    if isinstance(val, (int, str, bool)):
                        r = val
                    elif val is not None:
                        r = str(val)
                    data.append([key_path, r])
                    return r
            append_prop(s2rep.info)

            print("\n## REPLAY INFO\n")
            print(tabulate(data, tablefmt='github'))
            print()

    if 'players' in args.decode:
        hdkeys = GameParticipant.props

        data = []
        for x in s2rep.participants:
            data.append([x[key] for key in hdkeys])

        if args.json:
            sections['players'] = []
            for row in data:
                item = {}
                for [col, name] in enumerate(hdkeys):
                    item[name] = row[col]
                sections['players'].append(item)
        else:
            print("\n## PLAYERS\n")
            print(tabulate(data, headers=hdkeys, tablefmt='github'))
            print()


    if 'chat' in args.decode and s2rep.messageevents:
        sections['chat'] = []
        if not args.json:
            print("\n## CHATLOG\n")
        for ev in s2rep.messageevents:
            if ev['_event'] != 'NNet.Game.SChatMessage': continue

            if '_userid' in ev:
                participant = s2rep.participants.get_player_by_uid(ev['_userid']['m_userId'])
            elif '_playerid' in ev:
                participant = s2rep.participants.get_player_by_pid(ev['_playerid']['m_playerId'])
            else:
                raise Exception('couldn\'t determine user')

            secs = ev['_gameloop'] / 16
            msg = ev['m_string'].decode('utf8', 'replace')

            if args.json:
                sections['chat'].append({
                    'gameloop': ev['_gameloop'],
                    'uid': participant.uid,
                    'recipient': EMessageRecipient[ev['m_recipient']].lower(),
                    'message': msg,
                })
            else:
                print('%s | %06s | %-s: %s' % (
                    '%d:%02d:%02d' % (secs / 3600, secs % 3600 / 60, secs % 60),
                    EMessageRecipient[ev['m_recipient']],
                    participant.name,
                    msg
                ))
        if not args.json:
            print()


    if 'banks' in args.decode:
        if args.json:
            sections['banks'] = s2rep.banks
        else:
            hdkeys = ['idx', 'player'] + GameBankMeta.props
            data = []
            for i, cbank in enumerate(s2rep.banks):
                data.append([
                    i,
                    cbank.player.name,
                ] + [cbank[key] for key in GameBankMeta.props])
            print("\n## BANKS\n")
            print(tabulate(data, headers=hdkeys, tablefmt='github'))
            print()


    if args.bank_rebuild:
        if args.json:
            sections['sc2banks'] = []

        if not args.json and not args.force and os.path.isdir(args.out) and len(os.listdir(args.out)) > 0:
            logging.error('Specified output directory "%s" already exists and is not empty, aborting..' % (args.out))
        else:
            for gbmeta in s2rep.banks:
                pname = '%s' % (gbmeta.player.name)
                if gbmeta.player.handle:
                    pname += ' [%s]' % (gbmeta.player.handle)
                logging.info(f'Rebuilding "{gbmeta.name}.SC2Bank" for player {pname} ..')
                bank_store = GameBankStorage()
                bank_store.rebuild_from_meta(gbmeta)

                expected_signature = bank_store.signature()
                computed_signature = bank_store.compute_signature(s2rep.info.map_info.author_handle, gbmeta.player.handle)
                if expected_signature is not None and expected_signature != computed_signature:
                    logging.warning(
                        'Signature missmatch for player: %s bank: %s! expected: %s computed: %s',
                        pname,
                        bank_store.name,
                        expected_signature,
                        computed_signature
                    )

                if args.json:
                    sections['sc2banks'].append({
                        'uid': gbmeta.player.uid,
                        'name': bank_store.name,
                        'expected_signature': expected_signature,
                        'computed_signature': computed_signature,
                        'filename': bank_store.filename(s2rep.info.map_info.author_handle, gbmeta.player.handle),
                        'content': bank_store.tostring(not args.json_compact),
                    })
                else:
                    filename = bank_store.write_sc2bank(args.out, True, s2rep.info.map_info.author_handle, gbmeta.player.handle)
                    logging.debug(f'File saved at "{filename}"')

    if args.json:
        def dumper(obj):
            if hasattr(obj, 'toJSON'):
                return obj.toJSON()
            if isinstance(obj, bytes):
                return obj.decode('utf8')
            else:
                return obj.__dict__
        print(json.dumps(
            sections,
            default=dumper,
            indent=None if args.json_compact else '\t',
            separators=(',', ':') if args.json_compact else (',', ': ')
        ))


def setup_logger():
    logFormatter = ColoredFormatter(
        "%(asctime)s,%(msecs)-3d %(log_color)s%(levelname)-8s%(reset)s %(blue)s%(filename)s:%(lineno)s%(reset)s %(message)s",
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
    ver = ('%s (s2protocol %s)' % (S2REPDUMP_VERSION, versions.latest().__name__[8:]))
    parser = argparse.ArgumentParser(
        prog='s2repdump',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('replay_file', help='.SC2Replay file to load')

    comg = parser.add_argument_group('common')
    comg.add_argument('-v', '--verbose', help='verbose logging; stacks up to 3', action='count', default=0)
    comg.add_argument('-q', '--quiet', action='store_true')
    comg.add_argument('-V', '--version', action='version', version='%(prog)s ' + ver)
    comg.add_argument('-j', '--json', help='output data as JSON', action='store_true')
    comg.add_argument('-J', '--json-compact', help='output data as compact JSON', action='store_true')
    comg.add_argument('-O', '--out', help='output directory', type=str, default='./out')
    comg.add_argument('-f', '--force', action='store_true', help='force certain operations that otherwise would\'ve been aborted - such overwriting existing files')
    comg.add_argument('--strict', help='do not try to decode replays if there\'s not matching protocol', action='store_true')

    comg = parser.add_argument_group('actions')
    comg.add_argument('-d', '--decode', choices=['info', 'players', 'chat', 'banks'], type=str, action='append', default=[], help='decode and output specified data section')
    comg.add_argument('-R', '--bank-rebuild', help='rebuild SC2Bank files', action='store_true')

    args = parser.parse_args()
    if args.json_compact:
        args.json = True
    args.verbose = min(args.verbose, 3)

    setup_logger()
    logging.getLogger().setLevel(
        [logging.WARN, logging.INFO, logging.DEBUG, logging.NOTSET][args.verbose]
    )
    if args.quiet:
        logging.getLogger().setLevel(logging.CRITICAL)

    try:
        main(args)
    except:
        logging.exception('Unexpected error occured')
        sys.exit(1)


if __name__ == '__main__':
    cli()
