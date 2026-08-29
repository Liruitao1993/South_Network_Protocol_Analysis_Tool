"""Protocol parser lazy loading registry.

Keeps heavy parser modules out of GUI startup while preserving the singleton
parser instances expected by the rest of the application.
"""

from importlib import import_module
from typing import Any, Dict, Tuple


_PARSER_SPECS: Dict[str, Tuple[str, str]] = {
    "south": ("protocol_parser", "ProtocolFrameParser"),
    "plc_rf": ("plc_rf_parser", "PLCRFProtocolParser"),
    "hdlc": ("hdlc_parser", "HDLCParser"),
    "dlt645": ("dlt645_parser", "DLT645Parser"),
    "gdw": ("gdw10376_parser", "GDW10376Parser"),
    "dl_t698_45": ("dl_t698_45_parser", "DLT69845Parser"),
    "csg_new_gen": ("csg_new_gen_parser", "CSGNewGenParser"),
    "gw_new_gen": ("gw_new_gen_parser", "GWNewGenParser"),
    "hdc10": ("hdc10_parser", "HDC10Parser"),
}

_INSTANCES: Dict[str, Any] = {}
_MODULES: Dict[str, Any] = {}


def get_parser_module(name: str):
    """Return a parser module, importing it on first use."""
    try:
        spec = _PARSER_SPECS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown parser registry key: {name}") from exc

    module = _MODULES.get(name)
    if module is None:
        module = import_module(spec[0])
        _MODULES[name] = module
    return module


def get_parser_class(name: str):
    """Return a parser class, importing its module on first use."""
    module = get_parser_module(name)
    return getattr(module, _PARSER_SPECS[name][1])


def get_parser(name: str):
    """Return a shared parser instance, constructing it on first use."""
    parser = _INSTANCES.get(name)
    if parser is None:
        parser = get_parser_class(name)()
        _INSTANCES[name] = parser
    return parser


def get_parser_attr(name: str, attr: str):
    """Return a class or module attribute from a lazily imported parser."""
    return getattr(get_parser_module(name), attr)
