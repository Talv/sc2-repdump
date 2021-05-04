import os
import sys
import logging
import xml.etree.ElementTree as ET
import hashlib
from typing import Optional
from xml.dom import minidom
from s2repdump.types import GameBankMeta, EBankDataKind, MapInfo


data_kind_map = {
    EBankDataKind.FIXED: 'fixed',
    EBankDataKind.FLAG: 'flag',
    EBankDataKind.INT: 'int',
    EBankDataKind.STRING: 'string',
    # unit datatype uses COMPLEX variant, due to the fact it needs to store multiple values
    # it's yet to be determined whether its dedicated code is even being used
    # EBankDataKind.UNIT: '?',
    EBankDataKind.POINT: 'point',
    EBankDataKind.TEXT: 'text',
    EBankDataKind.COMPLEX: None,
}


class GameBankStorage:
    def __init__(self, name: str = ''):
        self.root = ET.Element('Bank')
        self.root.set('version', '1')
        self.name = name

    def from_file(self, filename):
        btree = ET.ElementTree()
        self.root = btree.parse(filename)
        self.name = os.path.basename(filename).split('.')[0]

    def rebuild_from_meta(self, gbmeta: GameBankMeta):
        self.name = gbmeta.name

        def enter_section(name):
            sc_curr = ET.Element('Section')
            sc_curr.set('name', name)
            return sc_curr

        def enter_key(sc_curr, name: str, data_kind: int, value: bytes):
            key_curr = ET.Element('Key')
            key_curr.set('name', name)
            sc_curr.append(key_curr)
            if data_kind != EBankDataKind.COMPLEX:
                enter_value(key_curr, 'Value', data_kind, value)
            return key_curr

        def enter_value(key_curr, name: str, data_kind: int, value: bytes):
            el = ET.Element(name)
            el.set(data_kind_map[data_kind], value.decode('utf8'))
            key_curr.append(el)

        def enter_signature(signature):
            el = ET.Element('Signature', {'value': ''.join('{:02X}'.format(x) for x in signature)})
            return el

        sc_curr = None # type: ET.Element
        key_curr = None # type: ET.Element

        # process events
        for ev in gbmeta.events:
            if ev['_event'] == 'NNet.Game.SBankSectionEvent':
                sc_curr = enter_section(ev['m_name'].decode('utf8'))
                self.root.append(sc_curr)
            elif ev['_event'] == 'NNet.Game.SBankKeyEvent':
                key_curr = enter_key(sc_curr, ev['m_name'].decode('utf8'), ev['m_type'], ev['m_data'])
            elif ev['_event'] == 'NNet.Game.SBankValueEvent':
                enter_value(key_curr, ev['m_name'].decode('utf8'), ev['m_type'], ev['m_data'])
            elif ev['_event'] == 'NNet.Game.SBankSignatureEvent':
                if len(ev['m_signature']) > 0:
                    sig_el = enter_signature(ev['m_signature'])
                    self.root.append(sig_el)
                    # ev['m_toonHandle'].decode()

    def compute_signature(self, author_handle: str = None, self_handle: str = None):
        pitems = []
        pitems.append(author_handle or '')
        pitems.append(self_handle or '')
        pitems.append(self.name)
        for section in sorted(list(self.root.findall('Section')), key=lambda x: x.attrib['name']):
            pitems.append(section.attrib['name'])
            for key in sorted(list(section.findall('Key')), key=lambda x: x.attrib['name']):
                pitems.append(key.attrib['name'])
                for value in sorted(list(key.findall('*')), key=lambda x: x.tag):
                    pitems.append(value.tag)
                    for k, v in value.attrib.items():
                        pitems.append(k)
                        # text value might be client defined, so it has to be skipped
                        if k != data_kind_map[EBankDataKind.TEXT]:
                            pitems.append(v)
        payload = ''.join(pitems).encode('utf8')
        return hashlib.sha1(payload).hexdigest().upper()

    def signature(self):
        sig_el = self.root.find('Signature')
        if sig_el is not None:
            return sig_el.attrib['value']
        else:
            return None

    def filename(self, author_handle: Optional[str] = None, self_handle: Optional[str] = None):
        return os.path.join(self_handle or '', author_handle or '', '%s.SC2Bank' % self.name)

    def tostring(self, prettify: bool = False):
        outxml = ET.tostring(self.root)
        if prettify:
            # beautify the content by rewriting it through minidom, so it matches SC2 formatting
            outxml = minidom.parseString(outxml).toprettyxml(encoding='utf-8', indent=" " * 4, newl="\r\n")
        return outxml

    def write_sc2bank(self, target_dir: Optional[str], prettify: bool = False, author_handle: str = None, self_handle: str = None):
        filename = self.filename(author_handle, self_handle)
        target_filename = os.path.join(
            # os.path.abspath(target_dir) if target_dir is not None else '',
            target_dir or '',
            filename
        )

        os.makedirs(os.path.dirname(target_filename), exist_ok=True)
        if prettify:
            outxml = self.tostring(prettify)
            with open(target_filename, 'wb') as f:
                f.write(outxml)
        else:
            btree = ET.ElementTree(self.root)
            btree.write(target_filename, encoding='utf-8', xml_declaration=True)

        return target_filename


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.DEBUG)
    b = GameBankStorage()
    b.from_file(sys.argv[1])
    print(b.compute_signature(sys.argv[2], sys.argv[3]))
