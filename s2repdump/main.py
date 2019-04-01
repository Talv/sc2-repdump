#!/usr/bin/python2
# -*- coding: utf-8 -*-

from __future__ import print_function
import sys
import os
import json
import argparse
import logging
import mpyq
from s2protocol import versions
import xml.etree.ElementTree as ET
from xml.dom import minidom


class SC2Bank(object):
    def __init__(self, name):
        self.name = name
        self.sections = {}
        self.sc_curr = None
        self.key_curr = None

        self.root = ET.Element('Bank')
        self.root.set('version', '1')

    def __str__(self):
        return '%s (sections=%d)' % (self.name, len(self.sections))

    def enter_section(self, name):
        self.sc_curr = ET.Element('Section')
        self.sc_curr.set('name', name)
        self.root.append(self.sc_curr)

    def enter_key(self, name, kind=None, value=None):
        self.key_curr = ET.Element('Key')
        self.key_curr.set('name', name)
        self.sc_curr.append(self.key_curr)
        if kind:
            self.enter_value(kind, value)

    def enter_value(self, kind, value):
        el = ET.Element('Value')
        if kind == 0:
            attr = 'fixed'
        elif kind == 1:
            attr = 'flag'
        elif kind == 2:
            attr = 'int'
        elif kind == 3:
            attr = 'string'
        # TODO: point
        # TODO: unit
        elif kind == 6:
            attr = 'text'
        elif kind == 7:
            # skip - value will be in the next message
            return
        else:
            raise Exception(
                'unkown data kind: "%d". section = "%s" ; key = "%s" ; value = "%s"' %
                (kind, self.sc_curr.get('name'), self.key_curr.get('name'), value)
            )
        el.set(attr, value.decode('utf8'))
        self.key_curr.append(el)

    def signature(self, signature):
        el = ET.Element('Signature', {'value': ''.join('{:02X}'.format(x) for x in signature)})
        self.root.append(el)

    def write(self, cdir='./'):
        fpath = os.path.abspath(cdir)
        try:
            os.makedirs(fpath)
        except OSError:
            if not os.path.isdir(fpath):
                raise
        filename = '%s.SC2Bank' % os.path.join(fpath, self.name)
        btree = ET.ElementTree(self.root)
        btree.write(filename, encoding='utf-8', xml_declaration=True)

        # rewrite through minidom to beautify
        pxml = minidom.parse(filename).toprettyxml(encoding='utf-8', indent=" " * 4, newl="\r\n")
        with open(filename, 'wb') as f:
            f.write(pxml)


def readArchiveContents(archive, content):
    contents = archive.read_file(content)
    if not contents:
        logging.critical('Archive missing file: "%s"' % content)
        sys.exit(1)
    return contents


def reconstruct_banks(gameevents, player_id):
    banks = []
    for ev in gameevents:
        if ev['_userid']['m_userId'] != player_id:
            continue

        if ev['_event'] == 'NNet.Game.SBankFileEvent':
            banks.append(SC2Bank(ev['m_name']))
        elif ev['_event'] == 'NNet.Game.SBankSectionEvent':
            banks[-1].enter_section(ev['m_name'])
        elif ev['_event'] == 'NNet.Game.SBankKeyEvent':
            banks[-1].enter_key(ev['m_name'], ev['m_type'], ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankValueEvent':
            banks[-1].enter_value(ev['m_type'], ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankSignatureEvent':
            banks[-1].signature(ev['m_signature'])
        else:
            if ev['_gameloop'] > 0:
                break
    return banks


def read_players(initd, details):
    working_slots = {}

    for slot_id, row in enumerate(initd['m_syncLobbyState']['m_lobbyState']['m_slots']):
        # if slot is FREE (0) or NOT AVAILABLE (1)
        if row['m_control'] <= 1:
            continue

        pslot = dict(
            player_id=slot_id + 1,
        )
        working_slots[row['m_workingSetSlotId']] = pslot

        if row['m_userId'] is not None:
            user_data = initd['m_syncLobbyState']['m_userInitialData'][row['m_userId']]
            pslot['user_id'] = row['m_userId']
            pslot['name'] = user_data['m_name']
            pslot['clan'] = user_data['m_clanTag']

    for row in details['m_playerList']:
        pslot = working_slots[row['m_workingSetSlotId']]
        pslot['handle'] = '%d-S2-%d-%d' % (row['m_toon']['m_region'], row['m_toon']['m_realm'], row['m_toon']['m_id'])

    return working_slots


def setupLogger():
    logging.basicConfig(
        format='%(asctime)s,%(msecs)-3d %(levelname)s [%(funcName)s]: %(message)s',
        datefmt='%H:%M:%S'
    )
    logging._levelNames[logging.DEBUG] = 'DEBG'
    logging._levelNames[logging.WARNING] = 'WARN'
    logging._levelNames[logging.ERROR] = 'ERRO'
    logging._levelNames[logging.CRITICAL] = 'CRIT'
    logging.addLevelName(logging.DEBUG, "\033[1;35m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
    logging.addLevelName(logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName(logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName(logging.CRITICAL, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.CRITICAL))


def main():
    parser = argparse.ArgumentParser(
        prog='s2repdump',
        description='''
: Dump player handles:
 --players [replay_file]

: Reconstruct players .SC2Bank files
 --bank [player_slot] [replay_file]
        ''',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('replay_file', help='.SC2Replay file to load')
    parser.add_argument('--players', help='print info about players', action='store_true')
    parser.add_argument('--chat', help='chat messages', action='store_true')
    parser.add_argument('--json', help='json', action='store_true')
    parser.add_argument('--bank', help='reconstruct player\'s SC2Bank files', type=int)
    parser.add_argument('--out', help='output directory', type=str, default='./out')
    parser.add_argument('-v', '--verbose', help='verbose logging', action='store_true')
    args = parser.parse_args()

    setupLogger()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    archive = mpyq.MPQArchive(args.replay_file)

    # HEADER
    contents = archive.header['user_data_header']['content']
    header = versions.latest().decode_replay_header(contents)

    # The header's baseBuild determines which protocol to use
    baseBuild = header['m_version']['m_baseBuild']
    try:
        protocol = versions.build(baseBuild)
    except Exception as e:
        logging.warn('Unsupported base build: %s (%s)' % (baseBuild, str(e)))
        protocol = versions.latest()
        logging.warn('Attempting to use newest possible instead: %s' % protocol.__name__)

    details = protocol.decode_replay_details(readArchiveContents(archive, 'replay.details'))
    initd = protocol.decode_replay_initdata(readArchiveContents(archive, 'replay.initData'))

    playerList = read_players(initd, details)
    userList = {}
    for slotId in playerList:
        if 'user_id' in playerList[slotId]:
            userList[playerList[slotId]['user_id']] = playerList[slotId]

    if args.players:
        print(json.dumps(playerList, indent=True))

    if args.chat:
        messageevents = protocol.decode_replay_message_events(readArchiveContents(archive, 'replay.message.events'))
        clog = []
        for ev in messageevents:
            if ev['_event'] == 'NNet.Game.SChatMessage':
                clog.append({
                    'gameloop': ev['_gameloop'],
                    'user_id': ev['_userid']['m_userId'],
                    'recipient': ev['m_recipient'],
                    'message': ev['m_string'],
                })
        if args.json:
            print(json.dumps(clog, indent=True))
        else:
            for x in clog:
                secs = x['gameloop'] / 16
                print('[%d:%02d:%02d] %s: %s' % (
                    secs / 3600,
                    secs % 3600 / 60,
                    secs % 60,
                    userList[x['user_id']]['name'],
                    x['message']
                ))

    if args.bank is not None:
        logging.info('Processing player "%s"' % userList[args.bank]['name'])
        gameevents = protocol.decode_replay_game_events(readArchiveContents(archive, 'replay.game.events'))
        banks = reconstruct_banks(gameevents, args.bank)
        for b in banks:
            logging.info('Reconstructed "%s.SC2Bank"' % b.name)
            b.write(args.out)


if __name__ == '__main__':
    main()
