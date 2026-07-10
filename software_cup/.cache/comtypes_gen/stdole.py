from enum import IntFlag

import comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 as __wrapper_module__
from comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 import (
    FontEvents, OLE_XPOS_HIMETRIC, VgaColor, FONTSIZE, HRESULT, Font,
    Monochrome, IEnumVARIANT, Default, BSTR, FONTBOLD,
    OLE_ENABLEDEFAULTBOOL, _check_version, IUnknown, IDispatch,
    OLE_YSIZE_PIXELS, StdPicture, typelib_path, OLE_YSIZE_HIMETRIC,
    DISPPARAMS, FONTUNDERSCORE, OLE_XSIZE_CONTAINER, Unchecked, Gray,
    Color, FONTITALIC, OLE_YPOS_PIXELS, FONTSTRIKETHROUGH,
    VARIANT_BOOL, GUID, COMMETHOD, DISPMETHOD, OLE_XPOS_PIXELS,
    EXCEPINFO, OLE_HANDLE, Checked, OLE_YSIZE_CONTAINER,
    OLE_YPOS_HIMETRIC, CoClass, DISPPROPERTY, _lcid, IPicture, dispid,
    Picture, IPictureDisp, OLE_YPOS_CONTAINER, OLE_XSIZE_HIMETRIC,
    IFontDisp, StdFont, IFontEventsDisp, FONTNAME, OLE_CANCELBOOL,
    OLE_XPOS_CONTAINER, OLE_COLOR, OLE_XSIZE_PIXELS, Library,
    OLE_OPTEXCLUSIVE, IFont
)


class OLE_TRISTATE(IntFlag):
    Unchecked = 0
    Checked = 1
    Gray = 2


class LoadPictureConstants(IntFlag):
    Default = 0
    Monochrome = 1
    VgaColor = 2
    Color = 4


__all__ = [
    'OLE_YPOS_PIXELS', 'FONTSTRIKETHROUGH', 'FontEvents',
    'OLE_XPOS_PIXELS', 'OLE_XPOS_HIMETRIC', 'VgaColor', 'FONTSIZE',
    'Font', 'Monochrome', 'OLE_HANDLE', 'Checked', 'Default',
    'OLE_YSIZE_CONTAINER', 'OLE_YPOS_HIMETRIC', 'FONTBOLD',
    'IPicture', 'OLE_ENABLEDEFAULTBOOL', 'LoadPictureConstants',
    'Picture', 'IPictureDisp', 'OLE_YSIZE_PIXELS',
    'OLE_YPOS_CONTAINER', 'OLE_XSIZE_HIMETRIC', 'IFontDisp',
    'StdFont', 'StdPicture', 'typelib_path', 'OLE_YSIZE_HIMETRIC',
    'IFontEventsDisp', 'FONTNAME', 'OLE_CANCELBOOL',
    'OLE_XPOS_CONTAINER', 'OLE_COLOR', 'OLE_XSIZE_PIXELS', 'Library',
    'FONTUNDERSCORE', 'OLE_OPTEXCLUSIVE', 'OLE_XSIZE_CONTAINER',
    'Unchecked', 'IFont', 'Gray', 'Color', 'FONTITALIC',
    'OLE_TRISTATE'
]

