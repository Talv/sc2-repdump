import json
from collections import OrderedDict

S2REPDUMP_VERSION = '0.3.0'


def enum(cls):
    keys = dict((getattr(cls, i), i) for i in dir(cls) if not i.startswith('__'))
    values = dict((i, getattr(cls, i)) for i in dir(cls) if not i.startswith('__'))

    def attr(_self, v):
        return values[v]

    def item(_self, v):
        return keys[v]

    cls.__getattr__ = attr
    cls.__getitem__ = item
    self = cls()
    return self


def resource(obj):
    if list in obj.__bases__:
        return obj

    if not hasattr(obj, '__annotations__'):
        return obj

    def get_props():
        return [*obj.__annotations__.keys()]

    @property
    def get_fields(self):
        return OrderedDict([k, self[k]] for k in self.props)

    obj.props = get_props()
    obj.fields = get_fields

    obj.__getitem__ = lambda self, attr: getattr(self, attr)
    obj.__setitem__ = lambda self, attr, value: setattr(self, attr, value)

    return obj


def to_json(data):
    def defs(d):
        # if hasattr(d, '__dict__'):
        #     return vars(d)
        #     return d.__dict__
        if hasattr(d, 'fields'):
            return d.fields
        else:
            return str(d)
    return json.dumps(data, indent=4, sort_keys=False, ensure_ascii=False, default=defs)
