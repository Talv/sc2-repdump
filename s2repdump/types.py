from typing import List
from s2repdump.utils import enum, resource


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
class EBankDataKind:
    FIXED     = 0
    FLAG      = 1
    INT       = 2
    STRING    = 3
    UNIT      = 4
    POINT     = 5
    TEXT      = 6
    COMPLEX   = 7


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


@enum
class EGameRegion:
    US   = 1
    EU   = 2
    KR   = 3
    # TW = 4
    CN   = 5
    SEA  = 6
    PTR  = 98


@resource
class MapInfo:
    cache_handles: List[str]
    author_handle: str


@resource
class ReplayInfo:
    title: str
    client_version: str
    region: EGameRegion
    timestamp: int
    elapsed_game_loops: int
    map_info: MapInfo


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

    def toJSON(self):
        return self.hex()


@resource
class GameParticipant:
    idx: int = None
    pid: int = None
    uid: int = None
    name: str = None
    clan: str = None
    ctrl: int = None
    handle: str = None
    working_slot: int = None
    color: PlayerColor = None


@resource
class GameBankMeta:
    name: str
    uid: int
    net_size: int = 0
    content_size: int = 0
    sections_count: int = 0
    keys_count: int = 0
    signed: bool = False

    def __init__(self, name, player: GameParticipant):
        self.name = name
        self.uid = player.uid
        self.player = player
        self.events = []

    def append_event(self, ev):
        self.events.append(ev)

        if ev['_event'] == 'NNet.Game.SBankSectionEvent':
            self.sections_count += 1
            self.content_size += len(ev['m_name'])
        elif ev['_event'] == 'NNet.Game.SBankKeyEvent':
            self.keys_count += 1
            self.content_size += len(ev['m_name'])
            self.content_size += len(ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankValueEvent':
            self.content_size += len(ev['m_name'])
            self.content_size += len(ev['m_data'])
        elif ev['_event'] == 'NNet.Game.SBankSignatureEvent' and len(ev['m_signature']) > 0:
            self.signed = True

        self.net_size += ev['_bits'] / 8

    def toJSON(self):
        return self.fields


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

    def get_player(self, puid=None, uid=None, pid=None, slot_id=None) -> GameParticipant:
        if puid is not None:
            if self.features.user_id_driven:
                uid = puid
            else:
                pid = puid

        try:
            if uid is not None:
                return next(filter(lambda x: x.uid == uid, self))
            elif pid is not None:
                return next(filter(lambda x: x.pid == pid, self))
            elif slot_id is not None:
                return next(filter(lambda x: x.working_slot == slot_id, self))
            else:
                raise Exception()
        except StopIteration:
            return None

    def get_player_by_uid(self, uid):
        return next(filter(lambda x: x.uid == uid, self))

    def get_player_by_pid(self, pid):
        return next(filter(lambda x: x.pid == pid, self))
