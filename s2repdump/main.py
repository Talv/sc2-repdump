#!/usr/bin/env python2

import sys
import os
import json
import argparse
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


def read_contents(archive, content):
    contents = archive.read_file(content)
    if not contents:
        print('Error: Archive missing {}'.format(content))
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


def read_players(details):
    p_map = {}
    for x in details['m_playerList']:
        p_map[x['m_workingSetSlotId']] = {
            'name': x['m_name'],
            'handle': '%d-S2-%d-%d' % (x['m_toon']['m_region'], x['m_toon']['m_realm'], x['m_toon']['m_id']),
        }
    return p_map


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
    parser.add_argument('replay_file', help='.SC2Replay file to load', nargs='?')
    parser.add_argument('--players', help='print info about players', action='store_true')
    parser.add_argument('--bank', help='reconstruct player\'s SC2Bank files', type=int)
    parser.add_argument('--out', help='output directory', type=str, default='./out')
    args = parser.parse_args()

    if args.replay_file is None:
        print(".SC2Replay file not specified")
        sys.exit(1)

    archive = mpyq.MPQArchive(args.replay_file)

    # HEADER
    contents = archive.header['user_data_header']['content']
    header = versions.latest().decode_replay_header(contents)

    # The header's baseBuild determines which protocol to use
    baseBuild = header['m_version']['m_baseBuild']
    try:
        protocol = versions.build(baseBuild)
    except Exception, e:
        print('Unsupported base build: {0} ({1})'.format(baseBuild, str(e)))
        protocol = versions.latest()
        print('Attempting to use newest possible instead: %s' % protocol.__name__)

    contents = read_contents(archive, 'replay.details')
    details = protocol.decode_replay_details(contents)
    p_map = read_players(details)

    if args.players:
        print(json.dumps(p_map, indent=True))

    if args.bank is not None:
        print('Processing player "%s"' % p_map[args.bank]['name'])
        contents = read_contents(archive, 'replay.game.events')
        banks = reconstruct_banks(protocol.decode_replay_game_events(contents), args.bank)
        for b in banks:
            print('Reconstructed "%s.SC2Bank"' % b.name)
            b.write(args.out)


if __name__ == '__main__':
    main()
