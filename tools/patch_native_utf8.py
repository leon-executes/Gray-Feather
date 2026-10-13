"""Build-only deterministic UTF-8 manifest addition for the native ASR child."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import pefile

def patch(source, destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination:
        raise ValueError('Preserve the upstream binary; choose a separate destination.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    pe=pefile.PE(str(source)); manifests=[]
    for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if entry.id==24:
            for item in entry.directory.entries:
                for lang in item.directory.entries:
                    data=lang.data.struct
                    manifests.append((item.id,lang.id,pe.get_data(data.OffsetToData,data.Size)))
    pe.close()
    if len(manifests)!=1:
        raise ValueError('Expected exactly one upstream process manifest.')
    identifier,language,raw=manifests[0]
    root=ET.fromstring(raw)
    asm='urn:schemas-microsoft-com:asm.v3'
    application=root.find('{'+asm+'}application')
    if application is None: application=ET.SubElement(root,'{'+asm+'}application')
    settings=application.find('{'+asm+'}windowsSettings')
    if settings is None: settings=ET.SubElement(application,'{'+asm+'}windowsSettings')
    cp=ET.SubElement(settings,'{http://schemas.microsoft.com/SMI/2019/WindowsSettings}activeCodePage')
    cp.text='UTF-8'
    encoded=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    shutil.copy2(source,destination)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    begin=kernel.BeginUpdateResourceW; begin.argtypes=[wintypes.LPCWSTR,wintypes.BOOL];begin.restype=wintypes.HANDLE
    update=kernel.UpdateResourceW;update.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,wintypes.WORD,ctypes.c_void_p,wintypes.DWORD];update.restype=wintypes.BOOL
    end=kernel.EndUpdateResourceW;end.argtypes=[wintypes.HANDLE,wintypes.BOOL];end.restype=wintypes.BOOL
    handle=begin(str(destination),False)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    buffer=ctypes.create_string_buffer(encoded)
    if not update(handle,24,identifier,language,buffer,len(encoded)):
        error=ctypes.get_last_error();end(handle,True);raise ctypes.WinError(error)
    if not end(handle,False): raise ctypes.WinError(ctypes.get_last_error())
    return {'source':str(source),'destination':str(destination),
        'upstream_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'patched_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'change':'UTF-8 process active code page only; preserves upstream manifest settings',
        'minimum_windows':'Windows10 version1903'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination');args=parser.parse_args()
    print(json.dumps(patch(args.source,args.destination),indent=2))
